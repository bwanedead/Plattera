"""Generic runtime runner.

The runner owns process/lifecycle mechanics and artifact emission only.
It resolves a surface-only adapter, composes one mechanical turn surface,
registers opaque tool handlers with the execution layer, and drives the
generic orchestration loop. It must not learn domain semantics, closure
doctrine, or pack-specific workflow language.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
import json
import logging
import os
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

_LOG = logging.getLogger(__name__)

from harness.execution.contracts import ExecutionSessionStartRequest
from harness.execution.executor import ExecutionExecutor
from harness.execution.session import ExecutionSessionManager
from harness.runtime.composition import ComposedTurnInput, DefaultTurnComposer, TurnSurface
from harness.runtime.memory.resume_snapshot import (
    hydrate_session_manager_from_resume_payload,
    load_kernel_resume_snapshot_from_path,
    merge_launch_latest_refs_with_resume_continuity,
    parse_kernel_resume_snapshot,
)
from harness.runtime.orchestration.lifecycle import (
    KernelPromptEventTraceObserver,
    OrchestrationLifecycle,
)
from harness.runtime.prompting import build_harness_turn_surface
from harness.runtime.orchestration.llm_turn_adapter import LlmTurnOrchestrationAdapter
from harness.runtime.orchestration.llm_turn_lifecycle import LlmTurnPreChooseActionParticipant
from harness.runtime.orchestration.orchestrator import run_orchestration_kernel_loop
from harness.runtime.orchestration.trace_collector import KernelTraceCollector
from services.llm.openai import OpenAIService
from .contracts import RuntimeAdapter, RuntimeArtifactTargets, RuntimeRunResult


class RuntimeRunnerError(RuntimeError):
    """Raised when the mechanical runner cannot complete its lifecycle."""

    def __init__(self, message: str, *, reason_code: str | None = None) -> None:
        super().__init__(message)
        self.reason_code = str(reason_code or message)


class RuntimeRunner:
    def __init__(
        self,
        *,
        adapter: RuntimeAdapter | None = None,
        adapter_factory: Callable[[Mapping[str, Any]], RuntimeAdapter] | None = None,
        adapter_loader: Callable[[Mapping[str, Any]], RuntimeAdapter] | None = None,
        model_caller: Callable[..., Mapping[str, Any] | str] | None = None,
        targets: RuntimeArtifactTargets | None = None,
    ) -> None:
        self._adapter = adapter
        self._adapter_factory = adapter_factory
        self._adapter_loader = adapter_loader
        self._model_caller = model_caller
        self._targets = targets

    def run(self, *, launch_context: Mapping[str, Any] | None = None) -> RuntimeRunResult:
        """Drive one logical run, which may span multiple bounded kernel slices.

        A kernel slice that returns ``waiting_human`` is a pause condition, not a
        terminal state.  This method owns the harness-level lifecycle: it polls the
        feedback store for the active blocking prompt and re-invokes the kernel from
        the stored resume snapshot when the answer arrives.  ``done.json`` is written
        only when the run reaches a true terminal state (completed / failed /
        exhausted, or a pause that timed out waiting for human input).

        Two lifecycle invariants enforced here:

        * **Canonical run_id**: one logical ``run_id`` is established before the
          first kernel slice and reused for all HITL lookups and state updates.
          If the launch context omits ``run_id`` a stable UUID is generated and
          written back into context so every collaborator (kernel, feedback store,
          CLI run-state) sees the same identity.

        * **Per-logical-run iteration budget**: ``max_iterations`` from the launch
          context is the *total* turn budget for the logical run, not a per-slice
          budget.  Resumed slices receive a reduced ``max_iterations`` equal to
          the remaining turns after subtracting iterations consumed by earlier
          slices.  Kernel iteration numbers are globally cumulative
          (``resume_start_iteration`` carries over), so ``loop_result.iterations``
          is always the total turns spent across all slices to date.
        """
        context = dict(launch_context or {})
        # CLI start sets HARNESS_CLI_LOOP_KIND but entrypoint launch JSON may omit
        # loop_kind; blocking-HITL resume must poll the same feedback namespace as
        # harness.cli.answer (which uses run-state loop_kind).
        if not str(context.get("loop_kind") or context.get("hitl_loop_kind") or "").strip():
            env_lk = str(os.environ.get("HARNESS_CLI_LOOP_KIND", "") or "").strip()
            if env_lk:
                context = dict(context)
                context["loop_kind"] = env_lk
        targets = self._targets or RuntimeArtifactTargets.from_env()

        try:
            adapter = self._resolve_adapter(context)
            surface = self._resolve_turn_surface(adapter, context)
            composed = DefaultTurnComposer().compose(build_harness_turn_surface(), surface)

            # ── Establish one canonical logical run_id for the whole logical run ──
            # _run_orchestration internally calls _select_run_id(context) with the
            # same logic.  We surface it here so the outer lifecycle (HITL poll,
            # run-state updates) always uses the same identity as the kernel, even
            # when the caller did not supply an explicit run_id.
            canonical_run_id = _select_run_id(context)
            if not str(context.get("run_id") or "").strip():
                context = dict(context)
                context["run_id"] = canonical_run_id

            # ── Logical-run iteration budget ──────────────────────────────────────
            # Fixed once at launch; reduced by the iterations each completed slice
            # consumed so resumed slices cannot silently exceed the total budget.
            logical_max_iterations = _select_max_iterations(context)
            # Tracks the globally highest iteration index seen so far.  Kernel
            # iteration numbers are 1-based and cumulative across resume boundaries,
            # so loop_result.iterations is the last iteration of the most-recent
            # slice globally — i.e., total turns spent across all slices.
            slices_iterations_used: int = 0

            # Harness-owned logical run lifecycle: loop over bounded kernel slices.
            # Each iteration is one execution slice; blocking HITL causes a pause then
            # resume — multiple slices may be part of a single logical run.
            result: RuntimeRunResult | None = None
            while True:
                # For resumed slices, reduce max_iterations to the turns remaining
                # after subtracting those already consumed by earlier slices.
                if slices_iterations_used > 0:
                    remaining = max(1, logical_max_iterations - slices_iterations_used)
                    context = dict(context)
                    context["max_iterations"] = remaining

                orchestration_context = _with_domain_policy_context(context, adapter)
                loop_result = self._run_orchestration(context=orchestration_context, composed=composed)
                # Update cumulative count; kernel iteration numbers are globally
                # monotonic so this correctly reflects total turns across all slices.
                slices_iterations_used = loop_result.iterations

                result = RuntimeRunResult(
                    status=str(loop_result.terminal_class),
                    reason_code=loop_result.reason_code,
                    result_payload=_build_loop_result_payload(loop_result),
                    done_payload=_build_loop_done_payload(loop_result),
                )

                if result.status != "waiting_human":
                    break

                # ── Harness-owned blocking-HITL pause/resume ───────────────────────
                # The kernel slice ended on a blocking HITL.  This is a pause, not a
                # final terminal state.  Poll the feedback store for the active prompt
                # answer; when it arrives, re-invoke the kernel from the resume snapshot.
                _maybe_update_cli_run_state("waiting_human")

                blocking_prompt_id = str(
                    (loop_result.runtime_state or {}).get("blocking_prompt_id") or ""
                ).strip()
                if not blocking_prompt_id:
                    # Kernel emitted waiting_human but left no blocking_prompt_id —
                    # cannot match an answer; return the paused state as terminal.
                    _LOG.warning("RUNNER waiting_human with no blocking_prompt_id — treating as terminal")
                    break

                loop_kind = _hitl_loop_kind_for_resume(orchestration_context)
                wait_timeout = _select_hitl_wait_timeout(context)

                _LOG.info(
                    "RUNNER pause waiting_human ► run_id=%s prompt_id=%s timeout=%ss",
                    canonical_run_id, blocking_prompt_id, wait_timeout,
                )
                answer = _poll_blocking_answer(
                    loop_kind=loop_kind,
                    run_id=canonical_run_id,
                    prompt_id=blocking_prompt_id,
                    timeout_seconds=wait_timeout,
                )

                if answer is None:
                    # Feedback did not arrive within the wait window.
                    # Return waiting_human as the terminal state so the caller knows
                    # the run is still paused (not completed or failed).
                    _LOG.info("RUNNER hitl_wait_timeout ► run_id=%s prompt_id=%s", canonical_run_id, blocking_prompt_id)
                    break

                # Answer arrived — build resume context for the next kernel slice.
                # The answer is already in the feedback store; the kernel will pick
                # it up via hitl_poll_feedback_store on the first iteration of the
                # resumed slice.  We inject the kernel_resume_snapshot so the new
                # slice continues from where the paused slice left off.
                remaining = logical_max_iterations - slices_iterations_used
                if remaining <= 0:
                    _LOG.info(
                        "RUNNER resume_budget_exhausted ► run_id=%s prompt_id=%s iterations=%s max_iterations=%s",
                        canonical_run_id,
                        blocking_prompt_id,
                        slices_iterations_used,
                        logical_max_iterations,
                    )
                    result = RuntimeRunResult(
                        status="exhausted",
                        reason_code="max_iterations_reached",
                        result_payload=_build_exhausted_result_payload(loop_result),
                        done_payload=_build_exhausted_done_payload(loop_result),
                    )
                    break

                snap = loop_result.kernel_resume_snapshot
                new_context = dict(context)
                new_context.pop("kernel_resume_snapshot_path", None)
                new_context.pop("resume_snapshot_path", None)
                if isinstance(snap, dict) and snap:
                    new_context["kernel_resume_snapshot"] = snap
                context = new_context
                _maybe_update_cli_run_state("resuming")
                _LOG.info("RUNNER resuming ► run_id=%s prompt_id=%s", canonical_run_id, blocking_prompt_id)
                # Loop to next kernel slice.

        except RuntimeRunnerError as exc:
            result = RuntimeRunResult(
                status="failed",
                reason_code=exc.reason_code,
                result_payload={"error": str(exc), "reason_code": exc.reason_code, "status": "failed"},
                done_payload={"error": str(exc), "reason_code": exc.reason_code, "status": "failed"},
            )
            self._write_artifacts(targets=targets, result=result)
            raise
        except Exception as exc:
            reason_code = str(getattr(exc, "reason_code", "") or "runner_exception")
            result = RuntimeRunResult(
                status="failed",
                reason_code=reason_code,
                result_payload={"error": str(exc), "reason_code": reason_code, "status": "failed"},
                done_payload={"error": str(exc), "reason_code": reason_code, "status": "failed"},
            )
            self._write_artifacts(targets=targets, result=result)
            raise RuntimeRunnerError(
                f"runtime_runner_failed:{reason_code}", reason_code=reason_code
            ) from exc

        assert result is not None  # loop always assigns result before break
        self._write_artifacts(targets=targets, result=result)
        return result

    def _resolve_adapter(self, launch_context: Mapping[str, Any]) -> RuntimeAdapter:
        if self._adapter is not None:
            return self._adapter
        if self._adapter_factory is not None:
            return self._adapter_factory(launch_context)
        if self._adapter_loader is not None:
            return self._adapter_loader(launch_context)
        raise RuntimeRunnerError("adapter_required")

    def _resolve_turn_surface(self, adapter: RuntimeAdapter, launch_context: Mapping[str, Any]) -> TurnSurface:
        surface = adapter.build_turn_surface(launch_context)
        if not isinstance(surface, TurnSurface):
            raise RuntimeRunnerError("turn_surface_required")
        return surface

    def _run_orchestration(self, *, context: Mapping[str, Any], composed: ComposedTurnInput) -> Any:
        model_name = _select_model_name(context)
        model_caller = self._model_caller or _build_default_model_caller(model_name=model_name)
        executor = ExecutionExecutor()
        for tool_id, handler in composed.tool_handlers.items():
            executor.register(tool_id, handler)

        resume_doc, resume_err = _load_resume_document(context)
        if resume_err:
            raise RuntimeRunnerError(resume_err)
        initial_loop_memory = None
        resume_start_iteration = 1
        if resume_doc is not None:
            initial_loop_memory, resume_start_iteration, perr = parse_kernel_resume_snapshot(resume_doc)
            if perr:
                raise RuntimeRunnerError(f"resume_snapshot_invalid:{perr}")

        session_manager = ExecutionSessionManager(executor=executor)
        run_id = _select_run_id(context)
        run_artifact_ref: str | None = None
        if resume_doc is not None:
            alt_mgr, eerr = hydrate_session_manager_from_resume_payload(resume_doc, executor=executor)
            if eerr:
                raise RuntimeRunnerError(f"resume_snapshot_invalid:{eerr}")
            if alt_mgr is not None:
                session_manager = alt_mgr
                session_ids = list(session_manager.sessions.keys())
                if len(session_ids) != 1:
                    raise RuntimeRunnerError("resume_snapshot_invalid:execution_session_count")
                session_id = session_ids[0]
                run_artifact_ref = str(context.get("run_artifact_ref") or "").strip() or None
            else:
                session_start = session_manager.start_session(
                    ExecutionSessionStartRequest(
                        run_id=run_id,
                        session_id=_select_session_id(context, run_id=run_id),
                        initial_latest_refs=merge_launch_latest_refs_with_resume_continuity(
                            _extract_initial_latest_refs(context),
                            initial_loop_memory=initial_loop_memory,
                        ),
                    )
                )
                session_id = session_start.session_id
                run_artifact_ref = session_start.run_artifact_ref
        else:
            session_start = session_manager.start_session(
                ExecutionSessionStartRequest(
                    run_id=run_id,
                    session_id=_select_session_id(context, run_id=run_id),
                    initial_latest_refs=_extract_initial_latest_refs(context),
                )
            )
            session_id = session_start.session_id
            run_artifact_ref = session_start.run_artifact_ref

        max_iterations = _select_max_iterations(context)
        request_id_prefix = _select_request_id_prefix(context, fallback=run_id)
        tracer = KernelTraceCollector(session_id=session_id, request_id=request_id_prefix, run_id=run_id)

        audit_writer = _build_audit_writer(run_id=run_id, session_id=session_id, request_id=request_id_prefix)
        prompt_event_observer = KernelPromptEventTraceObserver(tracer=tracer)
        lifecycle = OrchestrationLifecycle(
            pre_choose_action_participant=LlmTurnPreChooseActionParticipant(
                composed_input=composed,
                text_model_caller=model_caller,
                model_name=model_name,
                opaque_launch_context=context,
                prompt_event_observer=prompt_event_observer,
            ),
            prompt_event_observer=prompt_event_observer,
            raw_llm_io_observer=audit_writer,
            turn_completion_observer=audit_writer,
        )
        orchestration_adapter = LlmTurnOrchestrationAdapter(
            composed_input=composed,
            text_model_caller=model_caller,
            model_name=model_name,
            opaque_launch_context=context,
        )

        loop_result: Any = None
        try:
            loop_result = run_orchestration_kernel_loop(
                orchestration_adapter=orchestration_adapter,
                session_manager=session_manager,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                request_id_prefix=request_id_prefix,
                run_id=run_id,
                opaque_run_context=dict(context),
                max_iterations=max_iterations,
                initial_loop_memory=initial_loop_memory,
                resume_start_iteration=resume_start_iteration,
                lifecycle=lifecycle,
                tracer=tracer,
            )
            return loop_result
        finally:
            # Always flush audit — including when the loop raises (failed runs need
            # forensic artifacts most urgently).  RunAuditWriter.finalize() is
            # best-effort and never propagates exceptions.
            audit_writer.finalize(
                terminal_class=str(loop_result.terminal_class) if loop_result is not None else "failed",
                reason_code=loop_result.reason_code if loop_result is not None else "runner_exception",
                iterations=int(loop_result.iterations) if loop_result is not None else 0,
                latest_refs=dict(loop_result.latest_refs) if loop_result is not None else {},
                trace_events=list(loop_result.trace_events) if loop_result is not None else [],
                run_id=run_id,
            )

    def _write_artifacts(self, *, targets: RuntimeArtifactTargets, result: RuntimeRunResult) -> None:
        try:
            _write_json(targets.result_file, _build_result_document(result))
            _write_json(targets.done_file, _build_done_document(result))
        finally:
            _maybe_update_cli_run_state(result.status)
            _maybe_finalize_retention_and_cleanup(targets)


def run_runtime_from_env(
    *,
    adapter: RuntimeAdapter | None = None,
    adapter_factory: Callable[[Mapping[str, Any]], RuntimeAdapter] | None = None,
    adapter_loader: Callable[[Mapping[str, Any]], RuntimeAdapter] | None = None,
    model_caller: Callable[..., Mapping[str, Any] | str] | None = None,
    opaque_launch_context: Mapping[str, Any] | None = None,
) -> RuntimeRunResult:
    return RuntimeRunner(
        adapter=adapter,
        adapter_factory=adapter_factory,
        adapter_loader=adapter_loader,
        model_caller=model_caller,
    ).run(launch_context=opaque_launch_context)


def _build_loop_result_payload(loop_result: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "terminal_class": str(loop_result.terminal_class),
        "reason_code": loop_result.reason_code,
        "terminal_summary": getattr(loop_result, "terminal_summary", None),
        "iterations": loop_result.iterations,
        "session_id": loop_result.session_id,
        "run_artifact_ref": loop_result.run_artifact_ref,
        "latest_refs": dict(loop_result.latest_refs),
        "runtime_state": _jsonable(loop_result.runtime_state),
        "trace_events": _jsonable(loop_result.trace_events),
    }
    snap = getattr(loop_result, "kernel_resume_snapshot", None)
    if isinstance(snap, dict):
        payload["kernel_resume_snapshot"] = _jsonable(snap)
    return payload


def _build_loop_done_payload(loop_result: Any) -> dict[str, Any]:
    return {
        "terminal_class": str(loop_result.terminal_class),
        "reason_code": loop_result.reason_code,
        "terminal_summary": getattr(loop_result, "terminal_summary", None),
        "iterations": loop_result.iterations,
        "session_id": loop_result.session_id,
        "run_artifact_ref": loop_result.run_artifact_ref,
        "latest_refs": dict(loop_result.latest_refs),
    }


def _build_default_model_caller(*, model_name: str) -> Callable[..., Mapping[str, Any] | str]:
    service = OpenAIService()

    def _call(prompt: str, model: str, **kwargs: Any) -> Mapping[str, Any] | str:
        return service.call_text(prompt, model or model_name, **kwargs)

    return _call


def _select_model_name(context: Mapping[str, Any]) -> str:
    return (
        str(context.get("model") or os.environ.get("HARNESS_CLI_MODEL") or "gpt-5.4").strip()
        or "gpt-5.4"
    )


def _select_run_id(context: Mapping[str, Any]) -> str:
    value = str(context.get("run_id") or context.get("session_id") or "").strip()
    return value or f"run-{uuid4().hex}"


def _select_session_id(context: Mapping[str, Any], *, run_id: str) -> str:
    return str(context.get("session_id") or run_id).strip() or run_id


def _select_request_id_prefix(context: Mapping[str, Any], *, fallback: str) -> str:
    return str(context.get("request_id_prefix") or fallback).strip() or fallback


def _select_max_iterations(context: Mapping[str, Any]) -> int:
    raw = context.get("max_iterations")
    try:
        value = int(raw) if raw is not None else 3
    except (TypeError, ValueError):
        return 3
    return max(1, value)


def _load_resume_document(context: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(resume_dict, error_code)``. At most one of path vs inline may be set."""
    path_raw = context.get("kernel_resume_snapshot_path") or context.get("resume_snapshot_path")
    inline = context.get("kernel_resume_snapshot") or context.get("resume_snapshot")
    if path_raw is not None and inline is not None:
        return None, "resume_snapshot_conflict_path_and_inline"
    if path_raw is not None:
        path = Path(str(path_raw).strip())
        doc, err = load_kernel_resume_snapshot_from_path(path)
        return doc, err
    if isinstance(inline, dict):
        return dict(inline), None
    if inline is not None:
        return None, "resume_snapshot_inline_not_object"
    return None, None


