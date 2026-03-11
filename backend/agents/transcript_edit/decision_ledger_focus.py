from __future__ import annotations

from typing import Any

from .decision_ledger_closure import unresolved_mapping_blocking_requirements
from .decision_ledger_scope import (
    _ensure_ledger_shape,
    _normalize_scope_status,
    _scope_id_from_scope_status,
    _scope_label,
    _scope_rank,
)

_UNRESOLVED_STATES = {"unknown", "candidate_found", "disputed", "accepted_with_risk"}
_DECISION_PRIORITY: dict[str, int] = {
    "range": 0,
    "township": 1,
    "section": 2,
    "tie_distance": 3,
    "tie_bearing": 4,
    "closure_or_pob": 5,
    "acreage": 6,
}

def choose_investigation_focus(ledger: dict[str, Any] | None) -> dict[str, Any] | None:
    normalized = _ensure_ledger_shape(ledger)
    candidates: list[dict[str, Any]] = []
    mapping_blocking_by_key = {
        str(item.get("key") or ""): item
        for item in unresolved_mapping_blocking_requirements(normalized)
        if isinstance(item, dict)
    }
    for item in normalized["items"]:
        if not isinstance(item, dict):
            continue
        state = str(item.get("state") or "unknown")
        if state not in _UNRESOLVED_STATES:
            continue
        key = str(item.get("key") or "")
        requirement = item.get("closure_requirement") if isinstance(item.get("closure_requirement"), dict) else {}
        mapped_item = mapping_blocking_by_key.get(key)
        blocking = bool((mapped_item or {}).get("mapping_blocking")) if isinstance(mapped_item, dict) else bool(item.get("blocking"))
        if mapped_item is None and blocking:
            # Prefer materially mapped blockers first; unknown placeholders come after.
            blocking = False
        scope_status = _normalize_scope_status(requirement.get("scope_status"))
        scope_id = _scope_id_from_scope_status(scope_status)
        scope_priority = _scope_rank(scope_id)
        block_reason = str(requirement.get("block_reason") or "").strip().lower()
        contradiction_rank = 1 if block_reason == "contradiction" else 0
        candidates.append(
            {
                "key": key,
                "label": str(item.get("label") or key or "decision"),
                "state": state,
                "blocking": blocking,
                "alternatives": list(item.get("alternatives") or []),
                "priority": _DECISION_PRIORITY.get(key, 99),
                "evidence_count": len(list(item.get("evidence_refs") or [])),
                "block_reason": block_reason,
                "contradiction_rank": contradiction_rank,
                "scope_id": scope_id,
                "scope_label": _scope_label(scope_id),
                "scope_priority": scope_priority,
            }
        )
    if not candidates:
        return None
    candidates.sort(
        key=lambda c: (
            0 if c["blocking"] else 1,
            int(c["scope_priority"]),
            -int(c["contradiction_rank"]),
            -_uncertainty_rank(str(c["state"])),
            int(c["priority"]),
            -int(c["evidence_count"]),
        )
    )
    winner = candidates[0]
    reason_code, reason_text = _focus_reason_for_candidate(winner)
    return {
        "decision_key": winner["key"],
        "decision_label": winner["label"],
        "state": winner["state"],
        "blocking": winner["blocking"],
        "scope_id": winner["scope_id"],
        "scope_label": winner["scope_label"],
        "scope_priority": winner["scope_priority"],
        "in_target_scope": winner["scope_id"] == "target_scope",
        "next_check_reason_code": reason_code,
        "next_check_reason": reason_text,
    }

def has_blocking_dispute(ledger: dict[str, Any] | None) -> bool:
    normalized = _ensure_ledger_shape(ledger)
    for item in normalized["items"]:
        if not isinstance(item, dict):
            continue
        if bool(item.get("blocking")) and str(item.get("state") or "") == "disputed":
            alternatives = [str(v).strip() for v in list(item.get("alternatives") or []) if str(v).strip()]
            if len(alternatives) > 1:
                return True
    return False

def _uncertainty_rank(state: str) -> int:
    if state == "disputed":
        return 4
    if state == "unknown":
        return 3
    if state == "accepted_with_risk":
        return 2
    if state == "candidate_found":
        return 1
    return 0

def _focus_reason_for_candidate(candidate: dict[str, Any]) -> tuple[str, str]:
    state = str(candidate.get("state") or "unknown")
    label = str(candidate.get("label") or "mapping-critical detail")
    blocking = bool(candidate.get("blocking"))
    alternatives = [str(v).strip() for v in list(candidate.get("alternatives") or []) if str(v).strip()]
    if blocking and state == "disputed" and len(alternatives) > 1:
        return ("blocking_conflict_unresolved", f"Prioritizing {label}: blocking conflict remains unresolved.")
    if blocking and state in {"unknown", "candidate_found", "accepted_with_risk"}:
        return ("blocking_mapping_critical", f"Prioritizing {label}: mapping-critical evidence is still incomplete.")
    if state == "disputed":
        return ("highest_uncertainty", f"Prioritizing {label}: it has the highest unresolved uncertainty.")
    return ("next_open_item", f"Prioritizing {label}: it is the next unresolved checklist item.")
