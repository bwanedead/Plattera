from __future__ import annotations

import logging
from typing import Any

from ...execution.contracts import ExecutionState, ExecutionStepResult
from ...execution.session import ExecutionSessionManager

from ...terminal_taxonomy import TerminalClass
from .contracts import ActionPlan, KernelLoopResult, OrchestrationAdapter, OrchestratorContext
from ..memory import LoopMemoryState
from ..memory.continuity_journal import apply_kernel_turn_continuity_carriage, build_kernel_step_result_record
from ..memory.resume_snapshot import build_kernel_resume_snapshot
from ..hitl.request_shape import normalize_hitl_request, validate_hitl_consumed_prompt_ids
from ..hitl.transport import (
    apply_hitl_consumed_prompt_ids,
    clamp_hitl_lists,
    hitl_has_answer_for_prompt,
    hitl_poll_feedback_store,
    hitl_refresh_derived_state,
)
from ..hitl.watch import write_hitl_operator_sidecar
from .orchestrator_coercion import (
    coerce_kernel_action_plan,
    coerce_projection,
    coerce_step_request,
    coerce_terminal_evaluation,
)
from .state_patch_apply import (
    StatePatchError,
    apply_state_patch,
    sync_state_patch_after_committed_gate,
    sync_state_patch_after_step_refusal,
    sync_state_patch_when_no_step_dispatched,
)
from .trace_collector import KernelTraceCollector

_LOG = logging.getLogger(__name__)

_PUBLISH_ACTION_IDS = frozenset({"publish_workspace_artifact"})


def _notify_turn_completed(
    orchestration_adapter: OrchestrationAdapter,
    iteration: int,
    *,
    action_plan: ActionPlan,
    step_result: "ExecutionStepResult | None",
    loop_memory: LoopMemoryState,
    terminal_decision: str | None = None,
) -> None:
    """Notify adapter of turn completion for forensic audit.  Best-effort: discovery via hasattr."""
    fn = getattr(orchestration_adapter, "on_turn_completed", None)
    if not callable(fn):
        return
    tool_request: dict[str, Any] | None = None
    if not action_plan.complete_run and not action_plan.wait_for_human and action_plan.action_type is not None:
        tool_request = {
            "action_type": action_plan.action_type,
            "action_inputs": dict(action_plan.action_inputs),
            "idempotency_key": action_plan.idempotency_key,
            "skip_execution": action_plan.skip_execution,
            "wait_for_human": action_plan.wait_for_human,
            "complete_run": action_plan.complete_run,
            "rationale": action_plan.rationale,
        }
    tool_result_raw: dict[str, Any] | None = None
    if step_result is not None:
        rec = step_result.record
        tool_result_raw = {
            "execution_state": step_result.execution_state.value,
            "refusal": (
                {
                    "reason_code": step_result.refusal.reason_code,
                    "retryable": step_result.refusal.retryable,
                }
                if step_result.refusal is not None
                else None
            ),
            "outputs": (
                dict(rec.result.outputs or {})
                if rec is not None and rec.result is not None
                else {}
            ),
            "artifact_refs": (
                list(rec.result.artifact_refs or ())
                if rec is not None and rec.result is not None
                else []
            ),
            "image_evidence": (
                list(rec.result.image_evidence)
                if rec is not None and rec.result is not None and rec.result.image_evidence
                else []
            ),
        }
    try:
        fn(
            iteration,
            tool_request=tool_request,
            tool_result_raw=tool_result_raw,
            mission_state_after=loop_memory.continuity.mission_state,
            resolution_state_after=loop_memory.continuity.resolution_state,
            latest_refs_after=dict(loop_memory.continuity.latest_refs),
            state_patch_feedback=dict(loop_memory.continuity.state_patch_feedback),
            terminal_decision=terminal_decision,
        )
    except Exception:
        _LOG.warning("on_turn_completed raised; ignoring", exc_info=True)


def _hitl_loop_kind(opaque_run_context: dict[str, Any]) -> str:
    return str(opaque_run_context.get("hitl_loop_kind") or opaque_run_context.get("loop_kind") or "harness_cli").strip() or "harness_cli"


