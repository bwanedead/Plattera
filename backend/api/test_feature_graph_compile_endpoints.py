"""
Tests for Feature Graph Compile/Judge/Bundle API Endpoints
============================================================

Tests the compile, judge, and bundle endpoints in the feature graph router.
These endpoints execute deterministic operations on feature graphs and return
structured artifacts with provenance.

Test structure:
- Compile endpoint tests: successful compilation, gap handling, persistence
- Judge endpoint tests: validation reports, gap detection, deterministic output
- Bundle endpoint tests: dependency bundling, recursive discovery, portability
"""

import asyncio
import tempfile
from pathlib import Path

from feature_graph.models import FeatureGraph, FeatureNode, FeatureKind

# Import endpoint module
from api.endpoints import feature_graph as endpoint
from api.endpoints.feature_graph import (
    CompileRequest,
    JudgeRequest,
    BundleRequest,
)

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


# ============================================================================
# COMPILE ENDPOINT TESTS
# ============================================================================

def test_compile_simple_traverse():
    """Test compiling a simple traverse with LineStep operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        # Create a simple graph with two LineStep operations
        graph = {
            "graph_id": "test_traverse",
            "nodes": [
                {
                    "id": "start",
                    "kind": "POINT",
                    "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                    "labels": ["origin"]
                },
                {
                    "id": "line1",
                    "kind": "CURVE",
                    "op_expr": {
                        "operation": "Traverse/LineStep",
                        "operands": ["start"],
                        "params": {
                            "bearing_degrees": 0.0,
                            "distance_feet": 100.0
                        }
                    },
                    "labels": ["north 100ft"]
                },
                {
                    "id": "line2",
                    "kind": "CURVE",
                    "op_expr": {
                        "operation": "Traverse/LineStep",
                        "operands": ["line1"],
                        "params": {
                            "bearing_degrees": 90.0,
                            "distance_feet": 50.0
                        }
                    },
                    "labels": ["east 50ft"]
                }
            ],
            "edges": []
        }

        request = CompileRequest(
            graph=graph,
            dossier_id="test_dossier"
        )

        response = asyncio.run(endpoint.compile_feature_graph(request))

        assert response.success is True
        assert response.artifact is not None
        assert response.artifact_id is not None

        artifact = response.artifact
        assert artifact["artifact_type"] == "compile"
        assert "compiled_features" in artifact
        assert "gaps" in artifact

        # Should have compiled 3 features (start point + 2 lines)
        compiled = artifact["compiled_features"]
        assert "start" in compiled
        assert "line1" in compiled
        assert "line2" in compiled

        # No gaps for valid traverse
        assert len(artifact["gaps"]) == 0


def test_compile_with_missing_parameters():
    """Test compiling a graph with missing parameters produces typed gaps."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        graph = {
            "graph_id": "test_missing_params",
            "nodes": [
                {
                    "id": "start",
                    "kind": "POINT",
                    "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                    "labels": ["origin"]
                },
                {
                    "id": "bad_line",
                    "kind": "CURVE",
                    "op_expr": {
                        "operation": "Traverse/LineStep",
                        "operands": ["start"],
                        "params": {
                            "bearing_degrees": 45.0
                            # Missing distance_feet
                        }
                    },
                    "labels": ["incomplete step"]
                }
            ],
            "edges": []
        }

        request = CompileRequest(
            graph=graph,
            dossier_id="test_dossier"
        )

        response = asyncio.run(endpoint.compile_feature_graph(request))
        artifact = response.artifact

        # Should have at least one gap for missing parameter
        gaps = artifact["gaps"]
        assert len(gaps) > 0

        # Find the missing parameter gap
        param_gap = next((g for g in gaps if g["kind"] == "MissingParameter"), None)
        assert param_gap is not None
        assert param_gap["feature_id"] == "bad_line"
        assert "distance" in param_gap["description"].lower()


