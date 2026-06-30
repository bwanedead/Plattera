"""Tests for deed-to-IR read-action compact summaries."""

from __future__ import annotations

from harness.runtime.orchestration.action_batch import build_batch_item_result_row, project_batch_item_row
from tooling.mapping.deed_to_ir.read_action_projection import (
    compact_feature_graph_capabilities_summary,
    compact_hydrate_deed_to_ir_input_summary,
    compact_read_action_summary,
)


def test_hydrate_mapping_operands_summary_includes_operand_suite_and_groups():
    outputs = {
        "sections": ["mapping_operands"],
        "hydrated_section_count": 1,
        "mapping_operands": {
            "projection_mode": "mapping_operands",
            "operand_suite_ref": "deed_to_ir:operands:run:run-example",
            "operand_groups": [
                {
                    "group_id": "example_scope_calls",
                    "group_kind": "course_call_candidates",
                    "rows": [{"call_index": 1}],
                }
            ],
            "operands": [{"operand_id": "example_call_1_bearing"}],
            "totals": {"emitted": 1, "available": 1},
        },
        "inherited_handoff_conditions": {"projection_mode": "deferred_for_operand_lane"},
    }
    summary = compact_hydrate_deed_to_ir_input_summary(
        outputs,
        action_inputs={"sections": ["mapping_operands"]},
    )
    assert summary is not None
    assert summary["operand_suite_ref"] == "deed_to_ir:operands:run:run-example"
    assert summary["operand_groups"][0]["group_kind"] == "course_call_candidates"
    assert summary["inherited_handoff_conditions"] == "deferred_for_operand_lane"


def test_capabilities_summary_includes_sections_and_operations():
    outputs = {
        "sections": ["starter_contract"],
        "starter_contract": {
            "first_draft_authoring_card": {
                "normal_deed_operation_names": [
                    "ReferenceFrame",
                    "TiedPoint",
                    "CourseTraverse",
                    "Close",
                ],
            },
            "feature_kinds": ["point", "annotation", "unknown"],
            "feature_kind_vs_operation_contract": {
                "annotation_note": "annotation is a FeatureKind for blocked scope.",
            },
            "provenance_link_required_fields": ["entity_id", "entity_type", "source_ref"],
            "operations": [
                {"name": "CourseTraverse", "category": "geometry", "compiler_support": "supported"},
                {"name": "Close", "category": "geometry", "compiler_support": "supported"},
            ],
        },
    }
    summary = compact_feature_graph_capabilities_summary(
        outputs,
        action_inputs={
            "sections": ["starter_contract"],
            "operation_names": ["CourseTraverse", "Close"],
        },
    )
    assert summary is not None
    assert summary["requested_sections"] == ["starter_contract"]
    assert summary["requested_operation_names"] == ["CourseTraverse", "Close"]
    ops = summary["starter_contract"]["operations"]
    assert [row["name"] for row in ops] == ["CourseTraverse", "Close"]


def test_batch_item_row_attaches_read_action_summary_without_paths():
    outputs = {
        "sections": ["mapping_operands"],
        "mapping_operands": {
            "operand_suite_ref": "deed_to_ir:operands:run:run-example",
            "operand_groups": [{"group_kind": "course_call_candidates", "rows": [{"call_index": 1}]}],
            "operands": [{"operand_id": "example_call_1_bearing"}],
        },
    }
    row = build_batch_item_result_row(
        alias="hydrate_operands",
        action_type="hydrate_deed_to_ir_input",
        execution_state="executed",
        outputs=outputs,
        action_inputs={"sections": ["mapping_operands"]},
    )
    summary = row.get("read_action_summary")
    assert isinstance(summary, dict)
    assert summary["operand_suite_ref"] == "deed_to_ir:operands:run:run-example"
    projected = project_batch_item_row(row)
    assert projected["read_action_summary"]["operand_suite_ref"] == "deed_to_ir:operands:run:run-example"
    serialized = str(projected).lower()
    assert "test_fixtures" not in serialized
    assert "c:\\" not in serialized


def test_compact_read_action_summary_dispatches_by_action_type():
    hydrate = compact_read_action_summary(
        "hydrate_deed_to_ir_input",
        {"mapping_operands": {"operand_suite_ref": "deed_to_ir:operands:run:x"}},
        action_inputs={"sections": ["mapping_operands"]},
    )
    assert hydrate is not None
    assert hydrate["lane"] == "mapping_operands"
    caps = compact_read_action_summary(
        "describe_feature_graph_capabilities",
        {"sections": ["starter_contract"], "starter_contract": {"operations": []}},
        action_inputs={"sections": ["starter_contract"]},
    )
    assert caps is not None
    assert caps["lane"] == "feature_graph_capabilities"
    card = caps.get("first_draft_authoring_card")
    assert isinstance(card, dict)
    assert card.get("normal_deed_operation_names") == [
        "ReferenceFrame",
        "TiedPoint",
        "CourseTraverse",
        "Close",
    ]
