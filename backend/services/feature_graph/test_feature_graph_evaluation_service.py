"""Tests for canonical feature-graph compile/judge evaluation service."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from feature_graph.artifact_refs import parse_feature_graph_artifact_ref
from feature_graph.artifacts import create_ir_artifact
from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr

from services.feature_graph.feature_graph_evaluation_service import FeatureGraphEvaluationService
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService


def _service(tmpdir: str) -> FeatureGraphEvaluationService:
    root = Path(tmpdir) / "artifacts"
    state_dir = Path(tmpdir) / "state"
    persistence = FeatureGraphPersistenceService(root=root, state_dir=state_dir)
    return FeatureGraphEvaluationService(persistence)


def _linestep_graph(graph_id: str = "compile_chain") -> FeatureGraph:
    return FeatureGraph(
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


def test_compile_and_persist_supported_graph():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _service(tmpdir)
        outcome = svc.compile_and_persist(
            graph=_linestep_graph(),
            dossier_id="d1",
            parent_artifact_ids=["compile_chain"],
            artifact_id="compile_compile_chain",
        )
        assert outcome.compiled_feature_count == 2
        assert outcome.gap_count == 0
        assert outcome.artifact_ref == "feature_graph:compile:compile_compile_chain"
        assert "path" not in json.dumps(outcome.__dict__, default=str)


def test_compile_unsupported_operation_produces_typed_gap():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _service(tmpdir)
        graph = FeatureGraph(
            graph_id="compile_unsupported",
            nodes=[
                FeatureNode(
                    id="region1",
                    kind=FeatureKind.REGION,
                    op_expr=OpExpr(
                        op_name="Buffer",
                        operands=["line1"],
                        params={"distance": 10.0},
                    ),
                )
            ],
            edges=[],
        )
        outcome = svc.compile_and_persist(
            graph=graph,
            dossier_id="d1",
            parent_artifact_ids=["compile_unsupported"],
        )
        assert outcome.compiled_feature_count == 0
        assert outcome.gap_count == 1
        assert outcome.artifact.gaps[0]["kind"] == "unsupported_operation"


def test_judge_gaps_persist_unchanged():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _service(tmpdir)
        graph = FeatureGraph(
            graph_id="judge_deterministic",
            nodes=[
                FeatureNode(
                    id="line1",
                    kind=FeatureKind.CURVE,
                    op_expr=OpExpr(
                        op_name="LineStep",
                        operands=["missing_start"],
                        params={"bearing": 90.0},
                    ),
                )
            ],
            edges=[],
        )
        one = svc.judge_and_persist(
            graph=graph,
            dossier_id="d1",
            parent_artifact_ids=["judge_deterministic"],
            artifact_id="judge_judge_deterministic",
        )
        two = svc.judge_and_persist(
            graph=graph,
            dossier_id="d1",
            parent_artifact_ids=["judge_deterministic"],
            artifact_id="judge_judge_deterministic",
        )
        assert one.artifact.report.model_dump(mode="json") == two.artifact.report.model_dump(mode="json")


def test_compile_and_judge_ir_links_to_exact_ir_artifact():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _service(tmpdir)
        graph = _linestep_graph("ir_eval")
        ir = create_ir_artifact(artifact_id="ir_eval_001", graph=graph)
        svc._persistence.save_artifact(ir, dossier_id="d1")
        bundle = svc.compile_and_judge_ir(ir_artifact=ir, dossier_id="d1")
        assert bundle.ir_artifact_id == "ir_eval_001"
        assert bundle.compile_outcome.artifact.metadata.parent_artifact_ids == ["ir_eval_001"]
        assert bundle.judge_outcome.artifact.metadata.parent_artifact_ids == ["ir_eval_001"]
        assert bundle.compile_outcome.artifact_ref.startswith("feature_graph:compile:")
        assert bundle.judge_outcome.artifact_ref.startswith("feature_graph:judge:")


def test_raw_graph_evaluation_allows_empty_parent_lineage():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _service(tmpdir)
        outcome = svc.compile_and_persist(
            graph=_linestep_graph("raw_graph"),
            dossier_id="d1",
            parent_artifact_ids=[],
        )
        assert outcome.artifact.metadata.parent_artifact_ids == []


def test_generated_artifact_ids_do_not_collide():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _service(tmpdir)
        graph = _linestep_graph("collision_test")
        first = svc.compile_and_persist(
            graph=graph,
            dossier_id="d1",
            parent_artifact_ids=["collision_test"],
        )
        second = svc.compile_and_persist(
            graph=graph,
            dossier_id="d1",
            parent_artifact_ids=["collision_test"],
        )
        assert first.artifact_id != second.artifact_id
        assert first.artifact_ref != second.artifact_ref


def test_public_outcomes_are_path_free():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _service(tmpdir)
        outcome = svc.compile_and_persist(
            graph=_linestep_graph(),
            dossier_id="d1",
            parent_artifact_ids=["compile_chain"],
        )
        dumped = json.dumps(
            {
                "artifact_ref": outcome.artifact_ref,
                "artifact_id": outcome.artifact_id,
                "graph_id": outcome.graph_id,
            }
        )
        assert tmpdir not in dumped
        assert "artifacts" not in dumped.lower() or "feature_graph:compile:" in dumped
        parse_feature_graph_artifact_ref(outcome.artifact_ref)
