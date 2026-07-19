"""Same-turn run completion when a domain completion anchor is mechanically satisfied."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .action_sequence import effective_actions
from .completion_anchor import evaluate_completion_anchor, parse_completion_anchor_policy
from .contracts import ActionPlan

_SUCCESS_EXECUTION_STATES = frozenset({"executed", "deduped"})


@dataclass(frozen=True)
class SameTurnCompletionDecision:
    terminal_class: str
    terminal_reason_code: str
    completion_anchor: dict[str, Any]


def is_success_like_execution_state(state: Any) -> bool:
    return str(getattr(state, "value", state) or "").strip().lower() in _SUCCESS_EXECUTION_STATES


def _newest_step_record(
    step_result_records: list[Any] | tuple[Any, ...] | None,
) -> Mapping[str, Any] | None:
    if not step_result_records:
        return None
    row = step_result_records[-1]
    return row if isinstance(row, Mapping) else None


def evaluate_same_turn_completion_anchor(
    *,
    closure_policy: Mapping[str, Any] | None,
    action_plan: ActionPlan,
    latest_refs: Mapping[str, Any] | None,
    step_result_records: list[Any] | tuple[Any, ...] | None,
) -> SameTurnCompletionDecision | None:
    """Return a terminal decision when the just-completed turn satisfies the anchor."""
    policy = parse_completion_anchor_policy(closure_policy)
    if policy is None or not policy.terminal_on_satisfied_anchor:
        return None

    actions = effective_actions(action_plan)
    if len(actions) != 1:
        return None

    sole_action_type = str(actions[0].action_type or "").strip()
    if sole_action_type not in policy.publish_action_ids:
        return None

    current_record = _newest_step_record(step_result_records)
    if current_record is None:
        return None

    current_action_type = str(current_record.get("action_type") or "").strip()
    if current_action_type != sole_action_type:
        return None

    execution_state = str(current_record.get("execution_state") or "").strip().lower()
    if execution_state not in _SUCCESS_EXECUTION_STATES:
        return None

    anchor = evaluate_completion_anchor(
        closure_policy=closure_policy,
        latest_refs=latest_refs,
        step_result_records=(current_record,),
    )
    if not isinstance(anchor, Mapping) or not anchor.get("satisfied"):
        return None

    return SameTurnCompletionDecision(
        terminal_class="completed",
        terminal_reason_code="completion_anchor_satisfied",
        completion_anchor=dict(anchor),
    )
