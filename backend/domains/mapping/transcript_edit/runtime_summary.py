from __future__ import annotations

from typing import Any

from .decision_ledger import (
    has_unresolved_target_scope_mapping_blocking_closure,
    unresolved_closure_requirements,
)


def derive_mission_runtime_summary(
    *,
    decision_ledger: dict[str, Any] | None,
) -> dict[str, Any]:
    ledger = decision_ledger if isinstance(decision_ledger, dict) else {}
    unresolved = unresolved_closure_requirements(ledger)
    unresolved_count = len([item for item in unresolved if isinstance(item, dict)])
    closure_blocking = has_unresolved_target_scope_mapping_blocking_closure(ledger)
    summary_present = isinstance(ledger.get("blocker_feedback_state"), dict)
    blocker_feedback_state = dict(ledger.get("blocker_feedback_state")) if summary_present else {}
    unresolved_pairs = (
        list(blocker_feedback_state.get("unresolved_blocker_ticket_pairs"))
        if isinstance(blocker_feedback_state.get("unresolved_blocker_ticket_pairs"), list)
        else []
    )
    pending_feedback_prompt_id = _pending_feedback_prompt_id_from_pairs(unresolved_pairs)
    waiting_feedback = (
        int(blocker_feedback_state.get("unresolved_blockers_waiting_feedback_count") or 0) > 0
        if summary_present
        else False
    )
    open_blocker_count = (
        int(blocker_feedback_state.get("unresolved_mapping_blocker_count") or 0)
        if summary_present
        else None
    )
    answered_unintegrated_count = (
        int(blocker_feedback_state.get("unresolved_blockers_with_feedback_count") or 0)
        if summary_present
        else None
    )

    if closure_blocking:
        verification_status = "closure_blocking"
    elif unresolved_count > 0:
        verification_status = "closure_partial"
    else:
        verification_status = "closure_clear"

    return {
        "summary_present": summary_present,
        "waiting_feedback": waiting_feedback,
        "pending_feedback_prompt_id": pending_feedback_prompt_id,
        "active_blocker_id": None,
        "open_blocker_count": open_blocker_count,
        "answered_unintegrated_count": answered_unintegrated_count,
        "unresolved_closure_count": int(unresolved_count),
        "closure_blocking": bool(closure_blocking),
        "verification_status": verification_status,
        "verification_kind": "transcript_edit_closure_ledger",
    }


def _pending_feedback_prompt_id_from_pairs(rows: list[Any]) -> str | None:
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("pair_state") or "").strip().lower() != "waiting_feedback":
            continue
        ticket_id = str(row.get("associated_ticket_id") or "").strip()
        if ticket_id:
            return ticket_id
    return None
