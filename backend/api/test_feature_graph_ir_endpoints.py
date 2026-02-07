"""
Tests for Feature Graph IR API Endpoints
=========================================

These tests verify that the Feature Graph API endpoints:
- Save artifacts (IR, compile, judge, bundle) via save_artifact
- Retrieve artifacts via get_artifact
- List artifacts by dossier via list_artifacts_by_dossier
- List all artifacts via list_all_artifacts

Tests directly call endpoint functions with temp directories for isolation.
"""

import asyncio
import tempfile
from pathlib import Path

from feature_graph.artifacts import (
    create_ir_artifact,
    create_compile_artifact,
    create_judge_artifact,
    create_bundle_artifact,
)
from feature_graph.models import FeatureGraph, FeatureNode, FeatureKind, OpExpr
from feature_graph.gaps import JudgeReport

# Import endpoint module and request/response models
from api.endpoints import feature_graph as endpoint
from api.endpoints.feature_graph import SaveArtifactRequest

# Direct import to avoid triggering services/__init__.py
import sys
from pathlib import Path as PathLib
sys.path.insert(0, str(PathLib(__file__).parents[1] / "services" / "feature_graph"))
from feature_graph_persistence_service import FeatureGraphPersistenceService


def _setup_temp_persistence_service(tmpdir_path):
    """Helper to create an isolated persistence service for testing."""
    root = Path(tmpdir_path) / "artifacts"
    state_dir = Path(tmpdir_path) / "state"
    service = FeatureGraphPersistenceService(root=root, state_dir=state_dir)
    # Override the module-level service in the endpoint
    endpoint.persistence_service = service
    return service


def test_save_ir_artifact_via_api():
    """Can save an IR artifact via save_artifact endpoint."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        # Create a minimal IR artifact
        graph = FeatureGraph(
            graph_id="test_graph_001",
            nodes=[
                FeatureNode(
                    id="n1",
                    kind=FeatureKind.CURVE,
                    label="Test Curve",
                    op_expr=OpExpr(op_name="Literal", params={"value": "test"}),
                )
            ],
            edges=[],
        )
        artifact = create_ir_artifact(
            artifact_id="test_ir_001",
            graph=graph,
            source_document_id="doc_123",
            created_by="test",
        )

        # Save via API
        request = SaveArtifactRequest(
            artifact=artifact.model_dump(mode="json"),
            dossier_id="test_dossier",
        )
        response = asyncio.run(endpoint.save_artifact(request))

        assert response.success is True
        assert response.artifact_id == "test_ir_001"
        assert response.path is not None


def test_get_artifact_via_api():
    """Can retrieve an artifact via get_artifact."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _setup_temp_persistence_service(tmpdir)

        # Create and save an artifact directly
        graph = FeatureGraph(
            graph_id="test_graph_002",
            nodes=[],
            edges=[],
        )
        artifact = create_ir_artifact(
            artifact_id="test_ir_002",
            graph=graph,
            source_document_id="doc_456",
            created_by="test",
        )
        service.save_artifact(artifact, dossier_id="test_dossier_2")

        # Retrieve via API
        response = asyncio.run(endpoint.get_artifact("test_dossier_2", "test_ir_002"))

        assert response.found is True
        assert response.artifact["artifact_id"] == "test_ir_002"
        assert response.artifact["artifact_type"] == "ir"


def test_get_artifact_not_found():
    """Returns found=False when artifact does not exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        # Try to retrieve a non-existent artifact
        response = asyncio.run(endpoint.get_artifact("nonexistent", "nonexistent_artifact"))

        assert response.found is False
        assert response.artifact is None


def test_list_artifacts_by_dossier():
    """Can list artifacts for a dossier via list_artifacts_by_dossier."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _setup_temp_persistence_service(tmpdir)

        # Create and save multiple artifacts
        graph1 = FeatureGraph(graph_id="g1", nodes=[], edges=[])
        artifact1 = create_ir_artifact(
            artifact_id="ir_001",
            graph=graph1,
            source_document_id="doc_1",
            created_by="test",
        )
        service.save_artifact(artifact1, dossier_id="dossier_A")

        artifact2 = create_compile_artifact(
            artifact_id="compile_001",
            graph_id="g1",
            compiled_features={},
            gaps=[],
            warnings=[],
            created_by="test",
        )
        service.save_artifact(artifact2, dossier_id="dossier_A")

        # Different dossier
        artifact3 = create_ir_artifact(
            artifact_id="ir_002",
            graph=graph1,
            source_document_id="doc_2",
            created_by="test",
        )
        service.save_artifact(artifact3, dossier_id="dossier_B")

        # List artifacts for dossier_A
        response = asyncio.run(endpoint.list_artifacts_by_dossier("dossier_A"))

        assert response.count == 2
        assert len(response.artifacts) == 2
        artifact_ids = [a["artifact_id"] for a in response.artifacts]
        assert "ir_001" in artifact_ids
        assert "compile_001" in artifact_ids