def test_compile_saves_artifact():
    """Test that compile endpoint saves artifact to persistence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        graph = {
            "graph_id": "test_save",
            "nodes": [
                {
                    "id": "point1",
                    "kind": "POINT",
                    "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
                    "labels": ["test"]
                }
            ],
            "edges": []
        }

        request = CompileRequest(
            graph=graph,
            dossier_id="dossier_persist",
            artifact_id="compile_test_save"
        )

        response = asyncio.run(endpoint.compile_feature_graph(request))
        artifact_id = response.artifact_id

        # Verify artifact was saved to disk
        artifact_path = Path(tmpdir) / "artifacts" / "dossier_persist" / f"{artifact_id}.json"
        assert artifact_path.exists()


def test_compile_with_unsupported_operation():
    """Test compiling graph with unsupported operation produces gap."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        graph = {
            "graph_id": "test_unsupported",
            "nodes": [
                {
                    "id": "curve1",
                    "kind": "CURVE",
                    "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                    "labels": ["base curve"]
                },
                {
                    "id": "buffered",
                    "kind": "REGION",
                    "op_expr": {
                        "operation": "Derive/Buffer",
                        "operands": ["curve1"],
                        "params": {"width_feet": 10.0}
                    },
                    "labels": ["buffered region"]
                }
            ],
            "edges": []
        }

        request = CompileRequest(
            graph=graph,
            dossier_id="test_dossier"
        )

        response = asyncio.run(endpoint.compile_feature_graph(request))
        artifact = response.artifact

        # Should have gap for unsupported Buffer operation
        gaps = artifact["gaps"]
        unsupported_gap = next((g for g in gaps if g["kind"] == "UnsupportedOperation"), None)
        assert unsupported_gap is not None
        assert "Buffer" in unsupported_gap["description"]


# ============================================================================
# JUDGE ENDPOINT TESTS
# ============================================================================

def test_judge_valid_graph():
    """Test judging a valid graph with no gaps."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        graph = {
            "graph_id": "test_valid",
            "nodes": [
                {
                    "id": "frame1",
                    "kind": "FRAME",
                    "labels": ["NAD83"],
                    "params": {"datum": "NAD83"}
                },
                {
                    "id": "point1",
                    "kind": "POINT",
                    "geometry": {"type": "Point", "coordinates": [100.0, 200.0]},
                    "labels": ["anchored point"],
                    "op_expr": {
                        "operation": "Anchor",
                        "operands": ["frame1"],
                        "params": {"x": 100.0, "y": 200.0}
                    }
                }
            ],
            "edges": []
        }

        request = JudgeRequest(
            graph=graph,
            dossier_id="test_dossier"
        )

        response = asyncio.run(endpoint.judge_feature_graph(request))
        assert response.success is True

        artifact = response.artifact
        assert artifact["artifact_type"] == "judge"
        assert "judge_report" in artifact

        report = artifact["judge_report"]
        assert report["status"] in ["success", "partial", "failed"]
        assert "gaps" in report


def test_judge_missing_anchor():
    """Test judging a graph with missing anchor produces gap."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        graph = {
            "graph_id": "test_no_anchor",
            "nodes": [
                {
                    "id": "point1",
                    "kind": "POINT",
                    "labels": ["unanchored point"]
                    # No geometry, no frame reference
                }
            ],
            "edges": []
        }

        request = JudgeRequest(
            graph=graph,
            dossier_id="test_dossier"
        )

        response = asyncio.run(endpoint.judge_feature_graph(request))
        artifact = response.artifact
        report = artifact["judge_report"]

        # Should have gap for missing anchor
        gaps = report["gaps"]
        anchor_gap = next((g for g in gaps if g["kind"] == "MissingAnchor"), None)
        assert anchor_gap is not None
        assert anchor_gap["feature_id"] == "point1"


def test_judge_missing_operand():
    """Test judging a graph with missing operand produces gap."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        graph = {
            "graph_id": "test_missing_operand",
            "nodes": [
                {
                    "id": "line1",
                    "kind": "CURVE",
                    "op_expr": {
                        "operation": "Traverse/LineStep",
                        "operands": ["nonexistent_start"],  # References non-existent node
                        "params": {
                            "bearing_degrees": 0.0,
                            "distance_feet": 100.0
                        }
                    },
                    "labels": ["orphaned line"]
                }
            ],
            "edges": []
        }

        request = JudgeRequest(
            graph=graph,
            dossier_id="test_dossier"
        )

        response = asyncio.run(endpoint.judge_feature_graph(request))
        artifact = response.artifact
        report = artifact["judge_report"]

        # Should have gap for missing operand
        gaps = report["gaps"]
        operand_gap = next((g for g in gaps if g["kind"] == "MissingOperand"), None)
        assert operand_gap is not None
        assert "nonexistent_start" in operand_gap["description"]


def test_judge_saves_artifact():
    """Test that judge endpoint saves artifact to persistence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        graph = {
            "graph_id": "test_judge_save",
            "nodes": [
                {
                    "id": "point1",
                    "kind": "POINT",
                    "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
                    "labels": ["test"]
                }
            ],
            "edges": []
        }

        request = JudgeRequest(
            graph=graph,
            dossier_id="dossier_judge",
            artifact_id="judge_test_save"
        )

        response = asyncio.run(endpoint.judge_feature_graph(request))
        artifact_id = response.artifact_id

        # Verify artifact was saved to disk
        artifact_path = Path(tmpdir) / "artifacts" / "dossier_judge" / f"{artifact_id}.json"
        assert artifact_path.exists()


