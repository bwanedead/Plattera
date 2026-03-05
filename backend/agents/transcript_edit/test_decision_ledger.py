from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.decision_ledger import (
    choose_investigation_focus,
    closure_state_from_layers,
    derive_layer_statuses,
    has_blocking_dispute,
    initialize_decision_ledger,
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
