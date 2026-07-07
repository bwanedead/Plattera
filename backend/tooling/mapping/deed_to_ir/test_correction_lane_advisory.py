"""Tests for correction_lane_advisory and run-24-style upstream correction steering."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from domains.mapping.deed_to_ir.payloads.published_output import ALLOWED_CLOSURE_DIMENSION_IDS
from feature_graph.artifacts import create_compile_artifact
from feature_graph.compiler import compile_graph
from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr
from feature_graph.provenance import ProvenanceAttachment, SourceEntityLink
from harness.audit.human_timeline import _render_tool_result
from tooling.mapping.deed_to_ir.correction_lane_advisory import detect_correction_lane_advisory
from tooling.mapping.deed_to_ir.final_package_preview_persistence import prepare_deed_to_ir_final_package
from tooling.mapping.deed_to_ir.final_package_preview_projection import (
    render_final_package_preview_timeline_lines,
)
from tooling.mapping.deed_to_ir.mapping_sanity import (
    build_mapping_sanity_review,
    build_operand_evidence_index,
)
from tooling.mapping.deed_to_ir.output_persistence import publish_deed_to_ir_output
from tooling.mapping.deed_to_ir.publish_gate_feedback import render_publish_output_summary_timeline_lines
from tooling.mapping.deed_to_ir.test_final_package_preview import (
    _context,
    _patch_deed_root,
    _prepare_mapping,
)
from tooling.mapping.deed_to_ir.test_upstream_corrections import _sample_upstream_correction

_SOURCE_REPAIR_RESOLUTION = (
    Path(__file__).resolve().parents[4]
    / "practice_deeds"
    / "right_of_way"
    / "deed_to_ir"
    / "variants"
    / "corrupted_handoff_source_repair"
    / "resolution_state.json"
)
_CRITICAL_CROP = "image:derived:fba6f159e40d4010896245d6525d4acf"
_BEARING_CROP = "image:derived:523e479a744742cd992ccb6dbe67dae2"


def _closure_dimensions() -> list[dict]:
    return [
        {"dimension_id": dimension_id, "status": "partial"}
        for dimension_id in sorted(ALLOWED_CLOSURE_DIMENSION_IDS)
    ]


def _run24_suspicious_rows() -> dict:
    return {
        "scope_results": [
            {
                "scope_id": "example_scope_1",
                "status": "handoffable",
                "summary": "Source-grounded correction applied after upstream defect review.",
                "basis_refs": ["image:derived:example_source_crop"],
            }
        ],
        "external_dependencies": [],
        "closure_dimensions": _closure_dimensions(),
        "notes": [
            {
                "note_id": "repair_context",
                "summary": "Corrected IR uses a source-grounded value that differs from inherited handoff.",
                "basis_refs": [],
            }
        ],
        "upstream_corrections": [],
    }


def test_detect_advisory_on_suspicious_empty_corrections() -> None:
    advisory = detect_correction_lane_advisory(**_run24_suspicious_rows())
    assert advisory is not None
    assert advisory["upstream_corrections_empty"] is True
    assert advisory["possible_correction_language_found"] is True


def test_detect_advisory_absent_for_normal_package() -> None:
    advisory = detect_correction_lane_advisory(
        upstream_corrections=[],
        scope_results=[{"scope_id": "example_scope_1", "status": "handoffable", "summary": "Ready."}],
        closure_dimensions=_closure_dimensions(),
        notes=[{"note_id": "n1", "summary": "Routine handoff note.", "basis_refs": []}],
    )
    assert advisory is None


def test_detect_advisory_absent_when_correction_rows_present() -> None:
    advisory = detect_correction_lane_advisory(
        upstream_corrections=[_sample_upstream_correction()],
        scope_results=_run24_suspicious_rows()["scope_results"],
        closure_dimensions=_closure_dimensions(),
        notes=_run24_suspicious_rows()["notes"],
    )
    assert advisory is None


def test_prepare_run24_shape_returns_advisory(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)
        rows = _run24_suspicious_rows()
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **rows,
        )
    assert result["executed"] is True
    advisory = result["outputs"].get("correction_lane_advisory")
    assert isinstance(advisory, dict)
    assert advisory.get("upstream_corrections_empty") is True


def test_prepare_with_correction_row_has_no_advisory(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)
        rows = _run24_suspicious_rows()
        rows["upstream_corrections"] = [_sample_upstream_correction()]
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **rows,
        )
    assert result["executed"] is True
    assert result["outputs"].get("correction_lane_advisory") is None
    assert result["outputs"].get("upstream_correction_count") == 1


def test_publish_from_preview_carries_advisory(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)
        rows = _run24_suspicious_rows()
        prepared = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **rows,
        )
        preview_ref = prepared["outputs"]["final_package_preview_revision_ref"]
        published = publish_deed_to_ir_output(
            dossier_id="d-preview",
            final_package_preview_ref=preview_ref,
            persistence=persistence,
            **ctx,
        )
    assert published["executed"] is True
    assert isinstance(published["outputs"].get("correction_lane_advisory"), dict)


def test_timeline_renders_correction_lane_advisory() -> None:
    advisory = detect_correction_lane_advisory(**_run24_suspicious_rows())
    lines = render_final_package_preview_timeline_lines(
        {"correction_lane_advisory": advisory, "upstream_correction_count": 0},
    )
    body = "\n".join(lines)
    assert "correction_lane_advisory:" in body

    publish_lines = render_publish_output_summary_timeline_lines(
        {
            "output_revision_ref": "deed_to_ir:output:rev:0001",
            "correction_lane_advisory": advisory,
        }
    )
    assert "correction_lane_advisory:" in "\n".join(publish_lines)

    turn = {
        "tool_result_raw": {
            "execution_state": "executed",
            "outputs": {"correction_lane_advisory": advisory},
        }
    }
    rendered = "\n".join(_render_tool_result(turn))
    assert "correction_lane_advisory:" in rendered


def _source_repair_graph(*, leg2_distance: float) -> FeatureGraph:
    courses = [
        {"bearing": 68.5, "distance": 542.0},
        {"bearing": 267.583333, "distance": leg2_distance},
        {"bearing": 176.0, "distance": 180.0},
    ]
    return FeatureGraph(
        graph_id="source_repair_scope",
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
                            entity_id="p1_call2_bearing",
                            entity_type="bearing",
                            source_ref="transcript_edit:resolution_state:fixture",
                        ),
                    ]
                ),
            ),
        ],
        edges=[],
    )


def test_source_repair_resolution_indexes_critical_crop_for_call2_distance() -> None:
    snapshot = json.loads(_SOURCE_REPAIR_RESOLUTION.read_text(encoding="utf-8"))
    index = build_operand_evidence_index(snapshot)
    assert _CRITICAL_CROP in index.get("p1_call2_distance", [])
    assert _BEARING_CROP in index.get("p1_call2_bearing", [])


def test_sanity_review_prefers_distance_crop_for_leg2_even_when_only_bearing_linked() -> None:
    snapshot = json.loads(_SOURCE_REPAIR_RESOLUTION.read_text(encoding="utf-8"))
    index = build_operand_evidence_index(snapshot)
    graph = _source_repair_graph(leg2_distance=618.0)
    compile_artifact = create_compile_artifact(
        artifact_id="compile_source_repair",
        graph_id=graph.graph_id,
        compiled_features=compile_graph(graph).compiled_features,
    )
    sanity = build_mapping_sanity_review(
        graph=graph,
        compile_artifact=compile_artifact,
        operand_evidence_index=index,
    )
    leg2 = sanity["course_leg_tables"][0]["courses"][1]
    assert _CRITICAL_CROP in leg2["evidence_refs"]
    assert leg2["evidence_refs"][0] == _CRITICAL_CROP
    assert _CRITICAL_CROP in sanity["recommended_source_evidence_refs"]
