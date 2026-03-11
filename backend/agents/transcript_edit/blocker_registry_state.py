from __future__ import annotations

import time
from typing import Any

from .blocker_archetypes import menu_for_candidates

_STATE_VALUES = {
    "open",
    "waiting_feedback",
    "answered_unintegrated",
    "resolved",
    "superseded",
}
_FEEDBACK_STATUS_VALUES = {"none", "pending", "received", "integrated", "stale", "superseded"}
_SCOPE_VALUES = {"in_target", "outside_target", "unknown"}
_ACTION_VALUES = {
    "request_hitl",
    "integrate_feedback",
    "gather_image_evidence",
    "apply_edit_plan",
    "mark_blocked_by_incomplete_source",
}
_BLOCKING_CLASS_VALUES = {
    "mapping_blocking",
    "closure_blocking",
    "source_blocking",
    "quality_only",
}

_EMERGENT_KIND_BY_DECISION_KEY = {
    "range": "conflicting_location_token",
    "township": "conflicting_location_token",
    "section": "conflicting_location_token",
    "tie_distance": "ambiguous_boundary_call",
    "tie_bearing": "ambiguous_boundary_call",
    "closure_or_pob": "missing_anchor_reference",
    "acreage": "transcript_anchor_missing",
}

def initialize_blocker_registry(
    *,
    run_id: str,
    session_id: str,
    source_transcript_ref: str | None,
) -> dict[str, Any]:
    return {
        "version": 1,
        "run_id": str(run_id or "").strip() or None,
        "session_id": str(session_id or "").strip() or None,
        "source_transcript_ref": str(source_transcript_ref or "").strip() or None,
        "source_completeness": "unknown",
        "target_scope_status": "not_attempted",
        "active_blocker_id": None,
        "counts": _counts_empty(),
        "rows": [],
        "convention_context": {
            "document_convention": "unknown",
            "convention_confidence": 0.2,
            "convention_signals": [],
            "menu_family_candidates": ["unknown", "source_quality", "cross_convention_core"],
        },
        "archetype_menu": {
            "menu_family_candidates": ["unknown"],
            "archetypes": menu_for_candidates(["unknown"]),
        },
        "emergent": {
            "version": 1,
            "active_blocker_id": None,
            "counts": _counts_empty(),
            "rows": [],
            "history": [],
        },
        "history": [],
        "updated_at": int(time.time()),
    }

def set_convention_context(
    *,
    registry: dict[str, Any] | None,
    convention_context: dict[str, Any] | None,
) -> dict[str, Any]:
    working = _ensure_registry_shape(
        registry=registry,
        run_id=None,
        session_id=None,
        source_transcript_ref=None,
    )
    context = dict(convention_context) if isinstance(convention_context, dict) else {}
    document_convention = str(context.get("document_convention") or "").strip().lower() or "unknown"
    confidence_raw = context.get("convention_confidence")
    try:
        confidence = float(confidence_raw)
    except Exception:
        confidence = 0.2
    confidence = max(0.0, min(1.0, confidence))
    signals = [
        dict(row)
        for row in list(context.get("convention_signals") or [])
        if isinstance(row, dict)
    ][:12]
    menu_family_candidates = [
        str(value).strip().lower()
        for value in list(context.get("menu_family_candidates") or [])
        if str(value).strip()
    ]
    if not menu_family_candidates:
        menu_family_candidates = [document_convention]
    working["convention_context"] = {
        "document_convention": document_convention,
        "convention_confidence": confidence,
        "convention_signals": signals,
        "menu_family_candidates": menu_family_candidates,
    }
    working["archetype_menu"] = {
        "menu_family_candidates": menu_family_candidates,
        "archetypes": menu_for_candidates(menu_family_candidates),
    }
    _sync_emergent_rows_from_legacy(working)
    working["updated_at"] = int(time.time())
    return working

