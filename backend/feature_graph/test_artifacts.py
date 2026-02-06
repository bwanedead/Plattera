"""
Tests for Feature Graph Artifact Models
========================================

Validates artifact models (IRArtifact, CompileArtifact, JudgeArtifact, BundleArtifact)
and their lineage tracking, JSON serialization, and rehydration behavior.
"""

import pytest
import json
from datetime import datetime

from backend.feature_graph.artifacts import (
    ArtifactMetadata,
    IRArtifact,
    CompileArtifact,
    JudgeArtifact,
    BundleArtifact,
    create_ir_artifact,
    create_compile_artifact,
    create_judge_artifact,
    create_bundle_artifact
)
from backend.feature_graph.models import (
    FeatureGraph,
    FeatureNode,
    FeatureKind,
    OpExpr
)
from backend.feature_graph.gaps import (
    JudgeReport,
    FeatureGap,
    GapKind,
    missing_parameter_gap
)


def test_artifact_metadata_serialization():
    """ArtifactMetadata should serialize and deserialize correctly."""
    metadata = ArtifactMetadata(
        created_at="2024-01-01T00:00:00Z",
        created_by="test-agent",
        parent_artifact_ids=["parent-1", "parent-2"],
        version="1.0"
    )

    # JSON round-trip
    json_str = metadata.model_dump_json()
    rehydrated = ArtifactMetadata.model_validate_json(json_str)

    assert rehydrated.created_at == metadata.created_at
    assert rehydrated.created_by == metadata.created_by
    assert rehydrated.parent_artifact_ids == metadata.parent_artifact_ids
    assert rehydrated.version == metadata.version


def test_ir_artifact_minimal():
    """IRArtifact should serialize a minimal feature graph."""
    graph = FeatureGraph(
        graph_id="test-graph-1",
        nodes=[
            FeatureNode(id="P1", kind=FeatureKind.POINT, geometry={"type": "Point", "coordinates": [0, 0]})
        ]
    )

    metadata = ArtifactMetadata(
        created_at="2024-01-01T00:00:00Z",
        created_by="test-compiler"
    )

    artifact = IRArtifact(
        artifact_id="ir-artifact-1",
        artifact_type="ir",
        graph=graph,
        metadata=metadata
    )

    # JSON round-trip
    json_str = artifact.model_dump_json()
    rehydrated = IRArtifact.model_validate_json(json_str)

    assert rehydrated.artifact_id == artifact.artifact_id
    assert rehydrated.graph.graph_id == graph.graph_id
    assert len(rehydrated.graph.nodes) == 1
    assert rehydrated.graph.nodes[0].id == "P1"
    assert rehydrated.metadata.created_by == "test-compiler"


def test_ir_artifact_with_source_document():
    """IRArtifact should track source document references."""
    graph = FeatureGraph(graph_id="test-graph-2", nodes=[])

    artifact = create_ir_artifact(
        artifact_id="ir-artifact-2",
        graph=graph,
        created_by="extraction-agent",
        source_document_id="deed-123",
        parent_artifact_ids=["ocr-artifact-1"]
    )

    assert artifact.source_document_id == "deed-123"
    assert artifact.metadata.parent_artifact_ids == ["ocr-artifact-1"]
    assert artifact.metadata.created_by == "extraction-agent"

    # JSON round-trip
    json_str = artifact.model_dump_json()
    rehydrated = IRArtifact.model_validate_json(json_str)

    assert rehydrated.source_document_id == "deed-123"
    assert rehydrated.metadata.parent_artifact_ids == ["ocr-artifact-1"]


