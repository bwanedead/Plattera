"""Project transcript-edit decision ledger onto the generic harness resolution envelope."""
from __future__ import annotations

from typing import Any

from harness.mission_state.resolution_lifecycle import EMERGENT_RESOLUTION_ITEM_PREFIX
from harness.mission_state.resolution_projection import new_resolution_projection, resolution_item_row_dict

_PROJECTION_ID = "transcript_edit.decision_ledger"
HARNESS_EMERGENT_ITEM_PREFIX = EMERGENT_RESOLUTION_ITEM_PREFIX

_LEDGER_TO_BOARD_STATE: dict[str, str] = {
    "unknown": "open",
    "candidate_found": "investigating",
    "disputed": "blocked",
    "verified": "resolved",
    "accepted_with_risk": "narrowed",
}


def _blocking_impact_from_ledger(item: dict[str, Any]) -> str:
    impact = str(item.get("operational_impact") or "").strip().lower()
    if impact == "mapping_blocking":
        return "mapping_blocking"
    if impact == "transcript_quality_only":
        return "quality_only"
    if bool(item.get("blocking")):
        return "mapping_blocking"
    return "quality_only"


def _materiality(impact: str) -> str:
    return "high" if impact == "mapping_blocking" else "low"


def _ledger_priority_key(item: dict[str, Any]) -> int:
    try:
        return int(item.get("scope_priority") or 50)
    except (TypeError, ValueError):
        return 50


def _resolution_condition(item: dict[str, Any]) -> str | None:
    cr = item.get("closure_requirement")
    if not isinstance(cr, dict):
        return None
    ri = str(cr.get("required_information") or "").strip()
    if ri:
        return ri[:400]
    return str(cr.get("attempt_summary") or "").strip()[:400] or None


def _scope_from_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope_id": str(item.get("scope_id") or "").strip()[:64] or None,
        "scope_label": str(item.get("scope_label") or "").strip()[:120] or None,
        "in_target_scope": item.get("in_target_scope"),
        "layer_tag": str(item.get("layer_tag") or "").strip()[:64] or None,
    }


def _domain_payload(item: dict[str, Any]) -> dict[str, Any]:
    cr = item.get("closure_requirement") if isinstance(item.get("closure_requirement"), dict) else {}
    return {
        "decision_key": str(item.get("key") or "").strip().lower() or None,
        "ledger_label": str(item.get("label") or "").strip() or None,
        "layer_tag": str(item.get("layer_tag") or "").strip() or None,
        "verification_required": bool(item.get("verification_required")),
        "user_override_state": str(item.get("user_override_state") or "").strip() or None,
        "confidence": str(item.get("confidence") or "").strip() or None,
        "selected_value": item.get("selected_value"),
        "closure_requirement": dict(cr) if cr else {},
        "blocking_flag": bool(item.get("blocking")),
    }


def _summary_line(item: dict[str, Any]) -> str:
    label = str(item.get("label") or item.get("key") or "item").strip()
    state = str(item.get("state") or "unknown")
    sv = item.get("selected_value")
    sv_s = str(sv).strip()[:120] if sv is not None else ""
    if sv_s:
        return f"{label}: state={state}; candidate={sv_s}"
    return f"{label}: state={state}"


def project_decision_ledger_to_work_board(ledger: dict[str, Any] | None) -> dict[str, Any]:
    """Adapter: project transcript-edit checklist rows into generic harness ledger items (``te:ledger:*``)."""
    normalized = ledger if isinstance(ledger, dict) else {}
    items_raw = normalized.get("items")
    items_out: list[dict[str, Any]] = []
    if not isinstance(items_raw, list):
        return new_resolution_projection(domain_projection=_PROJECTION_ID, items=[])

    for raw in items_raw:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip().lower()
        if not key:
            continue
        state_raw = str(raw.get("state") or "unknown").strip().lower()
        board_state = _LEDGER_TO_BOARD_STATE.get(state_raw, "open")
        impact = _blocking_impact_from_ledger(raw)
        item_id = f"te:ledger:{key}"
        cr_obj = raw.get("closure_requirement")
        dep_opts: list[str] = []
        if isinstance(cr_obj, dict):
            dep_opts = [
                str(x).strip()
                for x in list(cr_obj.get("resolution_options") or [])
                if str(x).strip()
            ][:8]
        items_out.append(
            resolution_item_row_dict(
                item_id=item_id,
                title=str(raw.get("label") or key).strip()[:240] or key,
                kind="transcript_edit.decision_item",
                state=board_state,
                priority=_ledger_priority_key(raw),
                materiality=_materiality(impact),
                blocking_impact=impact,
                dependencies=dep_opts,
                evidence_refs=[str(x).strip() for x in list(raw.get("evidence_refs") or []) if str(x).strip()][
                    :24
                ],
                alternatives=[str(x).strip() for x in list(raw.get("alternatives") or []) if str(x).strip()][
                    :16
                ],
                resolution_condition=_resolution_condition(raw),
                scope=_scope_from_item(raw),
                summary=_summary_line(raw),
                notes=(
                    str((raw.get("closure_requirement") or {}).get("attempt_summary") or "").strip()[:500] or None
                    if isinstance(raw.get("closure_requirement"), dict)
                    else None
                ),
                provenance=str(raw.get("provenance") or "").strip()[:128] or None,
                domain_payload=_domain_payload(raw),
            )
        )

    return new_resolution_projection(domain_projection=_PROJECTION_ID, items=items_out)


def active_work_board_item_for_key(work_board: dict[str, Any], decision_key: str) -> dict[str, Any] | None:
    """Return the board row matching ``te:ledger:<decision_key>``."""
    if not isinstance(work_board, dict):
        return None
    key = str(decision_key or "").strip().lower()
    if not key:
        return None
    want = f"te:ledger:{key}"
    for row in list(work_board.get("items") or []):
        if isinstance(row, dict) and str(row.get("item_id") or "") == want:
            return dict(row)
    return None


def active_work_board_item_for_focus(work_board: dict[str, Any] | None, decision_key: str) -> dict[str, Any] | None:
    """Resolve active row for focus: ledger-backed ``te:ledger:*`` or durable harness-emergent ``item_id``."""
    if not isinstance(work_board, dict):
        return None
    raw = str(decision_key or "").strip()
    if not raw:
        return None
    if raw.lower().startswith(HARNESS_EMERGENT_ITEM_PREFIX.lower()):
        for row in list(work_board.get("items") or []):
            if isinstance(row, dict) and str(row.get("item_id") or "").strip() == raw:
                return dict(row)
        return None
    return active_work_board_item_for_key(work_board, raw.lower())
