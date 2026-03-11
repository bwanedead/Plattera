from __future__ import annotations

import re
import time
from typing import Any

from .decision_ledger_closure import (
    _attach_closure_requirements,
    _attempt_summary,
    _compute_blocker_feedback_state,
    _minimal_user_action_for_key,
    _required_information_for_key,
)
from .decision_ledger_scope import (
    _apply_scope_from_signal,
    _apply_scope_defaults,
    _compute_scope_summaries,
    _extract_source_completeness_signal,
    _merge_source_completeness_signal,
    _normalize_scope_proof_codes,
    _normalized_in_target_scope,
    _normalized_scope_id,
    _read_scope_priority,
    _scope_label,
)

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
