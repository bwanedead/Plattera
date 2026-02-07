"""
Tests for Feature Graph Compiler - Derive Operations
=====================================================

Tests for derive operations: Close and Buffer.
Validates that Close produces regions only when curves are properly closed,
and that Buffer emits UnsupportedOperation gaps with structured params.
"""

import pytest

from backend.feature_graph.compiler import (
    compile_graph,
    CompileResult
)
from backend.feature_graph.models import (
    FeatureGraph,
    FeatureNode,
    FeatureKind,
    OpExpr
)
from backend.feature_graph.gaps import GapKind


# ============================================================================
# CLOSE OPERATION TESTS
# ============================================================================

def test_close_on_closed_curve_produces_polygon():
    """
    Test that Close on a properly closed curve produces a polygon region.
    A curve is considered closed when its endpoints meet within tolerance.
    """
    # Create a simple square traverse (4 line segments forming a closed loop)
    graph = FeatureGraph(
        nodes=[
            # Segment 1: origin -> (100, 0)
            FeatureNode(
                id="seg1",
                kind=FeatureKind.LINE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 90, "distance": 100}
                )
            ),
            # Segment 2: (100, 0) -> (100, 100)
            FeatureNode(
                id="seg2",
                kind=FeatureKind.LINE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 0, "distance": 100}
                )
            ),
            # Segment 3: (100, 100) -> (0, 100)
            FeatureNode(
                id="seg3",
                kind=FeatureKind.LINE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 270, "distance": 100}
                )
            ),
            # Segment 4: (0, 100) -> (0, 0) [back to origin]
            FeatureNode(
                id="seg4",
                kind=FeatureKind.LINE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 180, "distance": 100}
                )
            ),
            # Create a closed curve from all segments (using direct geometry)
            FeatureNode(
                id="closed_curve",
                kind=FeatureKind.CURVE,
                geometry={
                    "type": "LineString",
                    "coordinates": [
                        [0, 0],
                        [100, 0],
                        [100, 100],
                        [0, 100],
                        [0, 0]  # Closed: first == last
                    ]
                }
            ),
            # Close operation on the curve
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(
                    op_name="Close",
                    operands=["closed_curve"]
                )
            )
        ],
        edges=[]
    )

    result = compile_graph(graph)

    # Should compile successfully with no gaps
    assert len(result.gaps) == 0, f"Expected no gaps, got: {[g.dict() for g in result.gaps]}"

    # Should have compiled the region
    assert "region" in result.compiled_features
    region_data = result.compiled_features["region"]

    # Should be a polygon
    assert region_data["geometry"]["type"] == "Polygon"
    assert region_data["is_closed"] is True
    assert region_data["source_curve_id"] == "closed_curve"

    # Polygon coordinates should form a closed ring
    ring = region_data["geometry"]["coordinates"][0]
    assert len(ring) == 5  # 4 corners + closing point
    assert ring[0] == ring[-1]  # First == last


def test_close_on_open_curve_emits_precondition_failed():
    """
    Test that Close on an open curve (endpoints don't meet) emits PreconditionFailed gap.
    """
    # Create an open curve (line that doesn't close)
    graph = FeatureGraph(
        nodes=[
            FeatureNode(
                id="open_curve",
                kind=FeatureKind.CURVE,
                geometry={
                    "type": "LineString",
                    "coordinates": [
                        [0, 0],
                        [100, 0],
                        [100, 100]
                        # Not closed: ends at (100, 100), starts at (0, 0)
                    ]
                }
            ),
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(
                    op_name="Close",
                    operands=["open_curve"]
                )
            )
        ],
        edges=[]
    )

    result = compile_graph(graph)

    # Should have exactly one PreconditionFailed gap
    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.kind == GapKind.PRECONDITION_FAILED
    assert gap.feature_id == "region"
    assert gap.operation == "Close"
    assert "curve endpoints must meet" in gap.precondition
    assert "does not match" in gap.reason

    # Should have metadata with start/end points and distance
    assert "start_point" in gap.metadata
    assert "end_point" in gap.metadata
    assert "distance" in gap.metadata
    assert gap.metadata["start_point"] == [0, 0]
    assert gap.metadata["end_point"] == [100, 100]

    # Region should not be compiled
    assert "region" not in result.compiled_features


