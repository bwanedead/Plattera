"""Validation tests for ``ResolutionCoveredUnit`` and its ``ResolutionItem`` binding."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from harness.mission_state import ResolutionCoveredUnit, ResolutionItem


def test_covered_unit_requires_unit_id_and_title() -> None:
    with pytest.raises(ValidationError):
        ResolutionCoveredUnit.model_validate({"title": "no id"})
    with pytest.raises(ValidationError):
        ResolutionCoveredUnit.model_validate({"unit_id": "u1"})


def test_covered_unit_allows_optional_fields_to_be_absent() -> None:
    unit = ResolutionCoveredUnit.model_validate({"unit_id": "u1", "title": "U One"})
    assert unit.status is None
    assert unit.determination is None
    assert unit.evidence_refs == []
    assert unit.opaque_payload == {}


def test_covered_unit_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ResolutionCoveredUnit.model_validate(
            {"unit_id": "u1", "title": "U One", "bogus_field": 1}
        )


def test_resolution_item_default_covered_units_is_empty_list() -> None:
    item = ResolutionItem.model_validate(
        {"item_id": "i1", "title": "I One", "kind": "claim", "status": "open"}
    )
    assert item.covered_units == []


def test_resolution_item_accepts_work_graph_value_fields() -> None:
    item = ResolutionItem.model_validate(
        {
            "item_id": "i1",
            "title": "NW corner bearing",
            "kind": "claim",
            "status": "closed",
            "determination": "earned",
            "label": "NW corner bearing",
            "value_kind": "bearing",
            "candidate_values": ["N 2° 00' W", "N 4° 00' W"],
            "determined_value": "N 4° 00' W",
        }
    )
    assert item.label == "NW corner bearing"
    assert item.value_kind == "bearing"
    assert item.candidate_values == ["N 2° 00' W", "N 4° 00' W"]
    assert item.determined_value == "N 4° 00' W"


def test_covered_unit_accepts_work_graph_value_fields() -> None:
    unit = ResolutionCoveredUnit.model_validate(
        {
            "unit_id": "u1",
            "title": "NW corner bearing",
            "label": "nw-bearing",
            "value_kind": "bearing",
            "candidate_values": ["N 2° 00' W", "N 4° 00' W"],
            "determined_value": "N 4° 00' W",
        }
    )
    assert unit.label == "nw-bearing"
    assert unit.value_kind == "bearing"
    assert unit.candidate_values == ["N 2° 00' W", "N 4° 00' W"]
    assert unit.determined_value == "N 4° 00' W"


def test_covered_unit_defaults_for_value_fields_are_empty_or_none() -> None:
    unit = ResolutionCoveredUnit.model_validate({"unit_id": "u1", "title": "U One"})
    assert unit.label is None
    assert unit.value_kind is None
    assert unit.candidate_values == []
    assert unit.determined_value is None


def test_covered_unit_candidate_values_has_max_length() -> None:
    with pytest.raises(ValidationError):
        ResolutionCoveredUnit.model_validate(
            {
                "unit_id": "u1",
                "title": "U One",
                "candidate_values": [f"v{i}" for i in range(17)],
            }
        )


def test_resolution_item_accepts_covered_units_list() -> None:
    item = ResolutionItem.model_validate(
        {
            "item_id": "g1",
            "title": "Group",
            "kind": "claim_group",
            "status": "open",
            "covered_units": [
                {"unit_id": "u1", "title": "U One", "status": "closed"},
                {"unit_id": "u2", "title": "U Two"},
            ],
        }
    )
    assert [u.unit_id for u in item.covered_units] == ["u1", "u2"]
    assert item.covered_units[0].status == "closed"


def test_determination_accepts_phrases_up_to_64_chars_across_models() -> None:
    """Contract ergonomics: determination was bumped from 32 → 64 chars."""
    from harness.mission_state import (
        ClosureDimension,
        MissionSuccessCondition,
        ResolutionCoveredUnit,
        ResolutionItem,
    )

    phrase = "earned_pending_downstream_human_ack_with_fallback_ok"
    assert 32 < len(phrase) <= 64

    ResolutionCoveredUnit.model_validate(
        {"unit_id": "u1", "title": "t", "determination": phrase}
    )
    ResolutionItem.model_validate(
        {"item_id": "i1", "title": "t", "kind": "k", "status": "open", "determination": phrase}
    )
    ClosureDimension.model_validate(
        {"dimension_id": "d1", "title": "t", "status": "open", "determination": phrase}
    )
    MissionSuccessCondition.model_validate(
        {"condition_id": "c1", "title": "t", "status": "open", "determination": phrase}
    )


def test_determination_rejects_phrases_over_64_chars() -> None:
    from harness.mission_state import ResolutionItem

    too_long = "x" * 65
    with pytest.raises(ValidationError):
        ResolutionItem.model_validate(
            {"item_id": "i1", "title": "t", "kind": "k", "status": "open", "determination": too_long}
        )
