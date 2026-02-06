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
]