def _extract_initial_latest_refs(context: Mapping[str, Any]) -> dict[str, Any]:
    raw = context.get("latest_refs")
    if isinstance(raw, Mapping):
        return dict(raw)
    raw = context.get("initial_latest_refs")
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}


def _build_result_document(result: RuntimeRunResult) -> dict[str, Any]:
    payload = dict(result.result_payload)
    if "status" not in payload:
        payload["status"] = result.status
    if result.reason_code is not None and "reason_code" not in payload:
        payload["reason_code"] = result.reason_code
    return payload


def _build_done_document(result: RuntimeRunResult) -> dict[str, Any]:
    payload = dict(result.done_payload)
    if "status" not in payload:
        payload["status"] = result.status
    if result.reason_code is not None and "reason_code" not in payload:
        payload["reason_code"] = result.reason_code
    return payload


def _build_exhausted_result_payload(loop_result: Any) -> dict[str, Any]:
    payload = _build_loop_result_payload(loop_result)
    payload["terminal_class"] = "exhausted"
    payload["reason_code"] = "max_iterations_reached"
    return payload


def _build_exhausted_done_payload(loop_result: Any) -> dict[str, Any]:
    payload = _build_loop_done_payload(loop_result)
    payload["terminal_class"] = "exhausted"
    payload["reason_code"] = "max_iterations_reached"
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _build_audit_writer(*, run_id: str = "", session_id: str = "", request_id: str = "") -> Any:
    """Return a ``RunAuditWriter`` scoped to the current CLI run dir, or a no-op if not in a CLI run."""
    from harness.audit.run_audit_writer import RunAuditWriter
    cli_run_id = os.environ.get("HARNESS_CLI_RUN_ID", "").strip()
    if not cli_run_id:
        return RunAuditWriter(None, run_id=run_id, session_id=session_id, request_id=request_id)
    try:
        from harness.cli.run_state import run_dir as cli_run_dir
        return RunAuditWriter(
            cli_run_dir(cli_run_id),
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
        )
    except Exception:
        return RunAuditWriter(None, run_id=run_id, session_id=session_id, request_id=request_id)


