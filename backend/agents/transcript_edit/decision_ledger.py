from __future__ import annotations

import re
import time
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
_SOURCE_COMPLETENESS_VALUES = {"complete", "partial_truncated", "partial_missing_context", "unknown"}
_SCOPE_ID_VALUES = {"target_scope", "outside_target_scope", "unknown_scope"}
_SCOPE_STATUS_VALUES = {"in_target", "outside_target", "unknown"}
_APPROVED_SCOPE_PROOF_CODES = {
    "explicit_outside_target_text",
    "source_truncation_boundary",
    "image_confirms_post_target_cutoff",
    "operator_marked_outside_target",
}
_SCOPE_CLOSURE_STATE_VALUES = {"achieved", "partial", "blocked", "not_attempted"}
_DECISION_PRIORITY: dict[str, int] = {
    "range": 0,
    "township": 1,
    "section": 2,
    "tie_distance": 3,
    "tie_bearing": 4,
    "closure_or_pob": 5,
    "acreage": 6,
}
_DECISION_KEYS = {spec[0] for spec in _DECISION_SPECS}


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
            "scope_id": "unknown_scope",
            "scope_label": "Unknown Scope",
            "scope_priority": 50,
            "in_target_scope": None,
            "scope_proof": [],
            "closure_requirement": None,
        }
        for key, label, blocking in _DECISION_SPECS
    ]
    ledger = {
        "items": items,
        "summary": _summary(items),
        "external_context_injections": [],
        "source_completeness": "unknown",
        "source_completeness_reason": None,
        "source_limitations": [],
        "scope_summaries": {},
        "blocker_feedback_state": {},
    }
    ledger["scope_summaries"] = _compute_scope_summaries(ledger)
    ledger["blocker_feedback_state"] = _compute_blocker_feedback_state(ledger)
    return ledger


def update_ledger_from_iteration(
    *,
    ledger: dict[str, Any] | None,
    findings: list[dict[str, Any]] | None = None,
    disagreement_hints: dict[str, Any] | None = None,
    image_results: list[dict[str, Any]] | None = None,
    readiness_blocker: str | None = None,
) -> dict[str, Any]:
    working = _ensure_ledger_shape(ledger)
    prior_source_completeness = str(working.get("source_completeness") or "unknown").strip().lower()
    source_completeness = prior_source_completeness if prior_source_completeness in _SOURCE_COMPLETENESS_VALUES else "unknown"
    source_completeness_reason = str(working.get("source_completeness_reason") or "").strip() or None
    source_limitations = [
        str(v).strip()
        for v in list(working.get("source_limitations") or [])
        if str(v).strip()
    ][:12]
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
            source_completeness, source_completeness_reason, source_limitations = _merge_source_completeness_signal(
                source_completeness=source_completeness,
                source_completeness_reason=source_completeness_reason,
                source_limitations=source_limitations,
                signal=_extract_source_completeness_signal(finding),
            )
            continue
        item = by_key[target_key]
        _apply_scope_from_signal(item=item, signal=finding)
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
        source_completeness, source_completeness_reason, source_limitations = _merge_source_completeness_signal(
            source_completeness=source_completeness,
            source_completeness_reason=source_completeness_reason,
            source_limitations=source_limitations,
            signal=_extract_source_completeness_signal(finding),
        )

    # Candidate disagreement hints are no longer authoritative decision-path input.
    del disagreement_hints

    for result in image_results or []:
        if not isinstance(result, dict):
            continue
        check_id = str(result.get("check_id") or "").lower()
        status = str(result.get("status") or "").lower()
        observed = str(result.get("observed_text") or "").strip() or None
        query = str(result.get("query") or "").strip()
        result_key = str(result.get("decision_key") or "").strip().lower()
        target_key = result_key if result_key in _DECISION_KEYS else _key_for_check_id(check_id)
        if not target_key:
            source_completeness, source_completeness_reason, source_limitations = _merge_source_completeness_signal(
                source_completeness=source_completeness,
                source_completeness_reason=source_completeness_reason,
                source_limitations=source_limitations,
                signal=_extract_source_completeness_signal(result),
            )
            continue
        item = by_key[target_key]
        _apply_scope_from_signal(item=item, signal=result)
        image_alternatives = _extract_alternatives_for_key(target_key, f"{query} {observed or ''}".strip())
        if image_alternatives:
            for alt in image_alternatives:
                _append_unique(item, "alternatives", alt)
        if len(image_alternatives) > 1:
            _apply_observation(item=item, state="disputed", value=observed, evidence_ref=check_id or None)
            if target_key in {"range", "township", "section"}:
                item["layer_tag"] = "layer2_canonical_sanity"
            continue
        if status in _CONFIRMED_STATUSES:
            _apply_observation(item=item, state="verified", value=observed, evidence_ref=check_id or None)
        elif status in _DISPUTED_STATUSES:
            _apply_observation(item=item, state="disputed", value=observed, evidence_ref=check_id or None)
        source_completeness, source_completeness_reason, source_limitations = _merge_source_completeness_signal(
            source_completeness=source_completeness,
            source_completeness_reason=source_completeness_reason,
            source_limitations=source_limitations,
            signal=_extract_source_completeness_signal(result),
        )

    if readiness_blocker == "mapping_critical_image_verification_unresolved":
        for item in working["items"]:
            if bool(item.get("blocking")) and str(item.get("state") or "") == "unknown":
                item["state"] = "accepted_with_risk"
                _append_unique(item, "evidence_refs", "terminal_readiness_blocker")

    _attach_closure_requirements(working["items"], readiness_blocker=readiness_blocker)
    _apply_scope_defaults(working["items"])
    working["source_completeness"] = source_completeness
    working["source_completeness_reason"] = source_completeness_reason
    working["source_limitations"] = source_limitations[:12]
    working["summary"] = _summary(working["items"])
    working["scope_summaries"] = _compute_scope_summaries(working)
    working["blocker_feedback_state"] = _compute_blocker_feedback_state(working)
    return working