def _dashboard_refs_python(step_result: ExecutionStepResult) -> dict[str, Any]:
    dash = step_result.dashboard
    if dash is None:
        return {}
    return dash.latest_refs.model_dump(mode="python")


def _dispatch_outputs_and_artifact_refs(step_result: ExecutionStepResult) -> tuple[dict[str, Any], list[str]]:
    rec = step_result.record
    if rec is None or rec.result is None:
        return {}, []
    r = rec.result
    return dict(r.outputs or {}), list(r.artifact_refs or ())


def _accumulate_image_evidence(
    *,
    loop_memory: LoopMemoryState,
    step_result: ExecutionStepResult,
) -> None:
    """Append any image evidence from this tool result to the per-iteration buffer."""
    rec = step_result.record
    if rec is None or rec.result is None:
        return
    evidence = rec.result.image_evidence
    if evidence:
        loop_memory.pending_image_evidence.extend(evidence)


def _append_kernel_step_result_continuity(
    *,
    loop_memory: LoopMemoryState,
    iteration: int,
    action_type: str | None,
    step_result: ExecutionStepResult,
) -> None:
    outs, refs = _dispatch_outputs_and_artifact_refs(step_result)
    loop_memory.continuity.kernel_step_result_records.append(
        build_kernel_step_result_record(
            kernel_turn_index=int(iteration),
            action_type=action_type,
            execution_state=step_result.execution_state.value,
            execution_reason_code=(
                step_result.refusal.reason_code if step_result.refusal is not None else None
            ),
            latest_refs_snapshot=_dashboard_refs_python(step_result),
            outputs=outs,
            artifact_refs=refs,
        )
    )


def _record_turn_continuity(
    *,
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
    iteration: int,
    execution_state: str,
    execution_reason_code: str | None,
) -> None:
    apply_kernel_turn_continuity_carriage(
        loop_memory=loop_memory,
        continuity_journal_entry=action_plan.continuity_journal_entry,
        operator_progress_message=action_plan.operator_progress_message,
        action_type=action_plan.action_type,
        action_inputs=dict(action_plan.action_inputs),
        idempotency_key=action_plan.idempotency_key,
        rationale=action_plan.rationale,
        latest_refs_snapshot=dict(loop_memory.continuity.latest_refs),
        skip_execution=action_plan.skip_execution,
        wait_for_human=action_plan.wait_for_human,
        complete_run=action_plan.complete_run,
        iteration=iteration,
        execution_state=execution_state,
        execution_reason_code=execution_reason_code,
    )


def _pack_id_from_prompt_metadata(metadata: dict[str, Any], info: dict[str, Any]) -> str:
    """Prompt-pack identifier from metadata (``pack_id`` only)."""
    return str(metadata.get("pack_id") or info.get("pack_id") or "")


def _closure_policy(run_ctx: dict[str, Any]) -> dict[str, Any] | None:
    raw = run_ctx.get("domain_closure_policy")
    return dict(raw) if isinstance(raw, dict) else None


def _effective_closure_state(
    *,
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
) -> Any:
    if not action_plan.state_patch:
        return loop_memory.continuity.mission_state.closure_state
    try:
        mission_state, _, _ = apply_state_patch(
            mission_state=loop_memory.continuity.mission_state,
            resolution_state=loop_memory.continuity.resolution_state,
            state_patch=action_plan.state_patch,
        )
        return mission_state.closure_state
    except StatePatchError:
        return loop_memory.continuity.mission_state.closure_state