def _maybe_update_cli_run_state(status: str) -> None:
    """Best-effort update of the CLI run-state record after a run completes."""
    cli_run_id = os.environ.get("HARNESS_CLI_RUN_ID", "").strip()
    if not cli_run_id:
        return
    try:
        from harness.cli.run_state import update_state_fields

        update_state_fields(cli_run_id, status=str(status))
    except Exception:
        import logging

        logging.getLogger(__name__).warning("run-state update failed for run_id=%s", cli_run_id, exc_info=True)


def _maybe_finalize_retention_and_cleanup(targets: RuntimeArtifactTargets) -> None:
    """Write retention.json and trigger latest-5 cleanup.  Best-effort; never raises."""
    cli_run_id = os.environ.get("HARNESS_CLI_RUN_ID", "").strip()
    if not cli_run_id:
        return
    try:
        from harness.audit.retention import cleanup_old_cli_runs, write_run_retention_json
        write_run_retention_json(cli_run_id)
        cleanup_old_cli_runs(keep_n=5)
    except Exception:
        import logging
        logging.getLogger(__name__).warning("retention/cleanup failed for run_id=%s", cli_run_id, exc_info=True)


def _select_hitl_wait_timeout(context: Mapping[str, Any]) -> float:
    """Max seconds to poll the feedback store for a blocking-HITL answer (default: 7200 = 2 h)."""
    raw = context.get("hitl_wait_timeout_seconds")
    try:
        value = float(raw) if raw is not None else 7200.0
    except (TypeError, ValueError):
        return 7200.0
    return max(1.0, value)


