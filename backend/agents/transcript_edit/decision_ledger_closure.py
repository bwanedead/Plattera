from __future__ import annotations

from typing import Any

from .decision_ledger_scope import (
    _ensure_ledger_shape,
    _normalize_scope_proof_codes,
    _normalize_scope_status,
    _read_scope_priority,
    _scope_id_for_item,
    _scope_id_from_scope_status,
    _scope_label,
    _scope_status_from_item_scope_fields,
)

_LAYER_STATUS_VALUES = {"satisfied", "blocked", "unknown"}
_IMPACT_VALUES = {"mapping_blocking", "transcript_quality_only"}
_UNRESOLVED_STATES = {"unknown", "candidate_found", "disputed", "accepted_with_risk"}

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
        state = str(item.get("state") or "unknown").strip().lower()
        if state not in _UNRESOLVED_STATES:
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
                "state": state,
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
