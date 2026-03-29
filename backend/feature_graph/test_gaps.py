"""
Tests for Feature Graph Gap Types and Judge Report Models
==========================================================

Validates that gap types and judge reports:
- Cover all required gap kinds
- Serialize correctly to JSON
- Convert to backend/domains/common/contracts.py Gap/CompileReport shape
- Carry citations and provenance
- Provide deterministic, typed failure information
"""

import pytest
import json
from typing import Dict, Any

from .gaps import (
    GapKind,
    FeatureGap,
    JudgeReport,
    missing_anchor_gap,
    missing_operand_gap,
    missing_parameter_gap,
    ambiguous_choice_gap,
    unsupported_operation_gap,
    precondition_failed_gap
)
from .provenance import Citation, TextSpan, EvidenceRef


def test_gap_kinds_coverage():
    """Verify all required gap kinds are defined."""
    required_kinds = {
        "missing_anchor",
        "missing_operand",
        "missing_parameter",
        "ambiguous_choice",
        "unsupported_operation",
        "precondition_failed"
    }
    actual_kinds = {kind.value for kind in GapKind}
    assert required_kinds == actual_kinds, f"Gap kinds mismatch: expected {required_kinds}, got {actual_kinds}"


def test_feature_gap_json_serialization():
    """Verify FeatureGap serializes to JSON and round-trips correctly."""
    gap = FeatureGap(
        kind=GapKind.MISSING_PARAMETER,
        message="Operation 'LineStep' missing required parameter 'distance'",
        feature_id="node_123",
        severity="error",
        citations=[],
        metadata={"operation": "LineStep", "parameter_name": "distance"}
    )

    # Serialize to JSON
    gap_json = gap.model_dump_json()
    gap_dict = json.loads(gap_json)

    # Validate structure
    assert gap_dict["kind"] == "missing_parameter"
    assert gap_dict["message"] == "Operation 'LineStep' missing required parameter 'distance'"
    assert gap_dict["feature_id"] == "node_123"
    assert gap_dict["severity"] == "error"
    assert gap_dict["metadata"]["operation"] == "LineStep"
    assert gap_dict["metadata"]["parameter_name"] == "distance"

    # Round-trip
    gap_restored = FeatureGap.model_validate(gap_dict)
    assert gap_restored.kind == gap.kind
    assert gap_restored.message == gap.message
    assert gap_restored.feature_id == gap.feature_id
    assert gap_restored.metadata == gap.metadata


def test_feature_gap_with_citations():
    """Verify FeatureGap preserves citations correctly."""
    citation = Citation(
        text_span=TextSpan(
            document_id="deed_abc",
            start_offset=100,
            end_offset=150,
            text_snippet="thence northerly 100 feet"
        ),
        evidence_refs=[
            EvidenceRef(
                corpus_doc_id="doc_123",
                chunk_id="chunk_5",
                evidence_type="textual",
                relevance_note="Contains bearing/distance info"
            )
        ],
        citation_type="direct"
    )

    gap = FeatureGap(
        kind=GapKind.MISSING_ANCHOR,
        message="Feature missing global frame reference",
        feature_id="node_456",
        severity="error",
        citations=[citation],
        metadata={"frame_type": "PLSS"}
    )

    # Serialize and round-trip
    gap_json = gap.model_dump_json()
    gap_dict = json.loads(gap_json)

    assert len(gap_dict["citations"]) == 1
    assert gap_dict["citations"][0]["text_span"]["document_id"] == "deed_abc"
    assert gap_dict["citations"][0]["evidence_refs"][0]["corpus_doc_id"] == "doc_123"

    gap_restored = FeatureGap.model_validate(gap_dict)
    assert len(gap_restored.citations) == 1
    assert gap_restored.citations[0].text_span.document_id == "deed_abc"


def test_feature_gap_to_contract_gap():
    """Verify FeatureGap converts to backend/domains/common/contracts.py Gap shape."""
    gap = FeatureGap(
        kind=GapKind.UNSUPPORTED_OPERATION,
        message="Operation 'Buffer' is not supported: not yet implemented",
        feature_id="node_789",
        severity="error",
        citations=[],
        metadata={"operation": "Buffer", "reason": "not yet implemented"}
    )

    contract_gap = gap.to_contract_gap()

    # Validate contract shape
    assert isinstance(contract_gap, dict)
    assert contract_gap["kind"] == "unsupported_operation"
    assert contract_gap["message"] == "Operation 'Buffer' is not supported: not yet implemented"
    assert contract_gap["severity"] == "error"
    assert "metadata" in contract_gap
    assert contract_gap["metadata"]["feature_id"] == "node_789"
    assert contract_gap["metadata"]["operation"] == "Buffer"
    assert contract_gap["metadata"]["citations_count"] == 0