def _ensure_registry_shape(
    *,
    registry: dict[str, Any] | None,
    run_id: str | None,
    session_id: str | None,
    source_transcript_ref: str | None,
) -> dict[str, Any]:
    base = initialize_blocker_registry(
        run_id=str(run_id or "").strip() or None,
        session_id=str(session_id or "").strip() or None,
        source_transcript_ref=source_transcript_ref,
    )
    if not isinstance(registry, dict):
        return base
    out = dict(base)
    out["run_id"] = str(registry.get("run_id") or out["run_id"] or "").strip() or None
    out["session_id"] = str(registry.get("session_id") or out["session_id"] or "").strip() or None
    out["source_transcript_ref"] = str(registry.get("source_transcript_ref") or out["source_transcript_ref"] or "").strip() or None
    out["source_completeness"] = str(registry.get("source_completeness") or out["source_completeness"] or "unknown").strip().lower() or "unknown"
    out["target_scope_status"] = str(registry.get("target_scope_status") or out["target_scope_status"] or "not_attempted").strip().lower() or "not_attempted"
    out["active_blocker_id"] = str(registry.get("active_blocker_id") or "").strip() or None
    out["rows"] = [dict(row) for row in list(registry.get("rows") or []) if isinstance(row, dict)][-80:]
    out["history"] = [dict(row) for row in list(registry.get("history") or []) if isinstance(row, dict)][-120:]
    context = registry.get("convention_context") if isinstance(registry.get("convention_context"), dict) else {}
    document_convention = str(context.get("document_convention") or "unknown").strip().lower() or "unknown"
    menu_candidates = [
        str(value).strip().lower()
        for value in list(context.get("menu_family_candidates") or [])
        if str(value).strip()
    ]
    if not menu_candidates:
        menu_candidates = [document_convention]
    try:
        context_confidence = float(context.get("convention_confidence") or 0.2)
    except Exception:
        context_confidence = 0.2
    out["convention_context"] = {
        "document_convention": document_convention,
        "convention_confidence": max(0.0, min(1.0, context_confidence)),
        "convention_signals": [
            dict(row)
            for row in list(context.get("convention_signals") or [])
            if isinstance(row, dict)
        ][:12],
        "menu_family_candidates": menu_candidates,
    }
    archetype_menu = registry.get("archetype_menu") if isinstance(registry.get("archetype_menu"), dict) else {}
    out["archetype_menu"] = {
        "menu_family_candidates": [
            str(value).strip().lower()
            for value in list(archetype_menu.get("menu_family_candidates") or menu_candidates)
            if str(value).strip()
        ][:12],
        "archetypes": [
            dict(row)
            for row in list(archetype_menu.get("archetypes") or menu_for_candidates(menu_candidates))
            if isinstance(row, dict)
        ][:40],
    }
    emergent = registry.get("emergent") if isinstance(registry.get("emergent"), dict) else {}
    out["emergent"] = {
        "version": int(emergent.get("version") or 1),
        "active_blocker_id": str(emergent.get("active_blocker_id") or "").strip() or None,
        "counts": dict(emergent.get("counts") or _counts_empty()),
        "rows": [dict(row) for row in list(emergent.get("rows") or []) if isinstance(row, dict)][-120:],
        "history": [dict(row) for row in list(emergent.get("history") or []) if isinstance(row, dict)][-120:],
    }
    out["counts"] = _counts_for_rows(out["rows"])
    _sync_emergent_rows_from_legacy(out)
    out["updated_at"] = int(registry.get("updated_at") or int(time.time()))
    return out

