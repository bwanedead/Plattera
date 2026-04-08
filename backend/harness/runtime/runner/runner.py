"""Generic runtime runner.

The runner owns process/lifecycle mechanics and artifact emission only.
It resolves a surface-only adapter, composes one mechanical turn surface,
registers opaque tool handlers with the execution layer, and drives the
generic orchestration loop. It must not learn domain semantics, closure
doctrine, or pack-specific workflow language.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

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
from harness.runtime.orchestration.llm_turn_adapter import LlmTurnOrchestrationAdapter
from harness.runtime.orchestration.orchestrator import run_orchestration_kernel_loop
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
        context = dict(launch_context or {})
        targets = self._targets or RuntimeArtifactTargets.from_env()

        try:
            adapter = self._resolve_adapter(context)
            surface = self._resolve_turn_surface(adapter, context)
            composed = DefaultTurnComposer().compose(surface)
            loop_result = self._run_orchestration(context=context, composed=composed)
            result = RuntimeRunResult(
                status=str(loop_result.terminal_class),
                reason_code=loop_result.reason_code,
                result_payload=_build_loop_result_payload(loop_result),
                done_payload=_build_loop_done_payload(loop_result),
            )
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

        orchestration_adapter = LlmTurnOrchestrationAdapter(
            composed_input=composed,
            text_model_caller=model_caller,
            model_name=model_name,
            opaque_launch_context=context,
        )
        max_iterations = _select_max_iterations(context)
        request_id_prefix = _select_request_id_prefix(context, fallback=run_id)

        # Wire per-turn raw I/O audit if a CLI run dir is available.
        audit_writer = _build_audit_writer()
        if hasattr(orchestration_adapter, "wire_raw_io_cb"):
            orchestration_adapter.wire_raw_io_cb(audit_writer.on_llm_io)
        if hasattr(orchestration_adapter, "wire_turn_result_cb"):
            orchestration_adapter.wire_turn_result_cb(audit_writer.on_turn_completed)

        loop_result: Any = None
        try:
            loop_result = run_orchestration_kernel_loop(
                orchestration_adapter=orchestration_adapter,
                session_manager=session_manager,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                request_id_prefix=request_id_prefix,
                opaque_run_context=dict(context),
                max_iterations=max_iterations,
                initial_loop_memory=initial_loop_memory,
                resume_start_iteration=resume_start_iteration,
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
        _write_json(targets.result_file, _build_result_document(result))
        _write_json(targets.done_file, _build_done_document(result))
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
    return str(context.get("model") or "gpt-5.4-mini").strip() or "gpt-5.4-mini"


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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _build_audit_writer() -> Any:
    """Return a ``RunAuditWriter`` scoped to the current CLI run dir, or a no-op if not in a CLI run."""
    from harness.audit.run_audit_writer import RunAuditWriter
    cli_run_id = os.environ.get("HARNESS_CLI_RUN_ID", "").strip()
    if not cli_run_id:
        return RunAuditWriter(None)
    try:
        from harness.cli.run_state import run_dir as cli_run_dir
        return RunAuditWriter(cli_run_dir(cli_run_id))
    except Exception:
        return RunAuditWriter(None)


def _maybe_finalize_retention_and_cleanup(targets: RuntimeArtifactTargets) -> None:
    """Write retention.json and trigger latest-4 cleanup.  Best-effort; never raises."""
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


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="python"))  # type: ignore[call-arg]
    if isinstance(value, Mapping):
        return {str(key): _jsonable(raw_value) for key, raw_value in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return [_jsonable(item) for item in sorted(value, key=str)]
    return value
