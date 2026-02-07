"""
Tests for Feature Graph Judge Engine
=====================================

Tests deterministic validation and gap detection.
"""

import pytest
from .models import (
    FeatureGraph,
    FeatureNode,
    FeatureKind,
    OpExpr,
    FeatureRef,
)
from .judge import (
    judge_graph,
    judge_missing_anchors,
    judge_missing_operands,
    judge_missing_parameters,
    judge_unsupported_operations,
)
from .gaps import GapKind
from .provenance import Citation


# ============================================================================
# TEST: JUDGE MISSING ANCHORS
# ============================================================================

def test_judge_missing_anchors_point_without_geometry():
    """Point without geometry should emit missing anchor gap."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(id="p1", kind=FeatureKind.POINT)
        ],
        edges=[]
    )

    gaps = []
    judge_missing_anchors(graph, gaps)

    assert len(gaps) == 1
    assert gaps[0].kind == GapKind.MISSING_ANCHOR
    assert gaps[0].feature_id == "p1"
    assert "lacks global frame reference" in gaps[0].message


def test_judge_missing_anchors_point_with_geometry():
    """Point with explicit geometry should not emit gap."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="p1",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [100.0, 200.0]}
            )
        ],
        edges=[]
    )

    gaps = []
    judge_missing_anchors(graph, gaps)

    assert len(gaps) == 0


def test_judge_missing_anchors_curve_without_anchor():
    """Curve without anchor should emit missing anchor gap."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="c1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(op_name="LineStep", params={"bearing": 45, "distance": 100})
            )
        ],
        edges=[]
    )

    gaps = []
    judge_missing_anchors(graph, gaps)

    assert len(gaps) == 1
    assert gaps[0].kind == GapKind.MISSING_ANCHOR
    assert gaps[0].feature_id == "c1"


def test_judge_missing_anchors_curve_anchored_to_frame():
    """Curve referencing a frame should not emit gap."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(id="frame1", kind=FeatureKind.FRAME),
            FeatureNode(
                id="c1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(op_name="LineStep", params={"bearing": 45, "distance": 100}, operands=["frame1"])
            )
        ],
        edges=[]
    )

    gaps = []
    judge_missing_anchors(graph, gaps)

    assert len(gaps) == 0


def test_judge_missing_anchors_region_without_anchor():
    """Region without anchor should emit missing anchor gap."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(id="r1", kind=FeatureKind.REGION)
        ],
        edges=[]
    )

    gaps = []
    judge_missing_anchors(graph, gaps)

    assert len(gaps) == 1
    assert gaps[0].kind == GapKind.MISSING_ANCHOR
    assert gaps[0].feature_id == "r1"


# ============================================================================
# TEST: JUDGE MISSING OPERANDS
# ============================================================================

def test_judge_missing_operands_valid_references():
    """Operations referencing valid features should not emit gaps."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(id="c1", kind=FeatureKind.CURVE),
            FeatureNode(
                id="r1",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Close", operands=["c1"])
            )
        ],
        edges=[]
    )

    gaps = []
    judge_missing_operands(graph, gaps)

    assert len(gaps) == 0


def test_judge_missing_operands_invalid_reference():
    """Operation referencing non-existent feature should emit gap."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="r1",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Close", operands=["c999"])
            )
        ],
        edges=[]
    )

    gaps = []
    judge_missing_operands(graph, gaps)

    assert len(gaps) == 1
    assert gaps[0].kind == GapKind.MISSING_OPERAND
    assert gaps[0].feature_id == "r1"
    assert gaps[0].metadata["missing_operand"] == "c999"
    assert "Close" in gaps[0].message


def test_judge_missing_operands_multiple_missing():
    """Operation with multiple missing operands should emit multiple gaps."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="r1",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Union", operands=["c1", "c2"])
            )
        ],
        edges=[]
    )

    gaps = []
    judge_missing_operands(graph, gaps)

    assert len(gaps) == 2
    missing_operands = {gap.metadata["missing_operand"] for gap in gaps}
    assert missing_operands == {"c1", "c2"}


