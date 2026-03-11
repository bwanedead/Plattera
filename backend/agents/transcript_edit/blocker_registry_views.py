from __future__ import annotations

from typing import Any

from .decision_ledger import unresolved_closure_requirements
from .blocker_registry_state import _ensure_registry_shape
from .blocker_registry_selection import _is_operationally_active, select_primary_blocker_with_reason

def registry_snapshot_for_payload(registry: dict[str, Any] | None) -> dict[str, Any]:
    working = _ensure_registry_shape(registry=registry, run_id=None, session_id=None, source_transcript_ref=None)
    emergent = working.get("emergent") if isinstance(working.get("emergent"), dict) else {}
    return {
        "version": int(working.get("version") or 1),
        "run_id": working.get("run_id"),
        "session_id": working.get("session_id"),
        "source_transcript_ref": working.get("source_transcript_ref"),
        "source_completeness": working.get("source_completeness"),
        "target_scope_status": working.get("target_scope_status"),
        "active_blocker_id": working.get("active_blocker_id"),
        "counts": dict(working.get("counts") or {}),
        "convention_context": dict(working.get("convention_context") or {}),
        "archetype_menu": {
            "menu_family_candidates": [
                str(value)
                for value in list((working.get("archetype_menu") or {}).get("menu_family_candidates") or [])
                if str(value).strip()
            ][:12],
            "archetypes": [
                dict(row)
                for row in list((working.get("archetype_menu") or {}).get("archetypes") or [])
                if isinstance(row, dict)
            ][:30],
        },
        "rows": [dict(row) for row in list(working.get("rows") or []) if isinstance(row, dict)][:80],
        "emergent": {
            "version": int(emergent.get("version") or 1),
            "active_blocker_id": str(emergent.get("active_blocker_id") or "").strip() or None,
            "counts": dict(emergent.get("counts") or {}),
            "rows": [
                dict(row)
                for row in list(emergent.get("rows") or [])
                if isinstance(row, dict)
            ][:120],
            "history": [
                dict(row)
                for row in list(emergent.get("history") or [])
                if isinstance(row, dict)
            ][-120:],
        },
        "history": [dict(row) for row in list(working.get("history") or []) if isinstance(row, dict)][-80:],
        "updated_at": int(working.get("updated_at") or int(time.time())),
    }

def blocker_registry_delta(
    *,
    before_registry: dict[str, Any] | None,
    after_registry: dict[str, Any] | None,
) -> dict[str, Any]:
    before = _ensure_registry_shape(
        registry=before_registry,
        run_id=None,
        session_id=None,
        source_transcript_ref=None,
    )
    after = _ensure_registry_shape(
        registry=after_registry,
        run_id=None,
        session_id=None,
        source_transcript_ref=None,
    )
    before_rows = [row for row in list(before.get("rows") or []) if isinstance(row, dict)]
    after_rows = [row for row in list(after.get("rows") or []) if isinstance(row, dict)]
    before_by_id = {
        str(row.get("blocker_id") or "").strip(): row
        for row in before_rows
        if str(row.get("blocker_id") or "").strip()
    }
    after_by_id = {
        str(row.get("blocker_id") or "").strip(): row
        for row in after_rows
        if str(row.get("blocker_id") or "").strip()
    }
    before_ids = set(before_by_id.keys())
    after_ids = set(after_by_id.keys())
    resolved_ids = sorted(
        [
            blocker_id
            for blocker_id in before_ids
            if blocker_id in after_by_id
            and str((before_by_id.get(blocker_id) or {}).get("state") or "").strip().lower() not in {"resolved", "superseded"}
            and str((after_by_id.get(blocker_id) or {}).get("state") or "").strip().lower() in {"resolved", "superseded"}
        ]
    )
    newly_opened_ids = sorted(
        [
            blocker_id
            for blocker_id in after_ids
            if blocker_id not in before_ids
            and str((after_by_id.get(blocker_id) or {}).get("state") or "").strip().lower() in {"open", "waiting_feedback", "answered_unintegrated"}
        ]
    )
    transitions: list[dict[str, Any]] = []
    for blocker_id in sorted(before_ids.intersection(after_ids)):
        before_state = str((before_by_id.get(blocker_id) or {}).get("state") or "").strip().lower() or None
        after_state = str((after_by_id.get(blocker_id) or {}).get("state") or "").strip().lower() or None
        if before_state == after_state:
            continue
        transitions.append(
            {
                "blocker_id": blocker_id,
                "before_state": before_state,
                "after_state": after_state,
            }
        )
    return {
        "blocker_count_before": int((before.get("counts") or {}).get("total") or 0),
        "blocker_count_after": int((after.get("counts") or {}).get("total") or 0),
        "active_blocker_before": str(before.get("active_blocker_id") or "").strip() or None,
        "active_blocker_after": str(after.get("active_blocker_id") or "").strip() or None,
        "resolved_blocker_ids": resolved_ids[:20],
        "newly_opened_blocker_ids": newly_opened_ids[:20],
        "state_transitions": transitions[:30],
    }

def blocker_health_snapshot(
    *,
    registry: dict[str, Any] | None,
    decision_ledger: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = _ensure_registry_shape(
        registry=registry,
        run_id=None,
        session_id=None,
        source_transcript_ref=None,
    )
    selected = select_primary_blocker_with_reason(normalized)
    selected_row = selected.get("row") if isinstance(selected.get("row"), dict) else {}
    unresolved_rows = [
        row
        for row in unresolved_closure_requirements(decision_ledger if isinstance(decision_ledger, dict) else None)
        if isinstance(row, dict)
    ]
    ledger_keys = {
        str(row.get("key") or "").strip().lower()
        for row in unresolved_rows
        if str(row.get("key") or "").strip()
    }
    registry_keys = {
        str(row.get("decision_key") or "").strip().lower()
        for row in list(normalized.get("rows") or [])
        if isinstance(row, dict)
        and _is_operationally_active(row)
        and str(row.get("decision_key") or "").strip()
    }
    mismatch = ledger_keys != registry_keys
    return {
        "active_blocker_id": str(normalized.get("active_blocker_id") or "").strip() or None,
        "active_blocker_decision_key": str(selected_row.get("decision_key") or "").strip().lower() or None,
        "selection_reason_code": str(selected.get("reason_code") or "").strip() or "no_active_blockers",
        "answered_unintegrated_count": int((normalized.get("counts") or {}).get("answered_unintegrated") or 0),
        "waiting_feedback_count": int((normalized.get("counts") or {}).get("waiting_feedback") or 0),
        "open_count": int((normalized.get("counts") or {}).get("open") or 0),
        "ledger_unresolved_keys": sorted(ledger_keys),
        "registry_unresolved_keys": sorted(registry_keys),
        "ledger_registry_mismatch": bool(mismatch),
        "mismatch_only_in_ledger": sorted(list(ledger_keys.difference(registry_keys)))[:20],
        "mismatch_only_in_registry": sorted(list(registry_keys.difference(ledger_keys)))[:20],
    }
