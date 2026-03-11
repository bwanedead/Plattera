from __future__ import annotations

from typing import Any

from .blocker_registry import select_primary_blocker, select_primary_emergent_blocker_with_reason
from .decision_ledger import is_unresolved_target_scope_mapping_blocking_decision
from .feedback_lifecycle import (
    active_ticket_snapshot,
    feedback_payload_from_registry_row,
    feedback_payload_from_ticket,
    latest_human_resolution_ticket,
    normalize_feedback_selected_value,
    stable_feedback_confirmation_count,
    ticket_lifecycle_snapshot_for_key,
)
from .focus_runtime import (
    baseline_evidence_attempts,
    baseline_residual_from_unresolved,
    conflict_map_from_ledger,
    decision_key_for_finding,
    findings_for_focus_key,
    next_recommended_action_text,
    recent_image_evidence_attempt_count,
    registry_row_for_decision_key,
    select_focus_decision_key,
)
from .resolver_gates import (
    accept_apply_edit_plan,
    accept_mark_blocked,
    accept_mark_resolved_no_edit,
    extract_validation_error_class,
    resolver_result_category,
)


def _select_focus_target(
    *,
    decision_ledger: dict[str, Any],
    fallback_focus: dict[str, Any] | None,
    focus_feedback: dict[str, Any] | None,
    blocker_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    emergent_selection = (
        select_primary_emergent_blocker_with_reason(blocker_registry)
        if isinstance(blocker_registry, dict)
        else {"row": None, "reason_code": "no_registry"}
    )
    emergent_row = dict(emergent_selection.get("row")) if isinstance(emergent_selection.get("row"), dict) else {}
    if emergent_row:
        emergent_state = str(emergent_row.get("state") or "").strip().lower()
        if emergent_state in {"answered_unintegrated", "waiting_feedback", "open"}:
            emergent_decision_key = (
                str(emergent_row.get("legacy_decision_key") or "").strip().lower()
                or str(emergent_row.get("decision_key") or "").strip().lower()
            )
            if not emergent_decision_key:
                emergent_decision_key = str((fallback_focus or {}).get("decision_key") or "").strip().lower()
            if emergent_decision_key:
                return {
                    "decision_key": emergent_decision_key,
                    "focus_source": "emergent_blocker",
                    "focus_reason_code": str(emergent_selection.get("reason_code") or "emergent_selected"),
                    "active_blocker": emergent_row,
                }

    primary = select_primary_blocker(blocker_registry if isinstance(blocker_registry, dict) else None) or {}
    primary_key = str(primary.get("decision_key") or "").strip().lower()
    primary_state = str(primary.get("state") or "").strip().lower()
    if (
        primary_key
        and primary_state in {"answered_unintegrated", "waiting_feedback"}
        and is_unresolved_target_scope_mapping_blocking_decision(decision_ledger, primary_key)
    ):
        return {
            "decision_key": primary_key,
            "focus_source": "legacy_fallback",
            "focus_reason_code": "legacy_priority_feedback_state",
            "active_blocker": None,
        }
    if isinstance(focus_feedback, dict):
        feedback_key = str(focus_feedback.get("decision_key") or "").strip().lower()
        if feedback_key and is_unresolved_target_scope_mapping_blocking_decision(decision_ledger, feedback_key):
            return {
                "decision_key": feedback_key,
                "focus_source": "legacy_fallback",
                "focus_reason_code": "legacy_feedback_key",
                "active_blocker": None,
            }
    key = str((fallback_focus or {}).get("decision_key") or "").strip().lower()
    if key:
        return {
            "decision_key": key,
            "focus_source": "legacy_fallback",
            "focus_reason_code": "legacy_fallback_focus",
            "active_blocker": None,
        }
    return {
        "decision_key": "",
        "focus_source": "legacy_fallback",
        "focus_reason_code": "legacy_focus_missing",
        "active_blocker": None,
    }


def _select_focus_decision_key(
    *,
    decision_ledger: dict[str, Any],
    fallback_focus: dict[str, Any] | None,
    focus_feedback: dict[str, Any] | None,
    blocker_registry: dict[str, Any] | None = None,
) -> str:
    return select_focus_decision_key(
        decision_ledger=decision_ledger,
        fallback_focus=fallback_focus,
        focus_feedback=focus_feedback,
        blocker_registry=blocker_registry,
        select_focus_target_fn=_select_focus_target,
    )


def _normalize_feedback_selected_value(*, decision_key: str, selected_value: str) -> str:
    return normalize_feedback_selected_value(decision_key=decision_key, selected_value=selected_value)


def _stable_feedback_confirmation_count(
    *,
    hitl_lifecycle_log: list[dict[str, Any]],
    decision_key: str | None,
    selected_value: str | None,
) -> int:
    return stable_feedback_confirmation_count(
        hitl_lifecycle_log=hitl_lifecycle_log,
        decision_key=decision_key,
        selected_value=selected_value,
    )


def _latest_human_resolution_ticket(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str | None,
    lifecycle_states: set[str],
) -> dict[str, Any] | None:
    return latest_human_resolution_ticket(
        decision_ledger=decision_ledger,
        decision_key=decision_key,
        lifecycle_states=lifecycle_states,
    )


def _feedback_payload_from_ticket(
    *,
    answered_ticket: dict[str, Any] | None,
    decision_key: str | None,
) -> dict[str, Any] | None:
    return feedback_payload_from_ticket(answered_ticket=answered_ticket, decision_key=decision_key)


def _feedback_payload_from_registry_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return feedback_payload_from_registry_row(row)


def _extract_validation_error_class(reason_suffix: str) -> str | None:
    return extract_validation_error_class(reason_suffix)


def _ticket_lifecycle_snapshot_for_key(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str | None,
) -> list[dict[str, Any]]:
    return ticket_lifecycle_snapshot_for_key(
        decision_ledger=decision_ledger,
        decision_key=decision_key,
    )


def _active_ticket_snapshot(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str | None,
) -> dict[str, Any] | None:
    return active_ticket_snapshot(
        decision_ledger=decision_ledger,
        decision_key=decision_key,
    )


def _resolver_result_category(*, move: str, reason: str) -> str:
    return resolver_result_category(move=move, reason=reason)


def _accept_mark_resolved_no_edit(*, decision_ledger: dict[str, Any], decision_key: str) -> bool:
    return accept_mark_resolved_no_edit(decision_ledger=decision_ledger, decision_key=decision_key)


def _accept_mark_blocked(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str,
    resolver_reason: str,
    hitl_enabled: bool,
) -> bool:
    return accept_mark_blocked(
        decision_ledger=decision_ledger,
        decision_key=decision_key,
        resolver_reason=resolver_reason,
        hitl_enabled=hitl_enabled,
    )


def _recent_image_evidence_attempt_count(
    *,
    continuity_log: list[dict[str, Any]],
    decision_key: str | None,
    window: int = 8,
) -> int:
    return recent_image_evidence_attempt_count(
        continuity_log=continuity_log,
        decision_key=decision_key,
        window=window,
    )


def _accept_apply_edit_plan(
    *,
    resolver_decision_key: str,
    focus_key: str,
    plan_payload: dict[str, Any],
) -> bool:
    return accept_apply_edit_plan(
        resolver_decision_key=resolver_decision_key,
        focus_key=focus_key,
        plan_payload=plan_payload,
    )


def _findings_for_focus_key(*, top_findings: list[dict[str, Any]], focus_key: str) -> list[dict[str, Any]]:
    return findings_for_focus_key(top_findings=top_findings, focus_key=focus_key)


def _decision_key_for_finding(finding: dict[str, Any]) -> str:
    return decision_key_for_finding(finding)


def _conflict_map_from_ledger(ledger: dict[str, Any] | None) -> list[dict[str, Any]]:
    return conflict_map_from_ledger(ledger)


def _baseline_residual_from_unresolved(item: dict[str, Any]) -> dict[str, Any]:
    return baseline_residual_from_unresolved(item)


def _baseline_evidence_attempts(
    *,
    span_context: list[dict[str, Any]],
    image_verification: dict[str, Any],
) -> list[dict[str, Any]]:
    return baseline_evidence_attempts(
        span_context=span_context,
        image_verification=image_verification,
    )


def _next_recommended_action_text(residual_blockers: list[dict[str, Any]]) -> str:
    return next_recommended_action_text(residual_blockers)


def _registry_row_for_decision_key(
    *,
    registry: dict[str, Any] | None,
    decision_key: str | None,
) -> dict[str, Any] | None:
    return registry_row_for_decision_key(
        registry=registry,
        decision_key=decision_key,
    )

__all__ = [
    "_select_focus_target",
    "_select_focus_decision_key",
    "_normalize_feedback_selected_value",
    "_stable_feedback_confirmation_count",
    "_latest_human_resolution_ticket",
    "_feedback_payload_from_ticket",
    "_feedback_payload_from_registry_row",
    "_extract_validation_error_class",
    "_ticket_lifecycle_snapshot_for_key",
    "_active_ticket_snapshot",
    "_resolver_result_category",
    "_accept_mark_resolved_no_edit",
    "_accept_mark_blocked",
    "_recent_image_evidence_attempt_count",
    "_accept_apply_edit_plan",
    "_findings_for_focus_key",
    "_decision_key_for_finding",
    "_conflict_map_from_ledger",
    "_baseline_residual_from_unresolved",
    "_baseline_evidence_attempts",
    "_next_recommended_action_text",
    "_registry_row_for_decision_key",
]