def _row_from_unresolved_item(
    *,
    item: dict[str, Any],
    prior: dict[str, Any],
    source_completeness: str,
    source_limitations: list[str],
) -> dict[str, Any]:
    now = int(time.time())
    closure = item.get("closure_requirement") if isinstance(item.get("closure_requirement"), dict) else {}
    decision_key = str(item.get("key") or "").strip().lower()
    scope_status = _normalize_scope_status(item, closure)
    prior_state = str(prior.get("state") or "").strip().lower()
    state = prior_state if prior_state in _STATE_VALUES else "open"
    if state in {"resolved", "superseded"}:
        # If the unresolved item still exists, reopen unless explicitly waiting for feedback.
        state = "waiting_feedback" if prior_state == "waiting_feedback" else "open"
    feedback_status = str(prior.get("feedback_status") or "").strip().lower()
    if feedback_status not in _FEEDBACK_STATUS_VALUES:
        feedback_status = "none"
    if state == "waiting_feedback":
        feedback_status = "pending"
    elif state == "answered_unintegrated":
        feedback_status = "received"
    elif state in {"resolved"} and feedback_status == "none":
        feedback_status = "integrated"
    if state == "answered_unintegrated":
        default_action = "integrate_feedback"
    else:
        default_action = "gather_image_evidence"
    actions = _normalize_actions(
        prior.get("next_valid_actions")
        if isinstance(prior.get("next_valid_actions"), list)
        else [default_action]
    )
    if state == "waiting_feedback":
        actions = []
    if state in {"open"} and "request_hitl" not in actions:
        actions = _normalize_actions(["request_hitl", *actions])
    if state == "answered_unintegrated":
        actions = _normalize_actions(["integrate_feedback", "apply_edit_plan", *actions])
    blocker_id = _blocker_id_for_item(item)
    row = {
        "blocker_id": blocker_id,
        "decision_key": decision_key,
        "scope_status": scope_status,
        "scope_proof": [str(v).strip().lower() for v in list(item.get("scope_proof") or closure.get("scope_proof") or []) if str(v).strip()][:6],
        "mapping_blocking": bool(item.get("mapping_blocking")),
        "state": state,
        "block_reason": str(closure.get("block_reason") or "").strip().lower() or "ambiguity",
        "required_information": str(closure.get("required_information") or "").strip() or None,
        "minimal_user_action": str(closure.get("minimal_user_action") or "").strip() or None,
        "current_evidence_summary": str(closure.get("attempt_summary") or "").strip() or None,
        "current_selected_value": item.get("selected_value"),
        "candidate_values": [str(v).strip() for v in list(item.get("alternatives") or []) if str(v).strip()][:8],
        "source_completeness": source_completeness,
        "source_limitations": source_limitations[:8],
        "next_valid_actions": actions,
        "linked_ticket_id": str(prior.get("linked_ticket_id") or "").strip() or None,
        "linked_prompt_id": str(prior.get("linked_prompt_id") or "").strip() or None,
        "feedback_status": feedback_status,
        "feedback_value": str(prior.get("feedback_value") or "").strip() or None,
        "feedback_note": str(prior.get("feedback_note") or "").strip() or None,
        "feedback_received_at": prior.get("feedback_received_at"),
        "integration_attempts": int(prior.get("integration_attempts") or 0),
        "last_transition_reason": str(prior.get("last_transition_reason") or "").strip() or "ledger_sync",
        "superseded_by_blocker_id": str(prior.get("superseded_by_blocker_id") or "").strip() or None,
        "created_at": int(prior.get("created_at") or now),
        "updated_at": now,
    }
    return row

def _blocker_id_for_item(item: dict[str, Any]) -> str:
    decision_key = str(item.get("key") or "").strip().lower() or "unknown"
    return f"blocker:{decision_key}"

def _normalize_scope_status(item: dict[str, Any], closure: dict[str, Any]) -> str:
    status = str(closure.get("scope_status") or item.get("scope_status") or "").strip().lower()
    if status in _SCOPE_VALUES:
        return status
    scope_id = str(item.get("scope_id") or "").strip().lower()
    if scope_id == "target_scope":
        return "in_target"
    if scope_id == "outside_target_scope":
        return "outside_target"
    return "unknown"

def _normalize_actions(values: list[Any]) -> list[str]:
    out: list[str] = []
    for value in values:
        action = str(value or "").strip().lower()
        if action not in _ACTION_VALUES:
            continue
        if action in out:
            continue
        out.append(action)
    return out[:6]


def _is_operationally_active(row: dict[str, Any]) -> bool:
    return str(row.get("state") or "").strip().lower() in {"open", "waiting_feedback", "answered_unintegrated"}


def _row_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    active_rank = 0 if _is_operationally_active(row) else 1
    return (active_rank, str(row.get("blocker_id") or ""))

def _find_latest_row_for_decision(*, rows: list[dict[str, Any]], decision_key: str) -> dict[str, Any] | None:
    key = str(decision_key or "").strip().lower()
    matches = [
        row
        for row in rows
        if isinstance(row, dict) and str(row.get("decision_key") or "").strip().lower() == key
    ]
    if not matches:
        return None
    matches.sort(key=lambda row: int(row.get("updated_at") or row.get("created_at") or 0), reverse=True)
    return matches[0]

