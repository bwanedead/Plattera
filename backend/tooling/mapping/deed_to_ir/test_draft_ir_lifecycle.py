"""Tests for draft IR lifecycle: versioning, compile/judge feedback, carry-forward."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr

from harness.audit.human_timeline import _render_tool_result
from harness.runtime.memory.tool_result_slices import build_recent_tool_result_slices
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService
from tooling.mapping.deed_to_ir.draft_ir_lifecycle import (
    build_draft_source_metadata,
    build_evaluation_feedback,
    compact_current_draft_ir_for_projection,
    draft_version_label,
)
from tooling.mapping.deed_to_ir.ir_persistence import save_ir_artifact


def _linestep_graph(graph_id: str = "parcel_1_ir") -> dict:
    graph = FeatureGraph(
        graph_id=graph_id,
        nodes=[
            FeatureNode(
                id="start",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            ),
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    operands=["start"],
                    params={"bearing": 0.0, "distance": 100.0},
                ),
            ),
        ],
        edges=[],
    )
    return graph.model_dump(mode="json")


def _service(tmpdir: str) -> FeatureGraphPersistenceService:
    return FeatureGraphPersistenceService(
        root=Path(tmpdir) / "artifacts",
        state_dir=Path(tmpdir) / "state",
    )


def test_draft_version_labels_increment_per_graph():
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)
        first = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=_linestep_graph(),
            persistence=service,
        )
        second = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=_linestep_graph(),
            persistence=service,
        )
    assert first["outputs"]["draft_version"] == "v0"
    assert first["outputs"]["draft_sequence_index"] == 0
    assert first["outputs"]["is_draft"] is True
    assert second["outputs"]["draft_version"] == "v1"
    assert second["outputs"]["draft_sequence_index"] == 1


def test_explicit_artifact_id_preserves_id_and_draft_metadata():
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)
        result = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=_linestep_graph("explicit_graph"),
            artifact_id="ir_explicit_test",
            persistence=service,
        )
    assert result["outputs"]["artifact_id"] == "ir_explicit_test"
    assert result["outputs"]["draft_ir_ref"] == "feature_graph:ir:ir_explicit_test"
    assert result["outputs"]["draft_version"] == "v0"


def test_successful_save_returns_compile_and_judge_refs():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=_linestep_graph(),
            persistence=_service(tmpdir),
        )
    outputs = result["outputs"]
    assert outputs["compile_artifact_ref"].startswith("feature_graph:compile:")
    assert outputs["judge_artifact_ref"].startswith("feature_graph:judge:")
    assert "compile_gap_count" in outputs
    assert "judge_finding_count" in outputs
    assert isinstance(outputs["compile_gaps"], list)
    assert isinstance(outputs["judge_findings"], list)
    assert "mechanically_mappable_candidate" in outputs
    dumped = json.dumps(result)
    assert "artifact_path" not in dumped


def test_invalid_schema_still_retryable_and_persists_nothing():
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)
        before = list(service.list_artifacts("d-test", artifact_type="ir"))
        result = save_ir_artifact(
            dossier_id="d-test",
            feature_graph={"graph_id": "bad", "nodes": "not-a-list"},
            persistence=service,
        )
        after = list(service.list_artifacts("d-test", artifact_type="ir"))
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert before == after


def test_current_draft_ir_in_tool_result_slices():
    outputs = {
        "draft_version": "v0",
        "current_draft_ir": {
            "draft_ir_ref": "feature_graph:ir:ir_test",
            "draft_version": "v0",
            "graph_id": "parcel_1_ir",
            "node_count": 2,
            "edge_count": 0,
            "unknown_node_count": 0,
            "source_entity_link_count": 0,
            "nodes": [{"id": "start", "kind": "point"}],
            "edges": [],
            "compile_gap_count": 0,
            "judge_finding_count": 0,
            "mechanically_mappable_candidate": True,
        },
    }
    slices = build_recent_tool_result_slices(
        [
            {
                "kernel_turn_index": 1,
                "action_type": "save_ir_artifact",
                "execution_state": "executed",
                "artifact_refs": ["feature_graph:ir:ir_test"],
                "outputs_for_continuity": outputs,
            }
        ]
    )
    assert slices
    row = slices[0]
    assert row.get("current_draft_ir")
    assert row["current_draft_ir"]["draft_version"] == "v0"


def test_timeline_renders_draft_version_and_counts():
    turn = {
        "tool_result_raw": {
            "execution_state": "executed",
            "artifact_refs": ["feature_graph:ir:ir_test"],
            "outputs": {
                "draft_version": "v1",
                "current_draft_ir": {
                    "draft_ir_ref": "feature_graph:ir:ir_test",
                    "draft_version": "v1",
                    "graph_id": "parcel_1_ir",
                    "node_count": 2,
                    "edge_count": 0,
                    "compile_gap_count": 0,
                    "judge_finding_count": 1,
                    "mechanically_mappable_candidate": False,
                    "mapping_submission_ready_candidate": False,
                    "placeholder_only_graph": False,
                    "renderable_feature_count": 2,
                },
                "compile_gap_count": 0,
                "judge_finding_count": 1,
            },
        }
    }
    body = "\n".join(_render_tool_result(turn))
    assert "draft_version: v1" in body
    assert "compile_gap_count: 0" in body
    assert "judge_finding_count: 1" in body
    assert "mapping_submission_ready_candidate" in body


def test_draft_metadata_helpers():
    assert draft_version_label(0) == "v0"
    meta = build_draft_source_metadata(graph_id="g1", draft_sequence_index=2)
    assert meta["draft_version"] == "v2"
    assert meta["is_draft"] is True
    compact = compact_current_draft_ir_for_projection(
        {
            "draft_ir_ref": "feature_graph:ir:x",
            "draft_version": "v0",
            "graph_id": "g1",
            "node_count": 1,
            "edge_count": 0,
        }
    )
    assert compact is not None
    assert compact["draft_version"] == "v0"


def test_build_evaluation_feedback_without_outcomes_is_not_mappable():
    feedback = build_evaluation_feedback(compile_outcome=None, judge_outcome=None)
    assert feedback["compile_artifact_ref"] is None
    assert feedback["judge_artifact_ref"] is None
    assert feedback["compile_gap_count"] is None
    assert feedback["judge_finding_count"] is None
    assert feedback["mechanically_mappable_candidate"] is False
    assert feedback["mapping_submission_ready_candidate"] is False


def test_evaluation_failure_still_saves_draft_but_not_mappable_candidate():
    class _FailingEvaluation:
        def compile_and_judge_ir(self, **_kwargs):
            raise RuntimeError("compile_judge_evaluation_failed")

    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)
        before = list(service.list_artifacts("d-test", artifact_type="ir"))
        result = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=_linestep_graph(),
            persistence=service,
            evaluation=_FailingEvaluation(),  # type: ignore[arg-type]
        )
        after = list(service.list_artifacts("d-test", artifact_type="ir"))
    assert result["executed"] is True
    assert len(after) == len(before) + 1
    outputs = result["outputs"]
    warning = outputs.get("evaluation_warning")
    assert isinstance(warning, dict)
    assert warning.get("reason_code") == "compile_judge_evaluation_failed"
    assert outputs["compile_artifact_ref"] is None
    assert outputs["judge_artifact_ref"] is None
    assert outputs["mechanically_mappable_candidate"] is False
    assert outputs["current_draft_ir"]["mechanically_mappable_candidate"] is False
    assert outputs["current_draft_ir"]["evaluation_warning"]["reason_code"] == "compile_judge_evaluation_failed"
