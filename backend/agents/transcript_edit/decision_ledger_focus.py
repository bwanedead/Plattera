from __future__ import annotations

from typing import Any

from harness.decision_ledger import envelope_is_unified_decision_ledger

from .board_focus_shaping import board_focus_sort_suffix, emergent_board_sort_suffix
from .decision_ledger_adapter import (
    TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY,
    legacy_decision_ledger_shape_from_unified,
)
from .decision_ledger_closure import unresolved_mapping_blocking_requirements
from .decision_ledger_scope import (
    _ensure_ledger_shape,
    _normalize_scope_status,
    _scope_id_from_scope_status,
    _scope_label,
    _scope_rank,
)
from .focus_authority_policy import authority_rank_for_candidate, focus_authority_audit
from .work_board_projection import (
    HARNESS_EMERGENT_ITEM_PREFIX,
    active_work_board_item_for_key,
    project_decision_ledger_to_work_board,
)
from .work_board_read import board_is_mapping_blocking

_UNRESOLVED_STATES = {"unknown", "candidate_found", "disputed", "accepted_with_risk"}


def _board_row_to_pseudo_ledger_state(board_state_raw: str) -> str:
    b = str(board_state_raw or "open").strip().lower()
    if b == "blocked":
        return "disputed"
    if b == "narrowed":
        return "accepted_with_risk"
    if b == "investigating":
        return "candidate_found"
    return "unknown"


def _harness_emergent_focus_candidates(
    unified_decision_ledger: dict[str, Any] | None,
    *,
    ledger_candidate_keys: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(unified_decision_ledger, dict):
        return []
    out: list[dict[str, Any]] = []
    for row in list(unified_decision_ledger.get("items") or []):
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("item_id") or "").strip()
        if not item_id.startswith(HARNESS_EMERGENT_ITEM_PREFIX):
            continue
        bstate = str(row.get("state") or "open").strip().lower()
        if bstate in {"resolved", "superseded"}:
            continue
        dp = row.get("domain_payload") if isinstance(row.get("domain_payload"), dict) else {}
        link = str(dp.get("decision_key") or "").strip().lower()
        if link and link in ledger_candidate_keys:
            continue
        pseudo_state = _board_row_to_pseudo_ledger_state(bstate)
        blocking = bool(board_is_mapping_blocking(row) or str(row.get("materiality") or "").strip().lower() == "high")
        scope = row.get("scope") if isinstance(row.get("scope"), dict) else {}
        scope_id_raw = str(scope.get("scope_id") or "unknown_scope").strip().lower()
        if scope_id_raw not in {"target_scope", "outside_target_scope", "unknown_scope"}:
            scope_id_raw = "unknown_scope"
        scope_priority = _scope_rank(scope_id_raw)
        out.append(
            {
                "key": item_id,
                "label": str(row.get("title") or item_id).strip()[:240] or item_id,
                "state": pseudo_state,
                "blocking": blocking,
                "alternatives": list(row.get("alternatives") or [])[:16],
                "priority": int(row.get("priority") or 50),
                "evidence_count": len(list(row.get("evidence_refs") or [])),
                "block_reason": "",
                "contradiction_rank": 0,
                "scope_id": scope_id_raw,
                "scope_label": _scope_label(scope_id_raw),
                "scope_priority": scope_priority,
                "_ledger_item": {},
                "_candidate_source": "harness_emergent",
                "_harness_emergent_row": dict(row),
            }
        )
    return out


def choose_investigation_focus(
    ledger: dict[str, Any] | None = None,
    *,
    work_board: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Select next focus from the **unified harness decision ledger** envelope.

    Transitional call shapes (all equivalent when data is consistent):

    - ``ledger`` = transcript-edit native store, ``work_board`` = unified envelope (preferred during migration).
    - ``ledger`` only: unified envelope is ``project_decision_ledger_to_work_board(ledger)`` (no emergent rows).
    - ``ledger`` = unified envelope (``work_board.v1``): closure rows are reconstructed from ``te:ledger:*`` items.
    - ``work_board`` only: pass ``ledger=None``; closure reconstructed from the envelope.
    """
    if work_board is not None:
        unified = work_board
        closure_source: dict[str, Any]
        if ledger is not None:
            closure_source = ledger
        else:
            closure_source = legacy_decision_ledger_shape_from_unified(unified)
    elif ledger is not None and envelope_is_unified_decision_ledger(ledger):
        unified = ledger
        closure_source = legacy_decision_ledger_shape_from_unified(unified)
    elif ledger is not None:
        unified = project_decision_ledger_to_work_board(ledger)
        closure_source = ledger
    else:
        return None

    normalized = _ensure_ledger_shape(closure_source)
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
                "priority": TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY.get(key, 99),
                "evidence_count": len(list(item.get("evidence_refs") or [])),
                "block_reason": block_reason,
                "contradiction_rank": contradiction_rank,
                "scope_id": scope_id,
                "scope_label": _scope_label(scope_id),
                "scope_priority": scope_priority,
                "_ledger_item": dict(item),
                "_candidate_source": "ledger_decision",
            }
        )
    ledger_candidate_keys = {str(c.get("key") or "").strip().lower() for c in candidates if str(c.get("key") or "").strip()}
    candidates.extend(
        _harness_emergent_focus_candidates(unified, ledger_candidate_keys=ledger_candidate_keys)
    )
    if not candidates:
        return None

    def sort_key(c: dict[str, Any]) -> tuple[Any, ...]:
        if str(c.get("_candidate_source") or "") == "harness_emergent":
            row_h = c.get("_harness_emergent_row") if isinstance(c.get("_harness_emergent_row"), dict) else {}
            suffix = emergent_board_sort_suffix(row_h)
        else:
            board_item = (
                active_work_board_item_for_key(unified, str(c.get("key") or ""))
                if isinstance(unified, dict)
                else None
            )
            suffix = board_focus_sort_suffix(
                str(c.get("key") or ""),
                c.get("_ledger_item") if isinstance(c.get("_ledger_item"), dict) else {},
                board_item,
            )
        return (
            authority_rank_for_candidate(c, mapping_blocking_by_key=mapping_blocking_by_key),
            0 if c["blocking"] else 1,
            int(c["scope_priority"]),
            -int(c["contradiction_rank"]),
            -_uncertainty_rank(str(c["state"])),
            int(c["priority"]),
            -int(c["evidence_count"]),
        ) + suffix

    candidates.sort(key=sort_key)
    winner = candidates[0]
    reason_code, reason_text = _focus_reason_for_candidate(winner)
    auth = focus_authority_audit(mapping_blocking_by_key=mapping_blocking_by_key, winner=winner)
    out = {
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
        "focus_target_kind": (
            "harness_emergent"
            if str(winner.get("_candidate_source") or "") == "harness_emergent"
            else "ledger_decision"
        ),
        "focus_authority": auth,
    }
    return out


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
    if str(candidate.get("_candidate_source") or "") == "harness_emergent":
        label = str(candidate.get("label") or "harness work item").strip()
        return (
            "harness_emergent_board_item",
            f"Prioritizing durable harness-emergent decision-ledger item: {label}.",
        )
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
