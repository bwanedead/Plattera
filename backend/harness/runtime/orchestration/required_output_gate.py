"""Mechanical required output-tier ref gate for domain-opt-in complete_run."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..memory import LoopMemoryState
from .action_sequence import effective_actions
from .contracts import ActionPlan

MAX_CONSECUTIVE_MISSING_OUTPUT_COMPLETE_ATTEMPTS = 3
MISSING_REQUIRED_OUTPUT_PREFIX = "missing_required_output_artifact:"


def closure_policy(run_ctx: dict[str, Any]) -> dict[str, Any] | None:
    raw = run_ctx.get("domain_closure_policy")
    return dict(raw) if isinstance(raw, dict) else None


def _policy_action_ids(policy: dict[str, Any], key: str) -> frozenset[str]:
    raw_values = policy.get(key) or ()
    if isinstance(raw_values, str):
        raw_values = (raw_values,)
    if not isinstance(raw_values, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(
        text
        for text in (str(value or "").strip() for value in raw_values)
        if text
    )


def _action_has_publish_role(*, policy: dict[str, Any], action_plan: ActionPlan) -> bool:
    publish_ids = _policy_action_ids(policy, "publish_action_ids")
    if not publish_ids:
        return False
    actions = effective_actions(action_plan)
    if not actions:
        action_id = str(action_plan.action_type or "").strip()
        return bool(action_id) and action_id in publish_ids
    return any(str(item.action_type or "").strip() in publish_ids for item in actions)


def latest_refs_contains_required_output(
    latest_refs: Mapping[str, Any],
    required_ref: str,
) -> bool:
    req = str(required_ref or "").strip()
    if not req:
        return False
    for key, value in latest_refs.items():
        if str(key).strip() == req:
            return True
        if str(value).strip() == req:
            return True
    return False


def required_output_ref_from_policy(run_ctx: dict[str, Any]) -> str | None:
    policy = closure_policy(run_ctx)
    if not policy:
        return None
    text = str(policy.get("required_output_ref_for_complete") or "").strip()
    return text or None


def required_output_artifact_enforcement_failure(
    *,
    run_ctx: dict[str, Any],
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
) -> tuple[str, str] | None:
    if not action_plan.complete_run:
        return None
    required = required_output_ref_from_policy(run_ctx)
    if not required:
        return None
    if latest_refs_contains_required_output(loop_memory.continuity.latest_refs, required):
        return None
    return (
        f"{MISSING_REQUIRED_OUTPUT_PREFIX}{required}",
        (
            f"complete_run requires output-tier ref {required!r} in latest_refs; "
            "working-tier refs are not sufficient"
        ),
    )


def is_missing_required_output_reason(reason_code: str) -> bool:
    return str(reason_code or "").startswith(MISSING_REQUIRED_OUTPUT_PREFIX)


def maybe_reset_missing_required_output_counter(
    *,
    run_ctx: dict[str, Any],
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan | None = None,
    executed_meaningful_dispatch: bool = False,
) -> None:
    """Reset consecutive missing-output counter on repair signals."""
    required = required_output_ref_from_policy(run_ctx)
    if not required:
        loop_memory.continuity.missing_required_output_complete_attempts = 0
        return
    if latest_refs_contains_required_output(loop_memory.continuity.latest_refs, required):
        loop_memory.continuity.missing_required_output_complete_attempts = 0
        return
    policy = closure_policy(run_ctx) or {}
    if action_plan is not None and _action_has_publish_role(policy=policy, action_plan=action_plan):
        loop_memory.continuity.missing_required_output_complete_attempts = 0
        return
    if executed_meaningful_dispatch and action_plan is not None and not action_plan.complete_run:
        loop_memory.continuity.missing_required_output_complete_attempts = 0


def missing_output_terminal_summary(*, required_ref: str, attempts: int) -> str:
    return (
        f"Required output artifact {required_ref!r} was not available in latest_refs after "
        f"{attempts} consecutive complete_run attempts. Terminating as blocked."
    )