def _normalize_active_blocker(working: dict[str, Any], preferred_blocker_id: str | None = None) -> None:
    rows = [row for row in list(working.get("rows") or []) if isinstance(row, dict)]
    active = None
    preferred = str(preferred_blocker_id or "").strip()
    if preferred:
        for row in rows:
            if str(row.get("blocker_id") or "").strip() == preferred and _is_operationally_active(row):
                active = preferred
                break
    if active is None:
        from .blocker_registry_selection import select_primary_blocker

        candidate = select_primary_blocker(working)
        active = str((candidate or {}).get("blocker_id") or "").strip() or None
    working["active_blocker_id"] = active

def _sync_emergent_rows_from_legacy(working: dict[str, Any]) -> None:
    if not isinstance(working, dict):
        return
    emergent = working.get("emergent")
    if not isinstance(emergent, dict):
        emergent = {"version": 1, "active_blocker_id": None, "counts": _counts_empty(), "rows": [], "history": []}
        working["emergent"] = emergent
    legacy_rows = [row for row in list(working.get("rows") or []) if isinstance(row, dict)]
    source_completeness = str(working.get("source_completeness") or "unknown").strip().lower() or "unknown"
    prior_rows = [dict(row) for row in list(emergent.get("rows") or []) if isinstance(row, dict)]
    by_id = {
        str(row.get("blocker_id") or "").strip(): row
        for row in prior_rows
        if str(row.get("blocker_id") or "").strip()
    }
    rows_out: list[dict[str, Any]] = []
    now = int(time.time())
    for legacy in legacy_rows:
        legacy_id = str(legacy.get("blocker_id") or "").strip()
        if not legacy_id:
            continue
        blocker_id = f"emergent:{legacy_id}"
        prior = by_id.get(blocker_id, {})
        rows_out.append(
            _emergent_row_from_legacy(
                legacy_row=legacy,
                prior=prior if isinstance(prior, dict) else {},
                source_completeness=source_completeness,
                now=now,
            )
        )
    # Preserve non-legacy emergent rows that the agent/runtime authored in this phase.
    projected_legacy_ids = {
        str(row.get("blocker_id") or "").strip()
        for row in rows_out
        if isinstance(row, dict) and str(row.get("blocker_id") or "").strip()
    }
    for prior in prior_rows:
        blocker_id = str(prior.get("blocker_id") or "").strip()
        if not blocker_id:
            continue
        if blocker_id in projected_legacy_ids:
            continue
        if blocker_id.startswith("emergent:blocker:"):
            # Legacy projection rows are owned by ledger sync; if they disappeared from projection,
            # keep terminal history but do not keep stale active duplicates.
            state = str(prior.get("state") or "").strip().lower()
            if state not in {"resolved", "superseded"}:
                continue
        rows_out.append(dict(prior))
    rows_out.sort(key=_emergent_row_priority_key)
    active_row = next(
        (
            row
            for row in rows_out
            if str(row.get("state") or "").strip().lower() not in {"resolved", "superseded"}
        ),
        None,
    )
    emergent["rows"] = rows_out[-120:]
    emergent["active_blocker_id"] = str((active_row or {}).get("blocker_id") or "").strip() or None
    emergent["counts"] = _counts_for_rows(emergent["rows"])
    history = [dict(row) for row in list(emergent.get("history") or []) if isinstance(row, dict)]
    if not history or history[-1].get("active_blocker_id") != emergent["active_blocker_id"]:
        history.append(
            {
                "timestamp_epoch_seconds": now,
                "active_blocker_id": emergent["active_blocker_id"],
                "counts": dict(emergent.get("counts") or {}),
            }
        )
    emergent["history"] = history[-120:]