def test_list_artifacts_by_dossier_filtered_by_type():
    """Can list artifacts filtered by artifact_type."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _setup_temp_persistence_service(tmpdir)

        # Create and save multiple artifacts of different types
        graph1 = FeatureGraph(graph_id="g1", nodes=[], edges=[])
        artifact1 = create_ir_artifact(
            artifact_id="ir_003",
            graph=graph1,
            source_document_id="doc_3",
            created_by="test",
        )
        service.save_artifact(artifact1, dossier_id="dossier_C")

        artifact2 = create_compile_artifact(
            artifact_id="compile_002",
            graph_id="g1",
            compiled_features={},
            gaps=[],
            warnings=[],
            created_by="test",
        )
        service.save_artifact(artifact2, dossier_id="dossier_C")

        # List only IR artifacts for dossier_C
        response = asyncio.run(endpoint.list_artifacts_by_dossier("dossier_C", artifact_type="ir"))

        assert response.count == 1
        assert response.artifacts[0]["artifact_id"] == "ir_003"
        assert response.artifacts[0]["artifact_type"] == "ir"


def test_list_all_artifacts():
    """Can list all artifacts across all dossiers via list_all_artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _setup_temp_persistence_service(tmpdir)

        # Create and save artifacts in multiple dossiers
        graph1 = FeatureGraph(graph_id="g1", nodes=[], edges=[])
        artifact1 = create_ir_artifact(
            artifact_id="ir_004",
            graph=graph1,
            source_document_id="doc_4",
            created_by="test",
        )
        service.save_artifact(artifact1, dossier_id="dossier_D")

        artifact2 = create_ir_artifact(
            artifact_id="ir_005",
            graph=graph1,
            source_document_id="doc_5",
            created_by="test",
        )
        service.save_artifact(artifact2, dossier_id="dossier_E")

        # List all artifacts
        response = asyncio.run(endpoint.list_all_artifacts())

        assert response.count == 2
        artifact_ids = [a["artifact_id"] for a in response.artifacts]
        assert "ir_004" in artifact_ids
        assert "ir_005" in artifact_ids


def test_list_all_artifacts_filtered_by_type():
    """Can list all artifacts filtered by artifact_type."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _setup_temp_persistence_service(tmpdir)

        # Create and save artifacts of different types
        graph1 = FeatureGraph(graph_id="g1", nodes=[], edges=[])
        artifact1 = create_ir_artifact(
            artifact_id="ir_006",
            graph=graph1,
            source_document_id="doc_6",
            created_by="test",
        )
        service.save_artifact(artifact1, dossier_id="dossier_F")

        artifact2 = create_compile_artifact(
            artifact_id="compile_003",
            graph_id="g1",
            compiled_features={},
            gaps=[],
            warnings=[],
            created_by="test",
        )
        service.save_artifact(artifact2, dossier_id="dossier_F")

        # List all compile artifacts
        response = asyncio.run(endpoint.list_all_artifacts(artifact_type="compile"))

        assert response.count == 1
        assert response.artifacts[0]["artifact_id"] == "compile_003"
        assert response.artifacts[0]["artifact_type"] == "compile"


def test_save_and_retrieve_compile_artifact():
    """Can save and retrieve a compile artifact."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        # Create a compile artifact
        artifact = create_compile_artifact(
            artifact_id="compile_004",
            graph_id="g1",
            compiled_features={"n1": {"geometry": "POINT(0 0)"}},
            gaps=[],
            warnings=["Warning 1"],
            created_by="test",
        )

        # Save via API
        request = SaveArtifactRequest(
            artifact=artifact.model_dump(mode="json"),
            dossier_id="test_dossier",
        )
        response = asyncio.run(endpoint.save_artifact(request))

        assert response.success is True

        # Retrieve via API
        response = asyncio.run(endpoint.get_artifact("test_dossier", "compile_004"))

        assert response.found is True
        assert response.artifact["artifact_type"] == "compile"
        assert len(response.artifact["warnings"]) == 1


def test_save_and_retrieve_judge_artifact():
    """Can save and retrieve a judge artifact."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        # Create a judge artifact
        report = JudgeReport(
            graph_id="g1",
            status="partial",
            diagnostics=[],
            warnings=[],
            artifacts={},
        )
        artifact = create_judge_artifact(
            artifact_id="judge_001",
            graph_id="g1",
            report=report,
            created_by="test",
        )

        # Save via API
        request = SaveArtifactRequest(
            artifact=artifact.model_dump(mode="json"),
            dossier_id="test_dossier",
        )
        response = asyncio.run(endpoint.save_artifact(request))

        assert response.success is True

        # Retrieve via API
        response = asyncio.run(endpoint.get_artifact("test_dossier", "judge_001"))

        assert response.found is True
        assert response.artifact["artifact_type"] == "judge"


def test_save_and_retrieve_bundle_artifact():
    """Can save and retrieve a bundle artifact."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        # Create a bundle artifact
        graph = FeatureGraph(graph_id="g1", nodes=[], edges=[])
        artifact = create_bundle_artifact(
            artifact_id="bundle_001",
            target_graph=graph,
            dependency_graphs=[],
            dependency_reasons={},
            created_by="test",
        )

        # Save via API
        request = SaveArtifactRequest(
            artifact=artifact.model_dump(mode="json"),
            dossier_id="test_dossier",
        )
        response = asyncio.run(endpoint.save_artifact(request))

        assert response.success is True

        # Retrieve via API
        response = asyncio.run(endpoint.get_artifact("test_dossier", "bundle_001"))

        assert response.found is True
        assert response.artifact["artifact_type"] == "bundle"
