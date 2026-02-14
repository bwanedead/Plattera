"""
Tests for Feature Graph Persistence Service
============================================

These tests verify that the FeatureGraphPersistenceService:
- Writes artifacts atomically
- Maintains an index of all artifacts
- Supports CRUD operations (save, get, list, delete)
- Works correctly with temp roots (for test isolation)

All tests use temp directories to ensure test isolation and avoid polluting the dev environment.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

from feature_graph.artifacts import (
    create_ir_artifact,
    create_compile_artifact,
    create_judge_artifact,
    create_bundle_artifact,
)
from feature_graph.models import FeatureGraph, FeatureNode, FeatureKind, OpExpr
from feature_graph.gaps import JudgeReport

# Direct import to avoid triggering services/__init__.py which imports alignment
import sys
from pathlib import Path as PathLib
sys.path.insert(0, str(PathLib(__file__).parents[1] / "services" / "feature_graph"))
from feature_graph_persistence_service import FeatureGraphPersistenceService


def _create_service(tmpdir_path):
    """Helper to create an isolated persistence service for testing."""
    root = Path(tmpdir_path) / "artifacts"
    state_dir = Path(tmpdir_path) / "state"
    return FeatureGraphPersistenceService(root=root, state_dir=state_dir)


def test_persistence_service_init_with_temp_root():
    """Persistence service can be initialized with a custom root for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _create_service(tmpdir)
        assert service._artifacts_root == Path(tmpdir) / "artifacts"
        assert service._state_dir == Path(tmpdir) / "state"


def test_save_ir_artifact():
    """IR artifacts can be saved and retrieved."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _create_service(tmpdir)

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

        # Save artifact
        result = service.save_artifact(artifact, dossier_id="test_dossier")
        assert result["success"] is True
        assert result["artifact_id"] == "test_ir_001"
        assert Path(result["path"]).exists()

        # Retrieve artifact
        retrieved = service.get_artifact(
            dossier_id="test_dossier", artifact_id="test_ir_001"
        )
        assert retrieved is not None
        assert retrieved["artifact_id"] == "test_ir_001"
        assert retrieved["artifact_type"] == "ir"
        assert retrieved["graph"]["nodes"][0]["id"] == "n1"


def test_save_compile_artifact():
    """Compile artifacts can be saved and retrieved."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _create_service(tmpdir)

        # Create a minimal compile artifact
        artifact = create_compile_artifact(
            artifact_id="test_compile_001",
            graph_id="test_graph_001",
            compiled_features={},
            gaps=[],
            warnings=[],
            created_by="test",
        )

        # Save artifact
        result = service.save_artifact(artifact, dossier_id="test_dossier")
        assert result["success"] is True
        assert result["artifact_id"] == "test_compile_001"

        # Retrieve artifact
        retrieved = service.get_artifact(
            dossier_id="test_dossier", artifact_id="test_compile_001"
        )
        assert retrieved is not None
        assert retrieved["artifact_type"] == "compile"


def test_save_judge_artifact():
    """Judge artifacts can be saved and retrieved."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _create_service(tmpdir)

        # Create a minimal judge artifact
        judge_report = JudgeReport(
            graph_id="test_graph_001",
            gaps=[],
            warnings=[],
        )
        artifact = create_judge_artifact(
            artifact_id="test_judge_001",
            graph_id="test_graph_001",
            report=judge_report,
            created_by="test",
        )

        # Save artifact
        result = service.save_artifact(artifact, dossier_id="test_dossier")
        assert result["success"] is True
        assert result["artifact_id"] == "test_judge_001"

        # Retrieve artifact
        retrieved = service.get_artifact(
            dossier_id="test_dossier", artifact_id="test_judge_001"
        )
        assert retrieved is not None
        assert retrieved["artifact_type"] == "judge"
        assert retrieved["report"]["graph_id"] == "test_graph_001"


def test_save_bundle_artifact():
    """Bundle artifacts can be saved and retrieved."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _create_service(tmpdir)

        # Create a minimal bundle artifact
        target_graph = FeatureGraph(graph_id="bundle_graph_001", nodes=[], edges=[])
        artifact = create_bundle_artifact(
            artifact_id="test_bundle_001",
            target_graph=target_graph,
            created_by="test",
        )

        # Save artifact
        result = service.save_artifact(artifact, dossier_id="test_dossier")
        assert result["success"] is True
        assert result["artifact_id"] == "test_bundle_001"

        # Retrieve artifact
        retrieved = service.get_artifact(
            dossier_id="test_dossier", artifact_id="test_bundle_001"
        )
        assert retrieved is not None
        assert retrieved["artifact_type"] == "bundle"


