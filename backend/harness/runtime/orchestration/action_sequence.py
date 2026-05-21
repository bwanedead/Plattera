"""Canonical action-sequence contract: one native ``ActionPlan.actions`` shape.

Legacy ``action_type``, ``action_batch``, and top-level ``hydrate_next`` lower into
this representation at the parser edge only. Runtime execution reads ``actions``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .action_batch import (
    ActionBatchItem,
    ActionBatchValidationError,
    build_action_batch_result_record,
    build_batch_item_result_row,
    build_batch_results_snapshot,
    build_batch_tool_request_summary,
    build_batch_tool_result_summary,
    normalize_action_batch_items,
    project_batch_item_row,
    validate_action_batch_policy,
    validate_alias,
    validate_stored_action_batch_result,
)
from .contracts import ActionPlan, ActionPlanAction
from .tool_batch_policy import DomainActionBatchPolicy, ToolBatchPolicy

DEFAULT_SINGLE_ACTION_ALIAS = "action"

# Re-export for modules that imported from ``action_sequence``.
__all__ = [
    "ActionPlanAction",
    "ActionSequenceValidationError",
    "DEFAULT_SINGLE_ACTION_ALIAS",
    "effective_actions",
    "action_plan_with_canonical_actions",
]


class ActionSequenceValidationError(ValueError):
    """Raised when an ``actions`` payload fails mechanical validation."""


def effective_actions(action_plan: ActionPlan) -> tuple[ActionPlanAction, ...]:
    """Runtime source of truth: canonical ``actions`` or legacy lowering."""
    if action_plan.actions:
        return action_plan.actions
    if action_plan.action_batch:
        return tuple(
            ActionPlanAction(
                alias=item.alias,
                action_type=item.action_type,
                action_inputs=dict(item.action_inputs),
            )
            for item in action_plan.action_batch
        )
    if action_plan.action_type:
        return (
            ActionPlanAction(
                alias=DEFAULT_SINGLE_ACTION_ALIAS,
                action_type=action_plan.action_type,
                action_inputs=dict(action_plan.action_inputs),
                hydrate_next=tuple(action_plan.hydrate_next),
                hydrate_next_reason=action_plan.hydrate_next_reason,
            ),
        )
    return ()


def action_plan_with_canonical_actions(
    *,
    actions: tuple[ActionPlanAction, ...],
    idempotency_key: str = "",
    skip_execution: bool = False,
    wait_for_human: bool = False,
    complete_run: bool = False,
    hitl_request: dict[str, Any] | None = None,
    hitl_consumed_prompt_ids: tuple[str, ...] = (),
    user_message_consumed_ids: tuple[str, ...] = (),
    user_message_defers: tuple[dict[str, Any], ...] = (),
    rationale: str | None = None,
    state_patch: dict[str, Any] | None = None,
    continuity_journal_entry: dict[str, Any] | None = None,
    operator_progress_message: str | None = None,
    hydrate_next: tuple[str, ...] = (),
    hydrate_next_reason: str | None = None,
    pin_refs: tuple[str, ...] = (),
    unpin_refs: tuple[str, ...] = (),
) -> ActionPlan:
    """Build an ``ActionPlan`` whose runtime dispatch uses only ``actions``."""
    return ActionPlan(
        actions=actions,
        action_type=None,
        action_batch=(),
        action_inputs={},
        hydrate_next=hydrate_next,
        hydrate_next_reason=hydrate_next_reason,
        pin_refs=pin_refs,
        unpin_refs=unpin_refs,
        idempotency_key=idempotency_key,
        skip_execution=skip_execution,
        wait_for_human=wait_for_human,
        complete_run=complete_run,
        hitl_request=hitl_request,
        hitl_consumed_prompt_ids=hitl_consumed_prompt_ids,
        user_message_consumed_ids=user_message_consumed_ids,
        user_message_defers=user_message_defers,
        rationale=rationale,
        state_patch=state_patch,
        continuity_journal_entry=continuity_journal_entry,
        operator_progress_message=operator_progress_message,
    )


def normalize_native_action_items(raw: Any) -> tuple[ActionPlanAction, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ActionSequenceValidationError("actions must be a JSON array")
    if len(raw) < 1:
        raise ActionSequenceValidationError("actions must be non-empty when present")
    batch_rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(raw):
        if not isinstance(row, Mapping):
            raise ActionSequenceValidationError(f"actions[{index}] must be an object")
        batch_rows.append(row)
    try:
        batch_items = normalize_action_batch_items(batch_rows)
    except ActionBatchValidationError as exc:
        raise ActionSequenceValidationError(str(exc)) from exc
    from .hydrate_next import (
        HydrateNextValidationError,
        normalize_hydrate_next,
        normalize_hydrate_next_reason,
    )

    items: list[ActionPlanAction] = []
    for index, (batch_item, row) in enumerate(zip(batch_items, raw, strict=True)):
        hydrate_raw = row.get("hydrate_next")
        hydrate_reason_raw = row.get("hydrate_next_reason")
        try:
            hydrate_refs, hydrate_errors = normalize_hydrate_next(hydrate_raw)
        except HydrateNextValidationError as exc:
            raise ActionSequenceValidationError(
                f"actions[{index}].hydrate_next failed validation: {exc}"
            ) from exc
        if hydrate_errors:
            raise ActionSequenceValidationError(
                f"actions[{index}].hydrate_next entries must be non-empty strings"
            )
        try:
            hydrate_reason = normalize_hydrate_next_reason(hydrate_reason_raw)
        except HydrateNextValidationError as exc:
            raise ActionSequenceValidationError(
                f"actions[{index}].hydrate_next_reason failed validation: {exc}"
            ) from exc
        items.append(
            ActionPlanAction(
                alias=batch_item.alias,
                action_type=batch_item.action_type,
                action_inputs=dict(batch_item.action_inputs),
                hydrate_next=tuple(hydrate_refs),
                hydrate_next_reason=hydrate_reason,
            )
        )
    return tuple(items)


def validate_action_sequence_policy(
    actions: tuple[ActionPlanAction, ...],
    *,
    available_tool_ids: tuple[str, ...],
    tool_batch_policies: Mapping[str, ToolBatchPolicy],
    domain_batch_policy: DomainActionBatchPolicy | None,
) -> None:
    if not actions:
        return
    if len(actions) == 1:
        item = actions[0]
        if available_tool_ids and item.action_type not in available_tool_ids:
            raise ActionSequenceValidationError(f"unknown action_type: {item.action_type}")
        return
    batch_items = tuple(
        ActionBatchItem(alias=a.alias, action_type=a.action_type, action_inputs=dict(a.action_inputs))
        for a in actions
    )
    try:
        validate_action_batch_policy(
            batch_items,
            available_tool_ids=available_tool_ids,
            tool_batch_policies=tool_batch_policies,
            domain_batch_policy=domain_batch_policy,
        )
    except ActionBatchValidationError as exc:
        raise ActionSequenceValidationError(str(exc)) from exc


def build_sequence_result_record(
    *,
    sequence_id: str,
    items: list[dict[str, Any]],
    source_turn_index: int,
) -> dict[str, Any]:
    return build_action_batch_result_record(
        batch_id=sequence_id,
        items=items,
        source_turn_index=source_turn_index,
    )


def build_sequence_results_snapshot(
    sequence_result: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    return build_batch_results_snapshot(sequence_result)


def validate_stored_action_sequence_result(row: Any) -> dict[str, Any] | None:
    return validate_stored_action_batch_result(row)


def project_sequence_item_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return project_batch_item_row(row)


def build_sequence_tool_request_summary(action_plan: ActionPlan) -> dict[str, Any]:
    actions = effective_actions(action_plan)
    return {
        "actions": [
            {
                "alias": item.alias,
                "action_type": item.action_type,
                "action_inputs": dict(item.action_inputs),
                "hydrate_next": list(item.hydrate_next),
                "hydrate_next_reason": item.hydrate_next_reason,
            }
            for item in actions
        ],
        "idempotency_key": str(action_plan.idempotency_key or ""),
        "skip_execution": bool(action_plan.skip_execution),
        "wait_for_human": bool(action_plan.wait_for_human),
        "complete_run": bool(action_plan.complete_run),
        "rationale": action_plan.rationale,
        "operator_progress_message": action_plan.operator_progress_message,
        "pin_refs": list(action_plan.pin_refs),
        "unpin_refs": list(action_plan.unpin_refs),
    }


def build_sequence_tool_result_summary(sequence_result: Mapping[str, Any] | None) -> dict[str, Any] | None:
    return build_batch_tool_result_summary(sequence_result)


def lower_legacy_action_batch(raw: Any) -> tuple[ActionPlanAction, ...]:
    try:
        batch = normalize_action_batch_items(raw)
    except ActionBatchValidationError as exc:
        raise ActionSequenceValidationError(str(exc)) from exc
    return tuple(
        ActionPlanAction(
            alias=item.alias,
            action_type=item.action_type,
            action_inputs=dict(item.action_inputs),
        )
        for item in batch
    )
