from __future__ import annotations

from typing import Any

from .decision_ledger import (
    has_unresolved_target_scope_mapping_blocking_closure,
    unresolved_closure_requirements,
)


def derive_mission_runtime_summary(
    *,
    decision_ledger: dict[str, Any] | None,
    blocker_registry: dict[str, Any] | None,
    waiting_projection: dict[str, Any] | None,
) -> dict[str, Any]:
    ledger = decision_ledger if isinstance(decision_ledger, dict) else {}
    registry = blocker_registry if isinstance(blocker_registry, dict) else {}
    projection = waiting_projection if isinstance(waiting_projection, dict) else {}

    unresolved = unresolved_closure_requirements(ledger)
    unresolved_count = len([item for item in unresolved if isinstance(item, dict)])
    closure_blocking = has_unresolved_target_scope_mapping_blocking_closure(ledger)

    counts = registry.get("counts") if isinstance(registry.get("counts"), dict) else {}
    open_blocker_count = counts.get("open") if isinstance(counts.get("open"), int) else None
    if open_blocker_count is None:
        rows = registry.get("rows")
        if isinstance(rows, list):
            open_blocker_count = sum(
                1
                for row in rows
                if isinstance(row, dict) and str(row.get("state") or "").strip().lower() == "open"
            )

    if closure_blocking:
        verification_status = "closure_blocking"
    elif unresolved_count > 0:
        verification_status = "closure_partial"
    else:
        verification_status = "closure_clear"

    return {
        "waiting_feedback": bool(projection.get("waiting_feedback")),
        "pending_feedback_prompt_id": str(projection.get("pending_feedback_prompt_id") or "").strip() or None,
        "open_blocker_count": int(open_blocker_count) if isinstance(open_blocker_count, int) else None,
        "unresolved_closure_count": int(unresolved_count),
        "closure_blocking": bool(closure_blocking),
        "verification_status": verification_status,
        "verification_kind": "transcript_edit_closure_ledger",
    }
