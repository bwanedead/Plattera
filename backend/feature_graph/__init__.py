"""
Feature Graph IR Module
=======================

Universal intermediate representation for deed meaning substrate.
Provides models for representing, compiling, and validating deed assertions
with deterministic outcomes and provenance tracking.
"""

from backend.feature_graph.models import (
    FeatureKind,
    FeatureNode,
    FeatureEdge,
    FeatureRef,
    OpExpr,
    Literal,
    FeatureGraph,
)

__all__ = [
    "FeatureKind",
    "FeatureNode",
    "FeatureEdge",
    "FeatureRef",
    "OpExpr",
    "Literal",
    "FeatureGraph",
]
