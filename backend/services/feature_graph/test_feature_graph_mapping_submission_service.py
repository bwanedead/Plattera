"""Tests for IR mapping submission orchestration."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from feature_graph.artifacts import create_ir_artifact
from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr
from services.feature_graph.feature_graph_evaluation_service import FeatureGraphEvaluationService
from services.feature_graph.feature_graph_mapping_service import FeatureGraphMappingService
from services.feature_graph.feature_graph_mapping_sidecar_service import FeatureGraphMappingSidecarService
from services.feature_graph.feature_graph_mapping_submission_service import (
    FeatureGraphMappingSubmissionService,
)
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService


def _submission_stack(tmp: str) -> FeatureGraphMappingSubmissionService:
    root = Path(tmp) / "artifacts"
    state = Path(tmp) / "state"
    persistence = FeatureGraphPersistenceService(root=root, state_dir=state)
    sidecars = FeatureGraphMappingSidecarService(artifacts_root=root)
    evaluation = FeatureGraphEvaluationService(persistence)
    mapping = FeatureGraphMappingService(persistence=persistence, sidecars=sidecars)
    return FeatureGraphMappingSubmissionService(evaluation=evaluation, mapping=mapping)


def _mappable_graph() -> FeatureGraph:
    return FeatureGraph(
        graph_id="parcel_submit",
        nodes=[
            FeatureNode(
                id="pob",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            ),
            FeatureNode(
                id="traverse",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    operands=["pob"],
                    params={
                        "courses": [
                            {"bearing": 90.0, "distance": 100.0},
                            {"bearing": 0.0, "distance": 50.0},
                        ]
                    },
                ),
            ),
            FeatureNode(
                id="parcel",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Close", operands=["traverse"]),
            ),
        ],
        edges=[],
    )


def test_submit_ir_artifact_persists_compile_judge_and_mapping_lineage() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        submitter = _submission_stack(tmp)
        graph = _mappable_graph()
        ir = create_ir_artifact(artifact_id="ir_submit_001", graph=graph)
        submitter._evaluation._persistence.save_artifact(ir, dossier_id="D_SUBMIT")
        outcome = submitter.submit_ir_artifact(ir_artifact=ir, dossier_id="D_SUBMIT")

        assert outcome.ir_artifact_ref == "feature_graph:ir:ir_submit_001"
        compile_artifact = outcome.evaluation.compile_outcome.artifact
        judge_artifact = outcome.evaluation.judge_outcome.artifact
        assert compile_artifact.metadata.parent_artifact_ids == ["ir_submit_001"]
        assert judge_artifact.metadata.parent_artifact_ids == ["ir_submit_001"]
        assert outcome.mapping.artifact.metadata.parent_artifact_ids == [
            "ir_submit_001",
            outcome.evaluation.compile_outcome.artifact_id,
            outcome.evaluation.judge_outcome.artifact_id,
        ]

        mapping_dir = (
            Path(tmp) / "artifacts" / "D_SUBMIT" / "mappings" / outcome.mapping.artifact_id
        )
        assert (mapping_dir / "geometry.geojson").exists()
        assert (mapping_dir / "clean.png").exists()
        assert (mapping_dir / "control.png").exists()
        dumped = json.dumps(outcome.__dict__, default=str)
        assert tmp not in dumped


def test_repeated_submissions_produce_distinct_artifact_ids() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        submitter = _submission_stack(tmp)
        graph = _mappable_graph()
        ir = create_ir_artifact(artifact_id="ir_repeat", graph=graph)
        submitter._evaluation._persistence.save_artifact(ir, dossier_id="D_REPEAT")
        first = submitter.submit_ir_artifact(ir_artifact=ir, dossier_id="D_REPEAT")
        second = submitter.submit_ir_artifact(ir_artifact=ir, dossier_id="D_REPEAT")

        assert first.mapping.artifact_id != second.mapping.artifact_id
        assert first.evaluation.compile_outcome.artifact_id != second.evaluation.compile_outcome.artifact_id
        assert first.evaluation.judge_outcome.artifact_id != second.evaluation.judge_outcome.artifact_id


def test_partial_compile_still_produces_mapping_from_valid_features() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        submitter = _submission_stack(tmp)
        graph = FeatureGraph(
            graph_id="partial_submit",
            nodes=[
                FeatureNode(
                    id="good",
                    kind=FeatureKind.POINT,
                    geometry={"type": "Point", "coordinates": [0.0, 0.0]},
                ),
                FeatureNode(
                    id="bad",
                    kind=FeatureKind.POINT,
                    geometry={"type": "Point", "coordinates": ["north", 0.0]},
                ),
            ],
            edges=[],
        )
        ir = create_ir_artifact(artifact_id="ir_partial", graph=graph)
        submitter._evaluation._persistence.save_artifact(ir, dossier_id="D_PARTIAL")
        outcome = submitter.submit_ir_artifact(ir_artifact=ir, dossier_id="D_PARTIAL")

        assert outcome.mapping.rendered_feature_count >= 1
        assert outcome.mapping.skipped_feature_count >= 1
        assert outcome.evaluation.compile_outcome.compiled_feature_count >= 1