def test_judge_with_warnings():
    """Test judge endpoint with include_warnings flag."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        graph = {
            "graph_id": "test_warnings",
            "nodes": [
                {
                    "id": "point1",
                    "kind": "POINT",
                    "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                    "labels": ["test"]
                }
            ],
            "edges": []
        }

        # Test with warnings enabled
        request_with_warnings = JudgeRequest(
            graph=graph,
            dossier_id="test_dossier",
            include_warnings=True
        )

        response = asyncio.run(endpoint.judge_feature_graph(request_with_warnings))
        assert response.success is True

        # Test with warnings disabled
        request_no_warnings = JudgeRequest(
            graph=graph,
            dossier_id="test_dossier",
            include_warnings=False
        )

        response = asyncio.run(endpoint.judge_feature_graph(request_no_warnings))
        assert response.success is True


# ============================================================================
# BUNDLE ENDPOINT TESTS
# ============================================================================

def test_bundle_simple_graph():
    """Test bundling a simple graph with no dependencies."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        graph = {
            "graph_id": "test_bundle",
            "nodes": [
                {
                    "id": "point1",
                    "kind": "POINT",
                    "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
                    "labels": ["standalone point"]
                }
            ],
            "edges": []
        }

        request = BundleRequest(
            target_graph=graph,
            dossier_id="test_dossier"
        )

        response = asyncio.run(endpoint.bundle_graph(request))
        assert response.success is True

        artifact = response.artifact
        assert artifact["artifact_type"] == "bundle"
        assert "target_graph" in artifact
        assert "dependency_graphs" in artifact
        assert "dependency_reasons" in artifact

        # No dependencies for simple graph
        assert len(artifact["dependency_graphs"]) == 0


def test_bundle_with_dependencies():
    """Test bundling a graph that references external dependencies."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        target_graph = {
            "graph_id": "parcel_a",
            "nodes": [
                {
                    "id": "origin",
                    "kind": "POINT",
                    "op_expr": {
                        "operation": "FeatureRef",
                        "operands": [],
                        "params": {
                            "ref": {
                                "graph_id": "section_1",
                                "feature_id": "ne_corner",
                                "is_external": True,
                                "label": "NE Corner Section 1"
                            }
                        }
                    },
                    "labels": ["starting point"]
                }
            ],
            "edges": []
        }

        dependency_graph = {
            "graph_id": "section_1",
            "nodes": [
                {
                    "id": "ne_corner",
                    "kind": "POINT",
                    "geometry": {"type": "Point", "coordinates": [1000.0, 2000.0]},
                    "labels": ["NE Corner"]
                }
            ],
            "edges": []
        }

        request = BundleRequest(
            target_graph=target_graph,
            available_graphs={
                "section_1": dependency_graph
            },
            dossier_id="test_dossier",
            bundle_purpose="Test bundle with dependencies"
        )

        response = asyncio.run(endpoint.bundle_graph(request))
        artifact = response.artifact

        # Should have exactly 1 dependency (section_1)
        deps = artifact["dependency_graphs"]
        assert len(deps) == 1
        assert deps[0]["graph_id"] == "section_1"

        # Should have reason for inclusion
        reasons = artifact["dependency_reasons"]
        assert "section_1" in reasons
        assert "origin" in reasons["section_1"]


def test_bundle_saves_artifact():
    """Test that bundle endpoint saves artifact to persistence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        graph = {
            "graph_id": "test_bundle_save",
            "nodes": [
                {
                    "id": "point1",
                    "kind": "POINT",
                    "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
                    "labels": ["test"]
                }
            ],
            "edges": []
        }

        request = BundleRequest(
            target_graph=graph,
            dossier_id="dossier_bundle",
            artifact_id="bundle_test_save"
        )

        response = asyncio.run(endpoint.bundle_graph(request))
        artifact_id = response.artifact_id

        # Verify artifact was saved to disk
        artifact_path = Path(tmpdir) / "artifacts" / "dossier_bundle" / f"{artifact_id}.json"
        assert artifact_path.exists()


def test_bundle_with_created_by():
    """Test bundle endpoint with created_by metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_temp_persistence_service(tmpdir)

        graph = {
            "graph_id": "test_metadata",
            "nodes": [
                {
                    "id": "point1",
                    "kind": "POINT",
                    "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
                    "labels": ["test"]
                }
            ],
            "edges": []
        }

        request = BundleRequest(
            target_graph=graph,
            dossier_id="test_dossier",
            created_by="test_agent",
            bundle_purpose="Testing metadata capture"
        )

        response = asyncio.run(endpoint.bundle_graph(request))
        artifact = response.artifact

        # Verify metadata was captured
        assert artifact.get("created_by") == "test_agent"
        assert artifact.get("bundle_purpose") == "Testing metadata capture"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