def _closure_enforcement_failure(
    *,
    run_ctx: dict[str, Any],
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
) -> tuple[str, str] | None:
    policy = _closure_policy(run_ctx)
    if not policy or not bool(policy.get("hard_enforced")):
        return None

    is_publish = str(action_plan.action_type or "").strip() in _PUBLISH_ACTION_IDS
    is_complete = bool(action_plan.complete_run)
    if not ((is_publish and bool(policy.get("enforce_on_publish"))) or (is_complete and bool(policy.get("enforce_on_complete")))):
        return None

    closure_state = _effective_closure_state(loop_memory=loop_memory, action_plan=action_plan)
    required_dimension_ids = tuple(
        str(value).strip()
        for value in (policy.get("required_dimension_ids") or ())
        if str(value).strip()
    )
    dimensions = {
        str(getattr(dim, "dimension_id", "") or ""): dim
        for dim in getattr(closure_state, "dimensions", ()) or ()
        if str(getattr(dim, "dimension_id", "") or "")
    }
    missing = [
        dim_id
        for dim_id in required_dimension_ids
        if dim_id not in dimensions or not str(getattr(dimensions[dim_id], "status", "") or "").strip()
    ]
    if missing:
        target = "publish" if is_publish else "complete"
        return (
            f"closure_{target}_dimensions_missing",
            f"closure enforcement missing required dimensions: {missing}",
        )

    if bool(getattr(closure_state, "requires_hitl", False)) or any(
        bool(getattr(dimensions[dim_id], "requires_hitl", False))
        for dim_id in required_dimension_ids
        if dim_id in dimensions
    ):
        target = "publish" if is_publish else "complete"
        return (
            f"closure_{target}_requires_hitl",
            "closure enforcement requires HITL before this action",
        )

    if is_publish and not bool(getattr(closure_state, "ready_to_publish", False)):
        return (
            "closure_publish_not_ready",
            "closure enforcement requires ready_to_publish before publish_workspace_artifact",
        )

    if is_complete and not bool(getattr(closure_state, "ready_to_close", False)):
        return (
            "closure_complete_not_ready",
            "closure enforcement requires ready_to_close before complete_run",
        )

    return None


def _handle_closure_enforcement_block(
    *,
    orchestration_adapter: OrchestrationAdapter,
    tracer: KernelTraceCollector,
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
    iteration: int,
    reason_code: str,
) -> None:
    action_id = "complete_run" if action_plan.complete_run else str(action_plan.action_type or "no_action")
    tracer.emit_execution_result(
        iteration=iteration,
        action_type=action_id,
        execution_state="refused",
        reason_code=reason_code,
        retryable=False,
        refs_delta=None,
    )
    sync_state_patch_after_committed_gate(
        loop_memory=loop_memory,
        action_plan=action_plan,
        tracer=tracer,
        iteration=iteration,
        gate="closure_enforcement_blocked",
    )
    _record_turn_continuity(
        loop_memory=loop_memory,
        action_plan=action_plan,
        iteration=iteration,
        execution_state="refused",
        execution_reason_code=reason_code,
    )
    _notify_turn_completed(
        orchestration_adapter,
        iteration,
        action_plan=action_plan,
        step_result=None,
        loop_memory=loop_memory,
        terminal_decision="closure_enforcement_blocked",
    )