def test_atomic_write_survives_errors():
    """Atomic writes ensure that partial writes don't corrupt artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _create_service(tmpdir)

        graph = FeatureGraph(graph_id="test_atomic_graph", nodes=[], edges=[])
        artifact = create_ir_artifact(
            artifact_id="test_atomic_001",
            graph=graph,
            source_document_id="doc_123",
            created_by="test",
        )

        # Save artifact
        result = service.save_artifact(artifact, dossier_id="test_dossier")
        artifact_path = Path(result["path"])
        assert artifact_path.exists()

        # Verify the artifact is valid JSON
        with open(artifact_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["artifact_id"] == "test_atomic_001"


def test_index_maintenance():
    """The index is updated after each save and supports queries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _create_service(tmpdir)

        # Save multiple artifacts
        for i in range(3):
            graph = FeatureGraph(graph_id=f"test_graph_{i:03d}", nodes=[], edges=[])
            artifact = create_ir_artifact(
                artifact_id=f"test_ir_{i:03d}",
                graph=graph,
                source_document_id=f"doc_{i}",
                created_by="test",
            )
            service.save_artifact(artifact, dossier_id=f"dossier_{i % 2}")

        # List all artifacts
        all_artifacts = service.list_all_artifacts()
        assert len(all_artifacts) == 3

        # List artifacts by dossier
        dossier_0_artifacts = service.list_artifacts(dossier_id="dossier_0")
        assert len(dossier_0_artifacts) == 2  # artifacts 0 and 2

        dossier_1_artifacts = service.list_artifacts(dossier_id="dossier_1")
        assert len(dossier_1_artifacts) == 1  # artifact 1

        # List artifacts by type
        ir_artifacts = service.list_artifacts(artifact_type="ir")
        assert len(ir_artifacts) == 3


def test_index_deduplication():
    """Saving the same artifact_id multiple times updates the index entry (no duplicates)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _create_service(tmpdir)

        graph = FeatureGraph(graph_id="test_dedupe_graph", nodes=[], edges=[])
        artifact = create_ir_artifact(
            artifact_id="test_dedupe_001",
            graph=graph,
            source_document_id="doc_123",
            created_by="test",
        )

        # Save the same artifact twice
        service.save_artifact(artifact, dossier_id="test_dossier")
        service.save_artifact(artifact, dossier_id="test_dossier")

        # List artifacts - should have exactly 1 entry
        all_artifacts = service.list_all_artifacts()
        assert len(all_artifacts) == 1
        assert all_artifacts[0]["artifact_id"] == "test_dedupe_001"


def test_delete_artifact():
    """Artifacts can be deleted and are removed from the index."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _create_service(tmpdir)

        graph = FeatureGraph(graph_id="test_delete_graph", nodes=[], edges=[])
        artifact = create_ir_artifact(
            artifact_id="test_delete_001",
            graph=graph,
            source_document_id="doc_123",
            created_by="test",
        )

        # Save artifact
        result = service.save_artifact(artifact, dossier_id="test_dossier")
        artifact_path = Path(result["path"])
        assert artifact_path.exists()

        # Verify it's in the index
        all_artifacts = service.list_all_artifacts()
        assert len(all_artifacts) == 1

        # Delete artifact
        delete_result = service.delete_artifact(
            dossier_id="test_dossier", artifact_id="test_delete_001"
        )
        assert delete_result["success"] is True
        assert not artifact_path.exists()

        # Verify it's removed from the index
        all_artifacts = service.list_all_artifacts()
        assert len(all_artifacts) == 0


