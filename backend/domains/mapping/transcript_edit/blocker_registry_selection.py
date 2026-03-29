from __future__ import annotations

from typing import Any

from .blocker_registry_state import (
    _emergent_row_priority_key,
    _ensure_registry_shape,
    _is_legacy_projection_emergent_row,
)

def select_primary_blocker(registry: dict[str, Any] | None) -> dict[str, Any] | None:
    selected = select_primary_blocker_with_reason(registry)
    row = selected.get("row") if isinstance(selected, dict) else None
    return dict(row) if isinstance(row, dict) else None

def select_primary_emergent_blocker(registry: dict[str, Any] | None) -> dict[str, Any] | None:
    selected = select_primary_emergent_blocker_with_reason(registry)
    row = selected.get("row") if isinstance(selected, dict) else None
    return dict(row) if isinstance(row, dict) else None

def select_primary_emergent_blocker_with_reason(registry: dict[str, Any] | None) -> dict[str, Any]:
    working = _ensure_registry_shape(registry=registry, run_id=None, session_id=None, source_transcript_ref=None)
    emergent = working.get("emergent") if isinstance(working.get("emergent"), dict) else {}
    rows = [row for row in list(emergent.get("rows") or []) if isinstance(row, dict)]
    candidates = [
        row
        for row in rows
        if str(row.get("state") or "").strip().lower() in {"answered_unintegrated", "waiting_feedback", "open"}
        and not _is_legacy_projection_emergent_row(row)
    ]
    if not candidates:
        return {"row": None, "reason_code": "no_active_emergent_blockers"}
    candidates.sort(key=_emergent_row_priority_key)
    selected = dict(candidates[0])
    state = str(selected.get("state") or "").strip().lower()
    blocking_class = str(selected.get("blocking_class") or "").strip().lower()
    reason = f"emergent_priority_{state}_{blocking_class}".strip("_")
    return {"row": selected, "reason_code": reason}

def select_primary_blocker_with_reason(registry: dict[str, Any] | None) -> dict[str, Any]:
    working = _ensure_registry_shape(registry=registry, run_id=None, session_id=None, source_transcript_ref=None)
    candidates = [row for row in list(working.get("rows") or []) if isinstance(row, dict) and _is_operationally_active(row)]
    if not candidates:
        return {"row": None, "reason_code": "no_active_blockers"}
    candidates.sort(key=_row_priority_key)
    selected = dict(candidates[0])
    return {
        "row": selected,
        "reason_code": _selection_reason_code(selected),
    }

def _is_operationally_active(row: dict[str, Any]) -> bool:
    return str(row.get("state") or "").strip().lower() not in {"resolved", "superseded"}

def _row_priority_key(row: dict[str, Any]) -> tuple[int, int, int, int]:
    state = str(row.get("state") or "").strip().lower()
    scope = str(row.get("scope_status") or "").strip().lower()
    mapping_blocking = bool(row.get("mapping_blocking"))
    state_rank = 5
    if state == "answered_unintegrated":
        state_rank = 0
    elif state == "open" and mapping_blocking and scope == "in_target":
        state_rank = 1
    elif state == "open" and mapping_blocking and scope == "unknown":
        state_rank = 2
    elif state == "waiting_feedback":
        state_rank = 3
    elif state == "open":
        state_rank = 4
    scope_rank = {"in_target": 0, "unknown": 1, "outside_target": 2}.get(scope, 3)
    blocking_rank = 0 if mapping_blocking else 1
    updated_rank = -int(row.get("updated_at") or 0)
    return (state_rank, scope_rank, blocking_rank, updated_rank)

def _selection_reason_code(row: dict[str, Any]) -> str:
    state = str(row.get("state") or "").strip().lower()
    scope = str(row.get("scope_status") or "").strip().lower()
    mapping_blocking = bool(row.get("mapping_blocking"))
    if state == "answered_unintegrated":
        return "priority_answered_unintegrated"
    if state == "open" and mapping_blocking and scope == "in_target":
        return "priority_open_target_scope_mapping_blocker"
    if state == "open" and mapping_blocking and scope == "unknown":
        return "priority_open_unknown_scope_mapping_blocker"
    if state == "waiting_feedback":
        return "priority_waiting_feedback"
    if state == "open" and (not mapping_blocking or scope == "outside_target"):
        return "priority_open_residual"
    return "priority_other_active_blocker"