def run_orchestration_kernel_loop(
    *,
    orchestration_adapter: OrchestrationAdapter,
    session_manager: ExecutionSessionManager,
    session_id: str,
    run_artifact_ref: str | None,
    request_id_prefix: str,
    opaque_run_context: dict[str, Any] | None = None,
    max_iterations: int,
    resume_hitl_response: dict[str, Any] | None = None,
    initial_loop_memory: LoopMemoryState | None = None,
    resume_start_iteration: int = 1,
) -> KernelLoopResult:
    """Drive the bounded per-run loop; ``orchestration_adapter`` implements ``OrchestrationAdapter``.

    Mechanical run status is emitted only through ``KernelTraceCollector`` (see
    ``KernelLoopResult.trace_events``)—no parallel host progress callback.

    Orchestration adapters may optionally define ``wire_identity_trace_cb`` for mechanical LLM
    observability (e.g. ``LlmTurnOrchestrationAdapter``); the hook is discovered via ``hasattr``
    and is not part of the ``OrchestrationAdapter`` protocol.

    For process restart, pass ``initial_loop_memory`` and ``resume_start_iteration`` from a parsed
    ``kernel_resume.v1`` snapshot (mechanical rehydration only; no semantic repair).
    """
    loop_memory = initial_loop_memory if initial_loop_memory is not None else LoopMemoryState()
    start_iteration = max(1, int(resume_start_iteration))
    if isinstance(resume_hitl_response, dict) and resume_hitl_response:
        pid = str(resume_hitl_response.get("prompt_id") or "").strip()
        if not pid and initial_loop_memory is not None:
            pid = str(
                initial_loop_memory.hitl.blocking_prompt_id
                or initial_loop_memory.hitl.pending_feedback_prompt_id
                or ""
            ).strip()
        if not pid:
            pid = "resume_injected"
        loop_memory.hitl.answered_hitl_responses.append(
            {"prompt_id": pid, "feedback": dict(resume_hitl_response)}
        )
        loop_memory.hitl.pending_feedback_response = dict(resume_hitl_response)
        loop_memory.hitl.pending_feedback_prompt_id = pid
        hitl_refresh_derived_state(loop_memory.hitl)
        _LOG.info("KERNEL resume_hitl_preseeded ► request_id=%s", request_id_prefix)

    run_ctx = dict(opaque_run_context) if isinstance(opaque_run_context, dict) else {}
    context = OrchestratorContext(
        session_manager=session_manager,
        session_id=session_id,
        loop_memory=loop_memory,
        request_id_prefix=request_id_prefix,
        opaque_run_context=run_ctx,
    )

    tracer = KernelTraceCollector(session_id=session_id, request_id=request_id_prefix)
    tracer.emit_request_start(
        opaque_run_context=run_ctx,
        max_iterations=max_iterations,
        run_artifact_ref=run_artifact_ref,
    )

    def _identity_trace_cb(info: dict[str, Any]) -> None:
        raw_iter = info.get("iteration")
        iteration_index: int | None = int(raw_iter) if isinstance(raw_iter, int) else None

        prompt_event = info.get("prompt_event")
        if isinstance(prompt_event, dict):
            metadata = prompt_event.get("metadata") if isinstance(prompt_event.get("metadata"), dict) else {}
            tracer.emit_prompt_event(
                iteration=iteration_index,
                prompt_event=prompt_event,
                surface=str(metadata.get("surface") or info.get("surface") or ""),
                pack_id=_pack_id_from_prompt_metadata(metadata, info),
                model=str(metadata.get("model") or info.get("model") or ""),
            )
            loop_memory.telemetry.register_prompt_event(
                prompt_event_id=str(metadata.get("prompt_event_id") or ""),
                surface=str(metadata.get("surface") or info.get("surface") or ""),
            )
            # Same contact is an LLM call: keep llm_contact_count aligned for operators (not only legacy identity path).
            loop_memory.telemetry.register_llm_contact()
            return
        tracer.emit_llm_call_identity(
            iteration=iteration_index,
            surface=str(info.get("surface") or ""),
            pack_id=_pack_id_from_prompt_metadata(info if isinstance(info, dict) else {}, info if isinstance(info, dict) else {}),
            inheritance_mode=str(info.get("inheritance_mode") or ""),
            constitution_version=str(info.get("constitution_version") or ""),
            run_link_id=str(info.get("run_link_id") or ""),
            model=str(info.get("model") or ""),
        )
        loop_memory.telemetry.register_llm_contact()

    if hasattr(orchestration_adapter, "wire_identity_trace_cb"):
        orchestration_adapter.wire_identity_trace_cb(_identity_trace_cb)  # type: ignore[attr-defined]

    _call_optional(orchestration_adapter, "initialize", context)

    for offset in range(max_iterations):
        iterations = start_iteration + offset
        loop_memory.iterations = iterations
        tracer.emit_iteration_start(iteration=iterations, hitl_state=loop_memory.hitl.hitl_state)

        hitl_poll_feedback_store(
            posture=loop_memory.hitl,
            loop_kind=_hitl_loop_kind(run_ctx),
            run_id=request_id_prefix,
        )
        hitl_refresh_derived_state(loop_memory.hitl)

        if loop_memory.hitl.hitl_state == "waiting" and loop_memory.hitl.blocking_prompt_id:
            if not hitl_has_answer_for_prompt(loop_memory.hitl, loop_memory.hitl.blocking_prompt_id):
                return _make_result(
                    loop_memory=loop_memory,
                    terminal_class="waiting_human",
                    reason_code="waiting_human_feedback",
                    iterations=iterations,
                    session_id=session_id,
                    run_artifact_ref=run_artifact_ref,
                    tracer=tracer,
                    session_manager=session_manager,
                )

        projection = coerce_projection(_call_optional(orchestration_adapter, "sync", context))
        if projection is not None:
            loop_memory.continuity.mission_state = projection.mission_state
            loop_memory.continuity.resolution_state = projection.resolution_state
            if projection.latest_refs:
                loop_memory.continuity.latest_refs = dict(projection.latest_refs)
            loop_memory.continuity.active_item_id = (
                projection.active_item_id
                or projection.resolution_state.active_item_id
                or loop_memory.continuity.active_item_id
            )

        terminal = coerce_terminal_evaluation(_call_optional(orchestration_adapter, "evaluate_terminal", context, projection))
        if terminal is not None:
            return _make_result(
                loop_memory=loop_memory,
                terminal_class=terminal.terminal_class,
                reason_code=terminal.reason_code,
                terminal_summary=terminal.terminal_summary,
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
                session_manager=session_manager,
            )

        pre_compact = getattr(orchestration_adapter, "run_continuity_pre_choose_action", None)
        if callable(pre_compact):
            pre_compact(context, projection, tracer=tracer)  # type: ignore[misc]

        action_plan = coerce_kernel_action_plan(_call_optional(orchestration_adapter, "choose_action", context, projection))
        if action_plan is None:
            continue

        patch_present = bool(action_plan.state_patch)

        try:
            consumed_ids = validate_hitl_consumed_prompt_ids(action_plan.hitl_consumed_prompt_ids)
        except ValueError:
            _LOG.warning("KERNEL invalid hitl_consumed_prompt_ids ► skipping iteration")
            continue
        apply_hitl_consumed_prompt_ids(loop_memory.hitl, consumed_ids)

        if action_plan.wait_for_human and action_plan.hitl_request is None:
            _LOG.warning("KERNEL wait_for_human without hitl_request ► skipping iteration")
            continue

        if action_plan.hitl_request is not None:
            try:
                norm = normalize_hitl_request(dict(action_plan.hitl_request), iteration=iterations)
            except ValueError as exc:
                _LOG.warning("KERNEL invalid hitl_request ► %s", exc)
                continue
            loop_memory.hitl.pending_hitl_requests.append(norm)
            clamp_hitl_lists(loop_memory.hitl)
            write_hitl_operator_sidecar(
                run_id=request_id_prefix,
                latest_record=norm,
                pending_snapshot=list(loop_memory.hitl.pending_hitl_requests),
            )
            tracer.emit_hitl_request_outbound(
                iteration=iterations,
                prompt_id=str(norm["prompt_id"]),
                blocking=action_plan.wait_for_human,
            )
            if action_plan.wait_for_human:
                sync_state_patch_after_committed_gate(
                    loop_memory=loop_memory,
                    action_plan=action_plan,
                    tracer=tracer,
                    iteration=iterations,
                    gate="wait_for_human",
                )
                _record_turn_continuity(
                    loop_memory=loop_memory,
                    action_plan=action_plan,
                    iteration=iterations,
                    execution_state="wait_for_human",
                    execution_reason_code=None,
                )
                loop_memory.hitl.blocking_prompt_id = str(norm["prompt_id"])
                loop_memory.hitl.pending_feedback_prompt_id = str(norm["prompt_id"])
                hitl_refresh_derived_state(loop_memory.hitl)
                _notify_turn_completed(
                    orchestration_adapter, iterations,
                    action_plan=action_plan, step_result=None,
                    loop_memory=loop_memory, terminal_decision="wait_for_human",
                )
                return _make_result(
                    loop_memory=loop_memory,
                    terminal_class="waiting_human",
                    reason_code="waiting_human_feedback",
                    iterations=iterations,
                    session_id=session_id,
                    run_artifact_ref=run_artifact_ref,
                    tracer=tracer,
                    session_manager=session_manager,
                )
            hitl_refresh_derived_state(loop_memory.hitl)
            sync_state_patch_after_committed_gate(
                loop_memory=loop_memory,
                action_plan=action_plan,
                tracer=tracer,
                iteration=iterations,
                gate="hitl_request_async",
            )

        if action_plan.complete_run and action_plan.hitl_request is not None:
            _LOG.warning("KERNEL complete_run with hitl_request ► skipping iteration")
            continue

        closure_failure = _closure_enforcement_failure(
            run_ctx=run_ctx,
            loop_memory=loop_memory,
            action_plan=action_plan,
        )
        if closure_failure is not None:
            reason_code, message = closure_failure
            _LOG.info("KERNEL closure_enforcement_blocked ► reason_code=%s message=%s", reason_code, message)
            _handle_closure_enforcement_block(
                orchestration_adapter=orchestration_adapter,
                tracer=tracer,
                loop_memory=loop_memory,
                action_plan=action_plan,
                iteration=iterations,
                reason_code=reason_code,
            )
            continue

        if action_plan.complete_run:
            sync_state_patch_after_committed_gate(
                loop_memory=loop_memory,
                action_plan=action_plan,
                tracer=tracer,
                iteration=iterations,
                gate="complete_run",
            )
            _record_turn_continuity(
                loop_memory=loop_memory,
                action_plan=action_plan,
                iteration=iterations,
                execution_state="complete_run",
                execution_reason_code=None,
            )
            _notify_turn_completed(
                orchestration_adapter, iterations,
                action_plan=action_plan, step_result=None,
                loop_memory=loop_memory, terminal_decision="complete_run",
            )
            return _make_result(
                loop_memory=loop_memory,
                terminal_class="completed",
                reason_code="complete_run",
                terminal_summary=str(action_plan.rationale) if action_plan.rationale is not None else None,
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
                session_manager=session_manager,
            )

        step_request = coerce_step_request(action_plan, session_id=session_id)
        if step_request is not None and not action_plan.skip_execution:
            step_result = session_manager.step(step_request)
            _append_kernel_step_result_continuity(
                loop_memory=loop_memory,
                iteration=iterations,
                action_type=action_plan.action_type,
                step_result=step_result,
            )
            _accumulate_image_evidence(loop_memory=loop_memory, step_result=step_result)
            if step_result.execution_state != ExecutionState.EXECUTED:
                refusal = step_result.refusal
                reason = refusal.reason_code if refusal is not None else "step_execution_refused"
                retryable = refusal.retryable if refusal is not None else False
                tracer.emit_execution_result(
                    iteration=iterations,
                    action_type=str(step_request.action_id),
                    execution_state="refused",
                    reason_code=reason,
                    retryable=retryable,
                    refs_delta=None,
                )
                sync_state_patch_after_step_refusal(
                    loop_memory=loop_memory,
                    tracer=tracer,
                    iteration=iterations,
                    patch_present=patch_present,
                    execution_reason_code=reason,
                )
                is_retryable = (
                    refusal is not None
                    and refusal.retryable
                    and not refusal.blocked_by_budget
                    and not refusal.blocked_by_invariant
                )
                if not is_retryable:
                    _record_turn_continuity(
                        loop_memory=loop_memory,
                        action_plan=action_plan,
                        iteration=iterations,
                        execution_state="refused",
                        execution_reason_code=reason,
                    )
                    _notify_turn_completed(
                        orchestration_adapter, iterations,
                        action_plan=action_plan, step_result=step_result,
                        loop_memory=loop_memory, terminal_decision="refused",
                    )
                    return _make_result(
                        loop_memory=loop_memory,
                        terminal_class="failed",
                        reason_code=reason,
                        iterations=iterations,
                        session_id=session_id,
                        run_artifact_ref=run_artifact_ref,
                        tracer=tracer,
                        session_manager=session_manager,
                    )
                _record_turn_continuity(
                    loop_memory=loop_memory,
                    action_plan=action_plan,
                    iteration=iterations,
                    execution_state="refused",
                    execution_reason_code=reason,
                )
                if step_result.dashboard is not None:
                    loop_memory.continuity.latest_refs = step_result.dashboard.latest_refs.model_dump(mode="json")
                _notify_turn_completed(
                    orchestration_adapter, iterations,
                    action_plan=action_plan, step_result=step_result,
                    loop_memory=loop_memory,
                )
            else:
                if step_result.dashboard is not None:
                    loop_memory.continuity.latest_refs = step_result.dashboard.latest_refs.model_dump(mode="json")
                tracer.emit_execution_result(
                    iteration=iterations,
                    action_type=str(step_request.action_id),
                    execution_state="executed",
                    reason_code=None,
                    retryable=None,
                    refs_delta=loop_memory.continuity.latest_refs,
                )
                sync_state_patch_after_committed_gate(
                    loop_memory=loop_memory,
                    action_plan=action_plan,
                    tracer=tracer,
                    iteration=iterations,
                    gate="step_executed",
                )
                _record_turn_continuity(
                    loop_memory=loop_memory,
                    action_plan=action_plan,
                    iteration=iterations,
                    execution_state="executed",
                    execution_reason_code=None,
                )
                _notify_turn_completed(
                    orchestration_adapter, iterations,
                    action_plan=action_plan, step_result=step_result,
                    loop_memory=loop_memory,
                )
        else:
            sync_state_patch_when_no_step_dispatched(
                loop_memory=loop_memory,
                action_plan=action_plan,
                tracer=tracer,
                iteration=iterations,
                patch_present=patch_present,
                skip_execution=action_plan.skip_execution,
            )
            _record_turn_continuity(
                loop_memory=loop_memory,
                action_plan=action_plan,
                iteration=iterations,
                execution_state="skipped" if action_plan.skip_execution else "not_dispatched",
                execution_reason_code=None,
            )
            _notify_turn_completed(
                orchestration_adapter, iterations,
                action_plan=action_plan, step_result=None,
                loop_memory=loop_memory,
            )

    return _make_result(
        loop_memory=loop_memory,
        terminal_class="exhausted",
        reason_code="max_iterations_reached",
        iterations=loop_memory.iterations,
        session_id=session_id,
        run_artifact_ref=run_artifact_ref,
        tracer=tracer,
        session_manager=session_manager,
    )


