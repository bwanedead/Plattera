"""Tests for compact first-draft authoring card projection."""

from __future__ import annotations

import json

from tooling.mapping.deed_to_ir.feature_graph_capabilities import describe_feature_graph_capabilities
from tooling.mapping.deed_to_ir.feature_graph_examples import example_forbidden_tokens
from tooling.mapping.deed_to_ir.first_draft_authoring_card import build_first_draft_authoring_card


def test_first_draft_authoring_card_is_generic_and_complete() -> None:
    card = build_first_draft_authoring_card()
    combined = json.dumps(card).lower()
    for token in example_forbidden_tokens():
        assert token not in combined
    assert "parcel_1" not in combined
    assert "referenceframe" in combined.replace("_", "")
    assert "tiedpoint" in combined.replace("_", "")
    assert "coursetraverse" in combined.replace("_", "")
    assert "close" in combined
    assert "annotation" in combined
    assert card["course_traverse_compiler_required_fields"] == ["bearing", "distance"]
    assert card["course_traverse_source_trace_fields"] == ["bearing_raw", "distance_raw"]
    assert "do not compile" in card["raw_only_course_fields_do_not_compile"].lower()
    assert isinstance(card["generic_skeleton"], dict)


def test_starter_contract_includes_first_draft_authoring_card() -> None:
    caps = describe_feature_graph_capabilities(sections=["starter_contract"])
    starter = caps["starter_contract"]
    card = starter["first_draft_authoring_card"]
    assert card["normal_deed_operation_names"] == [
        "ReferenceFrame",
        "TiedPoint",
        "CourseTraverse",
        "Close",
    ]
    assert "annotation" in str(card["blocked_incomplete_scope"]).lower()
