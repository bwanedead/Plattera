"""
Tests for Feature Graph Compiler - Traverse Operations
=======================================================

Tests for local traverse compilation, focusing on LineStep operations.
Validates that the compiler produces correct local geometry and handles
missing parameters gracefully with typed gaps.
"""

import pytest
import math

from backend.feature_graph.compiler import (
    compile_graph,
    compile_line_step,
    compile_node,
    CompileResult,
    bearing_to_radians,
    compute_endpoint,
    points_equal
)
from backend.feature_graph.models import (
    FeatureGraph,
    FeatureNode,
    FeatureKind,
    OpExpr
)
from backend.feature_graph.gaps import GapKind


# ============================================================================
# HELPER TESTS
# ============================================================================

def test_bearing_to_radians():
    """Test bearing angle conversion to radians."""
    # North (0 degrees) -> π/2 radians
    assert math.isclose(bearing_to_radians(0), math.pi / 2, abs_tol=1e-9)

    # East (90 degrees) -> 0 radians
    assert math.isclose(bearing_to_radians(90), 0, abs_tol=1e-9)

    # South (180 degrees) -> -π/2 radians
    assert math.isclose(bearing_to_radians(180), -math.pi / 2, abs_tol=1e-9)

    # West (270 degrees) -> -π radians (or equivalently π)
    # The formula gives -π, which is correct (west is π radians in standard math coords)
    assert math.isclose(bearing_to_radians(270), -math.pi, abs_tol=1e-9) or \
           math.isclose(bearing_to_radians(270), math.pi, abs_tol=1e-9)


def test_compute_endpoint():
    """Test endpoint computation from bearing and distance."""
    # From origin, bearing 0 (north), distance 100 -> (0, 100)
    x, y = compute_endpoint(0, 0, 0, 100)
    assert math.isclose(x, 0, abs_tol=1e-6)
    assert math.isclose(y, 100, abs_tol=1e-6)

    # From origin, bearing 90 (east), distance 100 -> (100, 0)
    x, y = compute_endpoint(0, 0, 90, 100)
    assert math.isclose(x, 100, abs_tol=1e-6)
    assert math.isclose(y, 0, abs_tol=1e-6)

    # From origin, bearing 180 (south), distance 100 -> (0, -100)
    x, y = compute_endpoint(0, 0, 180, 100)
    assert math.isclose(x, 0, abs_tol=1e-6)
    assert math.isclose(y, -100, abs_tol=1e-6)

    # From origin, bearing 270 (west), distance 100 -> (-100, 0)
    x, y = compute_endpoint(0, 0, 270, 100)
    assert math.isclose(x, -100, abs_tol=1e-6)
    assert math.isclose(y, 0, abs_tol=1e-6)

    # From (10, 20), bearing 45 (NE), distance 100
    x, y = compute_endpoint(10, 20, 45, 100)
    # 45 degrees: dx = 100 * cos(45°), dy = 100 * sin(45°)
    expected_x = 10 + 100 * math.cos(math.radians(45))
    expected_y = 20 + 100 * math.sin(math.radians(45))
    assert math.isclose(x, expected_x, abs_tol=1e-6)
    assert math.isclose(y, expected_y, abs_tol=1e-6)


def test_points_equal():
    """Test point equality with tolerance."""
    # Exact equality
    assert points_equal((0, 0), (0, 0))
    assert points_equal((10.5, 20.3), (10.5, 20.3))

    # Within tolerance (default 0.01)
    assert points_equal((0, 0), (0.005, 0.005))
    assert points_equal((100, 200), (100.009, 200.001))

    # Outside tolerance
    assert not points_equal((0, 0), (0.02, 0))
    assert not points_equal((100, 200), (100.1, 200))


# ============================================================================
# LINE STEP COMPILATION TESTS
# ============================================================================