def test_judge_missing_operands_nested_opexpr():
    """Nested OpExpr operands should not be validated as feature IDs."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="r1",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(
                    op_name="Close",
                    operands=[
                        OpExpr(op_name="LineStep", params={"bearing": 45, "distance": 100})
                    ]
                )
            )
        ],
        edges=[]
    )

    gaps = []
    judge_missing_operands(graph, gaps)

    # No gaps - nested OpExpr is not a feature ID reference
    assert len(gaps) == 0


# ============================================================================
# TEST: JUDGE MISSING PARAMETERS
# ============================================================================

def test_judge_missing_parameters_linestep_missing_bearing():
    """LineStep without bearing should emit gap."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="c1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(op_name="LineStep", params={"distance": 100})
            )
        ],
        edges=[]
    )

    gaps = []
    judge_missing_parameters(graph, gaps)

    assert len(gaps) == 1
    assert gaps[0].kind == GapKind.MISSING_PARAMETER
    assert gaps[0].feature_id == "c1"
    assert gaps[0].metadata["parameter_name"] == "bearing"
    assert gaps[0].metadata["operation"] == "LineStep"


def test_judge_missing_parameters_linestep_missing_distance():
    """LineStep without distance should emit gap."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="c1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(op_name="LineStep", params={"bearing": 45})
            )
        ],
        edges=[]
    )

    gaps = []
    judge_missing_parameters(graph, gaps)

    assert len(gaps) == 1
    assert gaps[0].kind == GapKind.MISSING_PARAMETER
    assert gaps[0].metadata["parameter_name"] == "distance"


def test_judge_missing_parameters_linestep_complete():
    """LineStep with all required params should not emit gaps."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="c1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(op_name="LineStep", params={"bearing": 45, "distance": 100})
            )
        ],
        edges=[]
    )

    gaps = []
    judge_missing_parameters(graph, gaps)

    assert len(gaps) == 0


def test_judge_missing_parameters_invalid_operand_count():
    """Operation with invalid operand count should emit precondition gap."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="r1",
                kind=FeatureKind.REGION,
                # Close requires exactly 1 operand
                op_expr=OpExpr(op_name="Close", operands=["c1", "c2"])
            )
        ],
        edges=[]
    )

    gaps = []
    judge_missing_parameters(graph, gaps)

    assert len(gaps) == 1
    assert gaps[0].kind == GapKind.PRECONDITION_FAILED
    assert gaps[0].feature_id == "r1"
    assert "operand count" in gaps[0].message.lower()


# ============================================================================
# TEST: JUDGE UNSUPPORTED OPERATIONS
# ============================================================================

def test_judge_unsupported_operations_not_in_registry():
    """Operation not in registry should emit unsupported gap."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="r1",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="MagicOperation", params={})
            )
        ],
        edges=[]
    )

    gaps = []
    judge_unsupported_operations(graph, gaps)

    assert len(gaps) == 1
    assert gaps[0].kind == GapKind.UNSUPPORTED_OPERATION
    assert gaps[0].feature_id == "r1"
    assert "not found in registry" in gaps[0].message


def test_judge_unsupported_operations_in_registry_but_not_supported():
    """Operation in registry but not supported should emit gap."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="r1",
                kind=FeatureKind.REGION,
                # Buffer is in registry but marked as not supported
                op_expr=OpExpr(op_name="Buffer", params={"distance": 10}, operands=["c1"])
            )
        ],
        edges=[]
    )

    gaps = []
    judge_unsupported_operations(graph, gaps)

    assert len(gaps) == 1
    assert gaps[0].kind == GapKind.UNSUPPORTED_OPERATION
    assert gaps[0].feature_id == "r1"
    assert "not yet implemented" in gaps[0].message.lower()


def test_judge_unsupported_operations_supported_operation():
    """Supported operations should not emit gaps."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="c1",
                kind=FeatureKind.CURVE,
                # LineStep is supported
                op_expr=OpExpr(op_name="LineStep", params={"bearing": 45, "distance": 100})
            )
        ],
        edges=[]
    )

    gaps = []
    judge_unsupported_operations(graph, gaps)

    assert len(gaps) == 0


# ============================================================================
# TEST: FULL JUDGE REPORT
# ============================================================================

def test_judge_graph_empty():
    """Empty graph should produce warning but no error gaps."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[],
        edges=[]
    )

    report = judge_graph(graph)

    assert report.graph_id == "test-graph"
    assert len(report.gaps) == 0
    assert len(report.warnings) == 1
    assert "no nodes" in report.warnings[0].lower()
    assert not report.has_errors


def test_judge_graph_disconnected_nodes():
    """Graph with nodes but no edges should produce warning."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(id="p1", kind=FeatureKind.POINT),
            FeatureNode(id="p2", kind=FeatureKind.POINT)
        ],
        edges=[]
    )

    report = judge_graph(graph)

    # Should have missing anchor gaps + disconnected warning
    assert len(report.gaps) == 2  # Both points missing anchors
    assert any("disconnected" in w.lower() for w in report.warnings)


