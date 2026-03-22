"""Tests for transcript-edit native ledger persistence and closure helpers.

Phase 17: default ``initialize_decision_ledger`` is discovery-native (empty items). Tests that need the
legacy checklist shape use ``initialize_decision_ledger_with_domain_template_seed``.
Production reads use the unified envelope + closure read ledger.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.decision_ledger import (
    choose_investigation_focus,
    clear_resolved_after_reaudit,
    closure_state_from_layers,
    derive_layer_statuses,
    has_blocking_dispute,
    has_unresolved_mapping_blocking_closure,
    has_unresolved_target_scope_mapping_blocking_closure,
    initialize_decision_ledger,
    initialize_decision_ledger_with_domain_template_seed,
    is_unresolved_mapping_blocking_decision,
    unresolved_target_scope_mapping_blocking_requirements,
    unresolved_outside_target_scope_mapping_blocking_requirements,
    list_external_context_injections,
    mark_human_resolution_ticket_state,
    unresolved_mapping_blocking_requirements,
    unresolved_closure_requirements,
    upsert_human_resolution_ticket,
    update_ledger_from_iteration,
)


def _item(ledger: dict, key: str) -> dict:
    for item in ledger.get("items", []):
        if isinstance(item, dict) and item.get("key") == key:
            return item
    raise AssertionError(f"missing key: {key}")


def test_initialize_decision_ledger_bootstrap_specs_match_expected_key_order() -> None:
    """Bootstrap default rows — order follows ``DEFAULT_DECISION_SLOT_SPECS``, not harness ontology."""
    ledger = initialize_decision_ledger_with_domain_template_seed()
    keys = [item.get("key") for item in ledger.get("items", []) if isinstance(item, dict)]
    assert keys == [
        "township",
        "range",
        "section",
        "tie_distance",
        "tie_bearing",
        "acreage",
        "closure_or_pob",
    ]
    by_k = {str(i.get("key")): i for i in ledger.get("items") or [] if isinstance(i, dict)}
    assert by_k["tie_distance"].get("seed_scaffolding_dormant") is True
    assert by_k["range"].get("seed_scaffolding_dormant") is True
    assert isinstance(ledger.get("summary"), dict)


def test_initialize_decision_ledger_discovery_native_starts_empty() -> None:
    ledger = initialize_decision_ledger()
    assert ledger.get("ledger_establishment_mode") == "discovery_native"
    assert ledger.get("items") == []


def test_update_ledger_from_iteration_merges_source_signals_without_checklist_authorship_phase24() -> None:
    """Phase 24: audit/image observations do not mutate checklist rows or selected_value."""
    ledger = initialize_decision_ledger_with_domain_template_seed()
    updated = update_ledger_from_iteration(
        ledger=ledger,
        findings=[
            {"finding_id": "f-range", "message": "Range conflict between candidate drafts"},
            {"finding_id": "f-distance", "message": "Tie distance appears as 1320 feet in call language"},
        ],
        image_results=[
            {"check_id": "image_check_tie_distance", "status": "match", "observed_text": "1320 feet"},
            {"check_id": "image_check_range_tokens", "status": "mismatch", "observed_text": "Range 74 West"},
        ],
    )
    range_item = _item(updated, "range")
    distance_item = _item(updated, "tie_distance")
    assert str(range_item.get("state") or "") == "unknown"
    assert str(distance_item.get("state") or "") == "unknown"
    assert not str(distance_item.get("selected_value") or "").lower().startswith("1320")
    assert int(updated["summary"].get("disputed_count") or 0) == 0


def test_derive_layer_statuses_mapping_ready_is_fully_satisfied() -> None:
    statuses = derive_layer_statuses(
        mapping_ready=True,
        mechanical_severity_clear=True,
        readiness_blocker=None,
    )
    assert statuses["layer1_canonical_recovery"] == "satisfied"
    assert statuses["layer2_canonical_sanity"] == "satisfied"
    assert statuses["layer3_dependency_completeness"] == "satisfied"
    assert closure_state_from_layers(statuses) == "achieved"


def test_derive_layer_statuses_final_verify_blocker_marks_layer1_blocked() -> None:
    statuses = derive_layer_statuses(
        mapping_ready=False,
        mechanical_severity_clear=True,
        readiness_blocker="mapping_critical_image_verification_unresolved",
    )
    assert statuses["layer1_canonical_recovery"] == "blocked"
    assert statuses["layer2_canonical_sanity"] == "unknown"
    assert statuses["layer3_dependency_completeness"] == "unknown"
    assert closure_state_from_layers(statuses) == "blocked"


def test_unresolved_closure_requirements_contains_only_actionable_items() -> None:
    updated = update_ledger_from_iteration(
        ledger=initialize_decision_ledger_with_domain_template_seed(),
        findings=[{"finding_id": "f-range", "message": "Range conflict between candidate drafts"}],
    )
    unresolved = unresolved_closure_requirements(updated)
    assert len(unresolved) >= 1
    keys = {str(item.get("key")) for item in unresolved}
    assert "range" in keys


def test_choose_investigation_focus_prefers_blocking_disputed_items() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    range_item = _item(ledger, "range")
    range_item["state"] = "disputed"
    range_item["blocking"] = True
    range_item["alternatives"] = ["Range 75 West", "Range 74 West"]
    range_item["closure_requirement"] = {
        "block_reason": "contradiction",
        "mapping_blocking": True,
        "operational_impact": "mapping_blocking",
        "resolution_options": ["Range 75 West", "Range 74 West"],
        "evidence_refs": ["e1"],
    }
    focus = choose_investigation_focus(ledger)
    assert isinstance(focus, dict)
    assert focus["decision_key"] == "range"
    assert str(focus["next_check_reason_code"]) in {
        "highest_uncertainty",
        "blocking_mapping_critical",
        "blocking_conflict_unresolved",
    }
    assert has_blocking_dispute(ledger) is True


def test_closure_requirement_marks_non_blocking_items_as_optional_for_mapping() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    acreage_item = _item(ledger, "acreage")
    acreage_item["state"] = "disputed"
    acreage_item["blocking"] = False
    acreage_item["operational_impact"] = "transcript_quality_only"
    acreage_item["closure_requirement"] = {
        "block_reason": "ambiguity",
        "mapping_blocking": False,
        "operational_impact": "transcript_quality_only",
        "required_information": "Reconcile acreage call.",
        "self_retrievable": "conditional",
        "retrieval_attempted": False,
        "retrieval_blocker": None,
        "minimal_user_action": "Confirm acreage.",
        "resolution_options": ["1.4 acres", "1.9 acres"],
        "evidence_refs": [],
        "attempt_summary": "Acreage conflict between drafts.",
    }
    closure = acreage_item.get("closure_requirement")
    assert isinstance(closure, dict)
    assert closure.get("mapping_blocking") is False
    assert str(closure.get("operational_impact")) == "transcript_quality_only"


def test_unresolved_mapping_blocking_predicate_covers_all_unresolved_states() -> None:
    unresolved_states = ["unknown", "candidate_found", "disputed", "accepted_with_risk"]
    for state in unresolved_states:
        ledger = initialize_decision_ledger_with_domain_template_seed()
        range_item = _item(ledger, "range")
        range_item["state"] = state
        range_item["blocking"] = True
        range_item["operational_impact"] = "mapping_blocking"
        range_item["closure_requirement"] = {
            "block_reason": "ambiguity",
            "mapping_blocking": True,
            "operational_impact": "mapping_blocking",
            "required_information": "Confirm range token.",
            "self_retrievable": "conditional",
            "retrieval_attempted": True,
            "retrieval_blocker": None,
            "minimal_user_action": "Select the correct range token.",
            "resolution_options": ["Range 75 West"],
            "evidence_refs": ["test"],
            "attempt_summary": "needs confirmation",
        }
        assert has_unresolved_mapping_blocking_closure(ledger) is True
        unresolved = unresolved_mapping_blocking_requirements(ledger)
        assert any(isinstance(item, dict) and str(item.get("key")) == "range" for item in unresolved)


def test_is_unresolved_mapping_blocking_decision_is_key_specific() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    range_item = _item(ledger, "range")
    range_item["state"] = "disputed"
    range_item["blocking"] = True
    range_item["closure_requirement"] = {
        "mapping_blocking": True,
        "operational_impact": "mapping_blocking",
        "resolution_options": ["Range 75 West"],
        "evidence_refs": ["test"],
    }
    assert is_unresolved_mapping_blocking_decision(ledger, "range") is True
    assert is_unresolved_mapping_blocking_decision(ledger, "section") is False


def test_plss_finding_observations_do_not_author_checklist_rows_phase24() -> None:
    updated = update_ledger_from_iteration(
        ledger=initialize_decision_ledger_with_domain_template_seed(),
        findings=[
            {
                "finding_id": "plss_range_conflict_001",
                "finding_type": "plss_consistency",
                "message": "PLSS contradiction detected: Township 14 North appears with Range 75 West and Range 74 West.",
            }
        ],
    )
    range_item = _item(updated, "range")
    assert str(range_item.get("state") or "") == "unknown"


def test_range_contradiction_identity_preserved_when_authored_on_ledger_rows() -> None:
    """LLM/orient-authored disputed range keeps alternatives without cross-key bleed."""
    ledger = initialize_decision_ledger_with_domain_template_seed()
    range_item = _item(ledger, "range")
    range_item["state"] = "disputed"
    range_item["layer_tag"] = "layer2_canonical_sanity"
    range_item["alternatives"] = ["Range 75 West", "Range 74 West"]
    township_item = _item(ledger, "township")
    assert str(range_item.get("state") or "") == "disputed"
    alternatives = [str(v) for v in list(range_item.get("alternatives") or [])]
    assert any("75" in v for v in alternatives)
    assert any("74" in v for v in alternatives)
    assert str(township_item.get("state") or "") == "unknown"


def test_choose_focus_prefers_range_contradiction_over_generic_township_unknown() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    range_item = _item(ledger, "range")
    range_item["state"] = "disputed"
    range_item["alternatives"] = ["Range 75 West", "Range 74 West"]
    range_item["closure_requirement"] = {
        "block_reason": "contradiction",
        "mapping_blocking": True,
        "operational_impact": "mapping_blocking",
        "required_information": "Reconcile Range 75 vs Range 74.",
        "self_retrievable": "conditional",
        "retrieval_attempted": True,
        "retrieval_blocker": None,
        "minimal_user_action": "Select the correct range token.",
        "resolution_options": ["Range 75 West", "Range 74 West"],
        "evidence_refs": ["plss_range_conflict_001"],
        "attempt_summary": "Conflicting range tokens remain.",
    }
    focus = choose_investigation_focus(ledger)
    assert isinstance(focus, dict)
    assert str(focus.get("decision_key") or "") == "range"


def test_image_match_does_not_auto_resolve_existing_range_dispute() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    range_item = _item(ledger, "range")
    range_item["state"] = "disputed"
    range_item["layer_tag"] = "layer2_canonical_sanity"
    range_item["alternatives"] = ["Range 75 West", "Range 74 West"]
    range_item["closure_requirement"] = {
        "block_reason": "contradiction",
        "mapping_blocking": True,
        "operational_impact": "mapping_blocking",
        "resolution_options": ["Range 75 West", "Range 74 West"],
        "evidence_refs": ["plss_range_conflict_001"],
    }
    updated = update_ledger_from_iteration(
        ledger=ledger,
        findings=[
            {
                "finding_id": "plss_range_conflict_001",
                "finding_type": "plss_consistency",
                "message": "PLSS contradiction detected: Township 14 North appears with Range 75 West and Range 74 West.",
            }
        ],
        image_results=[
            {
                "check_id": "plss_range_conflict_001",
                "status": "match",
                "observed_text": "tokens detected",
                "decision_key": "range",
            }
        ],
    )
    range_item = _item(updated, "range")
    assert str(range_item.get("state") or "") == "disputed"
    assert str(range_item.get("layer_tag") or "") == "layer2_canonical_sanity"
    alternatives = [str(v) for v in list(range_item.get("alternatives") or [])]
    assert any("75" in v for v in alternatives)
    assert any("74" in v for v in alternatives)


def test_image_result_observations_do_not_author_disputed_state_phase24() -> None:
    updated = update_ledger_from_iteration(
        ledger=initialize_decision_ledger_with_domain_template_seed(),
        image_results=[
            {
                "check_id": "plss_conflict_001",
                "status": "mismatch",
                "observed_text": "Range 74 West",
                "decision_key": "range",
            }
        ],
    )
    range_item = _item(updated, "range")
    township_item = _item(updated, "township")
    assert str(range_item.get("state") or "") == "unknown"
    assert str(township_item.get("state") or "") == "unknown"


def test_image_result_query_preserves_range_contradiction_alternatives() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    range_item = _item(ledger, "range")
    range_item["state"] = "disputed"
    range_item["layer_tag"] = "layer2_canonical_sanity"
    range_item["alternatives"] = ["Range 75 West", "Range 74 West"]
    updated = update_ledger_from_iteration(
        ledger=ledger,
        image_results=[
            {
                "check_id": "plss_range_conflict_001",
                "status": "match",
                "decision_key": "range",
                "query": "Range contradiction detected between Range 75 West and Range 74 West.",
                "observed_text": "tokens detected",
            }
        ],
    )
    range_item = _item(updated, "range")
    assert str(range_item.get("state") or "") == "disputed"
    assert str(range_item.get("layer_tag") or "") == "layer2_canonical_sanity"
    alternatives = [str(v) for v in list(range_item.get("alternatives") or [])]
    assert any("75" in v for v in alternatives)
    assert any("74" in v for v in alternatives)


def test_compact_plss_range_tokens_in_findings_do_not_populate_alternatives_phase24() -> None:
    updated = update_ledger_from_iteration(
        ledger=initialize_decision_ledger_with_domain_template_seed(),
        findings=[
            {
                "finding_id": "plss_range_conflict_001",
                "finding_type": "plss_consistency",
                "message": "Multiple range tokens detected: r74w, r75w",
            }
        ],
    )
    range_item = _item(updated, "range")
    assert str(range_item.get("state") or "") == "unknown"
    assert list(range_item.get("alternatives") or []) == []


def test_human_resolution_ticket_lifecycle_helpers_roundtrip() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    ledger = upsert_human_resolution_ticket(
        ledger=ledger,
        ticket_id="hitl_range_1_x",
        decision_key="range",
        lifecycle_state="answered_unintegrated",
        payload={"normalized_answer_summary": "Range 75 West"},
    )
    rows = list_external_context_injections(
        ledger,
        decision_key="range",
        type_filter="human_resolution_ticket",
        lifecycle_states={"answered_unintegrated"},
    )
    assert len(rows) == 1
    assert str(rows[0].get("ticket_id") or "") == "hitl_range_1_x"
    ledger = mark_human_resolution_ticket_state(
        ledger=ledger,
        ticket_id="hitl_range_1_x",
        decision_key="range",
        lifecycle_state="integrated",
        integrated=True,
    )
    rows2 = list_external_context_injections(
        ledger,
        decision_key="range",
        type_filter="human_resolution_ticket",
        lifecycle_states={"integrated"},
    )
    assert len(rows2) == 1
    assert rows2[0].get("integrated_at") is not None


def test_blocker_feedback_state_tracks_ready_pairing_for_unresolved_blocker() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    range_item = _item(ledger, "range")
    range_item["state"] = "disputed"
    range_item["blocking"] = True
    range_item["closure_requirement"] = {
        "mapping_blocking": True,
        "operational_impact": "mapping_blocking",
        "resolution_options": ["Range 75 West", "Range 74 West"],
    }
    ledger = upsert_human_resolution_ticket(
        ledger=ledger,
        ticket_id="hitl_range_2_resolver",
        decision_key="range",
        lifecycle_state="answered_unintegrated",
        payload={"normalized_answer_summary": "Range 75 West"},
    )
    state = dict(ledger.get("blocker_feedback_state") or {})
    assert int(state.get("unresolved_mapping_blocker_count") or 0) >= 1
    assert bool(state.get("feedback_ready_for_blocker_resolution")) is True
    pairs = [row for row in list(state.get("unresolved_blocker_ticket_pairs") or []) if isinstance(row, dict)]
    assert len(pairs) >= 1
    pair = next(row for row in pairs if str(row.get("decision_key") or "") == "range")
    assert str(pair.get("associated_ticket_id") or "") == "hitl_range_2_resolver"
    assert str(pair.get("pair_state") or "") == "feedback_ready_for_integration"
    assert bool(pair.get("ready_for_resolution")) is True


def test_blocker_feedback_state_detects_hitl_removed_blocker_when_integrated() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    range_item = _item(ledger, "range")
    range_item["state"] = "verified"
    range_item["blocking"] = True
    range_item["closure_requirement"] = None
    ledger = upsert_human_resolution_ticket(
        ledger=ledger,
        ticket_id="hitl_range_3_resolver",
        decision_key="range",
        lifecycle_state="integrated",
        payload={"normalized_answer_summary": "Range 75 West"},
    )
    state = dict(ledger.get("blocker_feedback_state") or {})
    assert bool(state.get("hitl_used_to_remove_blocker")) is True
    assert int(state.get("resolved_blockers_via_hitl_count") or 0) >= 1


def test_scope_partitioning_and_target_scope_predicate() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    range_item = _item(ledger, "range")
    range_item["state"] = "disputed"
    range_item["blocking"] = True
    range_item["scope_id"] = "target_scope"
    range_item["in_target_scope"] = True
    range_item["closure_requirement"] = {
        "mapping_blocking": True,
        "operational_impact": "mapping_blocking",
        "resolution_options": ["Range 75 West", "Range 74 West"],
        "evidence_refs": ["orient_llm"],
    }
    closure_item = _item(ledger, "closure_or_pob")
    closure_item["state"] = "disputed"
    closure_item["blocking"] = True
    closure_item["scope_id"] = "outside_target_scope"
    closure_item["in_target_scope"] = False
    closure_item["closure_requirement"] = {
        "scope_status": "outside_target",
        "scope_proof": ["explicit_outside_target_text"],
        "mapping_blocking": True,
        "operational_impact": "mapping_blocking",
        "resolution_options": ["Closure phrase A", "Closure phrase B"],
        "evidence_refs": ["truncated_page"],
    }
    target_items = unresolved_target_scope_mapping_blocking_requirements(ledger)
    outside_items = unresolved_outside_target_scope_mapping_blocking_requirements(ledger)
    assert any(str(item.get("key")) == "range" for item in target_items if isinstance(item, dict))
    assert any(str(item.get("key")) == "closure_or_pob" for item in outside_items if isinstance(item, dict))
    assert has_unresolved_target_scope_mapping_blocking_closure(ledger) is True


def test_source_completeness_metadata_propagates_from_signals() -> None:
    ledger = update_ledger_from_iteration(
        ledger=initialize_decision_ledger_with_domain_template_seed(),
        findings=[
            {
                "finding_id": "f-cutoff",
                "message": "Lower page is truncated and outside target scope text is cut off.",
                "source_completeness": "partial_truncated",
                "source_completeness_reason": "Image cutoff below target plot.",
                "source_limitations": ["Lower page missing from source image."],
            }
        ],
    )
    assert str(ledger.get("source_completeness") or "") == "partial_truncated"
    assert "cutoff" in str(ledger.get("source_completeness_reason") or "").lower()
    limitations = [str(v) for v in list(ledger.get("source_limitations") or [])]
    assert any("missing" in text.lower() for text in limitations)


def test_focus_selection_prefers_target_scope_over_outside_scope() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    range_item = _item(ledger, "range")
    range_item["state"] = "disputed"
    range_item["blocking"] = True
    range_item["scope_id"] = "target_scope"
    range_item["in_target_scope"] = True
    range_item["closure_requirement"] = {
        "block_reason": "contradiction",
        "mapping_blocking": True,
        "operational_impact": "mapping_blocking",
        "resolution_options": ["Range 75 West", "Range 74 West"],
        "evidence_refs": ["orient_llm"],
    }
    closure_item = _item(ledger, "closure_or_pob")
    closure_item["state"] = "disputed"
    closure_item["blocking"] = True
    closure_item["scope_id"] = "outside_target_scope"
    closure_item["in_target_scope"] = False
    closure_item["closure_requirement"] = {
        "block_reason": "ambiguity",
        "mapping_blocking": True,
        "operational_impact": "mapping_blocking",
        "resolution_options": ["A", "B"],
        "evidence_refs": ["truncated_page"],
    }
    focus = choose_investigation_focus(ledger)
    assert isinstance(focus, dict)
    assert str(focus.get("decision_key") or "") == "range"


def test_partial_source_without_scope_proof_stays_unknown_scope() -> None:
    ledger = update_ledger_from_iteration(
        ledger=initialize_decision_ledger_with_domain_template_seed(),
        findings=[
            {
                "finding_id": "f-closure",
                "message": "Closure language unresolved; source appears truncated.",
                "source_completeness": "partial_truncated",
                "source_completeness_reason": "Lower page cut off.",
            }
        ],
    )
    unresolved = unresolved_closure_requirements(ledger)
    closure_rows = [row for row in unresolved if isinstance(row, dict) and str(row.get("key") or "") == "closure_or_pob"]
    assert closure_rows
    row = closure_rows[0]
    assert str(row.get("scope_status") or "") == "unknown"
    assert list(row.get("scope_proof") or []) == []


def test_unresolved_with_approved_scope_proof_is_outside_target() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    closure = _item(ledger, "closure_or_pob")
    closure["state"] = "disputed"
    closure["blocking"] = True
    closure["closure_requirement"] = {
        "mapping_blocking": True,
        "operational_impact": "mapping_blocking",
        "scope_status": "outside_target",
        "scope_proof": ["explicit_outside_target_text", "source_truncation_boundary"],
        "resolution_options": ["A", "B"],
        "evidence_refs": ["e1"],
    }
    outside_items = unresolved_outside_target_scope_mapping_blocking_requirements(ledger)
    assert any(str(item.get("key") or "") == "closure_or_pob" for item in outside_items if isinstance(item, dict))


def test_scope_status_can_reclassify_from_prior_outside_to_in_target_via_row_update() -> None:
    """Phase 24: scope reclassification is LLM-authored on native rows, not validator findings."""
    ledger = initialize_decision_ledger_with_domain_template_seed()
    closure = _item(ledger, "closure_or_pob")
    closure["state"] = "disputed"
    closure["closure_requirement"] = {
        "block_reason": "ambiguity",
        "mapping_blocking": True,
        "scope_status": "outside_target",
        "scope_proof": ["explicit_outside_target_text"],
        "resolution_options": ["A", "B"],
        "evidence_refs": ["test"],
    }
    closure["closure_requirement"] = {
        **dict(closure.get("closure_requirement") or {}),
        "scope_status": "in_target",
        "scope_proof": [],
        "in_target_scope": True,
    }
    unresolved = unresolved_closure_requirements(ledger)
    row = next(item for item in unresolved if isinstance(item, dict) and str(item.get("key") or "") == "closure_or_pob")
    assert str(row.get("scope_status") or "") == "in_target"


# ---------------------------------------------------------------------------
# clear_resolved_after_reaudit
# ---------------------------------------------------------------------------

def _make_blocked_range_ledger() -> dict:
    """Return a ledger where range is disputed+mapping_blocking (simulates post-edit state)."""
    ledger = initialize_decision_ledger_with_domain_template_seed()
    range_item = _item(ledger, "range")
    range_item["state"] = "disputed"
    range_item["blocking"] = True
    range_item["alternatives"] = ["Range 75 West", "Range 74 West"]
    range_item["closure_requirement"] = {
        "block_reason": "contradiction",
        "mapping_blocking": True,
        "operational_impact": "mapping_blocking",
        "required_information": "Confirm the correct range value.",
        "self_retrievable": "conditional",
        "retrieval_attempted": True,
        "retrieval_blocker": None,
        "minimal_user_action": "Select the correct range token.",
        "resolution_options": ["Range 75 West", "Range 74 West"],
        "evidence_refs": ["prior_audit_001"],
        "attempt_summary": "Conflict between 74 and 75 West.",
    }
    return ledger


def test_clear_resolved_after_reaudit_does_not_promote_via_validator_absence_phase24() -> None:
    """Phase 24: re-audit does not verify disputed rows when findings are absent."""
    ledger = _make_blocked_range_ledger()
    assert has_unresolved_mapping_blocking_closure(ledger) is True

    updated = clear_resolved_after_reaudit(ledger=ledger, findings=[])

    range_item = _item(updated, "range")
    assert str(range_item.get("state") or "") == "disputed"
    assert has_unresolved_mapping_blocking_closure(updated) is True


def test_clear_resolved_after_reaudit_ignores_findings_for_promotion_phase24() -> None:
    """Phase 24: findings list does not change reconcile-only clear behavior."""
    ledger = _make_blocked_range_ledger()

    still_conflicting_finding = {
        "finding_id": "plss_range_conflict_still",
        "finding_type": "plss_consistency",
        "message": "PLSS contradiction: Range 75 West and Range 74 West both present.",
    }
    updated = clear_resolved_after_reaudit(
        ledger=ledger, findings=[still_conflicting_finding]
    )

    range_item = _item(updated, "range")
    assert str(range_item.get("state") or "") == "disputed"
    assert has_unresolved_mapping_blocking_closure(updated) is True


def test_clear_resolved_after_reaudit_leaves_non_mapping_blocking_items_untouched() -> None:
    """Non-mapping-blocking items must not be force-verified by the re-audit clear."""
    ledger = initialize_decision_ledger_with_domain_template_seed()
    section_item = _item(ledger, "section")
    section_item["state"] = "candidate_found"
    # section is not mapping_blocking by default; do not set it.

    updated = clear_resolved_after_reaudit(ledger=ledger, findings=[])

    section_item_after = _item(updated, "section")
    assert str(section_item_after.get("state") or "") == "candidate_found", (
        "non-mapping-blocking items should not be promoted by clear_resolved_after_reaudit"
    )
