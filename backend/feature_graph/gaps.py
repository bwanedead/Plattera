"""
Feature Graph Gap Types and Judge Report Models
================================================

Models for typed gaps detected during feature graph compilation and validation.
These gaps represent deterministic failures (missing anchors, parameters, etc)
that prevent full compilation.

Design principles:
- Gaps are deterministic and carry citations
- No silent failure: every compilation issue produces a typed gap
- Gaps can be serialized into backend/domains/common/contracts.py Gap/CompileReport shape
- Gap types cover all known failure modes: missing data, unsupported ops, precondition failures
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum

from .provenance import Citation


class GapKind(str, Enum):
    """
    Enumeration of all gap types that can occur during feature graph compilation.

    Each gap kind represents a specific, deterministic failure mode.
    """
    MISSING_ANCHOR = "missing_anchor"              # Feature missing global frame reference
    MISSING_OPERAND = "missing_operand"            # Operation missing required operand(s)
    MISSING_PARAMETER = "missing_parameter"        # Operation missing required parameter value
    AMBIGUOUS_CHOICE = "ambiguous_choice"          # Multiple valid interpretations, need disambiguation
    UNSUPPORTED_OPERATION = "unsupported_operation" # Operation not yet implemented in compiler
    PRECONDITION_FAILED = "precondition_failed"    # Prerequisites not met (e.g., unclosed curve)


class FeatureGap(BaseModel):
    """
    Typed gap record produced by the feature graph compiler or judge.

    A gap represents a deterministic failure during compilation that prevents
    producing a complete output. Every gap includes:
    - kind: the specific failure type
    - message: human-readable description
    - feature_id: the feature node/edge where gap occurred
    - citations: provenance links to source evidence
    - metadata: structured details about the failure
    """
    kind: GapKind = Field(..., description="Type of gap (missing anchor, parameter, etc)")
    message: str = Field(..., description="Human-readable description of the gap")
    feature_id: Optional[str] = Field(None, description="ID of feature node/edge where gap occurred")
    severity: str = Field("error", description="Severity: error, warning, info")

    # Provenance
    citations: List[Citation] = Field(default_factory=list, description="Source evidence citations for this gap")

    # Structured metadata for programmatic handling
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Structured details (param name, operation, etc)")

    class Config:
        frozen = False

    def to_contract_gap(self) -> Dict[str, Any]:
        """
        Convert this FeatureGap to the shape expected by backend/domains/common/contracts.py Gap.

        Returns a dict with keys: kind, message, severity, metadata
        This allows feature graph gaps to interoperate with existing agent contract types.
        """
        return {
            "kind": self.kind.value,
            "message": self.message,
            "severity": self.severity,
            "metadata": {
                **self.metadata,
                "feature_id": self.feature_id,
                "citations_count": len(self.citations)
            }
        }


class JudgeReport(BaseModel):
    """
    Report produced by the feature graph judge after validation/compilation.

    A judge report contains:
    - gaps: all typed gaps discovered during compilation
    - warnings: non-fatal issues that don't prevent compilation
    - artifacts: any partial compilation outputs (local geometry, etc)
    - metadata: compilation context (graph_id, timestamp, etc)

    The report can be serialized into backend/domains/common/contracts.py CompileReport shape.
    """
    graph_id: str = Field(..., description="ID of feature graph that was judged")
    gaps: List[FeatureGap] = Field(default_factory=list, description="All typed gaps discovered")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings")
    artifacts: Dict[str, Any] = Field(default_factory=dict, description="Partial outputs or metadata")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Judge context (timestamp, compiler version, etc)")

    class Config:
        frozen = False

    def to_contract_report(self) -> Dict[str, Any]:
        """
        Convert this JudgeReport to the shape expected by backend/domains/common/contracts.py CompileReport.

        Returns a dict with keys: status, diagnostics, warnings, errors, artifacts
        Status determination:
        - SUCCESS: no gaps or errors
        - PARTIAL: has gaps but also has some artifacts
        - FAILED: has gaps and no artifacts
        """
        # Determine status based on gaps and artifacts
        has_errors = any(gap.severity == "error" for gap in self.gaps)
        has_artifacts = bool(self.artifacts)

        if not has_errors and not self.gaps:
            status = "success"
        elif has_errors and not has_artifacts:
            status = "failed"
        elif has_errors and has_artifacts:
            status = "partial"
        else:
            status = "success"  # Only warnings, no errors

        # Convert gaps to diagnostic entries
        diagnostics = [gap.to_contract_gap() for gap in self.gaps]

        # Extract error messages from error-level gaps
        errors = [gap.message for gap in self.gaps if gap.severity == "error"]

        return {
            "status": status,
            "diagnostics": diagnostics,
            "warnings": self.warnings,
            "errors": errors,
            "artifacts": self.artifacts
        }

    @property
    def has_errors(self) -> bool:
        """Returns True if any gap has severity='error'."""
        return any(gap.severity == "error" for gap in self.gaps)

    @property
    def error_count(self) -> int:
        """Returns count of error-level gaps."""
        return sum(1 for gap in self.gaps if gap.severity == "error")

    @property
    def warning_count(self) -> int:
        """Returns count of warning-level gaps plus warnings list."""
        gap_warnings = sum(1 for gap in self.gaps if gap.severity == "warning")
        return gap_warnings + len(self.warnings)


# Gap constructor helpers for common scenarios

def missing_anchor_gap(
    feature_id: str,
    message: str,
    citations: Optional[List[Citation]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> FeatureGap:
    """Construct a MissingAnchor gap."""
    return FeatureGap(
        kind=GapKind.MISSING_ANCHOR,
        message=message,
        feature_id=feature_id,
        severity="error",
        citations=citations or [],
        metadata=metadata or {}
    )


def missing_operand_gap(
    feature_id: str,
    operation: str,
    missing_operand: str,
    citations: Optional[List[Citation]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> FeatureGap:
    """Construct a MissingOperand gap."""
    meta = metadata or {}
    meta.update({"operation": operation, "missing_operand": missing_operand})
    return FeatureGap(
        kind=GapKind.MISSING_OPERAND,
        message=f"Operation '{operation}' missing required operand '{missing_operand}'",
        feature_id=feature_id,
        severity="error",
        citations=citations or [],
        metadata=meta
    )


def missing_parameter_gap(
    feature_id: str,
    operation: str,
    parameter_name: str,
    citations: Optional[List[Citation]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> FeatureGap:
    """Construct a MissingParameter gap."""
    meta = metadata or {}
    meta.update({"operation": operation, "parameter_name": parameter_name})
    return FeatureGap(
        kind=GapKind.MISSING_PARAMETER,
        message=f"Operation '{operation}' missing required parameter '{parameter_name}'",
        feature_id=feature_id,
        severity="error",
        citations=citations or [],
        metadata=meta
    )


def ambiguous_choice_gap(
    feature_id: str,
    message: str,
    choices: List[str],
    citations: Optional[List[Citation]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> FeatureGap:
    """Construct an AmbiguousChoice gap."""
    meta = metadata or {}
    meta.update({"choices": choices})
    return FeatureGap(
        kind=GapKind.AMBIGUOUS_CHOICE,
        message=message,
        feature_id=feature_id,
        severity="error",
        citations=citations or [],
        metadata=meta
    )


def unsupported_operation_gap(
    feature_id: str,
    operation: str,
    reason: str,
    citations: Optional[List[Citation]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> FeatureGap:
    """Construct an UnsupportedOperation gap."""
    meta = metadata or {}
    meta.update({"operation": operation, "reason": reason})
    return FeatureGap(
        kind=GapKind.UNSUPPORTED_OPERATION,
        message=f"Operation '{operation}' is not supported: {reason}",
        feature_id=feature_id,
        severity="error",
        citations=citations or [],
        metadata=meta
    )


def precondition_failed_gap(
    feature_id: str,
    operation: str,
    precondition: str,
    reason: str,
    citations: Optional[List[Citation]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> FeatureGap:
    """Construct a PreconditionFailed gap."""
    meta = metadata or {}
    meta.update({"operation": operation, "precondition": precondition, "reason": reason})
    return FeatureGap(
        kind=GapKind.PRECONDITION_FAILED,
        message=f"Operation '{operation}' precondition failed: {precondition} - {reason}",
        feature_id=feature_id,
        severity="error",
        citations=citations or [],
        metadata=meta
    )

