"""
Feature Graph Artifact Models
==============================

Models for persisting feature graph IR, compilation outputs, judge reports, and bundles.
These artifacts represent durable, rehydratable states of the feature graph pipeline.

Design principles:
- Artifacts are durable: must serialize to disk and rehydrate deterministically
- Lineage tracking: every artifact knows its parent artifacts
- No ephemeral state: everything needed for rehydration is included
- Portability: bundles are self-contained and can be moved/shared
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

from .models import FeatureGraph
from .gaps import JudgeReport


class ArtifactMetadata(BaseModel):
    """
    Common metadata for all artifact types.

    Tracks creation time, creator, and lineage relationships.
    """
    created_at: str = Field(..., description="ISO timestamp of artifact creation")
    created_by: Optional[str] = Field(None, description="Agent/tool that created this artifact")
    parent_artifact_ids: List[str] = Field(default_factory=list, description="IDs of parent artifacts (lineage)")
    version: str = Field("1.0", description="Artifact schema version")

    class Config:
        frozen = False


class IRArtifact(BaseModel):
    """
    IR Artifact: persisted feature graph intermediate representation.

    This is the raw IR that can be stored, retrieved, and compiled.
    It contains the complete feature graph with all nodes, edges, and metadata.
    """
    artifact_id: str = Field(..., description="Unique artifact ID")
    artifact_type: str = Field("ir", description="Artifact type discriminator")
    graph: FeatureGraph = Field(..., description="The feature graph IR")
    metadata: ArtifactMetadata = Field(..., description="Artifact metadata with lineage")

    # Optional: source document references
    source_document_id: Optional[str] = Field(None, description="ID of source document (deed, plat, etc)")
    source_metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional source context")

    class Config:
        frozen = False


class CompileArtifact(BaseModel):
    """
    Compile Artifact: output of feature graph compilation.

    Contains the partial or complete compiled output (local geometry, constraints, etc)
    along with any gaps or warnings produced during compilation.
    """
    artifact_id: str = Field(..., description="Unique artifact ID")
    artifact_type: str = Field("compile", description="Artifact type discriminator")
    graph_id: str = Field(..., description="ID of source feature graph")
    metadata: ArtifactMetadata = Field(..., description="Artifact metadata with lineage")

    # Compilation outputs
    compiled_features: Dict[str, Any] = Field(default_factory=dict, description="Compiled feature outputs (node_id -> geometry/result)")
    gaps: List[Dict[str, Any]] = Field(default_factory=list, description="Gaps discovered during compilation")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal compilation warnings")

    # Compilation context
    compiler_version: Optional[str] = Field(None, description="Version of compiler used")
    compilation_metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional compilation context")

    class Config:
        frozen = False


class JudgeArtifact(BaseModel):
    """
    Judge Artifact: validation/judge report for a feature graph.

    Contains the complete judge report with all gaps, warnings, and validation results.
    This is a wrapper around JudgeReport that adds artifact metadata and lineage.
    """
    artifact_id: str = Field(..., description="Unique artifact ID")
    artifact_type: str = Field("judge", description="Artifact type discriminator")
    graph_id: str = Field(..., description="ID of feature graph that was judged")
    metadata: ArtifactMetadata = Field(..., description="Artifact metadata with lineage")

    # Judge report
    report: JudgeReport = Field(..., description="The complete judge report")

    # Judge context
    judge_version: Optional[str] = Field(None, description="Version of judge engine used")
    judge_metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional judge context")

    class Config:
        frozen = False


class BundleArtifact(BaseModel):
    """
    Bundle Artifact: portable, self-contained package of IR + dependencies.

    A bundle includes:
    - The target feature graph IR
    - Minimal dependency subgraph (referenced features, frames, etc)
    - Metadata explaining why each dependency was included
    - All provenance and lineage information

    Bundles are portable: they can be exported, shared, and imported into other systems.
    """
    artifact_id: str = Field(..., description="Unique bundle ID")
    artifact_type: str = Field("bundle", description="Artifact type discriminator")
    metadata: ArtifactMetadata = Field(..., description="Artifact metadata with lineage")

    # Target graph
    target_graph_id: str = Field(..., description="ID of primary feature graph in this bundle")
    target_graph: FeatureGraph = Field(..., description="The primary feature graph")

    # Dependencies
    dependency_graphs: List[FeatureGraph] = Field(default_factory=list, description="Dependency feature graphs")
    dependency_reasons: Dict[str, str] = Field(default_factory=dict, description="graph_id -> reason for inclusion")

    # Additional artifacts
    included_compile_artifacts: List[str] = Field(default_factory=list, description="IDs of compile artifacts included")
    included_judge_artifacts: List[str] = Field(default_factory=list, description="IDs of judge artifacts included")

    # Bundle metadata
    bundle_purpose: Optional[str] = Field(None, description="Why this bundle was created")
    bundle_metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional bundle context")

    class Config:
        frozen = False

    def get_all_graph_ids(self) -> List[str]:
        """Get all graph IDs in this bundle (target + dependencies)."""
        return [self.target_graph_id] + [g.graph_id for g in self.dependency_graphs]

    def get_dependency_reason(self, graph_id: str) -> Optional[str]:
        """Get the reason why a dependency was included."""
        return self.dependency_reasons.get(graph_id)


# Artifact constructor helpers

def create_ir_artifact(
    artifact_id: str,
    graph: FeatureGraph,
    created_by: Optional[str] = None,
    source_document_id: Optional[str] = None,
    parent_artifact_ids: Optional[List[str]] = None
) -> IRArtifact:
    """Construct an IR artifact with metadata."""
    metadata = ArtifactMetadata(
        created_at=datetime.utcnow().isoformat() + "Z",
        created_by=created_by,
        parent_artifact_ids=parent_artifact_ids or [],
        version="1.0"
    )
    return IRArtifact(
        artifact_id=artifact_id,
        artifact_type="ir",
        graph=graph,
        metadata=metadata,
        source_document_id=source_document_id
    )


def create_compile_artifact(
    artifact_id: str,
    graph_id: str,
    compiled_features: Dict[str, Any],
    gaps: Optional[List[Dict[str, Any]]] = None,
    warnings: Optional[List[str]] = None,
    created_by: Optional[str] = None,
    parent_artifact_ids: Optional[List[str]] = None,
    compiler_version: Optional[str] = None
) -> CompileArtifact:
    """Construct a compile artifact with metadata."""
    metadata = ArtifactMetadata(
        created_at=datetime.utcnow().isoformat() + "Z",
        created_by=created_by,
        parent_artifact_ids=parent_artifact_ids or [],
        version="1.0"
    )
    return CompileArtifact(
        artifact_id=artifact_id,
        artifact_type="compile",
        graph_id=graph_id,
        metadata=metadata,
        compiled_features=compiled_features,
        gaps=gaps or [],
        warnings=warnings or [],
        compiler_version=compiler_version
    )


def create_judge_artifact(
    artifact_id: str,
    graph_id: str,
    report: JudgeReport,
    created_by: Optional[str] = None,
    parent_artifact_ids: Optional[List[str]] = None,
    judge_version: Optional[str] = None
) -> JudgeArtifact:
    """Construct a judge artifact with metadata."""
    metadata = ArtifactMetadata(
        created_at=datetime.utcnow().isoformat() + "Z",
        created_by=created_by,
        parent_artifact_ids=parent_artifact_ids or [],
        version="1.0"
    )
    return JudgeArtifact(
        artifact_id=artifact_id,
        artifact_type="judge",
        graph_id=graph_id,
        metadata=metadata,
        report=report,
        judge_version=judge_version
    )


def create_bundle_artifact(
    artifact_id: str,
    target_graph: FeatureGraph,
    dependency_graphs: Optional[List[FeatureGraph]] = None,
    dependency_reasons: Optional[Dict[str, str]] = None,
    created_by: Optional[str] = None,
    parent_artifact_ids: Optional[List[str]] = None,
    bundle_purpose: Optional[str] = None
) -> BundleArtifact:
    """Construct a bundle artifact with metadata."""
    metadata = ArtifactMetadata(
        created_at=datetime.utcnow().isoformat() + "Z",
        created_by=created_by,
        parent_artifact_ids=parent_artifact_ids or [],
        version="1.0"
    )
    return BundleArtifact(
        artifact_id=artifact_id,
        artifact_type="bundle",
        metadata=metadata,
        target_graph_id=target_graph.graph_id,
        target_graph=target_graph,
        dependency_graphs=dependency_graphs or [],
        dependency_reasons=dependency_reasons or {},
        bundle_purpose=bundle_purpose
    )
