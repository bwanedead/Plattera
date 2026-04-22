from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ...execution.session import ExecutionSessionManager
from ...terminal_taxonomy import TerminalClass
from ..control import RunControlRequest
from ..memory import LoopMemoryState
from ..memory.resume_snapshot import build_kernel_resume_snapshot
from .contracts import KernelLoopResult
from .lifecycle import OrchestrationLifecycle
from .trace_collector import KernelTraceCollector

_LOG = logging.getLogger(__name__)

_CONTROL_COMMAND_TO_TERMINAL: dict[str, tuple[str, str]] = {
    "pause": ("paused", "paused_by_operator"),
    "stop": ("stopped", "stopped_by_operator"),
}


def poll_run_control(lifecycle: OrchestrationLifecycle) -> RunControlRequest | None:
    """Invoke the lifecycle reader if present; reader failures are non-fatal."""
    reader = lifecycle.run_control_reader
    if reader is None:
        return None
    try:
        req = reader()
    except Exception:
        _LOG.warning("run_control_reader_failed", exc_info=True)
        return None
    return req if isinstance(req, RunControlRequest) else None


def maybe_exit_for_run_control(
    *,
    lifecycle: OrchestrationLifecycle,
    loop_memory: LoopMemoryState,
    session_manager: ExecutionSessionManager,
    session_id: str,
    run_artifact_ref: str | None,
    tracer: KernelTraceCollector,
    iteration: int,
    checkpoint_writer: Callable[[int], None],
) -> KernelLoopResult | None:
    """Honor a pending operator control request at a safe loop boundary."""
    req = poll_run_control(lifecycle)
    if req is None:
        return None
    mapping = _CONTROL_COMMAND_TO_TERMINAL.get(req.command)
    if mapping is None:
        return None
    terminal_class, reason_code = mapping
    checkpoint_writer(iteration)
    _LOG.info(
        "KERNEL run_control_honored ► command=%s request_id=%s iteration=%s",
        req.command,
        req.request_id,
        iteration,
    )
    return build_kernel_loop_result(
        loop_memory=loop_memory,
        terminal_class=terminal_class,
        reason_code=reason_code,
        iterations=iteration,
        session_id=session_id,
        run_artifact_ref=run_artifact_ref,
        tracer=tracer,
        session_manager=session_manager,
        terminal_summary=req.reason,
        control_request=req,
    )


def build_kernel_loop_result(
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
    control_request: RunControlRequest | None = None,
) -> KernelLoopResult:
    tracer.emit_terminal(
        iteration=iterations,
        terminal_class=terminal_class,
        reason_code=reason_code,
        terminal_summary=terminal_summary,
    )
    snap = build_kernel_resume_snapshot(
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
        runtime_state=_build_runtime_state(
            loop_memory=loop_memory,
            iterations=iterations,
            control_request=control_request,
        ),
        trace_events=tracer.build_raw_events(),
        kernel_resume_snapshot=snap,
    )


def _build_runtime_state(
    *,
    loop_memory: LoopMemoryState,
    iterations: int,
    control_request: RunControlRequest | None,
) -> dict[str, Any]:
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
    if control_request is not None:
        runtime_state["control_request"] = control_request.to_json_dict()
        runtime_state["resumable"] = True
        runtime_state["interrupted_at_iteration"] = int(iterations)
    return runtime_state
