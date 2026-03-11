from __future__ import annotations

from typing import Any

def _post_feedback_ticket_seam(*, human_resolution_tickets: list[dict[str, Any]]) -> tuple[str | None, dict[str, Any] | None]:
    if not human_resolution_tickets:
        return None, None
    rows = [dict(row) for row in human_resolution_tickets if isinstance(row, dict)]
    if not rows:
        return None, None
    rows.sort(key=lambda row: int(row.get("updated_at") or row.get("created_at") or 0), reverse=True)
    preferred_order = {
        "integration_attempted_failed": 0,
        "answered_unintegrated": 1,
        "integrated": 2,
        "superseded": 3,
        "stale": 4,
        "issued_waiting_feedback": 5,
    }
    rows.sort(key=lambda row: preferred_order.get(str(row.get("lifecycle_state") or "").strip().lower(), 99))
    top = rows[0]
    state = str(top.get("lifecycle_state") or "").strip().lower() or None
    snapshot = {
        "ticket_id": str(top.get("ticket_id") or "").strip() or None,
        "ticket_state": state,
        "ticket_decision_key": str(top.get("decision_key") or "").strip().lower() or None,
        "ticket_strength": str(top.get("strength") or "").strip().lower() or None,
        "answered_at": top.get("answered_at"),
        "integrated_at": top.get("integrated_at"),
        "updated_at": top.get("updated_at"),
    }
    return state, snapshot

def _hitl_feedback_state_summary(
    *,
    feedback_received_count: int,
    feedback_consumed_count: int,
    feedback_stale_count: int,
    feedback_superseded_count: int,
    pending_feedback_prompt_ids: list[str],
    unresolved_mapping_blocking_items: list[dict[str, Any]],
) -> dict[str, Any]:
    provided = int(feedback_received_count) > 0
    consumed = int(feedback_consumed_count) > 0
    pending = len([str(v) for v in pending_feedback_prompt_ids if str(v).strip()]) > 0
    integrated_status = "unknown"
    if consumed and len(unresolved_mapping_blocking_items) == 0:
        integrated_status = "consumed_and_blocker_cleared"
    elif consumed and len(unresolved_mapping_blocking_items) > 0:
        integrated_status = "consumed_but_blockers_remain"
    elif provided and not consumed:
        integrated_status = "provided_not_consumed"
    elif pending:
        integrated_status = "awaiting_feedback"
    return {
        "hitl_feedback_provided": bool(provided),
        "hitl_feedback_consumed": bool(consumed),
        "hitl_feedback_pending": bool(pending),
        "consumed_definition": (
            "Consumed means the runtime matched a pending prompt response, normalized it, "
            "accepted it into loop state, and used it in focus-cycle decision processing."
        ),
        "integration_status": integrated_status,
        "feedback_received_count": int(feedback_received_count),
        "feedback_consumed_count": int(feedback_consumed_count),
        "feedback_stale_count": int(feedback_stale_count),
        "feedback_superseded_count": int(feedback_superseded_count),
    }