def test_close_with_missing_operand_emits_gap():
    """
    Test that Close with no operand emits MissingParameter gap.
    """
    graph = FeatureGraph(
        nodes=[
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(
                    op_name="Close",
                    operands=[]  # Missing operand
                )
            )
        ],
        edges=[]
    )

    result = compile_graph(graph)

    # Should have a gap for missing operand
    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.kind == GapKind.MISSING_PARAMETER
    assert gap.feature_id == "region"
    assert gap.operation == "Close"
    assert gap.parameter_name == "operand"
    assert "exactly one curve operand" in gap.metadata["reason"]


def test_close_with_uncompiled_operand_emits_precondition_failed():
    """
    Test that Close referencing an uncompiled/missing feature emits PreconditionFailed gap.
    """
    graph = FeatureGraph(
        nodes=[
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(
                    op_name="Close",
                    operands=["missing_curve"]  # References non-existent feature
                )
            )
        ],
        edges=[]
    )

    result = compile_graph(graph)

    # Should have a PreconditionFailed gap
    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.kind == GapKind.PRECONDITION_FAILED
    assert gap.feature_id == "region"
    assert gap.operation == "Close"
    assert "must be compiled first" in gap.precondition
    assert "not found in compiled features" in gap.reason


def test_close_on_non_curve_emits_precondition_failed():
    """
    Test that Close on a non-curve geometry emits PreconditionFailed gap.
    """
    graph = FeatureGraph(
        nodes=[
            # Point geometry (not a curve)
            FeatureNode(
                id="point",
                kind=FeatureKind.POINT,
                geometry={
                    "type": "Point",
                    "coordinates": [100, 200]
                }
            ),
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(
                    op_name="Close",
                    operands=["point"]
                )
            )
        ],
        edges=[]
    )

    result = compile_graph(graph)

    # Should have a PreconditionFailed gap
    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.kind == GapKind.PRECONDITION_FAILED
    assert gap.feature_id == "region"
    assert gap.operation == "Close"
    assert "must be a curve" in gap.precondition
    assert "Point" in gap.reason


def test_close_on_curve_with_insufficient_points_emits_precondition_failed():
    """
    Test that Close on a curve with fewer than 2 points emits PreconditionFailed gap.
    """
    graph = FeatureGraph(
        nodes=[
            FeatureNode(
                id="degenerate_curve",
                kind=FeatureKind.CURVE,
                geometry={
                    "type": "LineString",
                    "coordinates": [[0, 0]]  # Only one point
                }
            ),
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(
                    op_name="Close",
                    operands=["degenerate_curve"]
                )
            )
        ],
        edges=[]
    )

    result = compile_graph(graph)

    # Should have a PreconditionFailed gap
    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.kind == GapKind.PRECONDITION_FAILED
    assert gap.feature_id == "region"
    assert gap.operation == "Close"
    assert "at least 2 points" in gap.precondition
    assert "1 points" in gap.reason


# ============================================================================
# BUFFER OPERATION TESTS
# ============================================================================

def test_buffer_emits_unsupported_operation():
    """
    Test that Buffer operation emits UnsupportedOperation gap with structured params.
    Buffer is registered in the operations registry but not yet implemented in compiler.
    """
    graph = FeatureGraph(
        nodes=[
            # A simple line feature
            FeatureNode(
                id="line",
                kind=FeatureKind.LINE,
                geometry={
                    "type": "LineString",
                    "coordinates": [[0, 0], [100, 0]]
                }
            ),
            # Buffer operation (not supported)
            FeatureNode(
                id="buffered",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(
                    op_name="Buffer",
                    params={
                        "distance": 50,
                        "side": "both"
                    },
                    operands=["line"]
                )
            )
        ],
        edges=[]
    )

    result = compile_graph(graph)

    # Should have exactly one UnsupportedOperation gap
    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.kind == GapKind.UNSUPPORTED_OPERATION
    assert gap.feature_id == "buffered"
    assert gap.operation == "Buffer"
    assert "Not yet implemented" in gap.reason or "Stubbed" in gap.reason

    # Should preserve params in metadata
    assert "params" in gap.metadata
    assert gap.metadata["params"]["distance"] == 50
    assert gap.metadata["params"]["side"] == "both"

    # Should preserve operands in metadata
    assert "operands" in gap.metadata
    assert gap.metadata["operands"] == ["line"]

    # Buffered feature should not be compiled
    assert "buffered" not in result.compiled_features