def test_judge_graph_comprehensive_validation():
    """Graph with multiple issues should detect all gaps."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            # Missing anchor (point without geometry)
            FeatureNode(id="p1", kind=FeatureKind.POINT),
            # Missing operand
            FeatureNode(
                id="r1",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Close", operands=["c999"])
            ),
            # Missing parameter
            FeatureNode(
                id="c1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(op_name="LineStep", params={"bearing": 45})  # missing distance
            ),
            # Unsupported operation
            FeatureNode(
                id="c2",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(op_name="CurveStep", params={})  # not supported
            )
        ],
        edges=[]
    )

    report = judge_graph(graph)

    # Should have gaps for all issues
    assert report.has_errors
    assert report.error_count >= 4

    # Check gap kinds
    gap_kinds = {gap.kind for gap in report.gaps}
    assert GapKind.MISSING_ANCHOR in gap_kinds
    assert GapKind.MISSING_OPERAND in gap_kinds
    assert GapKind.MISSING_PARAMETER in gap_kinds
    assert GapKind.UNSUPPORTED_OPERATION in gap_kinds

    # Check metadata
    assert report.metadata["node_count"] == 4
    assert report.metadata["edge_count"] == 0
    assert report.metadata["gap_count"] >= 4


def test_judge_graph_valid_minimal():
    """Valid minimal graph should produce no error gaps."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            # Point with explicit geometry (anchored)
            FeatureNode(
                id="p1",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [0.0, 0.0]}
            )
        ],
        edges=[]
    )

    report = judge_graph(graph)

    assert not report.has_errors
    assert report.error_count == 0
    # May have warnings about missing edges, but no error gaps
    assert all(gap.severity != "error" for gap in report.gaps)


def test_judge_graph_with_citations():
    """Judge should preserve citations from provenance."""
    from .provenance import TextSpan

    citation = Citation(
        citation_type="direct",
        text_span=TextSpan(
            document_id="deed-123",
            start_offset=10,
            end_offset=50,
            text_snippet="sample text"
        ),
        evidence_refs=[]
    )

    from .provenance import ProvenanceAttachment
    provenance = ProvenanceAttachment(citations=[citation])

    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="p1",
                kind=FeatureKind.POINT,
                provenance=provenance
            )
        ],
        edges=[]
    )

    report = judge_graph(graph)

    # Should have missing anchor gap with citation
    assert len(report.gaps) > 0
    gap_with_citation = next((g for g in report.gaps if g.feature_id == "p1"), None)
    assert gap_with_citation is not None
    assert len(gap_with_citation.citations) == 1
    assert gap_with_citation.citations[0].text_span is not None
    assert gap_with_citation.citations[0].text_span.document_id == "deed-123"


def test_judge_report_to_contract():
    """JudgeReport should convert to contract format correctly."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(id="p1", kind=FeatureKind.POINT)
        ],
        edges=[]
    )

    report = judge_graph(graph)
    contract = report.to_contract_report()

    assert contract["status"] in ["success", "partial", "failed"]
    assert "diagnostics" in contract
    assert "warnings" in contract
    assert "errors" in contract
    assert "artifacts" in contract

    # Should have error diagnostics for missing anchor
    assert len(contract["diagnostics"]) > 0


def test_judge_report_metadata():
    """JudgeReport metadata should include counts."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(id="p1", kind=FeatureKind.POINT),
            FeatureNode(id="p2", kind=FeatureKind.POINT)
        ],
        edges=[]
    )

    report = judge_graph(graph)

    assert report.metadata["graph_id"] == "test-graph"
    assert report.metadata["node_count"] == 2
    assert report.metadata["edge_count"] == 0
    assert report.metadata["gap_count"] == report.metadata["error_count"]
    assert report.metadata["gap_count"] == 2  # Both points missing anchors


def test_judge_graph_without_warnings():
    """Judge with include_warnings=False should omit warnings."""
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[],
        edges=[]
    )

    report = judge_graph(graph, include_warnings=False)

    assert len(report.warnings) == 0
    # But gaps should still be present
    assert report.metadata["gap_count"] >= 0