def test_compile_line_step_basic():
    """Test basic LineStep compilation with valid parameters."""
    graph = FeatureGraph(
        graph_id="test-graph-1",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={
                        "bearing": 90,  # East
                        "distance": 100
                    }
                )
            )
        ]
    )

    result = compile_graph(graph)

    # Should have compiled successfully
    assert "line1" in result.compiled_features
    assert len(result.gaps) == 0

    # Check geometry
    compiled = result.compiled_features["line1"]
    assert compiled["geometry"]["type"] == "LineString"
    coords = compiled["geometry"]["coordinates"]
    assert len(coords) == 2
    assert coords[0] == [0, 0]  # Start at origin
    assert math.isclose(coords[1][0], 100, abs_tol=1e-6)  # End at (100, 0)
    assert math.isclose(coords[1][1], 0, abs_tol=1e-6)

    # Check metadata
    assert compiled["bearing"] == 90
    assert compiled["distance"] == 100
    assert compiled["start_point"] == [0, 0]
    assert math.isclose(compiled["end_point"][0], 100, abs_tol=1e-6)
    assert math.isclose(compiled["end_point"][1], 0, abs_tol=1e-6)


def test_compile_line_step_with_raw_strings():
    """Test LineStep with raw measurement strings preserved."""
    graph = FeatureGraph(
        graph_id="test-graph-2",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={
                        "bearing": 45.5,
                        "distance": 250.75,
                        "bearing_raw": "N 45°30' E",
                        "distance_raw": "250.75 feet"
                    }
                )
            )
        ]
    )

    result = compile_graph(graph)

    assert "line1" in result.compiled_features
    assert len(result.gaps) == 0

    compiled = result.compiled_features["line1"]
    assert compiled["bearing"] == 45.5
    assert compiled["distance"] == 250.75
    assert compiled["bearing_raw"] == "N 45°30' E"
    assert compiled["distance_raw"] == "250.75 feet"


def test_compile_line_step_chained():
    """Test multiple LineSteps chained together (traverse)."""
    graph = FeatureGraph(
        graph_id="test-graph-3",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 0, "distance": 100}  # North 100
                )
            ),
            FeatureNode(
                id="line2",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 90, "distance": 100}  # East 100
                )
            ),
            FeatureNode(
                id="line3",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 180, "distance": 100}  # South 100
                )
            )
        ]
    )

    result = compile_graph(graph)

    # All three should compile
    assert "line1" in result.compiled_features
    assert "line2" in result.compiled_features
    assert "line3" in result.compiled_features
    assert len(result.gaps) == 0

    # Line1: (0,0) to (0,100)
    line1 = result.compiled_features["line1"]
    assert line1["start_point"] == [0, 0]
    assert math.isclose(line1["end_point"][0], 0, abs_tol=1e-6)
    assert math.isclose(line1["end_point"][1], 100, abs_tol=1e-6)

    # Line2: (0,100) to (100,100) - chained from line1 endpoint
    line2 = result.compiled_features["line2"]
    assert math.isclose(line2["start_point"][0], 0, abs_tol=1e-6)
    assert math.isclose(line2["start_point"][1], 100, abs_tol=1e-6)
    assert math.isclose(line2["end_point"][0], 100, abs_tol=1e-6)
    assert math.isclose(line2["end_point"][1], 100, abs_tol=1e-6)

    # Line3: (100,100) to (100,0) - chained from line2 endpoint
    line3 = result.compiled_features["line3"]
    assert math.isclose(line3["start_point"][0], 100, abs_tol=1e-6)
    assert math.isclose(line3["start_point"][1], 100, abs_tol=1e-6)
    assert math.isclose(line3["end_point"][0], 100, abs_tol=1e-6)
    assert math.isclose(line3["end_point"][1], 0, abs_tol=1e-6)


def test_compile_line_step_bearing_normalization():
    """Test that bearings are normalized to [0, 360)."""
    graph = FeatureGraph(
        graph_id="test-graph-4",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 450, "distance": 100}  # 450 = 90 (normalized)
                )
            ),
            FeatureNode(
                id="line2",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": -90, "distance": 100}  # -90 = 270 (normalized)
                )
            )
        ]
    )

    result = compile_graph(graph)

    assert "line1" in result.compiled_features
    assert "line2" in result.compiled_features

    # Line1: bearing normalized to 90
    line1 = result.compiled_features["line1"]
    assert line1["bearing"] == 90

    # Line2: bearing normalized to 270
    line2 = result.compiled_features["line2"]
    assert line2["bearing"] == 270


# ============================================================================
# GAP HANDLING TESTS
# ============================================================================

