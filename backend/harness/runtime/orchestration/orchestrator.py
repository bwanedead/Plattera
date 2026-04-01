from __future__ import annotations

import logging
from typing import Any

from ...execution.contracts import ExecutionState, ExecutionStepRequest
from ...execution.session import ExecutionSessionManager

from ...mission_state import MissionState, ResolutionState
from ...terminal_taxonomy import TerminalClass
from .contracts import (
    ActionPlan,
    KernelLoopResult,
    OrchestrationAdapter,
    OrchestratorContext,
    SharedStateProjection,
    TerminalEvaluation,
)
from ..memory import LoopMemoryState
from .trace_collector import KernelTraceCollector

_LOG = logging.getLogger(__name__)


def _pack_id_from_prompt_metadata(metadata: dict[str, Any], info: dict[str, Any]) -> str:
    """Prompt-pack identifier from metadata (``pack_id`` only)."""
    return str(metadata.get("pack_id") or info.get("pack_id") or "")


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
) -> KernelLoopResult:
    """Drive the bounded per-run loop; ``orchestration_adapter`` implements ``OrchestrationAdapter``.

    Mechanical run status is emitted only through ``KernelTraceCollector`` (see
    ``KernelLoopResult.trace_events``)—no parallel host progress callback.

    Packs may optionally define ``wire_identity_trace_cb`` for LLM identity tracing; that hook is
    not part of the protocol and is discovered via ``hasattr``.
    """
    loop_memory = LoopMemoryState()
    if isinstance(resume_hitl_response, dict) and resume_hitl_response:
        loop_memory.hitl.hitl_state = "answered_unintegrated"
        loop_memory.hitl.pending_feedback_response = resume_hitl_response
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
        prompt_event = info.get("prompt_event")
        if isinstance(prompt_event, dict):
            metadata = prompt_event.get("metadata") if isinstance(prompt_event.get("metadata"), dict) else {}
            tracer.emit_prompt_event(
                iteration=None,
                prompt_event=prompt_event,
                surface=str(metadata.get("surface") or info.get("surface") or ""),
                pack_id=_pack_id_from_prompt_metadata(metadata, info),
                model=str(metadata.get("model") or info.get("model") or ""),
            )
            loop_memory.telemetry.register_prompt_event(
                prompt_event_id=str(metadata.get("prompt_event_id") or ""),
                surface=str(metadata.get("surface") or info.get("surface") or ""),
            )
            return
        tracer.emit_llm_call_identity(
            iteration=None,
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
    if hasattr(session_manager, "wire_identity_trace_cb"):
        session_manager.wire_identity_trace_cb(_identity_trace_cb)  # type: ignore[attr-defined]

    _call_optional(orchestration_adapter, "initialize", context)

    for iterations in range(1, max_iterations + 1):
        loop_memory.iterations = iterations
        tracer.emit_iteration_start(iteration=iterations, hitl_state=loop_memory.hitl.hitl_state)

        if (
            loop_memory.hitl.hitl_state == "waiting"
            and loop_memory.hitl.pending_feedback_response is None
        ):
            return _make_result(
                loop_memory=loop_memory,
                terminal_class="waiting_human",
                reason_code="waiting_human_feedback",
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
            )

        projection = _coerce_projection(_call_optional(orchestration_adapter, "sync", context))
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

        terminal = _coerce_terminal_evaluation(_call_optional(orchestration_adapter, "evaluate_terminal", context, projection))
        if terminal is not None:
            return _make_result(
                loop_memory=loop_memory,
                terminal_class=terminal.terminal_class,
                reason_code=terminal.reason_code,
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
            )

        action_plan = _coerce_action_plan(_call_optional(orchestration_adapter, "choose_action", context, projection))
        if action_plan is None:
            continue

        if action_plan.wait_for_human:
            loop_memory.hitl.hitl_state = "waiting"
            return _make_result(
                loop_memory=loop_memory,
                terminal_class="waiting_human",
                reason_code="waiting_human_feedback",
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
            )

        if action_plan.complete_run:
            return _make_result(
                loop_memory=loop_memory,
                terminal_class="completed",
                reason_code=str(action_plan.rationale or "complete_run"),
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
            )

        step_request = _coerce_step_request(action_plan, session_id=session_id)
        if step_request is not None and not action_plan.skip_execution:
            step_result = session_manager.step(step_request)
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
                is_retryable = (
                    refusal is not None
                    and refusal.retryable
                    and not refusal.blocked_by_budget
                    and not refusal.blocked_by_invariant
                )
                if not is_retryable:
                    return _make_result(
                        loop_memory=loop_memory,
                        terminal_class="failed",
                        reason_code=reason,
                        iterations=iterations,
                        session_id=session_id,
                        run_artifact_ref=run_artifact_ref,
                        tracer=tracer,
                    )
                if step_result.dashboard is not None:
                    loop_memory.continuity.latest_refs = step_result.dashboard.latest_refs.model_dump(mode="json")
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

    return _make_result(
        loop_memory=loop_memory,
        terminal_class="exhausted",
        reason_code="max_iterations_reached",
        iterations=loop_memory.iterations,
        session_id=session_id,
        run_artifact_ref=run_artifact_ref,
        tracer=tracer,
    )


def _call_optional(obj: OrchestrationAdapter, name: str, *args: Any, **kwargs: Any) -> Any:
    fn = getattr(obj, name, None)
    if not callable(fn):
        return None
    return fn(*args, **kwargs)


def _coerce_projection(value: Any) -> SharedStateProjection | None:
    if value is None:
        return None
    if isinstance(value, SharedStateProjection):
        return value
    if isinstance(value, dict):
        mission_state = value.get("mission_state")
        resolution_state = value.get("resolution_state")
        if not isinstance(mission_state, MissionState) or not isinstance(resolution_state, ResolutionState):
            return None
        return SharedStateProjection(
            mission_state=mission_state,
            resolution_state=resolution_state,
            latest_refs=dict(value.get("latest_refs") or {}),
            active_item_id=str(value.get("active_item_id") or "").strip() or None,
        )
    mission_state = getattr(value, "mission_state", None)
    resolution_state = getattr(value, "resolution_state", None)
    if not isinstance(mission_state, MissionState) or not isinstance(resolution_state, ResolutionState):
        return None
    latest_refs = getattr(value, "latest_refs", {})
    active_item_id = getattr(value, "active_item_id", None)
    return SharedStateProjection(
        mission_state=mission_state,
        resolution_state=resolution_state,
        latest_refs=dict(latest_refs) if isinstance(latest_refs, dict) else {},
        active_item_id=str(active_item_id or "").strip() or None,
    )


def _coerce_action_plan(value: Any) -> ActionPlan | None:
    if value is None:
        return None
    if isinstance(value, ActionPlan):
        return value
    if isinstance(value, dict):
        return ActionPlan(
            action_type=str(value.get("action_type") or "").strip() or None,
            action_inputs=dict(value.get("action_inputs") or {}),
            idempotency_key=str(value.get("idempotency_key") or ""),
            skip_execution=bool(value.get("skip_execution", False)),
            wait_for_human=bool(value.get("wait_for_human", False)),
            complete_run=bool(value.get("complete_run", False)),
            rationale=str(value.get("rationale") or "").strip() or None,
        )
    action_inputs = getattr(value, "action_inputs", None)
    return ActionPlan(
        action_type=str(getattr(value, "action_type", "") or "").strip() or None,
        action_inputs=action_inputs if isinstance(action_inputs, dict) else {},
        idempotency_key=str(getattr(value, "idempotency_key", "") or ""),
        skip_execution=bool(getattr(value, "skip_execution", False)),
        wait_for_human=bool(getattr(value, "wait_for_human", False)),
        complete_run=bool(getattr(value, "complete_run", False)),
        rationale=str(getattr(value, "rationale", "") or "").strip() or None,
    )


def _coerce_step_request(value: Any, *, session_id: str) -> ExecutionStepRequest | None:
    if value is None:
        return None
    if isinstance(value, ExecutionStepRequest):
        return value
    if isinstance(value, ActionPlan):
        if value.action_type is None:
            return None
        return ExecutionStepRequest(
            session_id=session_id,
            action_id=value.action_type,
            inputs=dict(value.action_inputs),
            idempotency_key=value.idempotency_key,
        )
    if isinstance(value, dict):
        action_type = value.get("action_type")
        inputs = value.get("inputs")
        if action_type is None:
            return None
        return ExecutionStepRequest(
            session_id=str(value.get("session_id") or session_id),
            action_id=action_type,
            inputs=inputs if isinstance(inputs, dict) else {},
            idempotency_key=str(value.get("idempotency_key") or ""),
        )
    action_type = getattr(value, "action_type", None)
    inputs = getattr(value, "inputs", None)
    if action_type is None:
        return None
    return ExecutionStepRequest(
        session_id=str(getattr(value, "session_id", None) or session_id),
        action_id=action_type,
        inputs=inputs if isinstance(inputs, dict) else {},
        idempotency_key=str(getattr(value, "idempotency_key", "") or ""),
    )


def _coerce_terminal_evaluation(value: Any) -> TerminalEvaluation | None:
    if value is None:
        return None
    if isinstance(value, TerminalEvaluation):
        return value
    if isinstance(value, dict):
        terminal_class = value.get("terminal_class")
        reason_code = str(value.get("reason_code") or "").strip()
        if terminal_class is None or not reason_code:
            return None
        return TerminalEvaluation(terminal_class=terminal_class, reason_code=reason_code)
    terminal_class = getattr(value, "terminal_class", None)
    reason_code = str(getattr(value, "reason_code", "") or "").strip()
    if terminal_class is None or not reason_code:
        return None
    return TerminalEvaluation(terminal_class=terminal_class, reason_code=reason_code)


def _make_result(
    *,
    loop_memory: LoopMemoryState,
    terminal_class: TerminalClass,
    reason_code: str,
    iterations: int,
    session_id: str,
    run_artifact_ref: str | None,
    tracer: KernelTraceCollector,
) -> KernelLoopResult:
    tracer.emit_terminal(
        iteration=iterations,
        terminal_class=terminal_class,
        reason_code=reason_code,
    )
    runtime_state = {
        "hitl_state": loop_memory.hitl.hitl_state,
        "pending_feedback_prompt_id": loop_memory.hitl.pending_feedback_prompt_id,
        "active_item_id": loop_memory.continuity.active_item_id,
        "llm_contact_count": loop_memory.telemetry.llm_contact_count,
        "prompt_event_count": loop_memory.telemetry.prompt_event_count,
        "last_prompt_event_id": loop_memory.telemetry.last_prompt_event_id,
        "last_prompt_event_surface": loop_memory.telemetry.last_prompt_event_surface,
        "mission_state": loop_memory.continuity.mission_state,
        "resolution_state": loop_memory.continuity.resolution_state,
    }
    return KernelLoopResult(
        terminal_class=terminal_class,
        reason_code=reason_code,
        iterations=iterations,
        session_id=session_id,
        run_artifact_ref=run_artifact_ref,
        latest_refs=dict(loop_memory.continuity.latest_refs),
        runtime_state=runtime_state,
        trace_events=tracer.build_raw_events(),
    )