def test_judge_report_json_serialization():
    """Verify JudgeReport serializes to JSON and round-trips correctly."""
    report = JudgeReport(
        graph_id="graph_abc",
        gaps=[
            FeatureGap(
                kind=GapKind.MISSING_PARAMETER,
                message="Missing distance",
                feature_id="node_1",
                severity="error",
                citations=[],
                metadata={"parameter_name": "distance"}
            )
        ],
        warnings=["Bearing format is non-standard"],
        artifacts={"local_geometry": {"type": "polyline", "points": [[0, 0], [100, 0]]}},
        metadata={"compiler_version": "0.1.0", "timestamp": "2026-02-06T12:00:00Z"}
    )

    # Serialize to JSON
    report_json = report.model_dump_json()
    report_dict = json.loads(report_json)

    # Validate structure
    assert report_dict["graph_id"] == "graph_abc"
    assert len(report_dict["gaps"]) == 1
    assert report_dict["gaps"][0]["kind"] == "missing_parameter"
    assert len(report_dict["warnings"]) == 1
    assert "local_geometry" in report_dict["artifacts"]
    assert report_dict["metadata"]["compiler_version"] == "0.1.0"

    # Round-trip
    report_restored = JudgeReport.model_validate(report_dict)
    assert report_restored.graph_id == report.graph_id
    assert len(report_restored.gaps) == 1
    assert report_restored.gaps[0].kind == GapKind.MISSING_PARAMETER


def test_judge_report_to_contract_report_success():
    """Verify JudgeReport converts to CompileReport with status=success when no errors."""
    report = JudgeReport(
        graph_id="graph_success",
        gaps=[],
        warnings=["Minor formatting issue"],
        artifacts={"output": "some_data"},
        metadata={}
    )

    contract_report = report.to_contract_report()

    assert contract_report["status"] == "success"
    assert len(contract_report["diagnostics"]) == 0
    assert len(contract_report["warnings"]) == 1
    assert len(contract_report["errors"]) == 0
    assert "output" in contract_report["artifacts"]


def test_judge_report_to_contract_report_partial():
    """Verify JudgeReport converts to CompileReport with status=partial when errors + artifacts."""
    report = JudgeReport(
        graph_id="graph_partial",
        gaps=[
            FeatureGap(
                kind=GapKind.MISSING_ANCHOR,
                message="Missing frame reference",
                feature_id="node_1",
                severity="error",
                citations=[],
                metadata={}
            )
        ],
        warnings=[],
        artifacts={"local_geometry": "partial_output"},
        metadata={}
    )

    contract_report = report.to_contract_report()

    assert contract_report["status"] == "partial"
    assert len(contract_report["diagnostics"]) == 1
    assert len(contract_report["errors"]) == 1
    assert contract_report["errors"][0] == "Missing frame reference"
    assert "local_geometry" in contract_report["artifacts"]


def test_judge_report_to_contract_report_failed():
    """Verify JudgeReport converts to CompileReport with status=failed when errors + no artifacts."""
    report = JudgeReport(
        graph_id="graph_failed",
        gaps=[
            FeatureGap(
                kind=GapKind.PRECONDITION_FAILED,
                message="Curve is not closed",
                feature_id="node_2",
                severity="error",
                citations=[],
                metadata={"precondition": "closed_curve"}
            )
        ],
        warnings=[],
        artifacts={},
        metadata={}
    )

    contract_report = report.to_contract_report()

    assert contract_report["status"] == "failed"
    assert len(contract_report["diagnostics"]) == 1
    assert len(contract_report["errors"]) == 1
    assert contract_report["errors"][0] == "Curve is not closed"
    assert contract_report["artifacts"] == {}


def test_judge_report_properties():
    """Verify JudgeReport convenience properties (has_errors, error_count, warning_count)."""
    report = JudgeReport(
        graph_id="graph_props",
        gaps=[
            FeatureGap(
                kind=GapKind.MISSING_PARAMETER,
                message="Missing param",
                feature_id="node_1",
                severity="error",
                citations=[],
                metadata={}
            ),
            FeatureGap(
                kind=GapKind.AMBIGUOUS_CHOICE,
                message="Ambiguous ref",
                feature_id="node_2",
                severity="warning",
                citations=[],
                metadata={}
            )
        ],
        warnings=["Extra warning"],
        artifacts={},
        metadata={}
    )

    assert report.has_errors is True
    assert report.error_count == 1
    assert report.warning_count == 2  # 1 gap warning + 1 warnings list entry