def _emergent_row_from_legacy(
    *,
    legacy_row: dict[str, Any],
    prior: dict[str, Any],
    source_completeness: str,
    now: int,
) -> dict[str, Any]:
    decision_key = str(legacy_row.get("decision_key") or "").strip().lower()
    legacy_state = str(legacy_row.get("state") or "").strip().lower() or "open"
    blocker_kind = _EMERGENT_KIND_BY_DECISION_KEY.get(decision_key) or f"custom:{decision_key or 'unknown'}"
    blocking_class = _emergent_blocking_class(
        decision_key=decision_key,
        legacy_row=legacy_row,
        source_completeness=source_completeness,
    )
    reason = str(legacy_row.get("block_reason") or "").strip().lower() or "ambiguity"
    title = str(legacy_row.get("decision_key") or "blocker").strip().replace("_", " ").title()
    source_impact = (
        "source_incomplete"
        if source_completeness in {"partial_truncated", "partial_missing_context"}
        else "none"
    )
    return {
        "blocker_id": f"emergent:{str(legacy_row.get('blocker_id') or '').strip()}",
        "blocker_kind": blocker_kind,
        "title": title,
        "blocking_class": blocking_class,
        "state": legacy_state,
        "reason": reason,
        "evidence_summary": str(legacy_row.get("current_evidence_summary") or "").strip() or None,
        "candidate_values": [
            str(value).strip()
            for value in list(legacy_row.get("candidate_values") or [])
            if str(value).strip()
        ][:10],
        "resolution_condition": str(legacy_row.get("required_information") or "").strip() or None,
        "next_valid_actions": [
            str(value).strip().lower()
            for value in list(legacy_row.get("next_valid_actions") or [])
            if str(value).strip()
        ][:8],
        "scope_status": str(legacy_row.get("scope_status") or "").strip().lower() or "unknown",
        "source_completeness_impact": source_impact,
        "linked_ticket_id": str(legacy_row.get("linked_ticket_id") or "").strip() or None,
        "legacy_blocker_id": str(legacy_row.get("blocker_id") or "").strip() or None,
        "legacy_decision_key": decision_key or None,
        "created_at": int(prior.get("created_at") or legacy_row.get("created_at") or now),
        "updated_at": int(legacy_row.get("updated_at") or now),
    }

def _emergent_blocking_class(
    *,
    decision_key: str,
    legacy_row: dict[str, Any],
    source_completeness: str,
) -> str:
    if source_completeness in {"partial_truncated", "partial_missing_context"}:
        if str(legacy_row.get("scope_status") or "").strip().lower() in {"unknown", "outside_target"}:
            return "source_blocking"
    if decision_key == "closure_or_pob":
        return "closure_blocking"
    if bool(legacy_row.get("mapping_blocking")):
        return "mapping_blocking"
    block_reason = str(legacy_row.get("block_reason") or "").strip().lower()
    if block_reason in {"dependency", "source", "incomplete_source"}:
        return "source_blocking"
    return "quality_only"

def _emergent_row_priority_key(row: dict[str, Any]) -> tuple[int, int, int, int]:
    state = str(row.get("state") or "").strip().lower()
    blocking_class = str(row.get("blocking_class") or "").strip().lower()
    state_rank = {
        "answered_unintegrated": 0,
        "waiting_feedback": 1,
        "open": 2,
        "resolved": 3,
        "superseded": 4,
    }.get(state, 5)
    class_rank = {
        "mapping_blocking": 0,
        "closure_blocking": 1,
        "source_blocking": 2,
        "quality_only": 3,
    }.get(blocking_class, 4)
    scope_rank = {"in_target": 0, "unknown": 1, "outside_target": 2}.get(
        str(row.get("scope_status") or "").strip().lower(),
        3,
    )
    updated_rank = -int(row.get("updated_at") or 0)
    return (state_rank, class_rank, scope_rank, updated_rank)

def _is_legacy_projection_emergent_row(row: dict[str, Any]) -> bool:
    blocker_id = str(row.get("blocker_id") or "").strip()
    if blocker_id.startswith("emergent:blocker:"):
        return True
    legacy_blocker_id = str(row.get("legacy_blocker_id") or "").strip()
    return bool(legacy_blocker_id)

def _counts_empty() -> dict[str, int]:
    return {
        "open": 0,
        "waiting_feedback": 0,
        "answered_unintegrated": 0,
        "resolved": 0,
        "superseded": 0,
        "total": 0,
    }

def _counts_for_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = _counts_empty()
    for row in rows:
        if not isinstance(row, dict):
            continue
        state = str(row.get("state") or "").strip().lower()
        if state not in counts:
            continue
        counts[state] = int(counts[state]) + 1
    counts["total"] = sum(
        int(v) for k, v in counts.items() if k != "total"
    )
    return counts
