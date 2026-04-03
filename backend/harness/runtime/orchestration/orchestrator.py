from __future__ import annotations

import logging
from typing import Any

from ...execution.contracts import ExecutionState
from ...execution.session import ExecutionSessionManager

from ...terminal_taxonomy import TerminalClass
from .contracts import KernelLoopResult, OrchestrationAdapter, OrchestratorContext
from ..memory import LoopMemoryState
from ..memory.resume_snapshot import build_kernel_resume_snapshot
from .orchestrator_coercion import (
    coerce_kernel_action_plan,
    coerce_projection,
    coerce_step_request,
    coerce_terminal_evaluation,
)
from .state_patch_apply import (
    sync_state_patch_after_committed_gate,
    sync_state_patch_after_step_refusal,
    sync_state_patch_when_no_step_dispatched,
)
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
    initial_loop_memory: LoopMemoryState | None = None,
    resume_start_iteration: int = 1,
) -> KernelLoopResult:
    """Drive the bounded per-run loop; ``orchestration_adapter`` implements ``OrchestrationAdapter``.

    Mechanical run status is emitted only through ``KernelTraceCollector`` (see
    ``KernelLoopResult.trace_events``)—no parallel host progress callback.

    Packs may optionally define ``wire_identity_trace_cb`` for LLM identity tracing; that hook is
    not part of the protocol and is discovered via ``hasattr``.

    For process restart, pass ``initial_loop_memory`` and ``resume_start_iteration`` from a parsed
    ``kernel_resume.v1`` snapshot (mechanical rehydration only; no semantic repair).
    """
    loop_memory = initial_loop_memory if initial_loop_memory is not None else LoopMemoryState()
    start_iteration = max(1, int(resume_start_iteration))
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

    for offset in range(max_iterations):
        iterations = start_iteration + offset
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
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
                session_manager=session_manager,
            )

        action_plan = coerce_kernel_action_plan(_call_optional(orchestration_adapter, "choose_action", context, projection))
        if action_plan is None:
            continue

        patch_present = bool(action_plan.state_patch)

        if action_plan.wait_for_human:
            sync_state_patch_after_committed_gate(
                loop_memory=loop_memory,
                action_plan=action_plan,
                tracer=tracer,
                iteration=iterations,
                gate="wait_for_human",
            )
            loop_memory.hitl.hitl_state = "waiting"
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

        if action_plan.complete_run:
            sync_state_patch_after_committed_gate(
                loop_memory=loop_memory,
                action_plan=action_plan,
                tracer=tracer,
                iteration=iterations,
                gate="complete_run",
            )
            return _make_result(
                loop_memory=loop_memory,
                terminal_class="completed",
                reason_code=str(action_plan.rationale or "complete_run"),
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
                session_manager=session_manager,
            )

        step_request = coerce_step_request(action_plan, session_id=session_id)
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
                sync_state_patch_after_committed_gate(
                    loop_memory=loop_memory,
                    action_plan=action_plan,
                    tracer=tracer,
                    iteration=iterations,
                    gate="step_executed",
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
        "state_patch_feedback": dict(loop_memory.continuity.state_patch_feedback),
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
        iterations=iterations,
        session_id=session_id,
        run_artifact_ref=run_artifact_ref,
        latest_refs=dict(loop_memory.continuity.latest_refs),
        runtime_state=runtime_state,
        trace_events=tracer.build_raw_events(),
        kernel_resume_snapshot=resume_snap,
    )
