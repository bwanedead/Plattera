from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.decision_ledger import (
    initialize_decision_ledger,
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
        disagreement_hints={
            "range_values": [{"value": "75 west", "count": 2}, {"value": "74 west", "count": 1}],
            "distance_values": [{"value": "1320", "count": 2}],
        },
        image_results=[
            {"check_id": "image_check_tie_distance", "status": "match", "observed_text": "1320 feet"},
            {"check_id": "image_check_range_tokens", "status": "mismatch", "observed_text": "Range 74 West"},
        ],
    )
    range_item = _item(updated, "range")
    distance_item = _item(updated, "tie_distance")
    assert range_item["state"] == "disputed"
    assert len(range_item["alternatives"]) >= 2
    assert distance_item["state"] == "verified"
    assert str(distance_item.get("selected_value") or "").lower().startswith("1320")
    assert updated["summary"]["disputed_count"] >= 1
