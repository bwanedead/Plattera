"""Policy-block handling for pre-dispatch enforcement gates.

Extracted from ``orchestrator.py`` to keep the loop driver under its hotspot budget.
Behavior is unchanged: refuse the turn, optionally commit state_patch after the
existing closure-enforcement gate, record continuity, observe completion, checkpoint.
"""

from __future__ import annotations

from typing import Any

from ...execution.session import ExecutionSessionManager
from ..memory import LoopMemoryState
from .action_sequence import effective_actions
from .contracts import ActionPlan
from .lifecycle import OrchestrationLifecycle, TurnCompletionObserver
from .orchestrator_turn import observe_turn_completed, record_turn_continuity
from .required_output_gate import MAX_CONSECUTIVE_MISSING_OUTPUT_COMPLETE_ATTEMPTS
from .resume_checkpointing import write_resume_checkpoint
from .state_patch_apply import sync_state_patch_after_committed_gate
from .trace_collector import KernelTraceCollector


def action_id_for_plan(action_plan: ActionPlan) -> str:
    if action_plan.complete_run:
        return "complete_run"
    if action_plan.wait_for_human:
        return "wait_for_human"
    actions = effective_actions(action_plan)
    if len(actions) > 1:
        return "action_sequence"
    if len(actions) == 1:
        return actions[0].action_type
    return str(action_plan.action_type or "no_action")


def handle_policy_block(
    *,
    turn_completion_observer: TurnCompletionObserver | None,
    tracer: KernelTraceCollector,
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
    iteration: int,
    reason_code: str,
    lifecycle: OrchestrationLifecycle,
    session_manager: ExecutionSessionManager,
    session_id: str,
    run_ctx: dict[str, Any] | None = None,
    required_output_gate_outcome: str | None = None,
) -> None:
    tracer.emit_execution_result(
        iteration=iteration,
        action_type=action_id_for_plan(action_plan),
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
    record_turn_continuity(
        loop_memory=loop_memory,
        action_plan=action_plan,
        iteration=iteration,
        execution_state="refused",
        execution_reason_code=reason_code,
    )
    mechanical_audit: dict[str, Any] | None = None
    if reason_code.startswith("missing_required_output_artifact:"):
        mechanical_audit = {
            "required_output_gate": {
                "reason_code": reason_code,
                "strike_count": int(loop_memory.continuity.missing_required_output_complete_attempts),
                "max_strikes": MAX_CONSECUTIVE_MISSING_OUTPUT_COMPLETE_ATTEMPTS,
                "outcome": required_output_gate_outcome or "repairable_continue",
            }
        }
    elif reason_code.startswith(("work_universe_", "closure_publish_", "closure_complete_")):
        from .closure_enforcement_feedback import build_closure_enforcement_block_feedback
        from .completion_anchor import evaluate_preview_ready_publish_bypass

        actions = effective_actions(action_plan)
        blocked_action_id = (
            actions[0].action_type
            if len(actions) == 1
            else (action_plan.action_type or "action_sequence")
        )
        preview_bypass = evaluate_preview_ready_publish_bypass(
            closure_policy=(run_ctx or {}).get("domain_closure_policy")
            if isinstance(run_ctx, dict)
            else None,
            action_plan=action_plan,
            step_result_records=loop_memory.continuity.kernel_step_result_records,
        )
        preview_valid = None
        if preview_bypass.get("allowed") or preview_bypass.get("final_package_preview_ref"):
            preview_valid = preview_bypass.get("allowed") is True
        mechanical_audit = {
            "closure_enforcement_block": build_closure_enforcement_block_feedback(
                blocked_action_id=str(blocked_action_id or ""),
                reason_code=reason_code,
                preview_still_valid=preview_valid,
            ),
        }
    observe_turn_completed(
        turn_completion_observer,
        iteration,
        action_plan=action_plan,
        step_result=None,
        loop_memory=loop_memory,
        terminal_decision="closure_enforcement_blocked",
        mechanical_audit=mechanical_audit,
    )
    write_resume_checkpoint(
        lifecycle=lifecycle,
        loop_memory=loop_memory,
        session_manager=session_manager,
        session_id=session_id,
        iteration=iteration,
    )