def test_compile_line_step_missing_bearing():
    """Test LineStep with missing bearing parameter produces gap."""
    graph = FeatureGraph(
        graph_id="test-gap-1",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"distance": 100}  # Missing bearing
                )
            )
        ]
    )

    result = compile_graph(graph)

    # Should NOT compile successfully
    assert "line1" not in result.compiled_features
    assert len(result.gaps) == 1

    # Check gap details
    gap = result.gaps[0]
    assert gap.kind == GapKind.MISSING_PARAMETER
    assert gap.feature_id == "line1"
    assert "bearing" in gap.message
    assert gap.metadata["operation"] == "LineStep"
    assert gap.metadata["parameter_name"] == "bearing"


def test_compile_line_step_missing_distance():
    """Test LineStep with missing distance parameter produces gap."""
    graph = FeatureGraph(
        graph_id="test-gap-2",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 90}  # Missing distance
                )
            )
        ]
    )

    result = compile_graph(graph)

    assert "line1" not in result.compiled_features
    assert len(result.gaps) == 1

    gap = result.gaps[0]
    assert gap.kind == GapKind.MISSING_PARAMETER
    assert gap.feature_id == "line1"
    assert "distance" in gap.message
    assert gap.metadata["parameter_name"] == "distance"


def test_compile_line_step_parse_failed_with_raw():
    """Test LineStep with raw string but missing numeric value (parse failed)."""
    graph = FeatureGraph(
        graph_id="test-gap-3",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={
                        "bearing_raw": "North by Northeast",  # Unparseable
                        "distance": 100
                    }
                )
            )
        ]
    )

    result = compile_graph(graph)

    assert "line1" not in result.compiled_features
    assert len(result.gaps) == 1

    gap = result.gaps[0]
    assert gap.kind == GapKind.MISSING_PARAMETER
    assert gap.feature_id == "line1"
    assert gap.metadata["parameter_name"] == "bearing"
    assert gap.metadata["bearing_raw"] == "North by Northeast"
    assert "parse may have failed" in gap.metadata["reason"]


def test_compile_line_step_invalid_numeric_types():
    """Test LineStep with non-numeric parameter values."""
    graph = FeatureGraph(
        graph_id="test-gap-4",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={
                        "bearing": "not-a-number",
                        "distance": 100
                    }
                )
            )
        ]
    )

    result = compile_graph(graph)

    assert "line1" not in result.compiled_features
    assert len(result.gaps) == 1

    gap = result.gaps[0]
    assert gap.kind == GapKind.MISSING_PARAMETER
    assert gap.feature_id == "line1"
    assert "could not be converted to numeric values" in gap.metadata["reason"]


def test_compile_line_step_both_missing():
    """Test LineStep with both bearing and distance missing."""
    graph = FeatureGraph(
        graph_id="test-gap-5",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={}  # Both missing
                )
            )
        ]
    )

    result = compile_graph(graph)

    assert "line1" not in result.compiled_features
    # Should produce gap for first missing parameter (bearing checked first)
    assert len(result.gaps) >= 1

    gap = result.gaps[0]
    assert gap.kind == GapKind.MISSING_PARAMETER
    assert gap.feature_id == "line1"
    assert gap.metadata["parameter_name"] == "bearing"


# ============================================================================
# UNSUPPORTED OPERATION TESTS
# ============================================================================

def test_compile_unsupported_operation():
    """Test that unsupported operations produce UnsupportedOperation gaps."""
    graph = FeatureGraph(
        graph_id="test-unsupported-1",
        nodes=[
            FeatureNode(
                id="curve1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CurveStep",
                    params={"radius": 100, "arc_length": 50}
                )
            )
        ]
    )

    result = compile_graph(graph)

    assert "curve1" not in result.compiled_features
    assert len(result.gaps) == 1

    gap = result.gaps[0]
    assert gap.kind == GapKind.UNSUPPORTED_OPERATION
    assert gap.feature_id == "curve1"
    assert "CurveStep" in gap.message
    assert gap.metadata["operation"] == "CurveStep"