def test_buffer_with_minimal_params_emits_unsupported_operation():
    """
    Test that Buffer with only required params (distance) emits UnsupportedOperation.
    """
    graph = FeatureGraph(
        nodes=[
            FeatureNode(
                id="point",
                kind=FeatureKind.POINT,
                geometry={
                    "type": "Point",
                    "coordinates": [50, 50]
                }
            ),
            FeatureNode(
                id="buffered",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(
                    op_name="Buffer",
                    params={"distance": 25},  # Only required param
                    operands=["point"]
                )
            )
        ],
        edges=[]
    )

    result = compile_graph(graph)

    # Should have UnsupportedOperation gap
    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.kind == GapKind.UNSUPPORTED_OPERATION
    assert gap.feature_id == "buffered"
    assert gap.operation == "Buffer"
    assert gap.metadata["params"]["distance"] == 25


def test_buffer_on_region_emits_unsupported_operation():
    """
    Test that Buffer can be applied to regions (not just lines/points) and emits UnsupportedOperation.
    """
    graph = FeatureGraph(
        nodes=[
            FeatureNode(
                id="polygon",
                kind=FeatureKind.REGION,
                geometry={
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]
                }
            ),
            FeatureNode(
                id="expanded",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(
                    op_name="Buffer",
                    params={"distance": 5, "side": "both"},
                    operands=["polygon"]
                )
            )
        ],
        edges=[]
    )

    result = compile_graph(graph)

    # Should have UnsupportedOperation gap
    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.kind == GapKind.UNSUPPORTED_OPERATION
    assert gap.feature_id == "expanded"
    assert gap.operation == "Buffer"


# ============================================================================
# MIXED SCENARIOS
# ============================================================================

def test_close_succeeds_and_buffer_fails_in_same_graph():
    """
    Test that a graph with both Close (supported) and Buffer (unsupported) operations
    produces correct results: Close succeeds, Buffer emits gap.
    """
    graph = FeatureGraph(
        nodes=[
            # Closed curve
            FeatureNode(
                id="closed_curve",
                kind=FeatureKind.CURVE,
                geometry={
                    "type": "LineString",
                    "coordinates": [[0, 0], [50, 0], [50, 50], [0, 50], [0, 0]]
                }
            ),
            # Close operation (should succeed)
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(
                    op_name="Close",
                    operands=["closed_curve"]
                )
            ),
            # Buffer operation on the region (should fail with unsupported)
            FeatureNode(
                id="buffered_region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(
                    op_name="Buffer",
                    params={"distance": 10},
                    operands=["region"]
                )
            )
        ],
        edges=[]
    )

    result = compile_graph(graph)

    # Should have exactly one gap (for Buffer)
    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.kind == GapKind.UNSUPPORTED_OPERATION
    assert gap.feature_id == "buffered_region"
    assert gap.operation == "Buffer"

    # Close should have succeeded
    assert "region" in result.compiled_features
    region_data = result.compiled_features["region"]
    assert region_data["geometry"]["type"] == "Polygon"
    assert region_data["is_closed"] is True

    # Buffer should not have compiled
    assert "buffered_region" not in result.compiled_features


def test_close_with_near_closed_curve_within_tolerance():
    """
    Test that Close succeeds when curve endpoints are within tolerance (0.01 feet).
    """
    graph = FeatureGraph(
        nodes=[
            FeatureNode(
                id="nearly_closed_curve",
                kind=FeatureKind.CURVE,
                geometry={
                    "type": "LineString",
                    "coordinates": [
                        [0, 0],
                        [100, 0],
                        [100, 100],
                        [0, 100],
                        [0.005, 0.005]  # Very close to origin (within 0.01 tolerance)
                    ]
                }
            ),
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(
                    op_name="Close",
                    operands=["nearly_closed_curve"]
                )
            )
        ],
        edges=[]
    )

    result = compile_graph(graph)

    # Should succeed (no gaps)
    assert len(result.gaps) == 0

    # Should have compiled the region
    assert "region" in result.compiled_features
    region_data = result.compiled_features["region"]
    assert region_data["geometry"]["type"] == "Polygon"
    assert region_data["is_closed"] is True