def test_gap_constructor_helpers():
    """Verify gap constructor helper functions produce correct gap types."""
    # MissingAnchor
    gap1 = missing_anchor_gap("node_1", "Frame not found")
    assert gap1.kind == GapKind.MISSING_ANCHOR
    assert gap1.message == "Frame not found"
    assert gap1.feature_id == "node_1"

    # MissingOperand
    gap2 = missing_operand_gap("node_2", "Union", "operand_B")
    assert gap2.kind == GapKind.MISSING_OPERAND
    assert gap2.metadata["operation"] == "Union"
    assert gap2.metadata["missing_operand"] == "operand_B"

    # MissingParameter
    gap3 = missing_parameter_gap("node_3", "LineStep", "bearing")
    assert gap3.kind == GapKind.MISSING_PARAMETER
    assert gap3.metadata["parameter_name"] == "bearing"

    # AmbiguousChoice
    gap4 = ambiguous_choice_gap("node_4", "Multiple parcels match", ["parcel_A", "parcel_B"])
    assert gap4.kind == GapKind.AMBIGUOUS_CHOICE
    assert gap4.metadata["choices"] == ["parcel_A", "parcel_B"]

    # UnsupportedOperation
    gap5 = unsupported_operation_gap("node_5", "CurveStep", "arc not implemented")
    assert gap5.kind == GapKind.UNSUPPORTED_OPERATION
    assert gap5.metadata["operation"] == "CurveStep"
    assert gap5.metadata["reason"] == "arc not implemented"

    # PreconditionFailed
    gap6 = precondition_failed_gap("node_6", "Close", "closed_curve", "curve endpoints do not match")
    assert gap6.kind == GapKind.PRECONDITION_FAILED
    assert gap6.metadata["operation"] == "Close"
    assert gap6.metadata["precondition"] == "closed_curve"
    assert gap6.metadata["reason"] == "curve endpoints do not match"


def test_complex_judge_report_with_multiple_gap_types():
    """Verify JudgeReport can handle multiple gap types and convert correctly."""
    citation1 = Citation(
        text_span=TextSpan(
            document_id="deed_123",
            start_offset=50,
            end_offset=100,
            text_snippet="beginning at the NE corner"
        ),
        evidence_refs=[],
        citation_type="direct"
    )

    citation2 = Citation(
        text_span=TextSpan(
            document_id="deed_123",
            start_offset=200,
            end_offset=250,
            text_snippet="thence N 45 E"
        ),
        evidence_refs=[],
        citation_type="direct"
    )

    report = JudgeReport(
        graph_id="graph_complex",
        gaps=[
            missing_anchor_gap("node_start", "Starting point not anchored to frame", citations=[citation1]),
            missing_parameter_gap("node_line1", "LineStep", "distance", citations=[citation2]),
            unsupported_operation_gap("node_curve1", "CurveStep", "arcs not implemented"),
            precondition_failed_gap("node_close", "Close", "closed_curve", "endpoints do not match")
        ],
        warnings=["Non-standard bearing format detected"],
        artifacts={"partial_polyline": [[0, 0], [100, 100]]},
        metadata={"compiler_version": "0.1.0"}
    )

    # Validate internal structure
    assert len(report.gaps) == 4
    assert report.has_errors is True
    assert report.error_count == 4
    assert report.warning_count == 1

    # Serialize to JSON
    report_json = report.model_dump_json()
    report_dict = json.loads(report_json)
    assert len(report_dict["gaps"]) == 4

    # Convert to contract shape
    contract_report = report.to_contract_report()
    assert contract_report["status"] == "partial"  # Has errors but also has artifacts
    assert len(contract_report["diagnostics"]) == 4
    assert len(contract_report["errors"]) == 4
    assert len(contract_report["warnings"]) == 1

    # Verify each diagnostic retains gap details
    diag_kinds = [d["kind"] for d in contract_report["diagnostics"]]
    assert "missing_anchor" in diag_kinds
    assert "missing_parameter" in diag_kinds
    assert "unsupported_operation" in diag_kinds
    assert "precondition_failed" in diag_kinds

    # Verify citations were preserved
    assert report.gaps[0].citations[0].text_span.text_snippet == "beginning at the NE corner"
    assert report.gaps[1].citations[0].text_span.text_snippet == "thence N 45 E"


def test_empty_judge_report():
    """Verify empty JudgeReport (no gaps, no warnings) serializes correctly."""
    report = JudgeReport(
        graph_id="graph_empty",
        gaps=[],
        warnings=[],
        artifacts={},
        metadata={}
    )

    # Serialize
    report_json = report.model_dump_json()
    report_dict = json.loads(report_json)

    assert report_dict["graph_id"] == "graph_empty"
    assert report_dict["gaps"] == []
    assert report_dict["warnings"] == []

    # Convert to contract
    contract_report = report.to_contract_report()
    assert contract_report["status"] == "success"
    assert contract_report["diagnostics"] == []
    assert contract_report["warnings"] == []
    assert contract_report["errors"] == []

    # Properties
    assert report.has_errors is False
    assert report.error_count == 0
    assert report.warning_count == 0

