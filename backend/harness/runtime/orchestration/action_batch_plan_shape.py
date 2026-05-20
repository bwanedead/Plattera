"""Parser helpers for ``action_batch`` — kept out of ``action_plan_parser.py`` hotspot."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .action_batch import (
    ActionBatchValidationError,
    normalize_action_batch_items,
    validate_action_batch_policy,
)
from .action_batch import ActionBatchItem
from .tool_batch_policy import DomainActionBatchPolicy, ToolBatchPolicy


def parse_action_batch_fields(
    payload: Mapping[str, Any],
    *,
    action_type: str | None,
    action_inputs: Mapping[str, Any],
    available_tool_ids: tuple[str, ...],
    tool_batch_policies: Mapping[str, ToolBatchPolicy],
    domain_batch_policy: DomainActionBatchPolicy | None,
) -> tuple[ActionBatchItem, ...]:
    raw = payload.get("action_batch")
    if raw is None:
        return ()
    if action_type:
        raise ValueError("action_type and action_batch are mutually exclusive")
    if action_inputs:
        raise ValueError("action_inputs must be empty when action_batch is present")
    try:
        items = normalize_action_batch_items(raw)
    except ActionBatchValidationError as exc:
        raise ValueError(str(exc)) from exc
    try:
        validate_action_batch_policy(
            items,
            available_tool_ids=available_tool_ids,
            tool_batch_policies=tool_batch_policies,
            domain_batch_policy=domain_batch_policy,
        )
    except ActionBatchValidationError as exc:
        raise ValueError(str(exc)) from exc
    return items
