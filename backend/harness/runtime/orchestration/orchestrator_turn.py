"""Per-turn tracking, notification, and continuity helpers for the orchestration kernel.

Extracted from ``orchestrator`` to keep the main loop focused on control flow.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ...execution.contracts import ExecutionStepResult
from ..memory import LoopMemoryState
from ..memory.continuity_journal import apply_kernel_turn_continuity_carriage, build_kernel_step_result_record
from .action_sequence import build_sequence_tool_request_summary, build_sequence_tool_result_summary, effective_actions
from .audit_turn_mechanics import project_action_sequence_for_audit
from ..memory.stable_context import build_stable_context_audit_projection
from .pinned_refs import build_pinned_refs_projection
from .action_batch import summarize_image_evidence_for_projection
from .contracts import ActionPlan
from .lifecycle import TurnCompletionObserver, lifecycle_jsonable
from ..memory.performance_evaluation import delegate_count_for_turn, turn_graph_delta

_LOG = logging.getLogger(__name__)


def dashboard_refs_python(step_result: ExecutionStepResult) -> dict[str, Any]:
    dash = step_result.dashboard
    if dash is None:
        return {}
    return dash.latest_refs.model_dump(mode="python")


def dispatch_outputs_and_artifact_refs(step_result: ExecutionStepResult) -> tuple[dict[str, Any], list[str]]:
    rec = step_result.record
    if rec is None or rec.result is None:
        return {}, []
    r = rec.result
    return dict(r.outputs or {}), list(r.artifact_refs or ())


def accumulate_image_evidence(
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


def append_kernel_step_result_continuity(
    *,
    loop_memory: LoopMemoryState,
    iteration: int,
    action_type: str | None,
    step_result: ExecutionStepResult,
) -> None:
    outs, refs = dispatch_outputs_and_artifact_refs(step_result)
    loop_memory.continuity.kernel_step_result_records.append(
        build_kernel_step_result_record(
            kernel_turn_index=int(iteration),
            action_type=action_type,
            execution_state=step_result.execution_state.value,
            execution_reason_code=(
                step_result.refusal.reason_code if step_result.refusal is not None else None
            ),
            latest_refs_snapshot=dashboard_refs_python(step_result),
            outputs=outs,
            artifact_refs=refs,
        )
    )


def record_turn_continuity(
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
        action_type=(
            "action_sequence"
            if len(effective_actions(action_plan)) > 1
            else (
                effective_actions(action_plan)[0].action_type
                if effective_actions(action_plan)
                else action_plan.action_type
            )
        ),
        action_inputs=(
            dict(effective_actions(action_plan)[0].action_inputs)
            if len(effective_actions(action_plan)) == 1
            else dict(action_plan.action_inputs)
        ),
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


def observe_turn_completed(
    observer: TurnCompletionObserver | None,
    iteration: int,
    *,
    action_plan: ActionPlan,
    step_result: "ExecutionStepResult | None",
    loop_memory: LoopMemoryState,
    terminal_decision: str | None = None,
    batch_result: dict[str, Any] | None = None,
    sequence_result: dict[str, Any] | None = None,
    mechanical_audit: dict[str, Any] | None = None,
) -> None:
    """Send an explicit post-turn mechanical record to the lifecycle observer."""
    actions = effective_actions(action_plan)
    tool_request: dict[str, Any] | None = None
    if actions and not action_plan.complete_run and not action_plan.wait_for_human:
        tool_request = build_sequence_tool_request_summary(action_plan)
    elif action_plan.pin_refs or action_plan.unpin_refs:
        tool_request = build_sequence_tool_request_summary(action_plan)
    tool_result_raw: dict[str, Any] | None = None
    seq_payload = sequence_result if sequence_result is not None else batch_result
    if actions and len(actions) > 1:
        tool_result_raw = build_sequence_tool_result_summary(seq_payload)
    elif step_result is not None:
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
            "image_evidence_summary": (
                summarize_image_evidence_for_projection(rec.result.image_evidence)
                if rec is not None and rec.result is not None and rec.result.image_evidence
                else None
            ),
        }
    pinned_refs_snapshot = build_pinned_refs_projection(
        loop_memory.continuity.pinned_refs,
        current_turn=iteration,
    )
    stable_context_snapshot = build_stable_context_audit_projection(
        loop_memory.continuity.stable_context,
        current_turn=iteration,
    )
    record = lifecycle_jsonable(
        {
            "turn_index": iteration,
            "tool_request": tool_request,
            "pin_refs_this_turn": list(action_plan.pin_refs),
            "unpin_refs_this_turn": list(action_plan.unpin_refs),
            "pinned_refs": pinned_refs_snapshot,
            "stable_context": stable_context_snapshot,
            "tool_result_raw": tool_result_raw,
            "mission_state_after": loop_memory.continuity.mission_state,
            "resolution_state_after": loop_memory.continuity.resolution_state,
            "latest_refs_after": dict(loop_memory.continuity.latest_refs),
            "state_patch_feedback": dict(loop_memory.continuity.state_patch_feedback),
            "user_message_ledger": list(loop_memory.continuity.user_message_ledger),
            "user_message_consumed_unknown_count": int(
                loop_memory.continuity.user_message_consumed_unknown_count
            ),
            "terminal_decision": terminal_decision,
            "recent_action_sequence_result": project_action_sequence_for_audit(
                loop_memory.continuity.recent_action_sequence_result,
            ),
        }
    )
    if mechanical_audit:
        record.update(mechanical_audit)
    _finalize_turn_performance_contact(
        loop_memory=loop_memory,
        turn_index=iteration,
        completion_record=record,
    )
    if observer is None:
        return
    try:
        observer.observe_turn_completed(record)
    except Exception:
        _LOG.warning("turn_completion_observer raised; ignoring", exc_info=True)


def _finalize_turn_performance_contact(
    *,
    loop_memory: LoopMemoryState,
    turn_index: int,
    completion_record: dict[str, Any],
) -> None:
    before: dict[str, Any] | None = None
    for row in reversed(loop_memory.telemetry.turn_contact_records):
        if int(row.get("turn_index") or -1) == int(turn_index):
            prior_before = row.get("resolution_state_before")
            if isinstance(prior_before, dict):
                before = prior_before
            break

    merged = dict(completion_record)
    if before is not None and "resolution_state_before" not in merged:
        merged["resolution_state_before"] = before
    delta = turn_graph_delta(merged)
    after = merged.get("resolution_state_after")
    loop_memory.telemetry.finalize_turn_contact(
        turn_index=int(turn_index),
        finished_at_epoch_seconds=time.time(),
        resolution_state_after=after if isinstance(after, dict) else None,
        delegate_count=delegate_count_for_turn(merged),
        determinations_changed=delta["determinations_changed"],
        units_closed=delta["units_closed"],
    )
