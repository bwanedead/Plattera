"""Tests for compact mapping review packets (submit, hydrate, slices, timeline)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr
from harness.audit.human_timeline import _render_tool_result
from tooling.mapping.deed_to_ir.artifact_hydration import hydrate_artifact_refs
from tooling.mapping.deed_to_ir.ir_mapping_submission import submit_ir_for_mapping
from tooling.mapping.deed_to_ir.ir_persistence import save_ir_artifact
from tooling.mapping.deed_to_ir.mapping_review import (
    compact_mapping_review_for_projection,
    render_mapping_review_timeline_lines,
)


def _service(tmpdir: str):
    from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

    return FeatureGraphPersistenceService(
        root=Path(tmpdir) / "artifacts",
        state_dir=Path(tmpdir) / "state",
    )


def _mappable_graph() -> FeatureGraph:
    return FeatureGraph(
        graph_id="example_scope_graph",
        nodes=[
            FeatureNode(
                id="anchor",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            ),
            FeatureNode(
                id="traverse",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    operands=["anchor"],
                    params={
                        "courses": [
                            {"bearing": 90.0, "distance": 100.0},
                            {"bearing": 0.0, "distance": 50.0},
                        ]
                    },
                ),
            ),
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Close", operands=["traverse"]),
            ),
        ],
        edges=[],
    )


def _submit_mapping(service, *, dossier_id: str = "d-review"):
    saved = save_ir_artifact(
        dossier_id=dossier_id,
        feature_graph=_mappable_graph().model_dump(mode="json"),
        persistence=service,
    )
    ir_ref = saved["outputs"]["ir_artifact_ref"]
    submitted = submit_ir_for_mapping(
        dossier_id=dossier_id,
        ir_artifact_ref=ir_ref,
        persistence=service,
    )
    return submitted, ir_ref


def test_submit_output_includes_mapping_review() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)
        submitted, ir_ref = _submit_mapping(service)
    assert submitted["executed"] is True
    review = submitted["outputs"]["mapping_review"]
    assert review["mapping_artifact_ref"] == submitted["outputs"]["mapping_artifact_ref"]
    assert review.get("sanity_review") is not None
    assert review["source_ir_artifact_ref"] == ir_ref
    assert review["recommended_publish_refs"]["expected_ir_artifact_ref"] == ir_ref
    assert review["recommended_publish_refs"]["mapping_artifact_ref"] == review["mapping_artifact_ref"]
    assert review["recommended_review_refs"] == [
        review["mapping_artifact_ref"],
        review["control_render_ref"],
        review["geometry_ref"],
    ]
    assert "b64" not in json.dumps(review)
    assert tmpdir not in json.dumps(review)


def test_hydrate_mapping_ref_includes_mapping_review() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)
        submitted, ir_ref = _submit_mapping(service)
        mapping_ref = submitted["outputs"]["mapping_artifact_ref"]
        hydrated = hydrate_artifact_refs(
            dossier_id="d-review",
            ref_ids=[mapping_ref],
            persistence=service,
        )
    row = hydrated["outputs"]["results"][0]
    review = row["mapping_review"]
    assert review["source_ir_artifact_ref"] == ir_ref
    assert review["recommended_publish_refs"]["expected_ir_artifact_ref"] == ir_ref
    assert review["geometry_ref"] == submitted["outputs"]["geometry_ref"]


def test_compact_mapping_review_preserves_refs_under_large_artifact_noise() -> None:
    review = {
        "mapping_artifact_ref": "feature_graph:mapping:mapping_example",
        "source_ir_artifact_ref": "feature_graph:ir:example_scope_v1",
        "control_render_ref": "artifact://dossiers/feature_graphs/d-example/mappings/m/control.png",
        "geometry_ref": "artifact://dossiers/feature_graphs/d-example/mappings/m/geometry.geojson",
        "compile_gap_count": 0,
        "judge_gap_count": 0,
        "skipped_feature_count": 1,
        "recommended_publish_refs": {
            "mapping_artifact_ref": "feature_graph:mapping:mapping_example",
            "expected_ir_artifact_ref": "feature_graph:ir:example_scope_v1",
        },
        # Noise that must not displace compact projection of publish refs.
        "pad": "x" * 4000,
    }
    compact = compact_mapping_review_for_projection(review)
    assert compact is not None
    assert compact["source_ir_artifact_ref"] == review["source_ir_artifact_ref"]
    assert compact["recommended_publish_refs"]["expected_ir_artifact_ref"] == review["source_ir_artifact_ref"]
    assert "pad" not in compact


def test_timeline_renders_mapping_review_compactly() -> None:
    review = {
        "mapping_artifact_ref": "feature_graph:mapping:mapping_example",
        "source_ir_artifact_ref": "feature_graph:ir:example_scope_v1",
        "control_render_ref": "artifact://dossiers/feature_graphs/d-example/mappings/m/control.png",
        "geometry_ref": "artifact://dossiers/feature_graphs/d-example/mappings/m/geometry.geojson",
        "compiled_feature_count": 3,
        "rendered_feature_count": 3,
        "skipped_feature_count": 1,
        "warning_count": 2,
        "compile_gap_count": 0,
        "judge_gap_count": 0,
        "recommended_publish_refs": {
            "mapping_artifact_ref": "feature_graph:mapping:mapping_example",
            "expected_ir_artifact_ref": "feature_graph:ir:example_scope_v1",
        },
    }
    lines = render_mapping_review_timeline_lines(review)
    body = "\n".join(lines)
    assert "mapping_review:" in body
    assert "source_ir: feature_graph:ir:example_scope_v1" in body
    assert "expected_ir_artifact_ref=feature_graph:ir:example_scope_v1" in body
    assert "b64" not in body
    assert "C:\\" not in body

    turn = {
        "tool_result_raw": {
            "execution_state": "executed",
            "outputs": {"mapping_review": review},
            "artifact_refs": [review["mapping_artifact_ref"]],
        }
    }
    rendered = "\n".join(_render_tool_result(turn))
    assert "mapping_review:" in rendered


def test_compact_mapping_review_projection_fields() -> None:
    review = {
        "mapping_artifact_ref": "feature_graph:mapping:m1",
        "source_ir_artifact_ref": "feature_graph:ir:v1",
        "control_render_ref": "artifact://x/control.png",
        "geometry_ref": "artifact://x/geometry.geojson",
        "compile_gap_count": 0,
        "judge_gap_count": 1,
        "skipped_feature_count": 2,
        "recommended_publish_refs": {
            "mapping_artifact_ref": "feature_graph:mapping:m1",
            "expected_ir_artifact_ref": "feature_graph:ir:v1",
        },
        "clean_render_ref": "artifact://x/clean.png",
    }
    compact = compact_mapping_review_for_projection(review)
    assert compact is not None
    assert "clean_render_ref" not in compact
    assert compact["recommended_publish_refs"]["expected_ir_artifact_ref"] == "feature_graph:ir:v1"
