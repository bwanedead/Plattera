"""Tests for Feature Graph compile/judge/bundle API endpoints with real IR shapes."""

import asyncio
import tempfile
from pathlib import Path

from api.endpoints import feature_graph as endpoint
from api.endpoints.feature_graph import BundleRequest, CompileRequest, JudgeRequest
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService


def _setup_temp_persistence_service(tmpdir_path: str) -> FeatureGraphPersistenceService:
    root = Path(tmpdir_path) / "artifacts"
    state_dir = Path(tmpdir_path) / "state"
    service = FeatureGraphPersistenceService(root=root, state_dir=state_dir)
    endpoint.persistence_service = service
    return service


def test_compile_returns_compile_artifact_for_valid_linestep_chain() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        graph = {
            "graph_id": "compile_chain",
            "nodes": [
                {
                    "id": "start",
                    "kind": "point",
                    "label": "origin",
                    "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                },
                {
                    "id": "line1",
                    "kind": "curve",
                    "label": "north leg",
                    "op_expr": {
                        "op_name": "LineStep",
                        "operands": ["start"],
                        "params": {"bearing": 0.0, "distance": 100.0},
                    },
                },
                {
                    "id": "line2",
                    "kind": "curve",
                    "label": "east leg",
                    "op_expr": {
                        "op_name": "LineStep",
                        "operands": ["line1"],
                        "params": {"bearing": 90.0, "distance": 50.0},
                    },
                },
            ],
            "edges": [],
        }

        response = asyncio.run(
            endpoint.compile_feature_graph(CompileRequest(graph=graph, dossier_id="dossier_compile"))
        )

        assert response.success is True
        assert response.artifact_id == "compile_compile_chain"
        assert response.artifact["artifact_type"] == "compile"
        assert response.artifact["graph_id"] == "compile_chain"
        assert set(response.artifact["compiled_features"].keys()) == {"start", "line1", "line2"}
        assert response.artifact["gaps"] == []

        artifact_path = Path(tmpdir) / "artifacts" / "dossier_compile" / "compile_compile_chain.json"
        assert artifact_path.exists()


def test_compile_missing_numeric_parameter_produces_typed_gap() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        graph = {
            "graph_id": "compile_missing_param",
            "nodes": [
                {
                    "id": "line1",
                    "kind": "curve",
                    "op_expr": {
                        "op_name": "LineStep",
                        "operands": [],
                        "params": {"bearing": 45.0, "distance_raw": "100 ft"},
                    },
                }
            ],
            "edges": [],
        }

        response = asyncio.run(
            endpoint.compile_feature_graph(CompileRequest(graph=graph, dossier_id="dossier_compile"))
        )

        assert response.success is True
        gaps = response.artifact["gaps"]
        assert len(gaps) == 1
        assert gaps[0]["kind"] == "missing_parameter"
        assert gaps[0]["feature_id"] == "line1"
        assert gaps[0]["metadata"]["parameter_name"] == "distance"


def test_compile_unsupported_operation_produces_gap() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        graph = {
            "graph_id": "compile_unsupported",
            "nodes": [
                {
                    "id": "region1",
                    "kind": "region",
                    "op_expr": {
                        "op_name": "Buffer",
                        "operands": ["line1"],
                        "params": {"distance": 10.0},
                    },
                }
            ],
            "edges": [],
        }

        response = asyncio.run(
            endpoint.compile_feature_graph(CompileRequest(graph=graph, dossier_id="dossier_compile"))
        )

        assert response.success is True
        gaps = response.artifact["gaps"]
        assert len(gaps) == 1
        assert gaps[0]["kind"] == "unsupported_operation"
        assert gaps[0]["feature_id"] == "region1"


def test_judge_returns_judge_artifact_with_deterministic_gaps() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        graph = {
            "graph_id": "judge_deterministic",
            "nodes": [
                {
                    "id": "line1",
                    "kind": "curve",
                    "op_expr": {
                        "op_name": "LineStep",
                        "operands": ["missing_start"],
                        "params": {"bearing": 90.0},
                    },
                },
                {
                    "id": "region1",
                    "kind": "region",
                    "op_expr": {"op_name": "CurveStep", "operands": [], "params": {}},
                },
            ],
            "edges": [],
        }

        request = JudgeRequest(graph=graph, dossier_id="dossier_judge")
        response_one = asyncio.run(endpoint.judge_feature_graph(request))
        response_two = asyncio.run(endpoint.judge_feature_graph(request))

        assert response_one.success is True
        assert response_one.artifact["artifact_type"] == "judge"
        assert response_one.artifact["graph_id"] == "judge_deterministic"
        assert response_one.artifact["report"]["gaps"] == response_two.artifact["report"]["gaps"]

        artifact_path = Path(tmpdir) / "artifacts" / "dossier_judge" / "judge_judge_deterministic.json"
        assert artifact_path.exists()


def test_bundle_returns_bundle_artifact_with_dependency_reasons() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        target_graph = {
            "graph_id": "parcel_a",
            "nodes": [
                {
                    "id": "origin",
                    "kind": "point",
                    "feature_ref": {
                        "feature_id": "ne_corner",
                        "graph_id": "section_1",
                        "is_external": True,
                        "label": "NE Corner Section 1",
                    },
                }
            ],
            "edges": [],
        }

        dependency_graph = {
            "graph_id": "section_1",
            "nodes": [
                {
                    "id": "ne_corner",
                    "kind": "point",
                    "geometry": {"type": "Point", "coordinates": [1000.0, 2000.0]},
                }
            ],
            "edges": [],
        }

        response = asyncio.run(
            endpoint.bundle_graph(
                BundleRequest(
                    target_graph=target_graph,
                    available_graphs={"section_1": dependency_graph},
                    dossier_id="dossier_bundle",
                    artifact_id="bundle_parcel_a",
                )
            )
        )

        assert response.success is True
        assert response.artifact_id == "bundle_parcel_a"
        assert response.artifact["artifact_type"] == "bundle"
        assert len(response.artifact["dependency_graphs"]) == 1
        assert response.artifact["dependency_graphs"][0]["graph_id"] == "section_1"
        assert "section_1" in response.artifact["dependency_reasons"]
        assert "origin" in response.artifact["dependency_reasons"]["section_1"]

        artifact_path = Path(tmpdir) / "artifacts" / "dossier_bundle" / "bundle_parcel_a.json"
        assert artifact_path.exists()