def _call_optional(obj: OrchestrationAdapter, name: str, *args: Any, **kwargs: Any) -> Any:
    fn = getattr(obj, name, None)
    if not callable(fn):
        return None
    return fn(*args, **kwargs)


def _make_result(
    *,
    loop_memory: LoopMemoryState,
    terminal_class: TerminalClass,
    reason_code: str,
    iterations: int,
    session_id: str,
    run_artifact_ref: str | None,
    tracer: KernelTraceCollector,
    session_manager: ExecutionSessionManager,
    terminal_summary: str | None = None,
) -> KernelLoopResult:
    tracer.emit_terminal(
        iteration=iterations,
        terminal_class=terminal_class,
        reason_code=reason_code,
        terminal_summary=terminal_summary,
    )
    runtime_state = {
        "hitl_state": loop_memory.hitl.hitl_state,
        "blocking_prompt_id": loop_memory.hitl.blocking_prompt_id,
        "pending_feedback_prompt_id": loop_memory.hitl.pending_feedback_prompt_id,
        "pending_hitl_requests_count": len(loop_memory.hitl.pending_hitl_requests),
        "answered_hitl_responses_count": len(loop_memory.hitl.answered_hitl_responses),
        "active_item_id": loop_memory.continuity.active_item_id,
        "llm_contact_count": loop_memory.telemetry.llm_contact_count,
        "prompt_event_count": loop_memory.telemetry.prompt_event_count,
        "last_prompt_event_id": loop_memory.telemetry.last_prompt_event_id,
        "last_prompt_event_surface": loop_memory.telemetry.last_prompt_event_surface,
        "mission_state": loop_memory.continuity.mission_state,
        "resolution_state": loop_memory.continuity.resolution_state,
        "state_patch_feedback": dict(loop_memory.continuity.state_patch_feedback),
        "operator_progress_message": loop_memory.continuity.operator_progress_message,
        "compacted_continuity_summary": loop_memory.continuity.compacted_continuity_summary,
        "continuity_journal_entry_count": len(loop_memory.continuity.continuity_journal_entries),
        "kernel_compaction_covered_through_turn_index": int(
            loop_memory.continuity.kernel_compaction_covered_through_turn_index
        ),
    }
    resume_snap = build_kernel_resume_snapshot(
        loop_memory=loop_memory,
        session_manager=session_manager,
        session_id=session_id,
        next_iteration=iterations + 1,
    )
    return KernelLoopResult(
        terminal_class=terminal_class,
        reason_code=reason_code,
        terminal_summary=terminal_summary,
        iterations=iterations,
        session_id=session_id,
        run_artifact_ref=run_artifact_ref,
        latest_refs=dict(loop_memory.continuity.latest_refs),
        runtime_state=runtime_state,
        trace_events=tracer.build_raw_events(),
        kernel_resume_snapshot=resume_snap,
    )