def _hitl_loop_kind_for_resume(context: Mapping[str, Any]) -> str:
    return str(
        context.get("hitl_loop_kind") or context.get("loop_kind") or "harness_cli"
    ).strip() or "harness_cli"


def _poll_blocking_answer(
    *,
    loop_kind: str,
    run_id: str,
    prompt_id: str,
    timeout_seconds: float,
    poll_interval: float = 2.0,
) -> dict[str, Any] | None:
    """Poll the feedback store until an answer for ``prompt_id`` arrives or the deadline passes.

    Returns the feedback entry dict, or ``None`` if the timeout is reached with no answer.
    This is purely mechanical: it does not interpret the answer content.
    """
    if not loop_kind or not run_id or not prompt_id:
        return None
    try:
        from services.agent_viewer import feedback_store
    except Exception:
        return None
    deadline = time.monotonic() + max(1.0, float(timeout_seconds))
    while time.monotonic() < deadline:
        try:
            entries = feedback_store.list_entries(loop_kind=loop_kind, run_id=run_id)
        except Exception:
            time.sleep(poll_interval)
            continue
        for ent in entries or []:
            if not isinstance(ent, dict):
                continue
            if str(ent.get("prompt_id") or "").strip() == prompt_id:
                return ent
        time.sleep(poll_interval)
    return None


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="python"))  # type: ignore[call-arg]
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(raw_value) for key, raw_value in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return [_jsonable(item) for item in sorted(value, key=str)]
    return value


def _with_domain_policy_context(
    launch_context: Mapping[str, Any],
    adapter: RuntimeAdapter,
) -> dict[str, Any]:
    merged = dict(launch_context)
    manifest = getattr(adapter, "manifest", None)
    if manifest is None:
        return merged
    domain_id = str(getattr(manifest, "domain_id", "") or "").strip()
    if domain_id and "domain_id" not in merged:
        merged["domain_id"] = domain_id
    closure_policy = getattr(manifest, "closure_policy", None)
    if closure_policy is not None:
        merged["domain_closure_policy"] = _jsonable(closure_policy)
    return merged
