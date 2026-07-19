"""Regression tests for surgical course_updates and draft_patch_targets (run-29 repair mode)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from feature_graph.compiler import compile_graph
from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr
from feature_graph.provenance import ProvenanceAttachment, SourceEntityLink
from harness.audit.human_timeline import _render_tool_result
from tooling.mapping.deed_to_ir.correction_contract_card import (
    agent_facing_example_contains_practice_deed_tokens,
)
from tooling.mapping.deed_to_ir.draft_patch_targets import (
    build_draft_patch_targets,
    join_correction_posture_to_patch_targets,
    render_draft_patch_targets_timeline_lines,
)
from tooling.mapping.deed_to_ir.ir_draft_patch import patch_ir_draft
from tooling.mapping.deed_to_ir.ir_persistence import save_ir_artifact
from tooling.mapping.deed_to_ir.mapping_review import (
    compact_mapping_review_for_projection,
    render_mapping_review_timeline_lines,
)
from tooling.mapping.deed_to_ir.mapping_sanity import build_course_leg_table


_CORRUPTED_DISTANCE = 618.0
_CORRECTED_DISTANCE = 518.0


def _services(tmpdir: str):
    from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

    return FeatureGraphPersistenceService(
        root=Path(tmpdir) / "artifacts",
        state_dir=Path(tmpdir) / "state",
    )


def _three_course_graph(*, leg2_distance: float) -> FeatureGraph:
    courses = [
        {"bearing": 68.5, "distance": 542.0, "bearing_raw": "N. 68° 30' E.", "distance_raw": "542 feet"},
        {
            "bearing": 267.583333,
            "distance": leg2_distance,
            "bearing_raw": "S. 87° 35' W.",
            "distance_raw": f"{int(leg2_distance)} feet",
        },
        {"bearing": 176.0, "distance": 180.0, "bearing_raw": "S. 4°00' E.", "distance_raw": "180 feet"},
    ]
    return FeatureGraph(
        graph_id="surgical_repair_scope",
        nodes=[
            FeatureNode(
                id="pob",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            ),
            FeatureNode(
                id="parcel_1_traverse",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    operands=["pob"],
                    params={"courses": courses},
                ),
                provenance=ProvenanceAttachment(
                    source_entity_links=[
                        SourceEntityLink(
                            entity_id="p1_call2_distance",
                            entity_type="distance",
                            source_ref="transcript_edit:resolution_state:fixture",
                        ),
                        SourceEntityLink(
                            entity_id="p1_call2_bearing",
                            entity_type="bearing",
                            source_ref="transcript_edit:resolution_state:fixture",
                        ),
                    ]
                ),
            ),
            FeatureNode(
                id="parcel_1_region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Close", operands=["parcel_1_traverse"]),
            ),
        ],
        edges=[],
    )


def test_patch_ir_draft_course_update_changes_exactly_one_course_distance() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        service = _services(tmp)
        saved = save_ir_artifact(
            dossier_id="d-course-update",
            feature_graph=_three_course_graph(leg2_distance=_CORRUPTED_DISTANCE).model_dump(mode="json"),
            persistence=service,
        )
        assert saved["executed"] is True
        base_ref = saved["outputs"]["working_draft_ref"]
        patched = patch_ir_draft(
            dossier_id="d-course-update",
            base_draft_ref=base_ref,
            course_updates=[
                {
                    "node_id": "parcel_1_traverse",
                    "course_index": 2,
                    "field": "distance",
                    "value": _CORRECTED_DISTANCE,
                    "source_entity_id": "p1_call2_distance",
                    "basis_refs": ["image:derived:fba6f159e40d4010896245d6525d4acf"],
                }
            ],
            persistence=service,
        )
        assert patched["executed"] is True
        assert patched["outputs"]["draft_version"] == "v1"
        assert patched["outputs"]["working_draft_ref"] != base_ref

        from tooling.mapping.deed_to_ir.artifact_hydration import hydrate_feature_graph_artifact_refs

        hydrated = hydrate_feature_graph_artifact_refs(
            dossier_id="d-course-update",
            ref_ids=[base_ref, patched["outputs"]["working_draft_ref"]],
            persistence=service,
        )
        by_ref = {row["ref_id"]: row for row in hydrated["outputs"]["results"]}
        v0_courses = next(
            node["op_expr"]["params"]["courses"]
            for node in by_ref[base_ref]["graph"]["nodes"]
            if node["id"] == "parcel_1_traverse"
        )
        v1_courses = next(
            node["op_expr"]["params"]["courses"]
            for node in by_ref[patched["outputs"]["working_draft_ref"]]["graph"]["nodes"]
            if node["id"] == "parcel_1_traverse"
        )
        assert v0_courses[1]["distance"] == _CORRUPTED_DISTANCE
        assert v1_courses[1]["distance"] == _CORRECTED_DISTANCE
        assert v1_courses[0]["distance"] == v0_courses[0]["distance"] == 542.0
        assert v1_courses[2]["distance"] == v0_courses[2]["distance"] == 180.0
        assert v1_courses[0]["bearing"] == v0_courses[0]["bearing"]
        assert v1_courses[2]["bearing"] == v0_courses[2]["bearing"]


def test_patch_ir_draft_course_update_refusals() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        service = _services(tmp)
        saved = save_ir_artifact(
            dossier_id="d-course-refuse",
            feature_graph=_three_course_graph(leg2_distance=_CORRUPTED_DISTANCE).model_dump(mode="json"),
            persistence=service,
        )
        base_ref = saved["outputs"]["working_draft_ref"]

        missing_node = patch_ir_draft(
            dossier_id="d-course-refuse",
            base_draft_ref=base_ref,
            course_updates=[
                {
                    "node_id": "missing_traverse",
                    "course_index": 2,
                    "field": "distance",
                    "value": _CORRECTED_DISTANCE,
                }
            ],
            persistence=service,
        )
        assert missing_node["executed"] is False
        assert missing_node["refusal"]["reason_code"] == "course_update_node_missing"
        assert missing_node["refusal"]["retryable"] is True

        not_traverse = patch_ir_draft(
            dossier_id="d-course-refuse",
            base_draft_ref=base_ref,
            course_updates=[
                {
                    "node_id": "parcel_1_region",
                    "course_index": 1,
                    "field": "distance",
                    "value": 100,
                }
            ],
            persistence=service,
        )
        assert not_traverse["refusal"]["reason_code"] == "course_update_not_course_traverse"
        assert not_traverse["refusal"]["retryable"] is True

        out_of_range = patch_ir_draft(
            dossier_id="d-course-refuse",
            base_draft_ref=base_ref,
            course_updates=[
                {
                    "node_id": "parcel_1_traverse",
                    "course_index": 99,
                    "field": "distance",
                    "value": _CORRECTED_DISTANCE,
                }
            ],
            persistence=service,
        )
        assert out_of_range["refusal"]["reason_code"] == "course_update_index_out_of_range"
        assert out_of_range["refusal"]["retryable"] is True

        bad_field = patch_ir_draft(
            dossier_id="d-course-refuse",
            base_draft_ref=base_ref,
            course_updates=[
                {
                    "node_id": "parcel_1_traverse",
                    "course_index": 2,
                    "field": "azimuth",
                    "value": 90,
                }
            ],
            persistence=service,
        )
        assert bad_field["refusal"]["reason_code"] == "course_update_field_invalid"
        assert bad_field["refusal"]["retryable"] is True

        bad_value = patch_ir_draft(
            dossier_id="d-course-refuse",
            base_draft_ref=base_ref,
            course_updates=[
                {
                    "node_id": "parcel_1_traverse",
                    "course_index": 2,
                    "field": "distance",
                    "value": "not-a-number",
                }
            ],
            persistence=service,
        )
        assert bad_value["refusal"]["reason_code"] == "course_update_value_invalid"
        assert bad_value["refusal"]["retryable"] is True

        blank_raw = patch_ir_draft(
            dossier_id="d-course-refuse",
            base_draft_ref=base_ref,
            course_updates=[
                {
                    "node_id": "parcel_1_traverse",
                    "course_index": 2,
                    "field": "distance_raw",
                    "value": "   ",
                }
            ],
            persistence=service,
        )
        assert blank_raw["refusal"]["reason_code"] == "course_update_value_invalid"


def test_mapping_review_emits_draft_patch_targets_from_course_legs() -> None:
    course_leg_tables = [
        {
            "feature_id": "parcel_1_traverse",
            "operation": "CourseTraverse",
            "course_count": 3,
            "courses": [
                {
                    "leg_index": 1,
                    "distance": 542.0,
                    "distance_raw": "542 feet",
                    "source_entity_ids": ["p1_call1_distance"],
                    "evidence_refs": ["image:derived:leg1"],
                },
                {
                    "leg_index": 2,
                    "distance": _CORRUPTED_DISTANCE,
                    "distance_raw": "618 feet",
                    "bearing": 267.583333,
                    "bearing_raw": "S. 87° 35' W.",
                    "source_entity_ids": ["p1_call2_distance", "p1_call2_bearing"],
                    "evidence_refs": ["image:derived:fba6f159e40d4010896245d6525d4acf"],
                },
            ],
        }
    ]
    targets = build_draft_patch_targets(course_leg_tables=course_leg_tables)
    by_id = {row["patch_target_id"]: row for row in targets}
    assert "course_distance:p1_call2_distance" in by_id
    distance_target = by_id["course_distance:p1_call2_distance"]
    assert distance_target["node_id"] == "parcel_1_traverse"
    assert distance_target["course_index"] == 2
    assert distance_target["course_array_index"] == 1
    assert distance_target["field"] == "distance"
    assert distance_target["current_value"] == _CORRUPTED_DISTANCE
    assert distance_target["current_raw"] == "618 feet"
    assert distance_target["evidence_refs"] == ["image:derived:fba6f159e40d4010896245d6525d4acf"]
    assert "course_bearing:p1_call2_bearing" in by_id

    review = {
        "mapping_artifact_ref": "feature_graph:mapping:example",
        "source_ir_artifact_ref": "feature_graph:ir:example_v0",
        "draft_patch_targets": targets,
        "sanity_review": {"course_leg_tables": course_leg_tables},
    }
    compact = compact_mapping_review_for_projection(review)
    assert compact is not None
    assert compact.get("draft_patch_targets")
    lines = render_mapping_review_timeline_lines(review)
    assert any("draft_patch_targets" in line for line in lines)
    assert any("course_distance:p1_call2_distance" in line for line in lines)


def test_correction_posture_joins_to_patch_target_and_shell() -> None:
    targets = build_draft_patch_targets(
        course_leg_tables=[
            {
                "feature_id": "parcel_1_traverse",
                "operation": "CourseTraverse",
                "courses": [
                    {
                        "leg_index": 2,
                        "distance": _CORRUPTED_DISTANCE,
                        "distance_raw": "618 feet",
                        "source_entity_ids": ["p1_call2_distance"],
                        "evidence_refs": ["image:derived:fba6f159e40d4010896245d6525d4acf"],
                    }
                ],
            }
        ]
    )
    posture = {
        "active": True,
        "reason_codes": ["ir_value_differs_from_inherited_operand"],
        "candidate_deltas": [
            {
                "target_entity_id": "p1_call2_distance",
                "value_kind": "distance",
                "inherited_value": "618 feet",
                "ir_value": "518 feet",
                "basis_refs": ["image:derived:fba6f159e40d4010896245d6525d4acf"],
            }
        ],
        "contract_ref": "deed_to_ir:correction_contract",
    }
    joined = join_correction_posture_to_patch_targets(
        correction_posture=posture,
        draft_patch_targets=targets,
        base_draft_ref="feature_graph:ir:example_scope_v0",
    )
    assert joined is not None
    delta = joined["candidate_deltas"][0]
    assert delta["matching_patch_target_id"] == "course_distance:p1_call2_distance"
    shells = joined["patch_update_shells"]
    assert len(shells) == 1
    assert shells[0]["base_draft_ref"] == "feature_graph:ir:example_scope_v0"
    update = shells[0]["course_updates"][0]
    assert update["node_id"] == "parcel_1_traverse"
    assert update["course_index"] == 2
    assert update["field"] == "distance"
    assert update["source_entity_id"] == "p1_call2_distance"
    assert isinstance(update["value"], str)
    assert "agent-authored" in update["value"]
    assert update["value"] != _CORRECTED_DISTANCE
    assert update["value"] != _CORRUPTED_DISTANCE


def test_draft_patch_targets_timeline_lines_render() -> None:
    targets = [
        {
            "patch_target_id": "course_distance:p1_call2_distance",
            "source_entity_id": "p1_call2_distance",
            "node_id": "parcel_1_traverse",
            "course_index": 2,
            "field": "distance",
            "current_value": 618,
        }
    ]
    lines = render_draft_patch_targets_timeline_lines(targets)
    assert lines
    turn = {
        "tool_result_raw": {
            "executed": True,
            "outputs": {
                "mapping_review": {
                    "mapping_artifact_ref": "feature_graph:mapping:x",
                    "draft_patch_targets": targets,
                }
            },
        }
    }
    rendered = "\n".join(_render_tool_result(turn))
    assert "draft_patch_targets" in rendered


def _two_parcel_course_tables(*, leg2_distance: float) -> list[dict]:
    courses_p1 = [
        {"bearing": 68.5, "distance": 542.0, "bearing_raw": "N. 68° 30' E.", "distance_raw": "542 feet"},
        {
            "bearing": 267.583333,
            "distance": leg2_distance,
            "bearing_raw": "S. 87° 35' W.",
            "distance_raw": f"{int(leg2_distance)} feet",
        },
    ]
    courses_p2 = [
        {"bearing": 87.583333, "distance": 400.0, "bearing_raw": "N. 87°35' E.", "distance_raw": "400 feet"},
    ]
    operand_index = {
        "p1_call1_distance": ["image:derived:p1d1"],
        "p1_call1_bearing": ["image:derived:p1b1"],
        "p1_call2_distance": ["image:derived:p1d2"],
        "p1_call2_bearing": ["image:derived:p1b2"],
        "p2_call1_distance": ["image:derived:p2d1"],
        "p2_call1_bearing": ["image:derived:p2b1"],
    }
    graph = FeatureGraph(
        graph_id="two_parcel_binding",
        nodes=[
            FeatureNode(
                id="pob",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            ),
            FeatureNode(
                id="parcel_1_traverse",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    operands=["pob"],
                    params={"courses": courses_p1},
                ),
                provenance=ProvenanceAttachment(
                    source_entity_links=[
                        SourceEntityLink(
                            entity_id="p1_call1_distance",
                            entity_type="distance",
                            source_ref="transcript_edit:resolution_state:test",
                        ),
                        SourceEntityLink(
                            entity_id="p1_call1_bearing",
                            entity_type="bearing",
                            source_ref="transcript_edit:resolution_state:test",
                        ),
                        SourceEntityLink(
                            entity_id="p1_call2_distance",
                            entity_type="distance",
                            source_ref="transcript_edit:resolution_state:test",
                        ),
                        SourceEntityLink(
                            entity_id="p1_call2_bearing",
                            entity_type="bearing",
                            source_ref="transcript_edit:resolution_state:test",
                        ),
                    ]
                ),
            ),
            FeatureNode(
                id="parcel_2_traverse",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    operands=["pob"],
                    params={"courses": courses_p2},
                ),
                provenance=ProvenanceAttachment(
                    source_entity_links=[
                        SourceEntityLink(
                            entity_id="p2_call1_distance",
                            entity_type="distance",
                            source_ref="transcript_edit:resolution_state:test",
                        ),
                        SourceEntityLink(
                            entity_id="p2_call1_bearing",
                            entity_type="bearing",
                            source_ref="transcript_edit:resolution_state:test",
                        ),
                    ]
                ),
            ),
        ],
        edges=[],
    )
    compiled = compile_graph(graph).compiled_features
    tables: list[dict] = []
    for node in graph.nodes:
        if node.op_expr is None or node.op_expr.op_name != "CourseTraverse":
            continue
        table = build_course_leg_table(
            node=node,
            compiled_entry=compiled[node.id],
            operand_evidence_index=operand_index,
        )
        if table is not None:
            tables.append(table)
    return tables


def test_br023_case_e_draft_patch_targets_contain_no_cross_parcel_contamination() -> None:
    tables = _two_parcel_course_tables(leg2_distance=_CORRUPTED_DISTANCE)
    targets = build_draft_patch_targets(course_leg_tables=tables)
    parcel_1_targets = [row for row in targets if row.get("node_id") == "parcel_1_traverse"]
    assert parcel_1_targets
    serialized = json.dumps({"targets": targets, "tables": tables})
    assert "p2_call" not in json.dumps(parcel_1_targets)
    assert "image:derived:p2" not in serialized.split("parcel_1_traverse")[1].split("parcel_2_traverse")[0]
    for target in parcel_1_targets:
        assert str(target.get("source_entity_id") or "").startswith("p1_")
        for ref in target.get("evidence_refs") or []:
            assert "p2" not in ref
