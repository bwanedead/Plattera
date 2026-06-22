"""Tests for mapping creation service."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from feature_graph.artifact_refs import parse_feature_graph_artifact_ref
from feature_graph.artifacts import create_compile_artifact, create_ir_artifact, create_judge_artifact
from feature_graph.compiler import compile_graph
from feature_graph.gaps import JudgeReport
from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr
from services.feature_graph.feature_graph_mapping_service import FeatureGraphMappingService
from services.feature_graph.feature_graph_mapping_sidecar_service import FeatureGraphMappingSidecarService
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService


def _services(tmp: str) -> FeatureGraphMappingService:
    root = Path(tmp) / "artifacts"
    state = Path(tmp) / "state"
    persistence = FeatureGraphPersistenceService(root=root, state_dir=state)
    sidecars = FeatureGraphMappingSidecarService(artifacts_root=root)
    return FeatureGraphMappingService(persistence=persistence, sidecars=sidecars)


def _parcel_graph() -> FeatureGraph:
    return FeatureGraph(
        graph_id="parcel_map",
        nodes=[
            FeatureNode(
                id="pob",
                kind=FeatureKind.POINT,
                label="POB",
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


def test_create_mapping_from_artifacts_persists_mapping_and_sidecars() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        svc = _services(tmp)
        graph = _parcel_graph()
        ir = create_ir_artifact(artifact_id="ir_parcel_map", graph=graph)
        compile_result = compile_graph(graph)
        compile_artifact = create_compile_artifact(
            artifact_id="compile_parcel_map",
            graph_id=graph.graph_id,
            compiled_features=compile_result.compiled_features,
            gaps=[gap.model_dump(mode="json") for gap in compile_result.gaps],
            warnings=list(compile_result.warnings),
            parent_artifact_ids=[ir.artifact_id],
        )
        judge_artifact = create_judge_artifact(
            artifact_id="judge_parcel_map",
            graph_id=graph.graph_id,
            report=JudgeReport(graph_id=graph.graph_id),
            parent_artifact_ids=[ir.artifact_id],
        )
        outcome = svc.create_mapping_from_artifacts(
            ir_artifact=ir,
            compile_artifact=compile_artifact,
            judge_artifact=judge_artifact,
            dossier_id="D_MAP",
            mapping_artifact_id="mapping_parcel_map",
        )
        assert outcome.artifact_ref == "feature_graph:mapping:mapping_parcel_map"
        assert outcome.rendered_feature_count >= 2
        assert outcome.artifact.clean_render.profile == "clean"
        assert outcome.artifact.control_render.profile == "control"
        assert outcome.artifact.metadata.parent_artifact_ids == [
            "ir_parcel_map",
            "compile_parcel_map",
            "judge_parcel_map",
        ]

        mapping_path = Path(tmp) / "artifacts" / "D_MAP" / "mapping_parcel_map.json"
        sidecar_dir = Path(tmp) / "artifacts" / "D_MAP" / "mappings" / "mapping_parcel_map"
        latest_path = Path(tmp) / "artifacts" / "D_MAP" / "latest_mapping.json"
        assert mapping_path.exists()
        assert latest_path.exists()
        assert (sidecar_dir / "geometry.geojson").exists()
        assert (sidecar_dir / "clean.png").exists()
        assert (sidecar_dir / "control.png").exists()

        dumped = json.dumps(outcome.__dict__, default=str)
        assert tmp not in dumped
        assert "artifacts" not in dumped.lower() or "feature_graph:mapping:" in dumped
        parse_feature_graph_artifact_ref(outcome.artifact_ref)


def test_mapping_save_get_and_list() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        svc = _services(tmp)
        graph = _parcel_graph()
        ir = create_ir_artifact(artifact_id="ir_list", graph=graph)
        compile_result = compile_graph(graph)
        compile_artifact = create_compile_artifact(
            artifact_id="compile_list",
            graph_id=graph.graph_id,
            compiled_features=compile_result.compiled_features,
            gaps=[gap.model_dump(mode="json") for gap in compile_result.gaps],
            parent_artifact_ids=[ir.artifact_id],
        )
        judge_artifact = create_judge_artifact(
            artifact_id="judge_list",
            graph_id=graph.graph_id,
            report=JudgeReport(graph_id=graph.graph_id),
            parent_artifact_ids=[ir.artifact_id],
        )
        outcome = svc.create_mapping_from_artifacts(
            ir_artifact=ir,
            compile_artifact=compile_artifact,
            judge_artifact=judge_artifact,
            dossier_id="D_LIST",
            mapping_artifact_id="mapping_list",
        )
        persistence = svc._persistence
        loaded = persistence.get_artifact("D_LIST", "mapping_list")
        assert loaded is not None
        assert loaded["artifact_type"] == "mapping"
        entries = persistence.list_artifacts(dossier_id="D_LIST", artifact_type="mapping")
        assert len(entries) == 1
        assert entries[0]["artifact_id"] == outcome.artifact_id


def test_create_mapping_rejects_stale_same_graph_lineage() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        svc = _services(tmp)
        graph = _parcel_graph()
        current_ir = create_ir_artifact(artifact_id="ir_current", graph=graph)
        stale_ir = create_ir_artifact(artifact_id="ir_stale", graph=graph)
        compile_result = compile_graph(graph)
        compile_artifact = create_compile_artifact(
            artifact_id="compile_stale_parent",
            graph_id=graph.graph_id,
            compiled_features=compile_result.compiled_features,
            gaps=[gap.model_dump(mode="json") for gap in compile_result.gaps],
            parent_artifact_ids=[stale_ir.artifact_id],
        )
        judge_artifact = create_judge_artifact(
            artifact_id="judge_stale_parent",
            graph_id=graph.graph_id,
            report=JudgeReport(graph_id=graph.graph_id),
            parent_artifact_ids=[stale_ir.artifact_id],
        )
        try:
            svc.create_mapping_from_artifacts(
                ir_artifact=current_ir,
                compile_artifact=compile_artifact,
                judge_artifact=judge_artifact,
                dossier_id="D_STALE",
            )
            assert False, "expected stale compile/judge lineage to be rejected"
        except ValueError as exc:
            assert "ir_parent_missing" in str(exc)


def test_create_mapping_skips_malformed_geometry_and_keeps_valid_features() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        svc = _services(tmp)
        graph = FeatureGraph(
            graph_id="mixed_valid_invalid",
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
        ir = create_ir_artifact(artifact_id="ir_mixed", graph=graph)
        compile_artifact = create_compile_artifact(
            artifact_id="compile_mixed",
            graph_id=graph.graph_id,
            compiled_features={
                "good": {"geometry": graph.nodes[0].geometry, "source": "direct"},
                "bad": {"geometry": graph.nodes[1].geometry, "source": "direct"},
            },
            parent_artifact_ids=[ir.artifact_id],
        )
        judge_artifact = create_judge_artifact(
            artifact_id="judge_mixed",
            graph_id=graph.graph_id,
            report=JudgeReport(graph_id=graph.graph_id),
            parent_artifact_ids=[ir.artifact_id],
        )
        outcome = svc.create_mapping_from_artifacts(
            ir_artifact=ir,
            compile_artifact=compile_artifact,
            judge_artifact=judge_artifact,
            dossier_id="D_MIXED",
            mapping_artifact_id="mapping_mixed",
        )
        assert outcome.rendered_feature_count == 1
        assert outcome.skipped_feature_count == 1
        assert outcome.artifact.skipped_features[0].reason == "invalid_geometry_coordinates"
        assert (Path(tmp) / "artifacts" / "D_MIXED" / "mappings" / "mapping_mixed" / "clean.png").exists()
