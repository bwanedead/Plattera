"""Canonical action-sequence execution and hydration capture."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from ...execution.contracts import ExecutionState, ExecutionStepRequest
from ...execution.session import ExecutionSessionManager
from ..memory import LoopMemoryState
from .action_batch import build_batch_item_result_row
from .action_sequence import (
    ActionPlanAction,
    build_sequence_result_record,
    build_sequence_results_snapshot,
    effective_actions,
)
from .contracts import ActionPlan
from .hydrate_next import (
    MAX_HYDRATE_NEXT_REFS,
    build_hydrate_next_record,
    build_tool_result_snapshot,
    resolve_hydrate_next_refs,
)
from .orchestrator_turn import (
    accumulate_image_evidence,
    append_kernel_step_result_continuity,
    observe_turn_completed,
    record_turn_continuity,
)
from .state_patch_apply import (
    sync_state_patch_after_committed_gate,
    sync_state_patch_after_step_refusal,
    sync_state_patch_when_no_step_dispatched,
)
from .subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE
from .tool_batch_policy import ToolBatchPolicy

_LOG = logging.getLogger(__name__)


@dataclass
class ActionSequenceOutcome:
    handled: bool
    action_plan: ActionPlan
    sequence_result: dict[str, Any] | None = None
    terminal_class: str | None = None
    terminal_reason_code: str | None = None


def clear_stale_action_sequence_result(*, loop_memory: LoopMemoryState, iteration: int) -> None:
    record = loop_memory.continuity.recent_action_sequence_result
    if not record:
        return
    try:
        source_turn = int(record.get("source_turn_index", 0))
    except (TypeError, ValueError):
        loop_memory.continuity.recent_action_sequence_result = None
        return
    if int(iteration) > source_turn + 1:
        loop_memory.continuity.recent_action_sequence_result = None


def capture_hydrate_after_sequence(
    *,
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
    sequence_result: dict[str, Any] | None,
    iteration: int,
) -> None:
    """Aggregate per-action ``hydrate_next`` into one pending hydration record."""
    actions = effective_actions(action_plan)
    if not actions:
        return
    snapshot = build_sequence_results_snapshot(sequence_result)
    requested_all: list[str] = []
    resolved_all: list[str] = []
    errors_all: list[dict[str, Any]] = []
    reasons: list[str] = []

    for item in actions:
        if not item.hydrate_next:
            continue
        tool_snapshot = snapshot.get(item.alias)
        resolved, errors = resolve_hydrate_next_refs(
            list(item.hydrate_next),
            tool_result=tool_snapshot,
            batch_results=None,
        )
        for ref in item.hydrate_next:
            if ref not in requested_all:
                requested_all.append(ref)
        for row in errors:
            tagged = dict(row)
            tagged["action_alias"] = item.alias
            errors_all.append(tagged)
        for ref in resolved:
            if ref not in resolved_all:
                resolved_all.append(ref)
        if item.hydrate_next_reason:
            reasons.append(f"{item.alias}: {item.hydrate_next_reason}")

    if not requested_all:
        return

    if len(resolved_all) > MAX_HYDRATE_NEXT_REFS:
        errors_all.append({
            "reason_code": "aggregate_hydrate_next_cap_exceeded",
            "resolved_count": len(resolved_all),
            "cap": MAX_HYDRATE_NEXT_REFS,
        })
        resolved_all = resolved_all[:MAX_HYDRATE_NEXT_REFS]

    combined_reason = "; ".join(reasons) if reasons else None
    record_payload = build_hydrate_next_record(
        requested_refs=requested_all,
        resolved_refs=resolved_all,
        reason=combined_reason,
        errors=errors_all,
        source_turn_index=iteration,
    )
    loop_memory.continuity.pending_agent_hydration = record_payload


def _execute_sequence_items(
    *,
    loop_memory: LoopMemoryState,
    session_manager: ExecutionSessionManager,
    session_id: str,
    actions: tuple[ActionPlanAction, ...],
    iteration: int,
    request_id_prefix: str,
    run_id: str,
    tool_batch_policies: dict[str, ToolBatchPolicy],
    multi_action: bool,
) -> tuple[dict[str, Any], Any | None]:
    sequence_id = (
        f"{request_id_prefix}:iter:{int(iteration)}:actions"
        if multi_action
        else f"{request_id_prefix}:iter:{int(iteration)}:dispatch:{actions[0].action_type}"
    )
    item_rows: list[dict[str, Any]] = []
    last_step_result: Any | None = None
    stop_remaining = False

    for item in actions:
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
        idem_key = (
            f"{request_id_prefix}:iter:{int(iteration)}:batch:{item.alias}"
            if multi_action
            else f"{request_id_prefix}:iter:{int(iteration)}:dispatch:{item.action_type}"
        )
        step_inputs = dict(item.action_inputs)
        if item.action_type == DELEGATE_SUBTASK_ACTION_TYPE:
            step_inputs["_subtask_alias"] = item.alias
        req = ExecutionStepRequest(
            session_id=session_id,
            action_id=item.action_type,
            inputs=step_inputs,
            idempotency_key=idem_key,
            run_id=run_id or None,
        )
        try:
            step_result = session_manager.step(req)
        except Exception:  # noqa: BLE001
            _LOG.warning("action_sequence_item_dispatch_failed", exc_info=True)
            item_rows.append(
                build_batch_item_result_row(
                    alias=item.alias,
                    action_type=item.action_type,
                    execution_state="retryable_error",
                    error={"reason_code": "sequence_dispatch_exception"},
                )
            )
            if multi_action and (policy is None or not policy.continues_after_item_failure):
                stop_remaining = True
            last_step_result = None
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
                    error={"reason_code": reason, "retryable": retryable},
                )
            )
            if multi_action and (policy is None or not policy.continues_after_item_failure):
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

    sequence_result = build_sequence_result_record(
        sequence_id=sequence_id,
        items=item_rows,
        source_turn_index=int(iteration),
    )
    loop_memory.continuity.recent_action_sequence_result = sequence_result
    return sequence_result, last_step_result


def run_action_sequence_turn_if_present(
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
    patch_present: bool,
) -> ActionSequenceOutcome:
    """Execute ``effective_actions(action_plan)``; single path for all dispatch."""
    actions = effective_actions(action_plan)
    if not actions or action_plan.skip_execution:
        return ActionSequenceOutcome(handled=False, action_plan=action_plan)

    from .tool_batch_policy import tool_batch_policies_from_run_context

    policies = tool_batch_policies_from_run_context(run_ctx)
    multi = len(actions) > 1

    if not str(action_plan.idempotency_key).strip():
        key = (
            f"{request_id_prefix}:iter:{int(iteration)}:actions"
            if multi
            else f"{request_id_prefix}:iter:{int(iteration)}:dispatch:{actions[0].action_type}"
        )
        action_plan = replace(action_plan, idempotency_key=key, skip_execution=False)

    sequence_result, last_step = _execute_sequence_items(
        loop_memory=loop_memory,
        session_manager=session_manager,
        session_id=session_id,
        actions=actions,
        iteration=iteration,
        request_id_prefix=request_id_prefix,
        run_id=run_id,
        tool_batch_policies=policies,
        multi_action=multi,
    )

    if not multi:
        return _finalize_single_action_turn(
            loop_memory=loop_memory,
            action_plan=action_plan,
            actions=actions,
            iteration=iteration,
            last_step=last_step,
            sequence_result=sequence_result,
            tracer=tracer,
            turn_completion_observer=turn_completion_observer,
            patch_present=patch_present,
        )

    any_executed = any(
        str(row.get("execution_state")) == "executed"
        for row in sequence_result.get("items") or []
        if isinstance(row, dict)
    )
    exec_state = "executed" if any_executed else "refused"
    reason = None if any_executed else "action_sequence_no_executed_items"
    tracer.emit_execution_result(
        iteration=iteration,
        action_type="action_sequence",
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
        gate="action_sequence_executed",
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
        sequence_result=sequence_result,
    )
    capture_hydrate_after_sequence(
        loop_memory=loop_memory,
        action_plan=action_plan,
        sequence_result=sequence_result,
        iteration=iteration,
    )
    return ActionSequenceOutcome(
        handled=True,
        action_plan=action_plan,
        sequence_result=sequence_result,
    )


def _finalize_single_action_turn(
    *,
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
    actions: tuple[ActionPlanAction, ...],
    iteration: int,
    last_step: Any | None,
    sequence_result: dict[str, Any],
    tracer: Any,
    turn_completion_observer: Any | None,
    patch_present: bool,
) -> ActionSequenceOutcome:
    item = actions[0]
    if last_step is None:
        row = (sequence_result.get("items") or [{}])[0]
        if isinstance(row, Mapping) and row.get("execution_state") in {
            "retryable_error",
            "refused",
        }:
            reason = str((row.get("error") or {}).get("reason_code") or "step_execution_refused")
            retryable = bool((row.get("error") or {}).get("retryable"))
            tracer.emit_execution_result(
                iteration=iteration,
                action_type=item.action_type,
                execution_state="refused",
                reason_code=reason,
                retryable=retryable,
                refs_delta=None,
            )
            sync_state_patch_after_step_refusal(
                loop_memory=loop_memory,
                tracer=tracer,
                iteration=iteration,
                patch_present=patch_present,
                execution_reason_code=reason,
                action_plan=action_plan,
            )
            if not retryable:
                record_turn_continuity(
                    loop_memory=loop_memory,
                    action_plan=action_plan,
                    iteration=iteration,
                    execution_state="refused",
                    execution_reason_code=reason,
                )
                observe_turn_completed(
                    turn_completion_observer,
                    iteration,
                    action_plan=action_plan,
                    step_result=None,
                    loop_memory=loop_memory,
                    terminal_decision="refused",
                    sequence_result=sequence_result,
                )
                capture_hydrate_after_sequence(
                    loop_memory=loop_memory,
                    action_plan=action_plan,
                    sequence_result=sequence_result,
                    iteration=iteration,
                )
                return ActionSequenceOutcome(
                    handled=True,
                    action_plan=action_plan,
                    sequence_result=sequence_result,
                    terminal_class="failed",
                    terminal_reason_code=reason,
                )
            record_turn_continuity(
                loop_memory=loop_memory,
                action_plan=action_plan,
                iteration=iteration,
                execution_state="refused",
                execution_reason_code=reason,
            )
            observe_turn_completed(
                turn_completion_observer,
                iteration,
                action_plan=action_plan,
                step_result=None,
                loop_memory=loop_memory,
                sequence_result=sequence_result,
            )
            capture_hydrate_after_sequence(
                loop_memory=loop_memory,
                action_plan=action_plan,
                sequence_result=sequence_result,
                iteration=iteration,
            )
            return ActionSequenceOutcome(
                handled=True,
                action_plan=action_plan,
                sequence_result=sequence_result,
            )

    if last_step.execution_state != ExecutionState.EXECUTED:
        refusal = last_step.refusal
        reason = refusal.reason_code if refusal is not None else "step_execution_refused"
        retryable = refusal.retryable if refusal is not None else False
        tracer.emit_execution_result(
            iteration=iteration,
            action_type=item.action_type,
            execution_state="refused",
            reason_code=reason,
            retryable=retryable,
            refs_delta=None,
        )
        sync_state_patch_after_step_refusal(
            loop_memory=loop_memory,
            tracer=tracer,
            iteration=iteration,
            patch_present=patch_present,
            execution_reason_code=reason,
            action_plan=action_plan,
        )
        is_retryable = (
            refusal is not None
            and refusal.retryable
            and not refusal.blocked_by_budget
            and not refusal.blocked_by_invariant
        )
        if not is_retryable:
            record_turn_continuity(
                loop_memory=loop_memory,
                action_plan=action_plan,
                iteration=iteration,
                execution_state="refused",
                execution_reason_code=reason,
            )
            observe_turn_completed(
                turn_completion_observer,
                iteration,
                action_plan=action_plan,
                step_result=last_step,
                loop_memory=loop_memory,
                terminal_decision="refused",
                sequence_result=sequence_result,
            )
            capture_hydrate_after_sequence(
                loop_memory=loop_memory,
                action_plan=action_plan,
                sequence_result=sequence_result,
                iteration=iteration,
            )
            return ActionSequenceOutcome(
                handled=True,
                action_plan=action_plan,
                sequence_result=sequence_result,
                terminal_class="failed",
                terminal_reason_code=reason,
            )
        record_turn_continuity(
            loop_memory=loop_memory,
            action_plan=action_plan,
            iteration=iteration,
            execution_state="refused",
            execution_reason_code=reason,
        )
        observe_turn_completed(
            turn_completion_observer,
            iteration,
            action_plan=action_plan,
            step_result=last_step,
            loop_memory=loop_memory,
            sequence_result=sequence_result,
        )
        capture_hydrate_after_sequence(
            loop_memory=loop_memory,
            action_plan=action_plan,
            sequence_result=sequence_result,
            iteration=iteration,
        )
        return ActionSequenceOutcome(
            handled=True,
            action_plan=action_plan,
            sequence_result=sequence_result,
        )

    tracer.emit_execution_result(
        iteration=iteration,
        action_type=item.action_type,
        execution_state="executed",
        reason_code=None,
        retryable=None,
        refs_delta=loop_memory.continuity.latest_refs,
    )
    sync_state_patch_after_committed_gate(
        loop_memory=loop_memory,
        action_plan=action_plan,
        tracer=tracer,
        iteration=iteration,
        gate="step_executed",
    )
    record_turn_continuity(
        loop_memory=loop_memory,
        action_plan=action_plan,
        iteration=iteration,
        execution_state="executed",
        execution_reason_code=None,
    )
    observe_turn_completed(
        turn_completion_observer,
        iteration,
        action_plan=action_plan,
        step_result=last_step,
        loop_memory=loop_memory,
        sequence_result=sequence_result,
    )
    capture_hydrate_after_sequence(
        loop_memory=loop_memory,
        action_plan=action_plan,
        sequence_result=sequence_result,
        iteration=iteration,
    )
    return ActionSequenceOutcome(
        handled=True,
        action_plan=action_plan,
        sequence_result=sequence_result,
    )