def test_compile_artifact_with_gaps():
    """CompileArtifact should store compiled features and gaps."""
    compiled_features = {
        "T1": {"type": "LineString", "coordinates": [[0, 0], [100, 0]]},
        "R1": {"type": "Polygon", "coordinates": [[[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]]}
    }

    gaps = [
        {
            "kind": "missing_parameter",
            "message": "Missing bearing parameter",
            "feature_id": "T2",
            "severity": "error"
        }
    ]

    artifact = create_compile_artifact(
        artifact_id="compile-artifact-1",
        graph_id="test-graph-1",
        compiled_features=compiled_features,
        gaps=gaps,
        warnings=["Some features could not be anchored"],
        created_by="compiler-v1",
        parent_artifact_ids=["ir-artifact-1"],
        compiler_version="1.0.0"
    )

    assert artifact.graph_id == "test-graph-1"
    assert len(artifact.compiled_features) == 2
    assert "T1" in artifact.compiled_features
    assert len(artifact.gaps) == 1
    assert artifact.gaps[0]["kind"] == "missing_parameter"
    assert len(artifact.warnings) == 1
    assert artifact.compiler_version == "1.0.0"

    # JSON round-trip
    json_str = artifact.model_dump_json()
    rehydrated = CompileArtifact.model_validate_json(json_str)

    assert rehydrated.graph_id == artifact.graph_id
    assert rehydrated.compiled_features == artifact.compiled_features
    assert rehydrated.gaps == artifact.gaps
    assert rehydrated.warnings == artifact.warnings


def test_compile_artifact_empty():
    """CompileArtifact should handle empty compilation results."""
    artifact = create_compile_artifact(
        artifact_id="compile-artifact-empty",
        graph_id="test-graph-empty",
        compiled_features={},
        created_by="compiler-v1",
        parent_artifact_ids=["ir-artifact-empty"]
    )

    assert artifact.compiled_features == {}
    assert artifact.gaps == []
    assert artifact.warnings == []

    # JSON round-trip
    json_str = artifact.model_dump_json()
    rehydrated = CompileArtifact.model_validate_json(json_str)

    assert rehydrated.compiled_features == {}
    assert rehydrated.gaps == []


def test_judge_artifact_with_report():
    """JudgeArtifact should wrap a JudgeReport with metadata."""
    # Create a judge report with gaps
    report = JudgeReport(
        graph_id="test-graph-1",
        gaps=[
            missing_parameter_gap(
                feature_id="T1",
                operation="LineStep",
                parameter_name="bearing"
            )
        ],
        warnings=["Feature T2 has no provenance"],
        artifacts={"local_geometry": "computed"}
    )

    artifact = create_judge_artifact(
        artifact_id="judge-artifact-1",
        graph_id="test-graph-1",
        report=report,
        created_by="judge-v1",
        parent_artifact_ids=["compile-artifact-1"],
        judge_version="1.0.0"
    )

    assert artifact.graph_id == "test-graph-1"
    assert artifact.report.graph_id == "test-graph-1"
    assert len(artifact.report.gaps) == 1
    assert artifact.report.gaps[0].kind == GapKind.MISSING_PARAMETER
    assert artifact.judge_version == "1.0.0"

    # JSON round-trip
    json_str = artifact.model_dump_json()
    rehydrated = JudgeArtifact.model_validate_json(json_str)

    assert rehydrated.graph_id == artifact.graph_id
    assert len(rehydrated.report.gaps) == 1
    assert rehydrated.report.gaps[0].kind == GapKind.MISSING_PARAMETER


def test_bundle_artifact_minimal():
    """BundleArtifact should bundle a single graph."""
    target_graph = FeatureGraph(
        graph_id="target-graph-1",
        nodes=[
            FeatureNode(id="P1", kind=FeatureKind.POINT, geometry={"type": "Point", "coordinates": [0, 0]})
        ]
    )

    artifact = create_bundle_artifact(
        artifact_id="bundle-artifact-1",
        target_graph=target_graph,
        created_by="bundler-v1",
        bundle_purpose="export-for-validation"
    )

    assert artifact.target_graph_id == "target-graph-1"
    assert artifact.target_graph.graph_id == "target-graph-1"
    assert len(artifact.dependency_graphs) == 0
    assert artifact.bundle_purpose == "export-for-validation"

    # JSON round-trip
    json_str = artifact.model_dump_json()
    rehydrated = BundleArtifact.model_validate_json(json_str)

    assert rehydrated.target_graph_id == artifact.target_graph_id
    assert rehydrated.target_graph.graph_id == artifact.target_graph.graph_id


def test_bundle_artifact_with_dependencies():
    """BundleArtifact should include dependency graphs with reasons."""
    target_graph = FeatureGraph(
        graph_id="target-graph-2",
        nodes=[
            FeatureNode(
                id="T1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(op_name="Traverse", operands=["start-point"])
            )
        ]
    )

    dep_graph_1 = FeatureGraph(
        graph_id="dep-graph-1",
        nodes=[
            FeatureNode(id="start-point", kind=FeatureKind.POINT, geometry={"type": "Point", "coordinates": [0, 0]})
        ]
    )

    dep_graph_2 = FeatureGraph(
        graph_id="dep-graph-2",
        nodes=[
            FeatureNode(id="frame-1", kind=FeatureKind.FRAME, metadata={"plss_section": "S1-T1N-R1E"})
        ]
    )

    artifact = create_bundle_artifact(
        artifact_id="bundle-artifact-2",
        target_graph=target_graph,
        dependency_graphs=[dep_graph_1, dep_graph_2],
        dependency_reasons={
            "dep-graph-1": "Required start point for Traverse",
            "dep-graph-2": "Frame reference for global anchoring"
        },
        created_by="bundler-v1",
        bundle_purpose="export-complete-graph"
    )

    assert artifact.target_graph_id == "target-graph-2"
    assert len(artifact.dependency_graphs) == 2
    assert len(artifact.dependency_reasons) == 2
    assert artifact.get_dependency_reason("dep-graph-1") == "Required start point for Traverse"
    assert artifact.get_dependency_reason("dep-graph-2") == "Frame reference for global anchoring"

    # Test get_all_graph_ids
    all_ids = artifact.get_all_graph_ids()
    assert len(all_ids) == 3
    assert "target-graph-2" in all_ids
    assert "dep-graph-1" in all_ids
    assert "dep-graph-2" in all_ids

    # JSON round-trip
    json_str = artifact.model_dump_json()
    rehydrated = BundleArtifact.model_validate_json(json_str)

    assert len(rehydrated.dependency_graphs) == 2
    assert rehydrated.dependency_reasons == artifact.dependency_reasons


def test_bundle_artifact_with_included_artifacts():
    """BundleArtifact should track included compile/judge artifact IDs."""
    target_graph = FeatureGraph(graph_id="target-graph-3", nodes=[])

    artifact = create_bundle_artifact(
        artifact_id="bundle-artifact-3",
        target_graph=target_graph,
        created_by="bundler-v1"
    )

    # Add included artifact IDs
    artifact.included_compile_artifacts = ["compile-artifact-1", "compile-artifact-2"]
    artifact.included_judge_artifacts = ["judge-artifact-1"]

    assert len(artifact.included_compile_artifacts) == 2
    assert len(artifact.included_judge_artifacts) == 1

    # JSON round-trip
    json_str = artifact.model_dump_json()
    rehydrated = BundleArtifact.model_validate_json(json_str)

    assert rehydrated.included_compile_artifacts == artifact.included_compile_artifacts
    assert rehydrated.included_judge_artifacts == artifact.included_judge_artifacts


def test_artifact_lineage_tracking():
    """All artifacts should track lineage through parent_artifact_ids."""
    # Create IR artifact (no parent)
    graph = FeatureGraph(graph_id="lineage-graph", nodes=[])
    ir_artifact = create_ir_artifact(
        artifact_id="ir-1",
        graph=graph,
        created_by="extractor"
    )
    assert ir_artifact.metadata.parent_artifact_ids == []

    # Create compile artifact (parent: IR artifact)
    compile_artifact = create_compile_artifact(
        artifact_id="compile-1",
        graph_id="lineage-graph",
        compiled_features={},
        parent_artifact_ids=["ir-1"],
        created_by="compiler"
    )
    assert compile_artifact.metadata.parent_artifact_ids == ["ir-1"]

    # Create judge artifact (parent: compile artifact)
    report = JudgeReport(graph_id="lineage-graph", gaps=[])
    judge_artifact = create_judge_artifact(
        artifact_id="judge-1",
        graph_id="lineage-graph",
        report=report,
        parent_artifact_ids=["compile-1"],
        created_by="judge"
    )
    assert judge_artifact.metadata.parent_artifact_ids == ["compile-1"]

    # Create bundle artifact (parents: IR + compile + judge)
    bundle_artifact = create_bundle_artifact(
        artifact_id="bundle-1",
        target_graph=graph,
        parent_artifact_ids=["ir-1", "compile-1", "judge-1"],
        created_by="bundler"
    )
    assert bundle_artifact.metadata.parent_artifact_ids == ["ir-1", "compile-1", "judge-1"]


def test_artifact_timestamps_are_set():
    """All artifact constructors should set created_at timestamps."""
    graph = FeatureGraph(graph_id="timestamp-graph", nodes=[])

    ir_artifact = create_ir_artifact(artifact_id="ir-ts", graph=graph)
    assert ir_artifact.metadata.created_at is not None
    assert "T" in ir_artifact.metadata.created_at  # ISO format check

    compile_artifact = create_compile_artifact(
        artifact_id="compile-ts",
        graph_id="timestamp-graph",
        compiled_features={}
    )
    assert compile_artifact.metadata.created_at is not None

    report = JudgeReport(graph_id="timestamp-graph", gaps=[])
    judge_artifact = create_judge_artifact(
        artifact_id="judge-ts",
        graph_id="timestamp-graph",
        report=report
    )
    assert judge_artifact.metadata.created_at is not None

    bundle_artifact = create_bundle_artifact(
        artifact_id="bundle-ts",
        target_graph=graph
    )
    assert bundle_artifact.metadata.created_at is not None


def test_all_artifact_types_have_discriminator():
    """All artifacts should have correct artifact_type discriminator."""
    graph = FeatureGraph(graph_id="discriminator-graph", nodes=[])

    ir_artifact = create_ir_artifact(artifact_id="ir-disc", graph=graph)
    assert ir_artifact.artifact_type == "ir"

    compile_artifact = create_compile_artifact(
        artifact_id="compile-disc",
        graph_id="discriminator-graph",
        compiled_features={}
    )
    assert compile_artifact.artifact_type == "compile"

    report = JudgeReport(graph_id="discriminator-graph", gaps=[])
    judge_artifact = create_judge_artifact(
        artifact_id="judge-disc",
        graph_id="discriminator-graph",
        report=report
    )
    assert judge_artifact.artifact_type == "judge"

    bundle_artifact = create_bundle_artifact(
        artifact_id="bundle-disc",
        target_graph=graph
    )
    assert bundle_artifact.artifact_type == "bundle"


def test_complex_bundle_round_trip():
    """BundleArtifact with complex nested graphs should serialize correctly."""
    # Create a complex target graph with operations
    target_graph = FeatureGraph(
        graph_id="complex-target",
        nodes=[
            FeatureNode(id="T1", kind=FeatureKind.CURVE, op_expr=OpExpr(
                op_name="Traverse",
                params={"start": "P1"},
                operands=[]
            )),
            FeatureNode(id="R1", kind=FeatureKind.REGION, op_expr=OpExpr(
                op_name="Close",
                operands=["T1"]
            ))
        ],
        metadata={"source": "deed-123"}
    )

    # Create dependency graphs
    dep_graph = FeatureGraph(
        graph_id="dep-complex",
        nodes=[
            FeatureNode(id="P1", kind=FeatureKind.POINT, geometry={"type": "Point", "coordinates": [0, 0]})
        ]
    )

    artifact = create_bundle_artifact(
        artifact_id="bundle-complex",
        target_graph=target_graph,
        dependency_graphs=[dep_graph],
        dependency_reasons={"dep-complex": "Start point for traverse"},
        created_by="bundler-v1",
        bundle_purpose="export-for-analysis"
    )

    # JSON round-trip
    json_str = artifact.model_dump_json()
    rehydrated = BundleArtifact.model_validate_json(json_str)

    assert rehydrated.target_graph.graph_id == "complex-target"
    assert len(rehydrated.target_graph.nodes) == 2
    assert rehydrated.target_graph.nodes[0].op_expr.op_name == "Traverse"
    assert rehydrated.target_graph.nodes[1].op_expr.op_name == "Close"
    assert len(rehydrated.dependency_graphs) == 1
    assert rehydrated.dependency_graphs[0].nodes[0].id == "P1"


def test_artifact_version_field():
    """All artifacts should have version field for schema evolution."""
    graph = FeatureGraph(graph_id="version-graph", nodes=[])

    ir_artifact = create_ir_artifact(artifact_id="ir-version", graph=graph)
    assert ir_artifact.metadata.version == "1.0"

    compile_artifact = create_compile_artifact(
        artifact_id="compile-version",
        graph_id="version-graph",
        compiled_features={}
    )
    assert compile_artifact.metadata.version == "1.0"

    report = JudgeReport(graph_id="version-graph", gaps=[])
    judge_artifact = create_judge_artifact(
        artifact_id="judge-version",
        graph_id="version-graph",
        report=report
    )
    assert judge_artifact.metadata.version == "1.0"

    bundle_artifact = create_bundle_artifact(
        artifact_id="bundle-version",
        target_graph=graph
    )
    assert bundle_artifact.metadata.version == "1.0"
