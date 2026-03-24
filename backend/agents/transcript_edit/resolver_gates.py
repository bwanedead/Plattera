from __future__ import annotations

from typing import Any

from .decision_ledger import (
    is_unresolved_target_scope_mapping_blocking_decision,
    unresolved_mapping_blocking_requirements,
)


def extract_validation_error_class(reason_suffix: str) -> str | None:
    text = str(reason_suffix or "").strip()
    if not text:
        return None
    parts = [segment.strip() for segment in text.split(":") if segment.strip()]
    for segment in parts:
        if segment.endswith("Error") or segment.endswith("Exception"):
            return segment
    return parts[0] if parts else None


def resolver_result_category(*, move: str, reason: str) -> str:
    move_value = str(move or "").strip().lower()
    reason_value = str(reason or "").strip().lower()
    if reason_value.startswith("resolver_move_invalid:resolver_invalid"):
        if "invalid_move" in reason_value:
            return "invalid_move"
        return "invalid_schema"
    if reason_value.startswith("resolver_move_invalid:"):
        return "invalid_schema"
    if move_value:
        return "valid"
    return "exhausted"


def accept_mark_resolved_no_edit(*, decision_ledger: dict[str, Any], decision_key: str) -> bool:
    return not is_unresolved_target_scope_mapping_blocking_decision(decision_ledger, decision_key)


def accept_mark_blocked(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str,
    resolver_reason: str,
    hitl_enabled: bool,
    policy_signals: dict[str, Any] | None = None,
) -> bool:
    reason = str(resolver_reason or "").strip().lower()
    signals = policy_signals if isinstance(policy_signals, dict) else {}
    if reason.startswith(
        (
            "resolver_move_invalid:",
            "resolver_plan_invalid:",
            "resolver_move_invalid",
            "resolver_plan_invalid",
        )
    ):
        return True
    if reason.startswith("blocked_no_safe_integration_after_feedback"):
        return True
    unresolved = unresolved_mapping_blocking_requirements(decision_ledger)
    focus_item = next(
        (
            item
            for item in unresolved
            if isinstance(item, dict) and str(item.get("key") or "").strip().lower() == decision_key
        ),
        None,
    )
    requirement = focus_item.get("closure_requirement") if isinstance(focus_item, dict) else {}
    block_reason = str(requirement.get("block_reason") or "").strip().lower() if isinstance(requirement, dict) else ""
    if block_reason == "dependency":
        return True
    if "repeat_budget" in reason or "evidence_budget" in reason:
        return True
    if not hitl_enabled and is_unresolved_target_scope_mapping_blocking_decision(decision_ledger, decision_key):
        return True
    if bool(signals.get("repeat_without_signal")) and "evidence" in reason:
        return True
    return False


def accept_request_human_feedback(*, policy_signals: dict[str, Any] | None = None, hitl_enabled: bool) -> bool:
    signals = policy_signals if isinstance(policy_signals, dict) else {}
    if not hitl_enabled:
        return False
    if str(signals.get("understanding_strength") or "").strip().lower() == "weak":
        return False
    if not (bool(signals.get("has_fresh_signal")) or bool(signals.get("cached_context_present"))):
        return False
    return True


def accept_apply_edit_plan(
    *,
    resolver_decision_key: str,
    focus_key: str,
    plan_payload: dict[str, Any],
    policy_signals: dict[str, Any] | None = None,
) -> bool:
    signals = policy_signals if isinstance(policy_signals, dict) else {}
    if resolver_decision_key != focus_key:
        return False
    if not isinstance(plan_payload, dict):
        return False
    ops = plan_payload.get("ops")
    if not isinstance(ops, list) or len(ops) <= 0:
        return False
    if str(signals.get("understanding_strength") or "").strip().lower() == "weak":
        return False
    if not (bool(signals.get("has_fresh_signal")) or bool(signals.get("cached_context_present"))):
        return False
    return True