def update_ledger_from_orient_baseline(
    *,
    ledger: dict[str, Any] | None,
    orient_items: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    working = _ensure_ledger_shape(ledger)
    prior_source_completeness = str(working.get("source_completeness") or "unknown").strip().lower()
    source_completeness = prior_source_completeness if prior_source_completeness in _SOURCE_COMPLETENESS_VALUES else "unknown"
    source_completeness_reason = str(working.get("source_completeness_reason") or "").strip() or None
    source_limitations = [
        str(v).strip()
        for v in list(working.get("source_limitations") or [])
        if str(v).strip()
    ][:12]
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
        _apply_scope_from_signal(item=item, signal=raw)
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
        source_completeness, source_completeness_reason, source_limitations = _merge_source_completeness_signal(
            source_completeness=source_completeness,
            source_completeness_reason=source_completeness_reason,
            source_limitations=source_limitations,
            signal=_extract_source_completeness_signal(raw),
        )
    _attach_closure_requirements(working["items"], readiness_blocker=None)
    _apply_scope_defaults(working["items"])
    working["source_completeness"] = source_completeness
    working["source_completeness_reason"] = source_completeness_reason
    working["source_limitations"] = source_limitations[:12]
    working["summary"] = _summary(working["items"])
    working["scope_summaries"] = _compute_scope_summaries(working)
    working["blocker_feedback_state"] = _compute_blocker_feedback_state(working)
    return working


def ledger_snapshot_for_payload(ledger: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _ensure_ledger_shape(ledger)
    return {
        "items": [dict(item) for item in normalized["items"]],
        "summary": dict(normalized["summary"]),
        "source_completeness": str(normalized.get("source_completeness") or "unknown"),
        "source_completeness_reason": normalized.get("source_completeness_reason"),
        "source_limitations": [
            str(v)
            for v in list(normalized.get("source_limitations") or [])
            if str(v).strip()
        ][:12],
        "scope_summaries": dict(normalized.get("scope_summaries") or {}),
        "blocker_feedback_state": dict(normalized.get("blocker_feedback_state") or {}),
        "external_context_injections": [
            dict(row)
            for row in list(normalized.get("external_context_injections") or [])
            if isinstance(row, dict)
        ],
    }


def list_external_context_injections(
    ledger: dict[str, Any] | None,
    *,
    decision_key: str | None = None,
    type_filter: str | None = None,
    lifecycle_states: set[str] | None = None,
) -> list[dict[str, Any]]:
    normalized = _ensure_ledger_shape(ledger)
    rows = normalized.get("external_context_injections")
    if not isinstance(rows, list):
        return []
    key = str(decision_key or "").strip().lower()
    type_value = str(type_filter or "").strip().lower()
    states = {str(v).strip().lower() for v in (lifecycle_states or set()) if str(v).strip()}
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_key = str(row.get("decision_key") or "").strip().lower()
        if key and row_key != key:
            continue
        row_type = str(row.get("type") or "").strip().lower()
        if type_value and row_type != type_value:
            continue
        row_state = str(row.get("lifecycle_state") or "").strip().lower()
        if states and row_state not in states:
            continue
        out.append(dict(row))
    return out


def upsert_human_resolution_ticket(
    *,
    ledger: dict[str, Any] | None,
    ticket_id: str,
    decision_key: str,
    lifecycle_state: str,
    strength: str = "binding",
    payload: dict[str, Any] | None = None,
    relevance: str | None = None,
    answered_at: int | None = None,
    integrated_at: int | None = None,
) -> dict[str, Any]:
    working = _ensure_ledger_shape(ledger)
    rows = working.get("external_context_injections")
    if not isinstance(rows, list):
        rows = []
        working["external_context_injections"] = rows
    ticket = str(ticket_id or "").strip()
    key = str(decision_key or "").strip().lower()
    state = str(lifecycle_state or "").strip().lower()
    if not ticket or not key or not state:
        working["blocker_feedback_state"] = _compute_blocker_feedback_state(working)
        return working
    now = int(time.time())
    existing = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "").strip().lower() != "human_resolution_ticket":
            continue
        if str(row.get("ticket_id") or "").strip() == ticket and str(row.get("decision_key") or "").strip().lower() == key:
            existing = row
            break
    if existing is None:
        existing = {
            "type": "human_resolution_ticket",
            "ticket_id": ticket,
            "decision_key": key,
            "created_at": now,
        }
        rows.append(existing)
    existing["lifecycle_state"] = state
    existing["strength"] = str(strength or "binding").strip().lower() or "binding"
    existing["updated_at"] = now
    existing["payload"] = dict(payload) if isinstance(payload, dict) else {}
    if relevance is not None:
        existing["relevance"] = str(relevance).strip().lower() or None
    if answered_at is not None:
        existing["answered_at"] = int(answered_at)
    if integrated_at is not None:
        existing["integrated_at"] = int(integrated_at)
    working["blocker_feedback_state"] = _compute_blocker_feedback_state(working)
    return working


def mark_human_resolution_ticket_state(
    *,
    ledger: dict[str, Any] | None,
    ticket_id: str,
    decision_key: str,
    lifecycle_state: str,
    integrated: bool = False,
    relevance: str | None = None,
) -> dict[str, Any]:
    working = _ensure_ledger_shape(ledger)
    rows = working.get("external_context_injections")
    if not isinstance(rows, list):
        working["blocker_feedback_state"] = _compute_blocker_feedback_state(working)
        return working
    ticket = str(ticket_id or "").strip()
    key = str(decision_key or "").strip().lower()
    state = str(lifecycle_state or "").strip().lower()
    now = int(time.time())
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "").strip().lower() != "human_resolution_ticket":
            continue
        if str(row.get("ticket_id") or "").strip() != ticket:
            continue
        if str(row.get("decision_key") or "").strip().lower() != key:
            continue
        row["lifecycle_state"] = state
        row["updated_at"] = now
        if integrated:
            row["integrated_at"] = now
        if relevance is not None:
            row["relevance"] = str(relevance).strip().lower() or None
        break
    working["blocker_feedback_state"] = _compute_blocker_feedback_state(working)
    return working


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
    source_completeness = str(normalized.get("source_completeness") or "unknown").strip().lower()
    unresolved: list[dict[str, Any]] = []
    for item in normalized["items"]:
        if not isinstance(item, dict):
            continue
        requirement = item.get("closure_requirement")
        if not isinstance(requirement, dict):
            continue
        scope_status = _normalize_scope_status(requirement.get("scope_status"))
        scope_proof = _normalize_scope_proof_codes(requirement.get("scope_proof"))
        if scope_status == "outside_target" and not scope_proof:
            scope_status = "unknown"
        scope_id = _scope_id_from_scope_status(scope_status)
        unresolved.append(
            {
                "key": item.get("key"),
                "label": item.get("label"),
                "state": item.get("state"),
                "scope_id": scope_id,
                "scope_label": str(item.get("scope_label") or _scope_label(scope_id)),
                "scope_priority": _read_scope_priority(item.get("scope_priority")),
                "in_target_scope": True if scope_status == "in_target" else False if scope_status == "outside_target" else None,
                "scope_status": scope_status,
                "scope_proof": scope_proof,
                "blocking": bool(item.get("blocking")),
                "mapping_blocking": bool(
                    (requirement.get("mapping_blocking") if isinstance(requirement, dict) else False)
                    or item.get("blocking")
                ),
                "incomplete_source_residual": bool(
                    scope_status == "outside_target"
                    and source_completeness in {"partial_truncated", "partial_missing_context"}
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


def unresolved_target_scope_mapping_blocking_requirements(ledger: dict[str, Any] | None) -> list[dict[str, Any]]:
    unresolved = unresolved_mapping_blocking_requirements(ledger)
    out: list[dict[str, Any]] = []
    for item in unresolved:
        if not isinstance(item, dict):
            continue
        scope_status = _normalize_scope_status(
            (item.get("closure_requirement") or {}).get("scope_status")
            if isinstance(item.get("closure_requirement"), dict)
            else item.get("scope_status")
        )
        if scope_status == "outside_target":
            continue
        out.append(item)
    return out


def unresolved_outside_target_scope_mapping_blocking_requirements(ledger: dict[str, Any] | None) -> list[dict[str, Any]]:
    unresolved = unresolved_mapping_blocking_requirements(ledger)
    out: list[dict[str, Any]] = []
    for item in unresolved:
        if not isinstance(item, dict):
            continue
        scope_status = _normalize_scope_status(
            (item.get("closure_requirement") or {}).get("scope_status")
            if isinstance(item.get("closure_requirement"), dict)
            else item.get("scope_status")
        )
        scope_proof = _normalize_scope_proof_codes(
            (item.get("closure_requirement") or {}).get("scope_proof")
            if isinstance(item.get("closure_requirement"), dict)
            else item.get("scope_proof")
        )
        if scope_status != "outside_target" or not scope_proof:
            continue
        out.append(item)
    return out


def has_unresolved_target_scope_mapping_blocking_closure(ledger: dict[str, Any] | None) -> bool:
    return len(unresolved_target_scope_mapping_blocking_requirements(ledger)) > 0


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


def is_unresolved_target_scope_mapping_blocking_decision(
    ledger: dict[str, Any] | None,
    decision_key: str | None,
) -> bool:
    key = str(decision_key or "").strip().lower()
    if not key:
        return False
    unresolved = unresolved_target_scope_mapping_blocking_requirements(ledger)
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


def scope_summaries_from_ledger(ledger: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _ensure_ledger_shape(ledger)
    return dict(normalized.get("scope_summaries") or {})


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
                "scope_id": _normalized_scope_id(raw.get("scope_id")),
                "scope_label": str(raw.get("scope_label") or _scope_label(_normalized_scope_id(raw.get("scope_id")))),
                "scope_priority": _read_scope_priority(raw.get("scope_priority")),
                "in_target_scope": _normalized_in_target_scope(raw.get("in_target_scope")),
                "scope_proof": _normalize_scope_proof_codes(raw.get("scope_proof")),
                "closure_requirement": (
                    dict(raw.get("closure_requirement"))
                    if isinstance(raw.get("closure_requirement"), dict)
                    else None
                ),
            }
        )
    raw_injections = ledger.get("external_context_injections") if isinstance(ledger, dict) else []
    injections = [dict(row) for row in list(raw_injections or []) if isinstance(row, dict)][-60:]
    _attach_closure_requirements(items, readiness_blocker=None)
    _apply_scope_defaults(items)
    source_completeness = str(ledger.get("source_completeness") or "unknown").strip().lower() if isinstance(ledger, dict) else "unknown"
    if source_completeness not in _SOURCE_COMPLETENESS_VALUES:
        source_completeness = "unknown"
    source_limitations = [
        str(v).strip()
        for v in list((ledger.get("source_limitations") if isinstance(ledger, dict) else []) or [])
        if str(v).strip()
    ][:12]
    out = {
        "items": items,
        "summary": _summary(items),
        "external_context_injections": injections,
        "source_completeness": source_completeness,
        "source_completeness_reason": (
            str(ledger.get("source_completeness_reason") or "").strip() or None
            if isinstance(ledger, dict)
            else None
        ),
        "source_limitations": source_limitations,
        "scope_summaries": {},
        "blocker_feedback_state": {},
    }
    out["scope_summaries"] = _compute_scope_summaries(out)
    out["blocker_feedback_state"] = _compute_blocker_feedback_state(out)
    return out


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
    # Preserve unresolved contradiction state until deterministic reconciliation
    # explicitly clears it; a single image "match" should not auto-collapse disputes.
    if current_state == "disputed" and observed_state == "verified":
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
        long_matches = re.findall(r"\brange[^0-9]{0,20}(\d{1,3})\s*(west|east|w|e)\b", text, re.IGNORECASE)
        short_matches = re.findall(r"\br\s*(\d{1,3})\s*([we])\b", text, re.IGNORECASE)
        matches = [*long_matches, *short_matches]
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
    if "plss_range" in check_id:
        return "range"
    if "plss_township" in check_id:
        return "township"
    if "plss_section" in check_id:
        return "section"
    if "range" in check_id:
        return "range"
    if "township" in check_id:
        return "township"
    if "section" in check_id:
        return "section"
    if "distance" in check_id:
        return "tie_distance"
    if "bearing" in check_id:
        return "tie_bearing"
    if "acreage" in check_id:
        return "acreage"
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
        requirement = _build_closure_requirement(
            item=item,
            readiness_blocker=blocker,
        )
        item["closure_requirement"] = requirement
        scope_status = str(requirement.get("scope_status") or "unknown")
        scope_proof = _normalize_scope_proof_codes(requirement.get("scope_proof"))
        item["scope_proof"] = scope_proof
        item["scope_id"] = _scope_id_from_scope_status(scope_status)
        item["scope_label"] = _scope_label(item["scope_id"])
        if scope_status == "in_target":
            item["in_target_scope"] = True
        elif scope_status == "outside_target":
            item["in_target_scope"] = False
        else:
            item["in_target_scope"] = None


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
    prior_scope_status = _normalize_scope_status(prior_requirement.get("scope_status"))
    inferred_scope_status = _scope_status_from_item_scope_fields(item)
    scope_status = inferred_scope_status
    if scope_status == "unknown" and prior_scope_status in {"in_target", "outside_target"}:
        scope_status = prior_scope_status
    scope_proof = _normalize_scope_proof_codes(item.get("scope_proof"))
    if not scope_proof:
        scope_proof = _normalize_scope_proof_codes(prior_requirement.get("scope_proof"))
    if scope_status == "outside_target" and not scope_proof:
        scope_status = "unknown"
    if scope_status != "outside_target":
        scope_proof = []

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
        "scope_status": scope_status,
        "scope_proof": scope_proof,
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


def _normalized_scope_id(raw_scope_id: Any) -> str:
    scope_id = str(raw_scope_id or "").strip().lower()
    if scope_id in _SCOPE_ID_VALUES:
        return scope_id
    return "unknown_scope"


def _scope_id_from_scope_status(scope_status: str) -> str:
    status = _normalize_scope_status(scope_status)
    if status == "in_target":
        return "target_scope"
    if status == "outside_target":
        return "outside_target_scope"
    return "unknown_scope"


def _normalize_scope_status(raw_scope_status: Any) -> str:
    status = str(raw_scope_status or "").strip().lower()
    if status in _SCOPE_STATUS_VALUES:
        return status
    if status in {"target_scope", "in_target_scope"}:
        return "in_target"
    if status in {"outside_target_scope", "out_of_scope"}:
        return "outside_target"
    return "unknown"


def _scope_status_from_item_scope_fields(item: dict[str, Any]) -> str:
    scope_id = _normalized_scope_id(item.get("scope_id"))
    in_target_scope = _normalized_in_target_scope(item.get("in_target_scope"))
    if scope_id == "target_scope" or in_target_scope is True:
        return "in_target"
    if scope_id == "outside_target_scope" or in_target_scope is False:
        return "outside_target"
    return "unknown"


def _normalize_scope_proof_codes(raw_scope_proof: Any) -> list[str]:
    codes: list[str] = []
    for entry in list(raw_scope_proof or []):
        code = str(entry or "").strip().lower()
        if code not in _APPROVED_SCOPE_PROOF_CODES:
            continue
        if code in codes:
            continue
        codes.append(code)
    return codes[:6]


def _merge_scope_proof_codes(base_codes: list[str], extra_codes: list[str]) -> list[str]:
    merged = list(base_codes)
    for code in extra_codes:
        normalized = str(code or "").strip().lower()
        if normalized not in _APPROVED_SCOPE_PROOF_CODES:
            continue
        if normalized in merged:
            continue
        merged.append(normalized)
    return merged[:6]


def _scope_proof_codes_from_signal(signal: dict[str, Any]) -> list[str]:
    if not isinstance(signal, dict):
        return []
    codes: list[str] = []
    if bool(signal.get("operator_marked_outside_target")):
        codes.append("operator_marked_outside_target")
    blob = " ".join(
        [
            str(signal.get("message") or ""),
            str(signal.get("reason") or ""),
            str(signal.get("query") or ""),
            str(signal.get("observed_text") or ""),
        ]
    ).lower()
    if "outside target" in blob or "outside target scope" in blob:
        codes.append("explicit_outside_target_text")
    if "truncation boundary" in blob or "cutoff boundary" in blob or "post-target cutoff" in blob:
        codes.append("source_truncation_boundary")
    if (
        str(signal.get("status") or "").strip().lower() in _CONFIRMED_STATUSES
        and ("post-target cutoff" in blob or "after target cutoff" in blob)
    ):
        codes.append("image_confirms_post_target_cutoff")
    return _normalize_scope_proof_codes(codes)


def _read_scope_priority(raw_scope_priority: Any) -> int:
    try:
        value = int(raw_scope_priority)
    except Exception:
        value = 50
    return max(0, min(100, value))


def _scope_label(scope_id: str) -> str:
    normalized = _normalized_scope_id(scope_id)
    if normalized == "target_scope":
        return "Target Scope"
    if normalized == "outside_target_scope":
        return "Outside Target Scope"
    return "Unknown Scope"


def _scope_rank(scope_id: str) -> int:
    normalized = _normalized_scope_id(scope_id)
    if normalized == "target_scope":
        return 0
    if normalized == "unknown_scope":
        return 1
    return 2


def _scope_id_for_item(item: dict[str, Any]) -> str:
    scope_id = _normalized_scope_id(item.get("scope_id"))
    if scope_id != "unknown_scope":
        if scope_id == "outside_target_scope" and not _normalize_scope_proof_codes(item.get("scope_proof")):
            return "unknown_scope"
        return scope_id
    in_target_scope = item.get("in_target_scope")
    if in_target_scope is True:
        return "target_scope"
    if in_target_scope is False:
        if _normalize_scope_proof_codes(item.get("scope_proof")):
            return "outside_target_scope"
        return "unknown_scope"
    return "unknown_scope"


def _normalized_in_target_scope(raw_value: Any) -> bool | None:
    if isinstance(raw_value, bool):
        return raw_value
    text = str(raw_value or "").strip().lower()
    if text in {"true", "yes", "target_scope"}:
        return True
    if text in {"false", "no", "outside_target_scope"}:
        return False
    return None


def _apply_scope_from_signal(*, item: dict[str, Any], signal: dict[str, Any]) -> None:
    if not isinstance(item, dict) or not isinstance(signal, dict):
        return
    proof_codes = _normalize_scope_proof_codes(signal.get("scope_proof"))
    proof_codes = _merge_scope_proof_codes(
        proof_codes,
        _scope_proof_codes_from_signal(signal),
    )
    explicit_scope_status = _normalize_scope_status(signal.get("scope_status"))
    explicit_scope_id = _normalized_scope_id(signal.get("scope_id"))
    in_target_scope = _normalized_in_target_scope(signal.get("in_target_scope"))
    scope_status = "unknown"
    if explicit_scope_status in _SCOPE_STATUS_VALUES:
        scope_status = explicit_scope_status
    elif explicit_scope_id in {"target_scope", "outside_target_scope"}:
        scope_status = "in_target" if explicit_scope_id == "target_scope" else "outside_target"
    elif in_target_scope is not None:
        scope_status = "in_target" if in_target_scope else "outside_target"
    if scope_status == "outside_target" and not proof_codes:
        scope_status = "unknown"
    if scope_status == "unknown" and proof_codes:
        if any(
            code in proof_codes
            for code in {
                "explicit_outside_target_text",
                "image_confirms_post_target_cutoff",
                "operator_marked_outside_target",
                "source_truncation_boundary",
            }
        ):
            scope_status = "outside_target"
    if scope_status == "outside_target":
        item["scope_id"] = "outside_target_scope"
        item["scope_label"] = str(signal.get("scope_label") or "Outside Target Scope")
        item["scope_priority"] = _read_scope_priority(
            signal.get("scope_priority")
            if signal.get("scope_priority") is not None
            else 80
        )
        item["in_target_scope"] = False
        item["scope_proof"] = proof_codes
        return
    if scope_status == "in_target":
        item["scope_id"] = "target_scope"
        item["scope_label"] = str(signal.get("scope_label") or "Target Scope")
        item["scope_priority"] = _read_scope_priority(
            signal.get("scope_priority")
            if signal.get("scope_priority") is not None
            else 0
        )
        item["in_target_scope"] = True
        item["scope_proof"] = []


def _apply_scope_defaults(items: list[dict[str, Any]]) -> None:
    for item in items:
        if not isinstance(item, dict):
            continue
        scope_id = _scope_id_for_item(item)
        scope_proof = _normalize_scope_proof_codes(item.get("scope_proof"))
        if scope_id == "outside_target_scope" and not scope_proof:
            scope_id = "unknown_scope"
        item["scope_id"] = scope_id
        item["scope_label"] = str(item.get("scope_label") or _scope_label(scope_id))
        item["scope_proof"] = scope_proof if scope_id == "outside_target_scope" else []
        priority_default = 0 if scope_id == "target_scope" else 80 if scope_id == "outside_target_scope" else 50
        item["scope_priority"] = _read_scope_priority(
            item.get("scope_priority") if item.get("scope_priority") is not None else priority_default
        )
        if item.get("in_target_scope") is None:
            if scope_id == "target_scope":
                item["in_target_scope"] = True
            elif scope_id == "outside_target_scope":
                item["in_target_scope"] = False
            else:
                item["in_target_scope"] = None


def _extract_source_completeness_signal(signal: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(signal, dict):
        return None
    explicit = str(signal.get("source_completeness") or "").strip().lower()
    if explicit in _SOURCE_COMPLETENESS_VALUES:
        limitations = [
            str(v).strip()
            for v in list(signal.get("source_limitations") or [])
            if str(v).strip()
        ][:6]
        return {
            "source_completeness": explicit,
            "reason": str(signal.get("source_completeness_reason") or "").strip() or None,
            "limitations": limitations,
        }

    blob = " ".join(
        [
            str(signal.get("message") or ""),
            str(signal.get("reason") or ""),
            str(signal.get("query") or ""),
            str(signal.get("observed_text") or ""),
            str(signal.get("retrieval_blocker") or ""),
        ]
    ).lower()
    if any(
        token in blob
        for token in {
            "truncated",
            "cut off",
            "cropped",
            "image ends",
            "missing lower",
            "below visible",
            "not visible in source",
        }
    ):
        return {
            "source_completeness": "partial_truncated",
            "reason": "Source image appears truncated or cut off.",
            "limitations": ["Source content appears cut off; lower-page context is unavailable."],
        }
    if any(
        token in blob
        for token in {
            "missing context",
            "context unavailable",
            "referenced record unavailable",
            "external dependency not available",
            "dependency missing",
        }
    ):
        return {
            "source_completeness": "partial_missing_context",
            "reason": "Required context is missing from the available source set.",
            "limitations": ["Missing context prevents full-document closure."],
        }
    return None


def _merge_source_completeness_signal(
    *,
    source_completeness: str,
    source_completeness_reason: str | None,
    source_limitations: list[str],
    signal: dict[str, Any] | None,
) -> tuple[str, str | None, list[str]]:
    if not isinstance(signal, dict):
        return source_completeness, source_completeness_reason, source_limitations
    incoming = str(signal.get("source_completeness") or "").strip().lower()
    if incoming not in _SOURCE_COMPLETENESS_VALUES:
        return source_completeness, source_completeness_reason, source_limitations
    priority = {"unknown": 0, "complete": 1, "partial_missing_context": 2, "partial_truncated": 3}
    current_priority = priority.get(source_completeness, 0)
    incoming_priority = priority.get(incoming, 0)
    merged = source_completeness
    if incoming_priority >= current_priority:
        merged = incoming
    merged_reason = source_completeness_reason
    incoming_reason = str(signal.get("reason") or "").strip() or None
    if incoming_reason and merged == incoming:
        merged_reason = incoming_reason
    limitations = list(source_limitations)
    for limitation in list(signal.get("limitations") or []):
        text = str(limitation).strip()
        if not text:
            continue
        if text in limitations:
            continue
        limitations.append(text)
    return merged, merged_reason, limitations[:12]


def _compute_scope_summaries(ledger: dict[str, Any]) -> dict[str, Any]:
    items = ledger.get("items") if isinstance(ledger, dict) else []
    if not isinstance(items, list):
        return {}
    source_completeness = str(ledger.get("source_completeness") or "unknown").strip().lower()
    rows: dict[str, dict[str, Any]] = {
        "target_scope": {"scope_id": "target_scope", "scope_label": "Target Scope", "scope_closure_state": "not_attempted", "unresolved_count": 0, "mapping_blocking_unresolved_count": 0, "resolved_count": 0},
        "outside_target_scope": {"scope_id": "outside_target_scope", "scope_label": "Outside Target Scope", "scope_closure_state": "not_attempted", "unresolved_count": 0, "mapping_blocking_unresolved_count": 0, "resolved_count": 0},
        "unknown_scope": {"scope_id": "unknown_scope", "scope_label": "Unknown Scope", "scope_closure_state": "not_attempted", "unresolved_count": 0, "mapping_blocking_unresolved_count": 0, "resolved_count": 0},
    }
    for item in items:
        if not isinstance(item, dict):
            continue
        requirement = item.get("closure_requirement") if isinstance(item.get("closure_requirement"), dict) else {}
        scope_status = _normalize_scope_status(requirement.get("scope_status"))
        if scope_status == "unknown":
            scope_status = _scope_status_from_item_scope_fields(item)
        state = str(item.get("state") or "unknown").strip().lower()
        if (
            scope_status == "unknown"
            and state not in _UNRESOLVED_STATES
            and bool(item.get("blocking"))
            and len([str(v).strip() for v in list(item.get("evidence_refs") or []) if str(v).strip()]) > 0
        ):
            scope_status = "in_target"
        scope_proof = _normalize_scope_proof_codes(requirement.get("scope_proof"))
        if not scope_proof:
            scope_proof = _normalize_scope_proof_codes(item.get("scope_proof"))
        if scope_status == "outside_target" and not scope_proof:
            scope_status = "unknown"
        scope_id = _scope_id_from_scope_status(scope_status)
        row = rows.get(scope_id)
        if not isinstance(row, dict):
            continue
        unresolved = state in _UNRESOLVED_STATES
        if unresolved:
            row["unresolved_count"] = int(row["unresolved_count"]) + 1
        else:
            row["resolved_count"] = int(row["resolved_count"]) + 1
        if unresolved and bool(item.get("blocking")):
            row["mapping_blocking_unresolved_count"] = int(row["mapping_blocking_unresolved_count"]) + 1
    for scope_id, row in rows.items():
        unresolved_count = int(row.get("unresolved_count") or 0)
        mapping_unresolved = int(row.get("mapping_blocking_unresolved_count") or 0)
        resolved_count = int(row.get("resolved_count") or 0)
        if unresolved_count <= 0 and resolved_count <= 0:
            scope_state = "not_attempted"
        elif mapping_unresolved > 0:
            if scope_id == "outside_target_scope" and source_completeness in {"partial_truncated", "partial_missing_context"}:
                scope_state = "partial"
            else:
                scope_state = "blocked"
        elif unresolved_count > 0:
            scope_state = "partial"
        else:
            scope_state = "achieved"
        if scope_state not in _SCOPE_CLOSURE_STATE_VALUES:
            scope_state = "partial"
        row["scope_closure_state"] = scope_state
    return rows


def _compute_blocker_feedback_state(ledger: dict[str, Any]) -> dict[str, Any]:
    items = ledger.get("items") if isinstance(ledger, dict) else []
    rows = ledger.get("external_context_injections") if isinstance(ledger, dict) else []
    if not isinstance(items, list):
        items = []
    if not isinstance(rows, list):
        rows = []
    unresolved_blockers: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip().lower()
        if not key:
            continue
        state = str(item.get("state") or "unknown").strip().lower()
        if state not in _UNRESOLVED_STATES:
            continue
        requirement = item.get("closure_requirement") if isinstance(item.get("closure_requirement"), dict) else {}
        mapping_blocking = bool(requirement.get("mapping_blocking", item.get("blocking")))
        if not mapping_blocking:
            continue
        unresolved_blockers[key] = {
            "decision_key": key,
            "decision_label": str(item.get("label") or key),
            "blocker_state": "open",
            "scope_id": _scope_id_for_item(item),
            "scope_label": str(item.get("scope_label") or _scope_label(_scope_id_for_item(item))),
        }

    by_decision: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "").strip().lower() != "human_resolution_ticket":
            continue
        key = str(row.get("decision_key") or "").strip().lower()
        if not key:
            continue
        by_decision.setdefault(key, []).append(row)

    unresolved_pairs: list[dict[str, Any]] = []
    unresolved_with_feedback_count = 0
    unresolved_waiting_feedback_count = 0
    unresolved_without_ticket_count = 0
    resolved_blockers_via_hitl_count = 0
    for key, blocker in unresolved_blockers.items():
        related = by_decision.get(key, [])
        latest_ticket = _latest_ticket_for_decision(related)
        lifecycle_state = str((latest_ticket or {}).get("lifecycle_state") or "").strip().lower() or None
        pair_state = "no_ticket"
        ready_for_resolution = False
        if lifecycle_state == "issued_waiting_feedback":
            pair_state = "waiting_feedback"
            unresolved_waiting_feedback_count += 1
        elif lifecycle_state == "answered_unintegrated":
            pair_state = "feedback_ready_for_integration"
            ready_for_resolution = True
            unresolved_with_feedback_count += 1
        elif lifecycle_state == "integration_attempted_failed":
            pair_state = "feedback_received_needs_refined_ticket"
            ready_for_resolution = True
            unresolved_with_feedback_count += 1
        elif lifecycle_state == "integrated":
            pair_state = "integrated_but_blocker_still_open"
        elif lifecycle_state == "superseded":
            pair_state = "superseded_waiting_reissue"
        elif lifecycle_state:
            pair_state = lifecycle_state
        else:
            unresolved_without_ticket_count += 1

        unresolved_pairs.append(
            {
                **blocker,
                "associated_ticket_id": str((latest_ticket or {}).get("ticket_id") or "").strip() or None,
                "associated_ticket_state": lifecycle_state,
                "associated_ticket_relevance": str((latest_ticket or {}).get("relevance") or "").strip().lower() or None,
                "pair_state": pair_state,
                "ready_for_resolution": ready_for_resolution,
            }
        )

    for key, related in by_decision.items():
        if key in unresolved_blockers:
            continue
        latest_ticket = _latest_ticket_for_decision(related)
        lifecycle_state = str((latest_ticket or {}).get("lifecycle_state") or "").strip().lower()
        if lifecycle_state == "integrated":
            resolved_blockers_via_hitl_count += 1

    return {
        "unresolved_mapping_blocker_count": int(len(unresolved_pairs)),
        "unresolved_blockers_with_feedback_count": int(unresolved_with_feedback_count),
        "unresolved_blockers_waiting_feedback_count": int(unresolved_waiting_feedback_count),
        "unresolved_blockers_without_ticket_count": int(unresolved_without_ticket_count),
        "hitl_present": int(len(by_decision)) > 0,
        "feedback_ready_for_blocker_resolution": int(unresolved_with_feedback_count) > 0,
        "hitl_used_to_remove_blocker": int(resolved_blockers_via_hitl_count) > 0,
        "resolved_blockers_via_hitl_count": int(resolved_blockers_via_hitl_count),
        "unresolved_blocker_ticket_pairs": unresolved_pairs[:12],
    }


def _latest_ticket_for_decision(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None

    def _sort_key(row: dict[str, Any]) -> tuple[int, int, int]:
        updated = int(row.get("updated_at") or 0)
        answered = int(row.get("answered_at") or 0)
        created = int(row.get("created_at") or 0)
        return (updated, answered, created)

    ordered = sorted(
        [dict(row) for row in rows if isinstance(row, dict)],
        key=_sort_key,
        reverse=True,
    )
    return ordered[0] if ordered else None


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
