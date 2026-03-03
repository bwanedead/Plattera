from __future__ import annotations

import re
from typing import Any

_DECISION_SPECS: list[tuple[str, str, bool]] = [
    ("township", "Township", True),
    ("range", "Range", True),
    ("section", "Section", True),
    ("tie_distance", "Tie Distance", True),
    ("tie_bearing", "Tie Bearing", True),
    ("acreage", "Acreage", False),
    ("closure_or_pob", "Closure / POB", True),
]

_DISPUTED_HINTS = {"disagree", "conflict", "mismatch", "ambiguous", "unclear"}
_CONFIRMED_STATUSES = {"match", "confirmed"}
_DISPUTED_STATUSES = {"mismatch", "rejected", "unclear", "unknown"}


def initialize_decision_ledger() -> dict[str, Any]:
    items = [
        {
            "key": key,
            "label": label,
            "state": "unknown",
            "selected_value": None,
            "alternatives": [],
            "confidence": None,
            "blocking": blocking,
            "evidence_refs": [],
            "user_override_state": "none",
        }
        for key, label, blocking in _DECISION_SPECS
    ]
    return {"items": items, "summary": _summary(items)}


def update_ledger_from_iteration(
    *,
    ledger: dict[str, Any] | None,
    findings: list[dict[str, Any]] | None = None,
    disagreement_hints: dict[str, Any] | None = None,
    image_results: list[dict[str, Any]] | None = None,
    readiness_blocker: str | None = None,
) -> dict[str, Any]:
    working = _ensure_ledger_shape(ledger)
    by_key: dict[str, dict[str, Any]] = {
        str(item.get("key")): item
        for item in working["items"]
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }

    for finding in findings or []:
        if not isinstance(finding, dict):
            continue
        message = str(finding.get("message") or "")
        target_key = _key_for_text(message)
        if not target_key:
            continue
        item = by_key[target_key]
        value = _extract_value_for_key(target_key, message)
        state = "disputed" if _looks_disputed(message) else "candidate_found"
        _apply_observation(item=item, state=state, value=value, evidence_ref=str(finding.get("finding_id") or "").strip() or None)

    _apply_disagreement_hints(by_key=by_key, disagreement_hints=disagreement_hints or {})

    for result in image_results or []:
        if not isinstance(result, dict):
            continue
        check_id = str(result.get("check_id") or "").lower()
        status = str(result.get("status") or "").lower()
        observed = str(result.get("observed_text") or "").strip() or None
        target_key = _key_for_check_id(check_id)
        if not target_key:
            continue
        item = by_key[target_key]
        if status in _CONFIRMED_STATUSES:
            _apply_observation(item=item, state="verified", value=observed, evidence_ref=check_id or None)
        elif status in _DISPUTED_STATUSES:
            _apply_observation(item=item, state="disputed", value=observed, evidence_ref=check_id or None)

    if readiness_blocker == "mapping_critical_image_verification_unresolved":
        for item in working["items"]:
            if bool(item.get("blocking")) and str(item.get("state") or "") == "unknown":
                item["state"] = "accepted_with_risk"
                _append_unique(item, "evidence_refs", "terminal_readiness_blocker")

    working["summary"] = _summary(working["items"])
    return working


