"""Parser-edge canonicalization for native ``actions`` and legacy spellings."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .action_batch import ActionBatchItem, ActionBatchValidationError, validate_action_batch_policy
from .action_sequence import (
    ActionPlanAction,
    ActionSequenceValidationError,
    DEFAULT_SINGLE_ACTION_ALIAS,
    lower_legacy_action_batch,
    normalize_native_action_items,
    validate_action_sequence_policy,
)
from .hydrate_next import HydrateNextValidationError, normalize_hydrate_next, normalize_hydrate_next_reason
from .tool_batch_policy import DomainActionBatchPolicy, ToolBatchPolicy


@dataclass(frozen=True)
class CanonicalActionParse:
    actions: tuple[ActionPlanAction, ...]
    legacy_top_hydrate_next: tuple[str, ...] = ()
    legacy_top_hydrate_next_reason: str | None = None


def canonicalize_actions_from_payload(
    payload: Mapping[str, Any],
    *,
    available_tool_ids: tuple[str, ...],
    tool_batch_policies: Mapping[str, ToolBatchPolicy],
    domain_batch_policy: DomainActionBatchPolicy | None,
) -> CanonicalActionParse:
    """Parse native ``actions`` or lower legacy forms; reject mixed native/legacy spellings."""
    has_actions = payload.get("actions") is not None
    action_type = str(payload.get("action_type") or "").strip() or None
    has_action_inputs = bool(payload.get("action_inputs"))
    has_action_batch = payload.get("action_batch") is not None
    has_top_hydrate = payload.get("hydrate_next") is not None
    has_top_hydrate_reason = payload.get("hydrate_next_reason") is not None
    legacy_top_hydrate: tuple[str, ...] = ()
    legacy_top_hydrate_reason: str | None = None

    if has_actions:
        if action_type or has_action_inputs or has_action_batch or has_top_hydrate or has_top_hydrate_reason:
            raise ValueError(
                "actions cannot be mixed with action_type, action_inputs, action_batch, "
                "or top-level hydrate_next"
            )
        try:
            items = normalize_native_action_items(payload.get("actions"))
        except ActionSequenceValidationError as exc:
            raise ValueError(str(exc)) from exc
    elif has_action_batch:
        if action_type or has_action_inputs:
            raise ValueError(
                "action_batch cannot be mixed with action_type or action_inputs"
            )
        try:
            items = lower_legacy_action_batch(payload.get("action_batch"))
        except ActionSequenceValidationError as exc:
            raise ValueError(str(exc)) from exc
        if has_top_hydrate or has_top_hydrate_reason:
            try:
                hydrate_refs, hydrate_errors = normalize_hydrate_next(payload.get("hydrate_next"))
            except HydrateNextValidationError as exc:
                raise ValueError(f"hydrate_next failed canonical validation: {exc}") from exc
            if hydrate_errors:
                raise ValueError("hydrate_next entries must be non-empty strings")
            try:
                legacy_top_hydrate_reason = normalize_hydrate_next_reason(
                    payload.get("hydrate_next_reason")
                )
            except HydrateNextValidationError as exc:
                raise ValueError(f"hydrate_next_reason failed canonical validation: {exc}") from exc
            legacy_top_hydrate = tuple(hydrate_refs)
    elif action_type:
        if has_action_batch:
            raise ValueError("action_type and action_batch are mutually exclusive")
        action_inputs = payload.get("action_inputs")
        if action_inputs is None:
            inputs: dict[str, Any] = {}
        elif isinstance(action_inputs, Mapping):
            inputs = dict(action_inputs)
        else:
            raise ValueError("action_inputs must be an object")
        try:
            hydrate_refs, hydrate_errors = normalize_hydrate_next(payload.get("hydrate_next"))
        except HydrateNextValidationError as exc:
            raise ValueError(f"hydrate_next failed canonical validation: {exc}") from exc
        if hydrate_errors:
            raise ValueError("hydrate_next entries must be non-empty strings")
        try:
            hydrate_reason = normalize_hydrate_next_reason(payload.get("hydrate_next_reason"))
        except HydrateNextValidationError as exc:
            raise ValueError(f"hydrate_next_reason failed canonical validation: {exc}") from exc
        items = (
            ActionPlanAction(
                alias=DEFAULT_SINGLE_ACTION_ALIAS,
                action_type=action_type,
                action_inputs=inputs,
                hydrate_next=tuple(hydrate_refs),
                hydrate_next_reason=hydrate_reason,
            ),
        )
    else:
        items = ()

    if has_action_batch and items:
        batch_items = tuple(
            ActionBatchItem(alias=a.alias, action_type=a.action_type, action_inputs=dict(a.action_inputs))
            for a in items
        )
        try:
            validate_action_batch_policy(
                batch_items,
                available_tool_ids=available_tool_ids,
                tool_batch_policies=tool_batch_policies,
                domain_batch_policy=domain_batch_policy,
            )
        except ActionBatchValidationError as exc:
            raise ValueError(str(exc)) from exc
    elif items:
        try:
            validate_action_sequence_policy(
                items,
                available_tool_ids=available_tool_ids,
                tool_batch_policies=tool_batch_policies,
                domain_batch_policy=domain_batch_policy,
            )
        except ActionSequenceValidationError as exc:
            raise ValueError(str(exc)) from exc
    return CanonicalActionParse(
        actions=items,
        legacy_top_hydrate_next=legacy_top_hydrate,
        legacy_top_hydrate_next_reason=legacy_top_hydrate_reason,
    )
