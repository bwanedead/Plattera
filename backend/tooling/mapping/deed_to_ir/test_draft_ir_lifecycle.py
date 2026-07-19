"""Tests for draft IR lifecycle: versioning, compile/judge feedback, carry-forward."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr

from harness.audit.human_timeline import _render_tool_result
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService
from tooling.mapping.deed_to_ir.draft_ir_lifecycle import (
    build_draft_repair_items,
    build_draft_source_metadata,
    build_evaluation_feedback,
    compact_current_draft_ir_for_projection,
    compute_draft_quality_flags,
    draft_version_label,
    render_current_draft_ir_timeline_lines,
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


def test_current_draft_ir_compacts_for_tooling_projection():
    current = {
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
    }
    compact = compact_current_draft_ir_for_projection(current)
    assert compact is not None
    assert compact["draft_version"] == "v0"
    assert compact["draft_ir_ref"] == "feature_graph:ir:ir_test"


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


def test_compute_draft_quality_flags_mechanical_only():
    assert compute_draft_quality_flags(source_entity_link_count=0, unknown_node_count=0) == [
        "no_source_entity_links"
    ]
    assert compute_draft_quality_flags(source_entity_link_count=2, unknown_node_count=1) == [
        "unknown_nodes_present"
    ]
    assert compute_draft_quality_flags(source_entity_link_count=0, unknown_node_count=2) == [
        "no_source_entity_links",
        "unknown_nodes_present",
    ]


def test_evaluation_feedback_surfaces_draft_quality_flags():
    flags = compute_draft_quality_flags(source_entity_link_count=0, unknown_node_count=1)
    assert flags == ["no_source_entity_links", "unknown_nodes_present"]
    compact = compact_current_draft_ir_for_projection(
        {
            "draft_ir_ref": "feature_graph:ir:x",
            "draft_version": "v0",
            "graph_id": "g1",
            "draft_quality_flags": flags,
        }
    )
    assert compact is not None
    assert compact["draft_quality_flags"] == flags


def test_timeline_renders_draft_quality_flags():
    lines = render_current_draft_ir_timeline_lines(
        {
            "draft_version": "v0",
            "graph_id": "example_scope_ir",
            "unknown_node_count": 1,
            "source_entity_link_count": 0,
            "draft_quality_flags": ["no_source_entity_links", "unknown_nodes_present"],
        }
    )
    body = "\n".join(lines)
    assert "draft_quality_flags" in body
    assert "no_source_entity_links" in body
    assert "unknown_nodes_present" in body


def test_save_ir_with_zero_links_surfaces_draft_quality_flags():
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)

        class _OkEvaluation:
            def compile_and_judge_ir(self, **_kwargs):
                from services.feature_graph.feature_graph_evaluation_service import (
                    FeatureGraphEvaluationArtifacts,
                    PersistedCompileOutcome,
                    PersistedJudgeOutcome,
                )

                return FeatureGraphEvaluationArtifacts(
                    compile_outcome=PersistedCompileOutcome(artifact_ref="compile:1", gap_count=0, gaps=[]),
                    judge_outcome=PersistedJudgeOutcome(artifact_ref="judge:1", gap_count=0, findings=[]),
                )

        result = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=_linestep_graph(),
            persistence=service,
            evaluation=_OkEvaluation(),  # type: ignore[arg-type]
        )
    outputs = result["outputs"]
    assert outputs["source_entity_link_count"] == 0
    assert outputs["draft_quality_flags"] == ["no_source_entity_links"]
    assert outputs["current_draft_ir"]["draft_quality_flags"] == ["no_source_entity_links"]


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


def test_build_draft_repair_items_dedupes_compile_and_judge():
    graph = FeatureGraph(
        graph_id="g1",
        nodes=[
            FeatureNode(
                id="parcel_1_boundary",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(op_name="deed_call_sequence", params={}, operands=[]),
            )
        ],
        edges=[],
    )
    gap_row = {
        "node_id": "parcel_1_boundary",
        "feature_id": "parcel_1_boundary",
        "gap_kind": "unsupported_operation",
        "operation": "deed_call_sequence",
        "reason": "Operation not in registry",
    }
    items = build_draft_repair_items(
        graph=graph,
        compile_gaps=[gap_row],
        judge_findings=[dict(gap_row)],
    )
    assert len(items) == 1
    assert items[0]["sources"] == ["compile", "judge"]


def test_unsupported_operation_gap_includes_node_precise_repair_items():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = save_ir_artifact(
            dossier_id="d-test",
            feature_graph={
                "graph_id": "parcel_1_ir",
                "nodes": [
                    {
                        "id": "parcel_1_boundary",
                        "kind": "curve",
                        "op_expr": {
                            "op_name": "deed_call_sequence",
                            "params": {},
                            "operands": [],
                        },
                    }
                ],
                "edges": [],
            },
            persistence=_service(tmpdir),
        )
    outputs = result["outputs"]
    assert outputs["compile_gap_count"] >= 1
    gap = outputs["compile_gaps"][0]
    assert gap["node_id"] == "parcel_1_boundary"
    assert gap["feature_id"] == "parcel_1_boundary"
    assert gap["gap_kind"] == "unsupported_operation"
    assert gap["operation"] == "deed_call_sequence"
    repair = outputs["draft_repair_items"]
    assert len(repair) == 1
    assert repair[0]["node_id"] == "parcel_1_boundary"
    assert repair[0]["current_operation"] == "deed_call_sequence"
    assert repair[0]["issue"] == "unsupported_operation"
    assert set(repair[0]["sources"]) == {"compile", "judge"}
    assert outputs["current_draft_ir"]["draft_repair_items"] == repair


def test_scoped_live_runs_each_start_at_v0_for_same_graph_id():
    graph = _linestep_graph("example_scope_graph")
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)
        run_a = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=graph,
            draft_run_id="live-run-a",
            persistence=service,
        )
        run_b = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=graph,
            draft_run_id="live-run-b",
            persistence=service,
        )
    assert run_a["outputs"]["draft_version"] == "v0"
    assert run_b["outputs"]["draft_version"] == "v0"
    assert run_a["outputs"]["draft_sequence_index"] == 0
    assert run_b["outputs"]["draft_sequence_index"] == 0
    assert run_a["outputs"]["artifact_id"] != run_b["outputs"]["artifact_id"]
    assert run_a["outputs"]["draft_run_id"] == "live-run-a"
    assert run_b["outputs"]["draft_run_id"] == "live-run-b"


def test_scoped_draft_continuation_in_same_run():
    graph = _linestep_graph("example_scope_graph")
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)
        first = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=graph,
            draft_run_id="live-run-a",
            persistence=service,
        )
        second = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=graph,
            base_draft_ref=first["outputs"]["draft_ir_ref"],
            draft_run_id="live-run-a",
            persistence=service,
        )
    assert first["outputs"]["draft_version"] == "v0"
    assert second["outputs"]["draft_version"] == "v1"
    assert second["outputs"]["draft_run_id"] == "live-run-a"


def test_base_draft_ref_rejects_cross_run_scope():
    graph = _linestep_graph("example_scope_graph")
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)
        first = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=graph,
            draft_run_id="live-run-a",
            persistence=service,
        )
        mismatch = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=graph,
            base_draft_ref=first["outputs"]["draft_ir_ref"],
            draft_run_id="live-run-b",
            persistence=service,
        )
    assert mismatch["executed"] is False
    assert mismatch["refusal"]["reason_code"] == "base_draft_scope_mismatch"
    assert mismatch["refusal"]["retryable"] is True


def test_stable_draft_artifact_ids_and_base_draft_ref_continuation():
    graph = _linestep_graph("right_of_way")
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)
        first = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=graph,
            persistence=service,
        )
        second = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=graph,
            base_draft_ref=first["outputs"]["draft_ir_ref"],
            persistence=service,
        )
    assert first["outputs"]["ir_artifact_ref"] == "feature_graph:ir:right_of_way_v0"
    assert first["outputs"]["draft_version"] == "v0"
    assert second["outputs"]["ir_artifact_ref"] == "feature_graph:ir:right_of_way_v1"
    assert second["outputs"]["draft_version"] == "v1"


def test_stale_base_draft_ref_allocates_next_free_without_overwrite():
    graph = _linestep_graph("right_of_way")
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)
        v0 = save_ir_artifact(dossier_id="d-test", feature_graph=graph, persistence=service)
        v1 = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=graph,
            base_draft_ref=v0["outputs"]["draft_ir_ref"],
            persistence=service,
        )
        v1_id = v1["outputs"]["artifact_id"]
        v1_before = service.get_artifact("d-test", v1_id)
        stale = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=graph,
            base_draft_ref=v0["outputs"]["draft_ir_ref"],
            persistence=service,
        )
        v1_after = service.get_artifact("d-test", v1_id)
        artifact_count = len(list(service.list_artifacts("d-test", artifact_type="ir")))
    assert stale["executed"] is True
    assert stale["outputs"]["ir_artifact_ref"] == "feature_graph:ir:right_of_way_v2"
    assert stale["outputs"]["draft_version"] == "v2"
    assert v1_before == v1_after
    assert artifact_count == 3


def test_base_draft_ref_graph_id_mismatch_is_retryable_and_persists_nothing():
    graph = _linestep_graph("right_of_way")
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(tmpdir)
        first = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=graph,
            persistence=service,
        )
        before = list(service.list_artifacts("d-test", artifact_type="ir"))
        mismatch = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=_linestep_graph("right_of_way_v1"),
            base_draft_ref=first["outputs"]["draft_ir_ref"],
            persistence=service,
        )
        after = list(service.list_artifacts("d-test", artifact_type="ir"))
    assert mismatch["executed"] is False
    assert mismatch["refusal"]["reason_code"] == "draft_graph_id_mismatch"
    assert mismatch["refusal"]["retryable"] is True
    assert mismatch["outputs"]["expected_graph_id"] == "right_of_way"
    assert mismatch["outputs"]["actual_graph_id"] == "right_of_way_v1"
    assert len(after) == len(before)


def test_draft_repair_items_in_tooling_projection_and_timeline():
    outputs = {
        "draft_version": "v0",
        "current_draft_ir": {
            "draft_ir_ref": "feature_graph:ir:parcel_1_ir_v0",
            "draft_version": "v0",
            "graph_id": "parcel_1_ir",
            "node_count": 1,
            "edge_count": 0,
            "compile_gap_count": 1,
            "judge_finding_count": 0,
            "draft_repair_items": [
                {
                    "node_id": "parcel_1_boundary",
                    "node_kind": "curve",
                    "current_operation": "deed_call_sequence",
                    "issue": "unsupported_operation",
                    "reason": "Operation not in registry",
                }
            ],
        },
    }
    compact = compact_current_draft_ir_for_projection(outputs["current_draft_ir"])
    assert compact is not None
    assert compact["draft_repair_items"][0]["node_id"] == "parcel_1_boundary"
    turn = {
        "tool_result_raw": {
            "execution_state": "executed",
            "outputs": outputs,
        }
    }
    body = "\n".join(_render_tool_result(turn))
    assert "draft_repair_items: 1" in body
    assert "parcel_1_boundary (unsupported_operation" in body
