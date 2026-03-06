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
_LAYER_STATUS_VALUES = {"satisfied", "blocked", "unknown"}
_LAYER_TAG_VALUES = {
    "layer1_canonical_recovery",
    "layer2_canonical_sanity",
    "layer3_dependency",
    "layer4_transcript_quality_optional",
}
_IMPACT_VALUES = {"mapping_blocking", "transcript_quality_only"}
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
            "layer_tag": "layer1_canonical_recovery",
            "operational_impact": "mapping_blocking" if blocking else "transcript_quality_only",
            "provenance": "deterministic",
            "verification_required": False,
            "closure_requirement": None,
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
        target_key = _key_for_finding(finding)
        if not target_key:
            continue
        item = by_key[target_key]
        alternatives = _extract_alternatives_for_key(target_key, message)
        if alternatives:
            for alt in alternatives:
                _append_unique(item, "alternatives", alt)
        value = _extract_value_for_key(target_key, message)
        state = "disputed" if (_looks_disputed(message) or len(alternatives) > 1) else "candidate_found"
        _apply_observation(item=item, state=state, value=value, evidence_ref=str(finding.get("finding_id") or "").strip() or None)
        finding_type = str(finding.get("finding_type") or "").strip().lower()
        if finding_type == "plss_consistency" and state == "disputed":
            item["layer_tag"] = "layer2_canonical_sanity"

    # Candidate disagreement hints are no longer authoritative decision-path input.
    del disagreement_hints

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

    _attach_closure_requirements(working["items"], readiness_blocker=readiness_blocker)
    working["summary"] = _summary(working["items"])
    return working


