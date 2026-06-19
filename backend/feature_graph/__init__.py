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
    SourceEntityLink,
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

from .judge import (
    judge_graph,
)

from .gaps import (
    JudgeReport,
    FeatureGap,
    GapKind,
)

from .bundle import (
    bundle_feature_graph,
    BundleOperation,
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
    "SourceEntityLink",
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
    "judge_graph",
    "JudgeReport",
    "FeatureGap",
    "GapKind",
    "bundle_feature_graph",
    "BundleOperation",
]
