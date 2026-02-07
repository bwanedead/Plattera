"""
Feature Graph IR Module
=======================

Universal intermediate representation for deed meaning substrate.
Provides models for representing, compiling, and validating deed assertions
with deterministic outcomes and provenance tracking.
"""

from .models import (
    FeatureKind,
    FeatureNode,
    FeatureEdge,
    FeatureRef,
    OpExpr,
    Literal,
    FeatureGraph,
)

from .provenance import (
    TextSpan,
    EvidenceRef,
    Citation,
    ProvenanceAttachment,
)

from .artifacts import (
    ArtifactMetadata,
    IRArtifact,
    CompileArtifact,
    JudgeArtifact,
    BundleArtifact,
    create_ir_artifact,
    create_compile_artifact,
    create_judge_artifact,
    create_bundle_artifact,
)

from .compiler import (
    compile_graph,
    CompileResult,
)

__all__ = [
    "FeatureKind",
    "FeatureNode",
    "FeatureEdge",
    "FeatureRef",
    "OpExpr",
    "Literal",
    "FeatureGraph",
    "TextSpan",
    "EvidenceRef",
    "Citation",
    "ProvenanceAttachment",
    "ArtifactMetadata",
    "IRArtifact",
    "CompileArtifact",
    "JudgeArtifact",
    "BundleArtifact",
    "create_ir_artifact",
    "create_compile_artifact",
    "create_judge_artifact",
    "create_bundle_artifact",
    "compile_graph",
    "CompileResult",
]