def update_ledger_from_orient_baseline(
    *,
    ledger: dict[str, Any] | None,
    orient_items: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    working = _ensure_ledger_shape(ledger)
    by_key: dict[str, dict[str, Any]] = {
        str(item.get("key")): item
        for item in working["items"]
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    for raw in orient_items or []:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        if not key or key not in by_key:
            continue
        item = by_key[key]
        state = str(raw.get("state") or item.get("state") or "unknown").strip()
        if state not in {"unknown", "candidate_found", "verified", "disputed", "accepted_with_risk"}:
            state = "unknown"
        selected_value = raw.get("selected_value")
        alternatives = [str(v).strip() for v in list(raw.get("alternatives") or []) if str(v).strip()][:8]
        confidence = str(raw.get("confidence") or item.get("confidence") or "medium").strip().lower()
        layer_tag = str(raw.get("layer_tag") or item.get("layer_tag") or "layer1_canonical_recovery").strip().lower()
        if layer_tag not in _LAYER_TAG_VALUES:
            layer_tag = "layer1_canonical_recovery"
        operational_impact = str(raw.get("operational_impact") or item.get("operational_impact") or "mapping_blocking").strip().lower()
        if operational_impact not in _IMPACT_VALUES:
            operational_impact = "mapping_blocking" if bool(item.get("blocking")) else "transcript_quality_only"
        mapping_blocking = operational_impact == "mapping_blocking"
        block_reason = str(raw.get("block_reason") or "ambiguity").strip().lower()
        if block_reason not in {"ambiguity", "contradiction", "dependency"}:
            block_reason = "ambiguity"
        required_information = str(raw.get("required_information") or _required_information_for_key(key)).strip()
        minimal_user_action = str(raw.get("minimal_user_action") or _minimal_user_action_for_key(key, block_reason=block_reason)).strip()
        resolution_options = [str(v).strip() for v in list(raw.get("resolution_options") or []) if str(v).strip()][:8]
        evidence_refs = [str(v).strip() for v in list(raw.get("evidence_refs") or []) if str(v).strip()][:8]
        if "orient_llm" not in evidence_refs:
            evidence_refs.append("orient_llm")
        retrieval_attempted = bool(raw.get("retrieval_attempted"))
        retrieval_blocker = str(raw.get("retrieval_blocker") or "").strip() or None
        self_retrievable = str(raw.get("self_retrievable") or ("yes" if not retrieval_attempted else "conditional")).strip().lower()
        if self_retrievable not in {"yes", "conditional"}:
            self_retrievable = "conditional"
        attempt_summary = str(raw.get("attempt_summary") or _attempt_summary(state=state, evidence_count=len(evidence_refs))).strip()
        item["state"] = state
        if selected_value is not None:
            item["selected_value"] = selected_value
        if alternatives:
            item["alternatives"] = alternatives
        item["confidence"] = confidence
        item["layer_tag"] = layer_tag
        item["operational_impact"] = operational_impact
        item["blocking"] = mapping_blocking
        item["provenance"] = str(raw.get("provenance") or "orient_llm")
        item["verification_required"] = bool(raw.get("verification_required"))
        item["evidence_refs"] = evidence_refs
        unresolved = state in _UNRESOLVED_STATES
        if unresolved:
            item["closure_requirement"] = {
                "block_reason": block_reason,
                "mapping_blocking": mapping_blocking,
                "operational_impact": operational_impact,
                "required_information": required_information,
                "self_retrievable": self_retrievable,
                "retrieval_attempted": retrieval_attempted,
                "retrieval_blocker": retrieval_blocker,
                "minimal_user_action": minimal_user_action,
                "resolution_options": resolution_options,
                "evidence_refs": evidence_refs,
                "attempt_summary": attempt_summary,
            }
        else:
            item["closure_requirement"] = None
    _attach_closure_requirements(working["items"], readiness_blocker=None)
    working["summary"] = _summary(working["items"])
    return working


def ledger_snapshot_for_payload(ledger: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _ensure_ledger_shape(ledger)
    return {
        "items": [dict(item) for item in normalized["items"]],
        "summary": dict(normalized["summary"]),
    }


def derive_layer_statuses(
    *,
    mapping_ready: bool,
    validator_clean: bool,
    readiness_blocker: str | None,
) -> dict[str, str]:
    """Compact, deterministic layer statuses for terminal reporting."""
    blocker = str(readiness_blocker or "").strip().lower()
    if mapping_ready:
        statuses = {
            "layer1_canonical_recovery": "satisfied",
            "layer2_canonical_sanity": "satisfied",
            "layer3_dependency_completeness": "satisfied",
        }
        return statuses

    layer1 = "blocked" if (not validator_clean or blocker == "mapping_critical_image_verification_unresolved") else "unknown"
    layer2 = "blocked" if blocker.startswith("canonical_sanity_") else "unknown"
    layer3 = "blocked" if blocker.startswith("dependency_") else "unknown"
    statuses = {
        "layer1_canonical_recovery": layer1,
        "layer2_canonical_sanity": layer2,
        "layer3_dependency_completeness": layer3,
    }
    # Defensive normalization so downstream contracts remain predictable.
    for key, value in list(statuses.items()):
        if value not in _LAYER_STATUS_VALUES:
            statuses[key] = "unknown"
    return statuses


def closure_state_from_layers(layer_statuses: dict[str, Any]) -> str:
    if not isinstance(layer_statuses, dict):
        return "blocked"
    values = {str(v) for v in layer_statuses.values()}
    if values and values.issubset({"satisfied"}):
        return "achieved"
    return "blocked"


def unresolved_closure_requirements(ledger: dict[str, Any] | None) -> list[dict[str, Any]]:
    normalized = _ensure_ledger_shape(ledger)
    unresolved: list[dict[str, Any]] = []
    for item in normalized["items"]:
        if not isinstance(item, dict):
            continue
        requirement = item.get("closure_requirement")
        if not isinstance(requirement, dict):
            continue
        unresolved.append(
            {
                "key": item.get("key"),
                "label": item.get("label"),
                "state": item.get("state"),
                "blocking": bool(item.get("blocking")),
                "mapping_blocking": bool(
                    (requirement.get("mapping_blocking") if isinstance(requirement, dict) else False)
                    or item.get("blocking")
                ),
                "closure_requirement": dict(requirement),
            }
        )
    return unresolved


def unresolved_mapping_blocking_requirements(ledger: dict[str, Any] | None) -> list[dict[str, Any]]:
    unresolved = unresolved_closure_requirements(ledger)
    filtered: list[dict[str, Any]] = []
    for item in unresolved:
        if not isinstance(item, dict):
            continue
        if not bool(item.get("mapping_blocking")):
            continue
        requirement = item.get("closure_requirement")
        if not isinstance(requirement, dict):
            continue
        if not _is_material_mapping_blocking_requirement(item=item, requirement=requirement):
            continue
        filtered.append(item)
    return filtered


def has_unresolved_mapping_blocking_closure(ledger: dict[str, Any] | None) -> bool:
    return len(unresolved_mapping_blocking_requirements(ledger)) > 0


def is_unresolved_mapping_blocking_decision(
    ledger: dict[str, Any] | None,
    decision_key: str | None,
) -> bool:
    key = str(decision_key or "").strip().lower()
    if not key:
        return False
    unresolved = unresolved_mapping_blocking_requirements(ledger)
    return any(
        isinstance(item, dict) and str(item.get("key") or "").strip().lower() == key
        for item in unresolved
    )


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
            }
        )
    if not candidates:
        return None
    candidates.sort(
        key=lambda c: (
            0 if c["blocking"] else 1,
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
                "layer_tag": str(raw.get("layer_tag") or ("layer1_canonical_recovery" if bool(raw.get("blocking", blocking)) else "layer4_transcript_quality_optional")),
                "operational_impact": str(raw.get("operational_impact") or ("mapping_blocking" if bool(raw.get("blocking", blocking)) else "transcript_quality_only")),
                "provenance": str(raw.get("provenance") or "deterministic"),
                "verification_required": bool(raw.get("verification_required")),
                "closure_requirement": (
                    dict(raw.get("closure_requirement"))
                    if isinstance(raw.get("closure_requirement"), dict)
                    else None
                ),
            }
        )
    _attach_closure_requirements(items, readiness_blocker=None)
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
        if blocking and state in _UNRESOLVED_STATES:
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
    if " range " in f" {lower} ":
        return "range"
    if "township" in lower:
        return "township"
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


def _key_for_finding(finding: dict[str, Any]) -> str | None:
    finding_id = str(finding.get("finding_id") or "").strip().lower()
    finding_type = str(finding.get("finding_type") or "").strip().lower()
    message = str(finding.get("message") or "")
    blob = f"{finding_id} {finding_type} {message}".lower()
    if "range" in blob:
        return "range"
    if "township" in blob:
        return "township"
    if "section" in blob:
        return "section"
    if "bearing" in blob:
        return "tie_bearing"
    if "distance" in blob:
        return "tie_distance"
    if "acre" in blob:
        return "acreage"
    if "point of beginning" in blob or "closure" in blob or "pob" in blob:
        return "closure_or_pob"
    return _key_for_text(message)


def _extract_alternatives_for_key(key: str, text: str) -> list[str]:
    if key == "range":
        matches = re.findall(r"\brange[^0-9]{0,20}(\d{1,3})\s*(west|east|w|e)\b", text, re.IGNORECASE)
        values = [f"Range {num} {'West' if str(dir_).lower().startswith('w') else 'East'}" for num, dir_ in matches]
        return _dedupe_keep_order(values)
    if key == "township":
        matches = re.findall(r"\btownship[^0-9]{0,20}(\d{1,3})\s*(north|south|n|s)\b", text, re.IGNORECASE)
        values = [f"Township {num} {'North' if str(dir_).lower().startswith('n') else 'South'}" for num, dir_ in matches]
        return _dedupe_keep_order(values)
    if key == "section":
        matches = re.findall(r"\bsection[^0-9]{0,12}(\d{1,2})\b", text, re.IGNORECASE)
        values = [f"Section {num}" for num in matches]
        return _dedupe_keep_order(values)
    return []


def _dedupe_keep_order(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


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


def _attach_closure_requirements(items: list[dict[str, Any]], readiness_blocker: str | None) -> None:
    blocker = str(readiness_blocker or "").strip().lower()
    for item in items:
        if not isinstance(item, dict):
            continue
        state = str(item.get("state") or "unknown")
        blocking = bool(item.get("blocking"))
        unresolved = state in _UNRESOLVED_STATES
        requires = bool(unresolved)
        if not requires:
            item["closure_requirement"] = None
            continue
        item["closure_requirement"] = _build_closure_requirement(
            item=item,
            readiness_blocker=blocker,
        )


def _build_closure_requirement(*, item: dict[str, Any], readiness_blocker: str) -> dict[str, Any]:
    key = str(item.get("key") or "")
    state = str(item.get("state") or "unknown")
    alternatives = [str(v).strip() for v in list(item.get("alternatives") or []) if str(v).strip()]
    evidence_refs = [str(v).strip() for v in list(item.get("evidence_refs") or []) if str(v).strip()]
    retrieval_attempted = bool(evidence_refs)

    prior_requirement = item.get("closure_requirement") if isinstance(item.get("closure_requirement"), dict) else {}

    if readiness_blocker.startswith("dependency_"):
        block_reason = "dependency"
    elif str(prior_requirement.get("block_reason") or "") in {"ambiguity", "contradiction", "dependency"}:
        block_reason = str(prior_requirement.get("block_reason"))
    elif state == "disputed" and len(alternatives) > 1:
        block_reason = "contradiction"
    else:
        block_reason = "ambiguity"

    if block_reason == "dependency":
        self_retrievable = "conditional"
        retrieval_blocker = "external_dependency_not_available"
    elif retrieval_attempted:
        self_retrievable = "conditional"
        retrieval_blocker = None
    else:
        self_retrievable = "yes"
        retrieval_blocker = "insufficient_evidence_collected"

    options = alternatives[:4]
    if not options and item.get("selected_value"):
        options = [str(item.get("selected_value"))]
    prior_mapping_blocking = prior_requirement.get("mapping_blocking")
    mapping_blocking = bool(prior_mapping_blocking) if isinstance(prior_mapping_blocking, bool) else bool(item.get("blocking"))
    prior_operational_impact = str(prior_requirement.get("operational_impact") or "").strip()
    if prior_operational_impact in _IMPACT_VALUES:
        operational_impact = prior_operational_impact
    else:
        operational_impact = "mapping_blocking" if mapping_blocking else "transcript_quality_only"
    required_information = str(prior_requirement.get("required_information") or _required_information_for_key(key)).strip()
    minimal_user_action = str(
        prior_requirement.get("minimal_user_action") or _minimal_user_action_for_key(key, block_reason=block_reason)
    ).strip()
    resolution_options = [str(v).strip() for v in list(prior_requirement.get("resolution_options") or options) if str(v).strip()]
    prior_self_retrievable = str(prior_requirement.get("self_retrievable") or "").strip()
    if prior_self_retrievable in {"yes", "conditional"}:
        self_retrievable = prior_self_retrievable
    prior_retrieval_attempted = prior_requirement.get("retrieval_attempted")
    if isinstance(prior_retrieval_attempted, bool):
        retrieval_attempted = prior_retrieval_attempted
    prior_retrieval_blocker = str(prior_requirement.get("retrieval_blocker") or "").strip() or None
    if prior_retrieval_blocker:
        retrieval_blocker = prior_retrieval_blocker

    return {
        "block_reason": block_reason,
        "mapping_blocking": mapping_blocking,
        "operational_impact": operational_impact,
        "required_information": required_information,
        "self_retrievable": self_retrievable,
        "retrieval_attempted": retrieval_attempted,
        "retrieval_blocker": retrieval_blocker,
        "minimal_user_action": minimal_user_action,
        "resolution_options": resolution_options,
        "evidence_refs": evidence_refs[:8],
        "attempt_summary": _attempt_summary(state=state, evidence_count=len(evidence_refs)),
    }


def _required_information_for_key(key: str) -> str:
    if key == "township":
        return "Confirm exact township token (number and N/S suffix)."
    if key == "range":
        return "Confirm exact range token (number and E/W suffix)."
    if key == "section":
        return "Confirm section number token."
    if key == "tie_distance":
        return "Confirm tie distance numeric value and unit."
    if key == "tie_bearing":
        return "Confirm tie bearing notation (quadrant + degrees)."
    if key == "acreage":
        return "Confirm acreage numeric value (optional for mapping if geometry is otherwise closed)."
    if key == "closure_or_pob":
        return "Confirm closure/POB reference language."
    return "Confirm unresolved mapping-critical token."


def _minimal_user_action_for_key(key: str, *, block_reason: str) -> str:
    if block_reason == "dependency":
        return "Provide or identify the referenced external record so mapping can proceed."
    if key == "acreage":
        return "Confirm acreage if available, or defer if mapping geometry is already sufficient."
    if key in {"range", "township", "section", "tie_distance", "tie_bearing", "acreage"}:
        return "Select the correct value from options, or enter Other if none match."
    return "Confirm the correct clause value or provide corrected text."


def _attempt_summary(*, state: str, evidence_count: int) -> str:
    if evidence_count <= 0:
        return f"No evidence checks recorded yet; state remains {state}."
    if state == "disputed":
        return f"Collected {evidence_count} evidence signal(s), but they remain conflicting."
    return f"Collected {evidence_count} evidence signal(s), but resolution is still incomplete."


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


def _is_material_mapping_blocking_requirement(*, item: dict[str, Any], requirement: dict[str, Any]) -> bool:
    state = str(item.get("state") or "unknown").strip().lower()
    if state in {"disputed", "accepted_with_risk"}:
        return True
    if isinstance(requirement.get("resolution_options"), list) and len(requirement.get("resolution_options") or []) > 0:
        return True
    if str(item.get("selected_value") or "").strip():
        return True
    if isinstance(requirement.get("evidence_refs"), list) and len(requirement.get("evidence_refs") or []) > 0:
        return True
    if bool(item.get("verification_required")):
        return True
    provenance = str(item.get("provenance") or "").strip().lower()
    if provenance and provenance != "deterministic":
        return True
    return False
