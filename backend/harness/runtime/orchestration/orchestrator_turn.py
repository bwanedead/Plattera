"""Per-turn tracking, notification, and continuity helpers for the orchestration kernel.

Extracted from ``orchestrator`` to keep the main loop focused on control flow.
"""

from __future__ import annotations

import logging
from typing import Any

from ...execution.contracts import ExecutionStepResult
from ..memory import LoopMemoryState
from ..memory.continuity_journal import apply_kernel_turn_continuity_carriage, build_kernel_step_result_record
from .contracts import ActionPlan, OrchestrationAdapter
from .trace_collector import KernelTraceCollector

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


def notify_turn_completed(
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
