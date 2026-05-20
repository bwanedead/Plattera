"""Orchestrator execution hook for agent-authored ``action_batch`` plans."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any

from ...execution.contracts import ExecutionState, ExecutionStepRequest
from ...execution.session import ExecutionSessionManager
from ..memory import LoopMemoryState
from .action_batch import (
    build_action_batch_result_record,
    build_batch_item_result_row,
)
from .contracts import ActionPlan
from .orchestrator_turn import (
    accumulate_image_evidence,
    append_kernel_step_result_continuity,
    observe_turn_completed,
    record_turn_continuity,
)
from .state_patch_apply import sync_state_patch_after_committed_gate
from .tool_batch_policy import ToolBatchPolicy

_LOG = logging.getLogger(__name__)


@dataclass
class ActionBatchExecutionOutcome:
    batch_result: dict[str, Any]
    last_step_result: Any | None


def execute_action_batch(
    *,
    loop_memory: LoopMemoryState,
    session_manager: ExecutionSessionManager,
    session_id: str,
    action_plan: ActionPlan,
    iteration: int,
    request_id_prefix: str,
    run_id: str,
    tool_batch_policies: dict[str, ToolBatchPolicy],
) -> ActionBatchExecutionOutcome:
    """Validate-then-run each batch item sequentially; never raises."""
    batch_id = f"{request_id_prefix}:iter:{int(iteration)}:batch"
    item_rows: list[dict[str, Any]] = []
    last_step_result: Any | None = None
    stop_remaining = False

    for item in action_plan.action_batch:
        if stop_remaining:
            item_rows.append(
                build_batch_item_result_row(
                    alias=item.alias,
                    action_type=item.action_type,
                    execution_state="skipped_due_to_prior_batch_failure",
                    error={"reason_code": "skipped_due_to_prior_batch_failure"},
                )
            )
            continue

        policy = tool_batch_policies.get(item.action_type)
        idem = f"{request_id_prefix}:iter:{int(iteration)}:batch:{item.alias}"
        req = ExecutionStepRequest(
            session_id=session_id,
            action_id=item.action_type,
            inputs=dict(item.action_inputs),
            idempotency_key=idem,
            run_id=run_id or None,
        )
        try:
            step_result = session_manager.step(req)
        except Exception:  # noqa: BLE001
            _LOG.warning("action_batch_item_dispatch_failed", exc_info=True)
            item_rows.append(
                build_batch_item_result_row(
                    alias=item.alias,
                    action_type=item.action_type,
                    execution_state="retryable_error",
                    error={"reason_code": "batch_dispatch_exception"},
                )
            )
            if policy is None or not policy.continues_after_item_failure:
                stop_remaining = True
            continue

        last_step_result = step_result
        append_kernel_step_result_continuity(
            loop_memory=loop_memory,
            iteration=iteration,
            action_type=item.action_type,
            step_result=step_result,
        )
        accumulate_image_evidence(loop_memory=loop_memory, step_result=step_result)

        if step_result.execution_state != ExecutionState.EXECUTED:
            refusal = step_result.refusal
            reason = refusal.reason_code if refusal is not None else "step_execution_refused"
            retryable = bool(refusal.retryable) if refusal is not None else False
            state_label = "retryable_error" if retryable else "refused"
            item_rows.append(
                build_batch_item_result_row(
                    alias=item.alias,
                    action_type=item.action_type,
                    execution_state=state_label,
                    error={
                        "reason_code": reason,
                        "retryable": retryable,
                    },
                )
            )
            if policy is None or not policy.continues_after_item_failure:
                stop_remaining = True
            continue

        rec = step_result.record
        result = rec.result if rec is not None else None
        outputs = dict(result.outputs or {}) if result is not None else {}
        artifact_refs = list(result.artifact_refs or ()) if result is not None else []
        image_evidence = list(result.image_evidence) if result is not None and result.image_evidence else []
        if step_result.dashboard is not None:
            loop_memory.continuity.latest_refs = step_result.dashboard.latest_refs.model_dump(mode="json")

        item_rows.append(
            build_batch_item_result_row(
                alias=item.alias,
                action_type=item.action_type,
                execution_state="executed",
                outputs=outputs,
                artifact_refs=artifact_refs,
                image_evidence=image_evidence,
            )
        )

    batch_result = build_action_batch_result_record(
        batch_id=batch_id,
        items=item_rows,
        source_turn_index=int(iteration),
    )
    loop_memory.continuity.recent_action_batch_result = batch_result
    return ActionBatchExecutionOutcome(
        batch_result=batch_result,
        last_step_result=last_step_result,
    )


def clear_stale_action_batch_result(*, loop_memory: LoopMemoryState, iteration: int) -> None:
    """Drop batch summary after it has been visible for one choose-action turn."""
    record = loop_memory.continuity.recent_action_batch_result
    if not record:
        return
    try:
        source_turn = int(record.get("source_turn_index", 0))
    except (TypeError, ValueError):
        loop_memory.continuity.recent_action_batch_result = None
        return
    if int(iteration) > source_turn + 1:
        loop_memory.continuity.recent_action_batch_result = None


def run_action_batch_turn_if_present(
    *,
    loop_memory: LoopMemoryState,
    session_manager: ExecutionSessionManager,
    session_id: str,
    action_plan: ActionPlan,
    iteration: int,
    request_id_prefix: str,
    run_id: str,
    run_ctx: dict[str, Any],
    tracer: Any,
    turn_completion_observer: Any | None,
) -> tuple[bool, ActionPlan, Any | None]:
    """Execute ``action_batch`` when present. Returns ``(handled, plan, step_result)``."""
    if not action_plan.action_batch or action_plan.skip_execution:
        return False, action_plan, None

    from .tool_batch_policy import tool_batch_policies_from_run_context

    action_plan = materialize_batch_action_plan_idempotency(
        action_plan,
        request_id_prefix=request_id_prefix,
        iteration=iteration,
    )
    batch_outcome = execute_action_batch(
        loop_memory=loop_memory,
        session_manager=session_manager,
        session_id=session_id,
        action_plan=action_plan,
        iteration=iteration,
        request_id_prefix=request_id_prefix,
        run_id=run_id,
        tool_batch_policies=tool_batch_policies_from_run_context(run_ctx),
    )
    any_executed = any(
        str(row.get("execution_state")) == "executed"
        for row in batch_outcome.batch_result.get("items") or []
        if isinstance(row, dict)
    )
    exec_state = "executed" if any_executed else "refused"
    reason = None if any_executed else "action_batch_no_executed_items"
    tracer.emit_execution_result(
        iteration=iteration,
        action_type="action_batch",
        execution_state=exec_state,
        reason_code=reason,
        retryable=None,
        refs_delta=loop_memory.continuity.latest_refs,
    )
    sync_state_patch_after_committed_gate(
        loop_memory=loop_memory,
        action_plan=action_plan,
        tracer=tracer,
        iteration=iteration,
        gate="action_batch_executed",
    )
    record_turn_continuity(
        loop_memory=loop_memory,
        action_plan=action_plan,
        iteration=iteration,
        execution_state=exec_state,
        execution_reason_code=reason,
    )
    observe_turn_completed(
        turn_completion_observer,
        iteration,
        action_plan=action_plan,
        step_result=None,
        loop_memory=loop_memory,
        batch_result=batch_outcome.batch_result,
    )
    return True, action_plan, batch_outcome.last_step_result


def materialize_batch_action_plan_idempotency(
    action_plan: ActionPlan,
    *,
    request_id_prefix: str,
    iteration: int,
) -> ActionPlan:
    """Batch turns skip single-action dispatch; host owns per-item keys in the hook."""
    if not action_plan.action_batch:
        return action_plan
    if str(action_plan.idempotency_key).strip():
        return action_plan
    generated = f"{request_id_prefix}:iter:{int(iteration)}:action_batch"
    return replace(action_plan, idempotency_key=generated, skip_execution=False)