def ledger_snapshot_for_payload(ledger: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _ensure_ledger_shape(ledger)
    return {
        "items": [dict(item) for item in normalized["items"]],
        "summary": dict(normalized["summary"]),
    }


def _ensure_ledger_shape(ledger: dict[str, Any] | None) -> dict[str, Any]:
    base = initialize_decision_ledger()
    if not isinstance(ledger, dict):
        return base
    incoming_items = ledger.get("items")
    if not isinstance(incoming_items, list):
        return base
    by_key = {
        str(item.get("key")): item
        for item in incoming_items
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    items: list[dict[str, Any]] = []
    for key, label, blocking in _DECISION_SPECS:
        raw = by_key.get(key) or {}
        items.append(
            {
                "key": key,
                "label": label,
                "state": str(raw.get("state") or "unknown"),
                "selected_value": raw.get("selected_value"),
                "alternatives": list(raw.get("alternatives") or []),
                "confidence": raw.get("confidence"),
                "blocking": bool(raw.get("blocking", blocking)),
                "evidence_refs": list(raw.get("evidence_refs") or []),
                "user_override_state": str(raw.get("user_override_state") or "none"),
            }
        )
    return {"items": items, "summary": _summary(items)}


def _summary(items: list[dict[str, Any]]) -> dict[str, int]:
    blocking_open_count = 0
    verified_count = 0
    disputed_count = 0
    unknown_count = 0
    for item in items:
        state = str(item.get("state") or "unknown")
        blocking = bool(item.get("blocking"))
        if state == "verified":
            verified_count += 1
        if state == "disputed":
            disputed_count += 1
        if state == "unknown":
            unknown_count += 1
        if blocking and state in {"unknown", "candidate_found", "disputed", "accepted_with_risk"}:
            blocking_open_count += 1
    return {
        "blocking_open_count": blocking_open_count,
        "verified_count": verified_count,
        "disputed_count": disputed_count,
        "unknown_count": unknown_count,
    }


def _apply_disagreement_hints(*, by_key: dict[str, dict[str, Any]], disagreement_hints: dict[str, Any]) -> None:
    hint_map = {
        "range_values": "range",
        "distance_values": "tie_distance",
        "bearing_values": "tie_bearing",
        "acreage_values": "acreage",
    }
    for hint_key, decision_key in hint_map.items():
        values = disagreement_hints.get(hint_key)
        if not isinstance(values, list) or not values:
            continue
        item = by_key[decision_key]
        alternatives = []
        for entry in values[:4]:
            if not isinstance(entry, dict):
                continue
            value = str(entry.get("value") or "").strip()
            if value:
                alternatives.append(value)
        if alternatives:
            item["alternatives"] = alternatives
        if len(alternatives) > 1:
            item["state"] = "disputed"
            _append_unique(item, "evidence_refs", hint_key)
        elif alternatives and str(item.get("state") or "") == "unknown":
            item["state"] = "candidate_found"
            item["selected_value"] = alternatives[0]
            _append_unique(item, "evidence_refs", hint_key)


def _apply_observation(
    *,
    item: dict[str, Any],
    state: str,
    value: str | None,
    evidence_ref: str | None,
) -> None:
    current_state = str(item.get("state") or "unknown")
    next_state = _pick_state(current_state=current_state, observed_state=state)
    item["state"] = next_state
    if value:
        item["selected_value"] = value
    if evidence_ref:
        _append_unique(item, "evidence_refs", evidence_ref)


def _pick_state(*, current_state: str, observed_state: str) -> str:
    if observed_state == "disputed":
        return "disputed"
    rank = {"unknown": 0, "candidate_found": 1, "verified": 2}
    current_rank = rank.get(current_state, 0)
    observed_rank = rank.get(observed_state, 0)
    if observed_rank >= current_rank:
        return observed_state
    return current_state


def _append_unique(item: dict[str, Any], field: str, value: str) -> None:
    raw = item.get(field)
    if not isinstance(raw, list):
        raw = []
        item[field] = raw
    if value not in raw:
        raw.append(value)


def _looks_disputed(message: str) -> bool:
    lower = message.lower()
    return any(token in lower for token in _DISPUTED_HINTS)


def _key_for_text(message: str) -> str | None:
    lower = message.lower()
    if "township" in lower:
        return "township"
    if " range " in f" {lower} ":
        return "range"
    if "section" in lower:
        return "section"
    if "tie distance" in lower or "distance" in lower:
        return "tie_distance"
    if "bearing" in lower:
        return "tie_bearing"
    if "acre" in lower:
        return "acreage"
    if "point of beginning" in lower or "pob" in lower or "closure" in lower:
        return "closure_or_pob"
    return None


def _key_for_check_id(check_id: str) -> str | None:
    if "range" in check_id:
        return "range"
    if "distance" in check_id:
        return "tie_distance"
    if "bearing" in check_id:
        return "tie_bearing"
    if "acreage" in check_id:
        return "acreage"
    if "plss" in check_id:
        return "township"
    return None


def _extract_value_for_key(key: str, text: str) -> str | None:
    if key == "tie_distance":
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:feet|foot|ft)\b", text, re.IGNORECASE)
        return match.group(0) if match else None
    if key == "acreage":
        match = re.search(r"(\d+(?:\.\d+)?)\s*ac(?:re|res)?\b", text, re.IGNORECASE)
        return match.group(0) if match else None
    if key == "tie_bearing":
        match = re.search(r"\b[NS]\s*\d{1,3}(?:\s*[°º])?(?:\s*\d{1,2})?\s*[EW]\b", text, re.IGNORECASE)
        return match.group(0) if match else None
    if key in {"range", "township", "section"}:
        match = re.search(rf"{key}\s*[:\-]?\s*([A-Za-z0-9 \-]+)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    if key == "closure_or_pob":
        lower = text.lower()
        if "point of beginning" in lower:
            return "point of beginning"
        if "pob" in lower:
            return "pob"
        if "closure" in lower:
            return "closure"
    return None
