"""Tests for mapping sanity review packet and ref safety."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from feature_graph.artifacts import create_compile_artifact
from feature_graph.compiler import compile_graph
from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr
from feature_graph.provenance import ProvenanceAttachment, SourceEntityLink
from feature_graph.rendering.geometry_projection import project_compiled_geometry
from feature_graph.rendering.renderer import render_clean_png, render_control_png
from harness.audit.human_timeline import _render_tool_result
from tooling.mapping.deed_to_ir.artifact_hydration import hydrate_artifact_refs
from tooling.mapping.deed_to_ir.final_package_preview_persistence import prepare_deed_to_ir_final_package
from tooling.mapping.deed_to_ir.ir_mapping_submission import submit_ir_for_mapping
from tooling.mapping.deed_to_ir.ir_persistence import save_ir_artifact
from tooling.mapping.deed_to_ir.mapping_review import (
    compact_mapping_review_for_projection,
    render_mapping_review_timeline_lines,
)
from tooling.mapping.deed_to_ir.mapping_sanity import (
    AMBIGUOUS_OPERAND_FAMILY_REASON,
    build_course_leg_table,
    build_mapping_sanity_review,
    build_operand_evidence_index,
    ordered_entity_ids_for_leg,
)
from feature_graph.artifacts import create_judge_artifact, create_ir_artifact
from feature_graph.gaps import JudgeReport


def _service(tmpdir: str):
    from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

    return FeatureGraphPersistenceService(
        root=Path(tmpdir) / "artifacts",
        state_dir=Path(tmpdir) / "state",
    )


def _parcel1_graph(*, leg2_distance: float) -> FeatureGraph:
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
        graph_id="parcel1_scope",
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
        ],
        edges=[],
    )


def test_course_leg_table_includes_source_and_evidence_refs() -> None:
    graph = _parcel1_graph(leg2_distance=618.0)
    compile_result = compile_graph(graph)
    node = graph.nodes[1]
    entry = compile_result.compiled_features["parcel_1_traverse"]
    operand_index = {"p1_call2_distance": ["image:derived:fba6f159e40d4010896245d6525d4acf"]}
    table = build_course_leg_table(
        node=node,
        compiled_entry=entry,
        operand_evidence_index=operand_index,
    )
    assert table is not None
    assert table["operation"] == "CourseTraverse"
    assert table["course_count"] == 3
    leg2 = table["courses"][1]
    assert leg2["leg_index"] == 2
    assert leg2["distance"] == 618.0
    assert leg2["bearing_raw"] == "S. 87° 35' W."
    assert "p1_call2_distance" in leg2["source_entity_ids"]
    assert leg2["evidence_refs"] == ["image:derived:fba6f159e40d4010896245d6525d4acf"]


def test_sanity_review_includes_endpoint_displacement_candidates() -> None:
    graph = _parcel1_graph(leg2_distance=618.0)
    compile_artifact = create_compile_artifact(
        artifact_id="compile_sanity",
        graph_id=graph.graph_id,
        compiled_features=compile_graph(graph).compiled_features,
    )
    sanity = build_mapping_sanity_review(graph=graph, compile_artifact=compile_artifact)
    assert sanity["endpoint_displacement_candidates"]
    candidate = sanity["endpoint_displacement_candidates"][0]
    assert candidate["feature_id"] == "parcel_1_traverse"
    assert float(candidate["endpoint_displacement"]) > 90.0
    assert sanity["review_questions"]


def test_submit_output_includes_sanity_review() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)
        saved = save_ir_artifact(
            dossier_id="d-sanity",
            feature_graph=_parcel1_graph(leg2_distance=618.0).model_dump(mode="json"),
            persistence=service,
        )
        submitted = submit_ir_for_mapping(
            dossier_id="d-sanity",
            ir_artifact_ref=saved["outputs"]["ir_artifact_ref"],
            persistence=service,
        )
    review = submitted["outputs"]["mapping_review"]
    sanity = review.get("sanity_review")
    assert isinstance(sanity, dict)
    assert sanity.get("endpoint_displacement_candidates")


def test_submit_includes_source_evidence_refs_from_resolution_snapshot() -> None:
    evidence_ref = "image:derived:fba6f159e40d4010896245d6525d4acf"
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)
        saved = save_ir_artifact(
            dossier_id="d-sanity-submit-evidence",
            feature_graph=_parcel1_graph(leg2_distance=618.0).model_dump(mode="json"),
            persistence=service,
        )
        submitted = submit_ir_for_mapping(
            dossier_id="d-sanity-submit-evidence",
            ir_artifact_ref=saved["outputs"]["ir_artifact_ref"],
            persistence=service,
            resolution_state_snapshot={
                "items": [
                    {
                        "covered_units": [
                            {
                                "unit_id": "p1_call2_distance",
                                "evidence_refs": [evidence_ref],
                            }
                        ]
                    }
                ]
            },
        )
    sanity = submitted["outputs"]["mapping_review"]["sanity_review"]
    assert evidence_ref in (sanity.get("recommended_source_evidence_refs") or [])
    leg2 = sanity["course_leg_tables"][0]["courses"][1]
    assert leg2["distance"] == 618.0
    assert evidence_ref in leg2["evidence_refs"]


def test_hydrate_mapping_ref_includes_sanity_review() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)
        saved = save_ir_artifact(
            dossier_id="d-sanity-hydrate",
            feature_graph=_parcel1_graph(leg2_distance=618.0).model_dump(mode="json"),
            persistence=service,
        )
        submitted = submit_ir_for_mapping(
            dossier_id="d-sanity-hydrate",
            ir_artifact_ref=saved["outputs"]["ir_artifact_ref"],
            persistence=service,
        )
        mapping_ref = submitted["outputs"]["mapping_artifact_ref"]
        hydrated = hydrate_artifact_refs(
            dossier_id="d-sanity-hydrate",
            ref_ids=[mapping_ref],
            persistence=service,
            handoff_context={
                "resolution_state_snapshot": {
                    "items": [
                        {
                            "covered_units": [
                                {
                                    "unit_id": "p1_call2_distance",
                                    "evidence_refs": ["image:derived:fba6f159e40d4010896245d6525d4acf"],
                                }
                            ]
                        }
                    ]
                }
            },
        )
    review = hydrated["outputs"]["results"][0]["mapping_review"]
    sanity = review.get("sanity_review")
    assert isinstance(sanity, dict)
    evidence_refs = sanity.get("recommended_source_evidence_refs") or []
    assert "image:derived:fba6f159e40d4010896245d6525d4acf" in evidence_refs


def test_compact_mapping_review_preserves_full_mapping_ref_and_sanity() -> None:
    full_mapping_ref = "feature_graph:mapping:mapping_right_of_way_deed_66fe47f4"
    review = {
        "mapping_artifact_ref": full_mapping_ref,
        "source_ir_artifact_ref": "feature_graph:ir:example_scope_v1",
        "control_render_ref": "artifact://dossiers/feature_graphs/d-example/mappings/m/control.png",
        "geometry_ref": "artifact://dossiers/feature_graphs/d-example/mappings/m/geometry.geojson",
        "compile_gap_count": 0,
        "judge_gap_count": 0,
        "skipped_feature_count": 0,
        "recommended_publish_refs": {
            "mapping_artifact_ref": full_mapping_ref,
            "expected_ir_artifact_ref": "feature_graph:ir:example_scope_v1",
        },
        "sanity_review": {
            "feature_metrics": [
                {
                    "feature_id": "parcel_1_traverse",
                    "endpoint_displacement": 100.8495,
                    "total_length": 1340.0,
                    "vertex_count": 4,
                }
            ],
            "course_leg_tables": [
                {
                    "feature_id": "parcel_1_traverse",
                    "course_count": 3,
                    "courses": [
                        {
                            "leg_index": 2,
                            "distance": 618,
                            "bearing": 267.583333,
                            "evidence_refs": ["image:derived:fba6f159e40d4010896245d6525d4acf"],
                        }
                    ],
                }
            ],
            "endpoint_displacement_candidates": [
                {"feature_id": "parcel_1_traverse", "endpoint_displacement": 100.8495}
            ],
            "recommended_source_evidence_refs": ["image:derived:fba6f159e40d4010896245d6525d4acf"],
            "review_questions": ["Does endpoint displacement matter for the authored geometry role?"],
        },
        "pad": "x" * 4000,
    }
    compact = compact_mapping_review_for_projection(review)
    assert compact is not None
    assert compact["mapping_artifact_ref"] == full_mapping_ref
    assert compact["recommended_publish_refs"]["mapping_artifact_ref"] == full_mapping_ref
    assert compact.get("sanity_review") is not None
    assert "pad" not in compact
    serialized = json.dumps(compact)
    assert full_mapping_ref in serialized


def test_prepare_missing_mapping_ref_is_retryable_with_valid_refs() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)
        graph = _parcel1_graph(leg2_distance=518.0)
        saved = save_ir_artifact(
            dossier_id="d-prepare-missing",
            feature_graph=graph.model_dump(mode="json"),
            persistence=service,
        )
        submitted = submit_ir_for_mapping(
            dossier_id="d-prepare-missing",
            ir_artifact_ref=saved["outputs"]["ir_artifact_ref"],
            persistence=service,
        )
        valid_ref = submitted["outputs"]["mapping_artifact_ref"]
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-prepare-missing",
            transcription_id="tx1",
            workspace_id="ws1",
            run_id=None,
            transcript_edit_source_revision_ref="transcript_edit:output",
            resolution_state_ref="transcript_edit:resolution_state:fixture-001",
            mapping_artifact_ref="feature_graph:mapping:missing_map",
            scope_results=[],
            external_dependencies=[],
            closure_dimensions=[],
            persistence=service,
        )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "mapping_artifact_not_found"
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False
    assert valid_ref in result["outputs"]["valid_mapping_refs"]
    assert "submit_ir_for_mapping" in result["outputs"]["repair_hint"]


def test_timeline_renders_mapping_sanity_and_full_refs() -> None:
    full_mapping_ref = "feature_graph:mapping:mapping_right_of_way_deed_66fe47f4"
    review = {
        "mapping_artifact_ref": full_mapping_ref,
        "source_ir_artifact_ref": "feature_graph:ir:example_scope_v1",
        "sanity_review": {
            "feature_metrics": [
                {
                    "feature_id": "parcel_1_traverse",
                    "endpoint_displacement": 100.8495,
                    "total_length": 1340.0,
                    "vertex_count": 4,
                }
            ],
            "course_leg_tables": [
                {
                    "courses": [
                        {
                            "leg_index": 2,
                            "distance": 618,
                            "bearing": 267.583333,
                            "evidence_refs": ["image:derived:fba6f159e40d4010896245d6525d4acf"],
                        }
                    ]
                }
            ],
        },
    }
    lines = render_mapping_review_timeline_lines(review)
    body = "\n".join(lines)
    assert full_mapping_ref in body
    assert "mapping_sanity:" in body
    assert "endpoint_gap=100.8495" in body
    assert "leg 2 distance=618" in body
    assert "image:derived:fba6f159e40d4010896245d6525d4acf" in body

    turn = {
        "tool_result_raw": {
            "execution_state": "executed",
            "outputs": {"mapping_review": review},
        }
    }
    rendered = "\n".join(_render_tool_result(turn))
    assert full_mapping_ref in rendered
    assert "mapping_sanity:" in rendered


def test_compact_projection_preserves_sanity_lane() -> None:
    review = {
        "mapping_artifact_ref": "feature_graph:mapping:m1",
        "source_ir_artifact_ref": "feature_graph:ir:v1",
        "sanity_review": {
            "feature_metrics": [{"feature_id": "parcel_1_traverse", "endpoint_displacement": 2.85}],
            "endpoint_displacement_candidates": [{"feature_id": "parcel_1_traverse", "endpoint_displacement": 2.85}],
            "review_questions": ["Does endpoint displacement matter for the authored geometry role?"],
        },
    }
    compact = compact_mapping_review_for_projection(review)
    assert compact is not None
    assert compact.get("sanity_review") is not None


def test_control_render_includes_gap_annotation_without_cluttering_clean() -> None:
    graph = _parcel1_graph(leg2_distance=618.0)
    compile_artifact = create_compile_artifact(
        artifact_id="compile_render_gap",
        graph_id=graph.graph_id,
        compiled_features=compile_graph(graph).compiled_features,
    )
    judge_artifact = create_judge_artifact(
        artifact_id="judge_render_gap",
        graph_id=graph.graph_id,
        report=JudgeReport(graph_id=graph.graph_id),
    )
    ir_artifact = create_ir_artifact(artifact_id="ir_render_gap", graph=graph)
    projection = project_compiled_geometry(graph=graph, compile_artifact=compile_artifact)
    clean_bytes = render_clean_png(
        projection=projection,
        graph=graph,
        compile_artifact=compile_artifact,
        judge_artifact=judge_artifact,
    )
    control_bytes = render_control_png(
        projection=projection,
        graph=graph,
        compile_artifact=compile_artifact,
        judge_artifact=judge_artifact,
    )
    assert len(clean_bytes) > 100
    assert len(control_bytes) > 100
    assert control_bytes != clean_bytes


def test_operand_evidence_index_is_mechanical() -> None:
    index = build_operand_evidence_index(
        {
            "items": [
                {
                    "covered_units": [
                        {
                            "unit_id": "p1_call2_distance",
                            "evidence_refs": ["image:derived:abc"],
                        }
                    ]
                }
            ]
        }
    )
    assert index["p1_call2_distance"] == ["image:derived:abc"]


_CRITICAL_CROP = "image:derived:fba6f159e40d4010896245d6525d4acf"


def _single_course_graph(
    *,
    node_id: str,
    provenance_entity_ids: list[str],
    distance: float = 542.0,
) -> FeatureGraph:
    return FeatureGraph(
        graph_id="binding_scope",
        nodes=[
            FeatureNode(
                id="pob",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            ),
            FeatureNode(
                id=node_id,
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    operands=["pob"],
                    params={
                        "courses": [
                            {
                                "bearing": 68.5,
                                "distance": distance,
                                "bearing_raw": "N. 68° 30' E.",
                                "distance_raw": f"{int(distance)} feet",
                            }
                        ]
                    },
                ),
                provenance=ProvenanceAttachment(
                    source_entity_links=[
                        SourceEntityLink(
                            entity_id=entity_id,
                            entity_type="distance" if "distance" in entity_id else "bearing",
                            source_ref="transcript_edit:resolution_state:test",
                        )
                        for entity_id in provenance_entity_ids
                    ]
                ),
            ),
        ],
        edges=[],
    )


def _two_parcel_leg1_operand_index() -> dict[str, list[str]]:
    return {
        "p1_call1_distance": ["image:derived:p1d1"],
        "p1_call1_bearing": ["image:derived:p1b1"],
        "p2_call1_distance": ["image:derived:p2d1"],
        "p2_call1_bearing": ["image:derived:p2b1"],
    }


def test_br023_case_a_shared_call_ordinals_bind_only_same_parcel_family() -> None:
    graph = _single_course_graph(
        node_id="parcel_1_traverse",
        provenance_entity_ids=["p1_call1_distance", "p1_call1_bearing"],
    )
    node = graph.nodes[1]
    entry = compile_graph(graph).compiled_features["parcel_1_traverse"]
    table = build_course_leg_table(
        node=node,
        compiled_entry=entry,
        operand_evidence_index=_two_parcel_leg1_operand_index(),
    )
    assert table is not None
    leg1 = table["courses"][0]
    assert leg1["source_entity_ids"] == ["p1_call1_distance", "p1_call1_bearing"]
    assert leg1["evidence_refs"] == ["image:derived:p1d1", "image:derived:p1b1"]
    assert "p2_call1_distance" not in leg1["source_entity_ids"]
    assert "image:derived:p2d1" not in leg1["evidence_refs"]


def test_br023_case_b_partial_direct_provenance_supplements_same_family_only() -> None:
    graph = _parcel1_graph(leg2_distance=618.0)
    graph.nodes[1].provenance = ProvenanceAttachment(
        source_entity_links=[
            SourceEntityLink(
                entity_id="p1_call2_bearing",
                entity_type="bearing",
                source_ref="transcript_edit:resolution_state:test",
            )
        ]
    )
    node = graph.nodes[1]
    entry = compile_graph(graph).compiled_features["parcel_1_traverse"]
    operand_index = {
        "p1_call2_distance": [_CRITICAL_CROP],
        "p2_call2_distance": ["image:derived:parcel2_wrong"],
    }
    table = build_course_leg_table(
        node=node,
        compiled_entry=entry,
        operand_evidence_index=operand_index,
    )
    leg2 = table["courses"][1]
    assert leg2["source_entity_ids"] == ["p1_call2_distance", "p1_call2_bearing"]
    assert leg2["evidence_refs"] == [_CRITICAL_CROP]
    assert "p2_call2_distance" not in leg2["source_entity_ids"]


def test_br023_same_family_unknown_kind_not_supplemented_from_index() -> None:
    graph = _parcel1_graph(leg2_distance=618.0)
    graph.nodes[1].provenance = ProvenanceAttachment(
        source_entity_links=[
            SourceEntityLink(
                entity_id="p1_call2_bearing",
                entity_type="bearing",
                source_ref="transcript_edit:resolution_state:test",
            )
        ]
    )
    node = graph.nodes[1]
    entry = compile_graph(graph).compiled_features["parcel_1_traverse"]
    operand_index = {
        "p1_call2_distance": [_CRITICAL_CROP],
        "p1_call2_note": ["image:derived:note_should_not_bind"],
    }
    table = build_course_leg_table(
        node=node,
        compiled_entry=entry,
        operand_evidence_index=operand_index,
    )
    leg2 = table["courses"][1]
    assert leg2["source_entity_ids"] == ["p1_call2_distance", "p1_call2_bearing"]
    assert "p1_call2_note" not in leg2["source_entity_ids"]
    assert "image:derived:note_should_not_bind" not in leg2["evidence_refs"]


def test_br023_case_c_unambiguous_index_only_fallback() -> None:
    operand_index = {
        "p1_call2_distance": [_CRITICAL_CROP],
        "p1_call2_bearing": ["image:derived:523e479a744742cd992ccb6dbe67dae2"],
    }
    entity_ids = ordered_entity_ids_for_leg(
        source_entity_ids=[],
        operand_evidence_index=operand_index,
        leg_index=2,
    )
    assert entity_ids == ["p1_call2_distance", "p1_call2_bearing"]


def test_br023_case_d_ambiguous_index_only_fallback_is_observable() -> None:
    operand_index = {
        "p1_call2_distance": [_CRITICAL_CROP],
        "p2_call2_distance": ["image:derived:parcel2_wrong"],
    }
    graph = _parcel1_graph(leg2_distance=618.0)
    graph.nodes[1].provenance = None
    node = graph.nodes[1]
    entry = compile_graph(graph).compiled_features["parcel_1_traverse"]
    table = build_course_leg_table(
        node=node,
        compiled_entry=entry,
        operand_evidence_index=operand_index,
    )
    leg2 = table["courses"][1]
    assert leg2.get("source_entity_ids") is None
    assert leg2["source_entity_ids_reason"] == AMBIGUOUS_OPERAND_FAMILY_REASON
    assert leg2["evidence_refs"] == []
    assert leg2["evidence_refs_reason"] == AMBIGUOUS_OPERAND_FAMILY_REASON
    assert "no_operand_evidence_indexed" not in leg2
    assert "p1_call2_distance" not in json.dumps(leg2)
    assert "p2_call2_distance" not in json.dumps(leg2)


def test_br023_case_f_run40_shaped_parcel1_leg2_evidence_binding() -> None:
    graph = _parcel1_graph(leg2_distance=618.0)
    compile_artifact = create_compile_artifact(
        artifact_id="compile_run40_shape",
        graph_id=graph.graph_id,
        compiled_features=compile_graph(graph).compiled_features,
    )
    sanity = build_mapping_sanity_review(
        graph=graph,
        compile_artifact=compile_artifact,
        operand_evidence_index={"p1_call2_distance": [_CRITICAL_CROP]},
    )
    leg2 = sanity["course_leg_tables"][0]["courses"][1]
    assert leg2["distance"] == 618.0
    assert leg2["source_entity_ids"] == ["p1_call2_distance", "p1_call2_bearing"]
    assert _CRITICAL_CROP in leg2["evidence_refs"]


def test_br024_course_leg_intake_omissions_count_only_retained_tables() -> None:
    from tooling.mapping.deed_to_ir.mapping_sanity import (
        MAX_PROJECTED_COURSE_LEG_TABLES,
        MAX_PROJECTED_COURSE_ROWS,
        compact_sanity_review_for_projection,
    )

    source_table_count = 4
    courses_per_table = 8
    raw_tables = [
        {
            "feature_id": f"parcel_{table_idx}_traverse",
            "courses": [
                {"leg_index": course_idx + 1, "distance": 500.0 + course_idx, "bearing": 90.0}
                for course_idx in range(courses_per_table)
            ],
        }
        for table_idx in range(source_table_count)
    ]
    compact = compact_sanity_review_for_projection({"course_leg_tables": raw_tables})
    assert compact is not None
    kept_tables = compact["course_leg_tables"]
    assert len(kept_tables) == MAX_PROJECTED_COURSE_LEG_TABLES
    assert compact["course_leg_tables_omitted_count"] == source_table_count - MAX_PROJECTED_COURSE_LEG_TABLES
    for table in kept_tables:
        assert table["courses_source_count"] == courses_per_table
        assert len(table["courses"]) == MAX_PROJECTED_COURSE_ROWS
    expected_course_omitted = MAX_PROJECTED_COURSE_LEG_TABLES * (
        courses_per_table - MAX_PROJECTED_COURSE_ROWS
    )
    assert compact["courses_omitted_count"] == expected_course_omitted
    assert len(kept_tables) + compact["course_leg_tables_omitted_count"] == source_table_count
    for table in kept_tables:
        assert len(table["courses"]) + (courses_per_table - len(table["courses"])) == courses_per_table
