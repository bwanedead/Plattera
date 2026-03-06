from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.decision_ledger import (
    choose_investigation_focus,
    closure_state_from_layers,
    derive_layer_statuses,
    has_blocking_dispute,
    has_unresolved_mapping_blocking_closure,
    initialize_decision_ledger,
    is_unresolved_mapping_blocking_decision,
    unresolved_mapping_blocking_requirements,
    unresolved_closure_requirements,
    update_ledger_from_iteration,
)


def _item(ledger: dict, key: str) -> dict:
    for item in ledger.get("items", []):
        if isinstance(item, dict) and item.get("key") == key:
            return item
    raise AssertionError(f"missing key: {key}")


def test_initialize_decision_ledger_has_expected_keys() -> None:
    ledger = initialize_decision_ledger()
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
    assert isinstance(ledger.get("summary"), dict)


def test_update_ledger_from_audit_and_image_signals() -> None:
    ledger = initialize_decision_ledger()
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
    assert range_item["state"] == "disputed"
    assert distance_item["state"] == "verified"
    assert str(distance_item.get("selected_value") or "").lower().startswith("1320")
    assert updated["summary"]["disputed_count"] >= 1
    assert isinstance(range_item.get("closure_requirement"), dict)
    assert range_item["closure_requirement"]["block_reason"] in {"ambiguity", "contradiction"}
    assert distance_item.get("closure_requirement") is None


def test_derive_layer_statuses_mapping_ready_is_fully_satisfied() -> None:
    statuses = derive_layer_statuses(
        mapping_ready=True,
        validator_clean=True,
        readiness_blocker=None,
    )
    assert statuses["layer1_canonical_recovery"] == "satisfied"
    assert statuses["layer2_canonical_sanity"] == "satisfied"
    assert statuses["layer3_dependency_completeness"] == "satisfied"
    assert closure_state_from_layers(statuses) == "achieved"


def test_derive_layer_statuses_final_verify_blocker_marks_layer1_blocked() -> None:
    statuses = derive_layer_statuses(
        mapping_ready=False,
        validator_clean=True,
        readiness_blocker="mapping_critical_image_verification_unresolved",
    )
    assert statuses["layer1_canonical_recovery"] == "blocked"
    assert statuses["layer2_canonical_sanity"] == "unknown"
    assert statuses["layer3_dependency_completeness"] == "unknown"
    assert closure_state_from_layers(statuses) == "blocked"


def test_unresolved_closure_requirements_contains_only_actionable_items() -> None:
    updated = update_ledger_from_iteration(
        ledger=initialize_decision_ledger(),
        findings=[{"finding_id": "f-range", "message": "Range conflict between candidate drafts"}],
    )
    unresolved = unresolved_closure_requirements(updated)
    assert len(unresolved) >= 1
    keys = {str(item.get("key")) for item in unresolved}
    assert "range" in keys


def test_choose_investigation_focus_prefers_blocking_disputed_items() -> None:
    updated = update_ledger_from_iteration(
        ledger=initialize_decision_ledger(),
        findings=[{"finding_id": "f-range", "message": "Range conflict between candidate drafts"}],
    )
    focus = choose_investigation_focus(updated)
    assert isinstance(focus, dict)
    assert focus["decision_key"] == "range"
    assert str(focus["next_check_reason_code"]) in {"highest_uncertainty", "blocking_mapping_critical"}
    assert has_blocking_dispute(updated) is False


def test_closure_requirement_marks_non_blocking_items_as_optional_for_mapping() -> None:
    updated = update_ledger_from_iteration(
        ledger=initialize_decision_ledger(),
        findings=[{"finding_id": "f-acre", "message": "Acreage conflict between drafts (1.4 acres vs 1.9 acres)."}],
    )
    acreage_item = _item(updated, "acreage")
    closure = acreage_item.get("closure_requirement")
    assert isinstance(closure, dict)
    assert closure.get("mapping_blocking") is False
    assert str(closure.get("operational_impact")) == "transcript_quality_only"


def test_unresolved_mapping_blocking_predicate_covers_all_unresolved_states() -> None:
    unresolved_states = ["unknown", "candidate_found", "disputed", "accepted_with_risk"]
    for state in unresolved_states:
        ledger = initialize_decision_ledger()
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
    ledger = initialize_decision_ledger()
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


def test_range_contradiction_identity_preserved_from_plss_finding() -> None:
    updated = update_ledger_from_iteration(
        ledger=initialize_decision_ledger(),
        findings=[
            {
                "finding_id": "plss_range_conflict_001",
                "finding_type": "plss_consistency",
                "message": "PLSS contradiction detected: Township 14 North appears with Range 75 West and Range 74 West.",
            }
        ],
    )
    range_item = _item(updated, "range")
    township_item = _item(updated, "township")
    assert str(range_item.get("state") or "") == "disputed"
    assert str(range_item.get("layer_tag") or "") == "layer2_canonical_sanity"
    alternatives = [str(v) for v in list(range_item.get("alternatives") or [])]
    assert any("75" in v for v in alternatives)
    assert any("74" in v for v in alternatives)
    # Township should not absorb the range contradiction identity.
    assert str(township_item.get("state") or "") == "unknown"


def test_choose_focus_prefers_range_contradiction_over_generic_township_unknown() -> None:
    ledger = initialize_decision_ledger()
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