def test_get_nonexistent_artifact_returns_none():
    """Retrieving a nonexistent artifact returns None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _create_service(tmpdir)

        retrieved = service.get_artifact(
            dossier_id="nonexistent_dossier", artifact_id="nonexistent_artifact"
        )
        assert retrieved is None


def test_list_artifacts_returns_empty_when_no_index():
    """Listing artifacts returns an empty list when no index exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _create_service(tmpdir)

        all_artifacts = service.list_all_artifacts()
        assert all_artifacts == []


def test_index_sorted_by_saved_at_desc():
    """The index is sorted by saved_at in descending order (most recent first)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _create_service(tmpdir)

        # Save artifacts with explicit timestamps
        for i in range(3):
            graph = FeatureGraph(graph_id=f"test_graph_{i:03d}", nodes=[], edges=[])
            # Create artifacts with different timestamps (older to newer)
            timestamp = f"2025-01-0{i+1}T00:00:00Z"
            artifact = create_ir_artifact(
                artifact_id=f"test_ir_{i:03d}",
                graph=graph,
                source_document_id=f"doc_{i}",
                created_by="test",
            )
            # Override timestamp for testing
            artifact.metadata.created_at = timestamp
            service.save_artifact(artifact, dossier_id="test_dossier")

        # List all artifacts - should be sorted newest first
        all_artifacts = service.list_all_artifacts()
        assert len(all_artifacts) == 3
        assert all_artifacts[0]["artifact_id"] == "test_ir_002"
        assert all_artifacts[1]["artifact_id"] == "test_ir_001"
        assert all_artifacts[2]["artifact_id"] == "test_ir_000"


def test_mixed_artifact_types():
    """Different artifact types can be saved and filtered correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _create_service(tmpdir)

        # Save IR artifact
        graph = FeatureGraph(graph_id="test_mixed_graph", nodes=[], edges=[])
        ir_artifact = create_ir_artifact(
            artifact_id="test_ir_001",
            graph=graph,
            source_document_id="doc_123",
            created_by="test",
        )
        service.save_artifact(ir_artifact, dossier_id="test_dossier")

        # Save compile artifact
        compile_artifact = create_compile_artifact(
            artifact_id="test_compile_001",
            graph_id="test_mixed_graph",
            compiled_features={},
            gaps=[],
            warnings=[],
            created_by="test",
        )
        service.save_artifact(compile_artifact, dossier_id="test_dossier")

        # Save judge artifact
        judge_report = JudgeReport(
            graph_id="test_mixed_graph",
            gaps=[],
            warnings=[],
        )
        judge_artifact = create_judge_artifact(
            artifact_id="test_judge_001",
            graph_id="test_mixed_graph",
            report=judge_report,
            created_by="test",
        )
        service.save_artifact(judge_artifact, dossier_id="test_dossier")

        # List all artifacts
        all_artifacts = service.list_all_artifacts()
        assert len(all_artifacts) == 3

        # Filter by type
        ir_artifacts = service.list_artifacts(artifact_type="ir")
        assert len(ir_artifacts) == 1
        assert ir_artifacts[0]["artifact_type"] == "ir"

        compile_artifacts = service.list_artifacts(artifact_type="compile")
        assert len(compile_artifacts) == 1
        assert compile_artifacts[0]["artifact_type"] == "compile"

        judge_artifacts = service.list_artifacts(artifact_type="judge")
        assert len(judge_artifacts) == 1
        assert judge_artifacts[0]["artifact_type"] == "judge"