def test_compile_unknown_operation():
    """Test that unknown operations (not in registry) produce gaps."""
    graph = FeatureGraph(
        graph_id="test-unknown-1",
        nodes=[
            FeatureNode(
                id="unknown1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="MysteryOperation",
                    params={"foo": "bar"}
                )
            )
        ]
    )

    result = compile_graph(graph)

    assert "unknown1" not in result.compiled_features
    assert len(result.gaps) == 1

    gap = result.gaps[0]
    assert gap.kind == GapKind.UNSUPPORTED_OPERATION
    assert gap.feature_id == "unknown1"
    assert "MysteryOperation" in gap.message


# ============================================================================
# MIXED SCENARIOS
# ============================================================================

def test_compile_mixed_success_and_gaps():
    """Test graph with some successful compilations and some gaps."""
    graph = FeatureGraph(
        graph_id="test-mixed-1",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 0, "distance": 100}
                )
            ),
            FeatureNode(
                id="line2",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 90}  # Missing distance
                )
            ),
            FeatureNode(
                id="curve1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CurveStep",  # Unsupported
                    params={"radius": 50}
                )
            ),
            FeatureNode(
                id="line3",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 180, "distance": 50}
                )
            )
        ]
    )

    result = compile_graph(graph)

    # line1 and line3 should compile successfully
    assert "line1" in result.compiled_features
    assert "line3" in result.compiled_features

    # line2 and curve1 should have gaps
    assert "line2" not in result.compiled_features
    assert "curve1" not in result.compiled_features
    assert len(result.gaps) == 2

    # Check gap kinds
    gap_kinds = {gap.kind for gap in result.gaps}
    assert GapKind.MISSING_PARAMETER in gap_kinds
    assert GapKind.UNSUPPORTED_OPERATION in gap_kinds


def test_compile_graph_empty():
    """Test compiling an empty graph."""
    graph = FeatureGraph(graph_id="empty-graph", nodes=[])
    result = compile_graph(graph)

    assert len(result.compiled_features) == 0
    assert len(result.gaps) == 0
    assert len(result.warnings) == 0


def test_compile_graph_direct_geometry():
    """Test that nodes with direct geometry are included in output."""
    graph = FeatureGraph(
        graph_id="test-direct-1",
        nodes=[
            FeatureNode(
                id="point1",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [100, 200]}
            ),
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 45, "distance": 100}
                )
            )
        ]
    )

    result = compile_graph(graph)

    # Both should be in compiled features
    assert "point1" in result.compiled_features
    assert "line1" in result.compiled_features

    # point1 should have direct geometry
    assert result.compiled_features["point1"]["source"] == "direct"
    assert result.compiled_features["point1"]["geometry"]["type"] == "Point"


# ============================================================================
# EDGE CASES
# ============================================================================

def test_compile_line_step_zero_distance():
    """Test LineStep with zero distance (degenerate line)."""
    graph = FeatureGraph(
        graph_id="test-edge-1",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 90, "distance": 0}
                )
            )
        ]
    )

    result = compile_graph(graph)

    # Should compile (even though it's degenerate)
    assert "line1" in result.compiled_features
    assert len(result.gaps) == 0

    compiled = result.compiled_features["line1"]
    assert compiled["start_point"] == [0, 0]
    assert compiled["end_point"] == [0, 0]


def test_compile_line_step_negative_distance():
    """Test LineStep with negative distance (should work - reverse direction)."""
    graph = FeatureGraph(
        graph_id="test-edge-2",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 0, "distance": -100}
                )
            )
        ]
    )

    result = compile_graph(graph)

    # Should compile (negative distance goes backwards)
    assert "line1" in result.compiled_features
    assert len(result.gaps) == 0

    compiled = result.compiled_features["line1"]
    # Bearing 0 (north) with distance -100 should go south to (0, -100)
    assert math.isclose(compiled["end_point"][0], 0, abs_tol=1e-6)
    assert math.isclose(compiled["end_point"][1], -100, abs_tol=1e-6)


def test_compile_result_to_dict():
    """Test CompileResult serialization."""
    graph = FeatureGraph(
        graph_id="test-serialize-1",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 90, "distance": 100}
                )
            )
        ]
    )

    result = compile_graph(graph)
    result_dict = result.to_dict()

    assert "compiled_features" in result_dict
    assert "gaps" in result_dict
    assert "warnings" in result_dict

    assert isinstance(result_dict["compiled_features"], dict)
    assert isinstance(result_dict["gaps"], list)
    assert isinstance(result_dict["warnings"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
