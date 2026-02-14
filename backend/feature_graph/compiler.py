"""
Feature Graph Compiler
=======================

Compiles feature graph IR into concrete geometry outputs.
This is a best-effort compiler: it produces partial results with typed gaps
for unsupported operations or missing parameters.

Design principles:
- Best-effort compilation: partial results + typed gaps, never silent failure
- Local geometry first: produces local coordinates without global anchoring
- Deterministic: same input always produces same output (no LLM, no randomness)
- Explicit gaps: missing parameters or unsupported ops produce typed gap records

Currently supported operations:
- Traverse/LineStep: straight line segments with bearing and distance
- Derive/Close: close a curve to form a region (if endpoints meet)

All other operations emit UnsupportedOperation gaps with structured params.
"""

from __future__ import annotations

from typing import Dict, List, Any, Optional, Tuple
import math

from .models import FeatureGraph, FeatureNode, FeatureKind, OpExpr
from .gaps import (
    FeatureGap,
    missing_parameter_gap,
    unsupported_operation_gap,
    precondition_failed_gap,
)
from .operations import get_operation_def, is_supported_operation


# ============================================================================
# COMPILATION RESULT
# ============================================================================

class CompileResult:
    """
    Result of compiling a feature graph.

    Contains:
    - compiled_features: map of node_id -> compiled geometry/result
    - gaps: list of typed gaps encountered during compilation
    - warnings: list of non-fatal warning messages
    """
    def __init__(self):
        self.compiled_features: Dict[str, Any] = {}
        self.gaps: List[FeatureGap] = []
        self.warnings: List[str] = []

    def add_feature(self, node_id: str, result: Any):
        """Add a successfully compiled feature."""
        self.compiled_features[node_id] = result

    def add_gap(self, gap: FeatureGap):
        """Record a gap encountered during compilation."""
        self.gaps.append(gap)

    def add_warning(self, message: str):
        """Record a non-fatal warning."""
        self.warnings.append(message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "compiled_features": self.compiled_features,
            "gaps": [gap.dict() for gap in self.gaps],
            "warnings": self.warnings
        }


# ============================================================================
# COORDINATE HELPERS
# ============================================================================

def bearing_to_radians(bearing_degrees: float) -> float:
    """
    Convert bearing (degrees clockwise from north) to radians for math operations.

    Bearing system: 0° = north, 90° = east, 180° = south, 270° = west
    Math system: 0 rad = east, π/2 rad = north (counterclockwise from east)

    Formula: math_angle = π/2 - (bearing * π/180)
    """
    return math.radians(90 - bearing_degrees)


def compute_endpoint(
    start_x: float,
    start_y: float,
    bearing_degrees: float,
    distance_feet: float
) -> Tuple[float, float]:
    """
    Compute endpoint of a line segment given start point, bearing, and distance.

    Args:
        start_x: X coordinate of start point (feet)
        start_y: Y coordinate of start point (feet)
        bearing_degrees: Bearing angle in degrees (0 = north, 90 = east)
        distance_feet: Distance to travel (feet)

    Returns:
        (end_x, end_y): Endpoint coordinates
    """
    angle_rad = bearing_to_radians(bearing_degrees)
    end_x = start_x + distance_feet * math.cos(angle_rad)
    end_y = start_y + distance_feet * math.sin(angle_rad)
    return (end_x, end_y)


def points_equal(p1: Tuple[float, float], p2: Tuple[float, float], tolerance: float = 0.01) -> bool:
    """
    Check if two points are equal within tolerance.

    Args:
        p1: First point (x, y)
        p2: Second point (x, y)
        tolerance: Maximum distance for points to be considered equal (default 0.01 feet)

    Returns:
        True if points are within tolerance, False otherwise
    """
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    distance = math.sqrt(dx*dx + dy*dy)
    return distance <= tolerance


# ============================================================================
# OPERATION COMPILERS
# ============================================================================

def compile_line_step(
    node: FeatureNode,
    op_expr: OpExpr,
    previous_point: Optional[Tuple[float, float]],
    result: CompileResult
) -> Optional[Dict[str, Any]]:
    """
    Compile a LineStep operation into a line segment.

    LineStep requires:
    - bearing: numeric angle in degrees (0-360)
    - distance: numeric distance in feet

    Optional:
    - bearing_raw: original bearing string (for provenance)
    - distance_raw: original distance string (for provenance)

    Returns:
        Dict with:
        - geometry: {"type": "LineString", "coordinates": [[x1,y1], [x2,y2]]}
        - start_point: [x1, y1]
        - end_point: [x2, y2]
        - bearing: numeric bearing
        - distance: numeric distance

        Or None if required parameters are missing (gaps are recorded in result)
    """
    params = op_expr.params

    # Start point: use previous point or default to origin
    if previous_point is not None:
        start_x, start_y = previous_point
    else:
        start_x, start_y = (0.0, 0.0)

    # Extract bearing (required)
    bearing = params.get("bearing")
    if bearing is None:
        # Check if bearing_raw exists but numeric bearing is missing
        bearing_raw = params.get("bearing_raw")
        if bearing_raw:
            result.add_gap(missing_parameter_gap(
                feature_id=node.id,
                operation="LineStep",
                parameter_name="bearing",
                metadata={
                    "bearing_raw": bearing_raw,
                    "reason": "Numeric bearing value not available (parse may have failed)"
                }
            ))
        else:
            result.add_gap(missing_parameter_gap(
                feature_id=node.id,
                operation="LineStep",
                parameter_name="bearing",
                metadata={"reason": "No bearing or bearing_raw provided"}
            ))
        return None

    # Extract distance (required)
    distance = params.get("distance")
    if distance is None:
        # Check if distance_raw exists but numeric distance is missing
        distance_raw = params.get("distance_raw")
        if distance_raw:
            result.add_gap(missing_parameter_gap(
                feature_id=node.id,
                operation="LineStep",
                parameter_name="distance",
                metadata={
                    "distance_raw": distance_raw,
                    "reason": "Numeric distance value not available (parse may have failed)"
                }
            ))
        else:
            result.add_gap(missing_parameter_gap(
                feature_id=node.id,
                operation="LineStep",
                parameter_name="distance",
                metadata={"reason": "No distance or distance_raw provided"}
            ))
        return None

    # Validate types
    try:
        bearing_val = float(bearing)
        distance_val = float(distance)
    except (TypeError, ValueError) as e:
        result.add_gap(missing_parameter_gap(
            feature_id=node.id,
            operation="LineStep",
            parameter_name="bearing or distance",
            metadata={
                "bearing": bearing,
                "distance": distance,
                "error": str(e),
                "reason": "Parameters could not be converted to numeric values"
            }
        ))
        return None

    # Normalize bearing to [0, 360)
    bearing_val = bearing_val % 360.0

    # Compute endpoint
    end_x, end_y = compute_endpoint(start_x, start_y, bearing_val, distance_val)

    # Build geometry
    line_geometry = {
        "type": "LineString",
        "coordinates": [
            [start_x, start_y],
            [end_x, end_y]
        ]
    }

    # Build result with geometry and metadata
    return {
        "geometry": line_geometry,
        "start_point": [start_x, start_y],
        "end_point": [end_x, end_y],
        "bearing": bearing_val,
        "distance": distance_val,
        "bearing_raw": params.get("bearing_raw"),
        "distance_raw": params.get("distance_raw")
    }


def compile_close(
    node: FeatureNode,
    op_expr: OpExpr,
    graph: FeatureGraph,
    compiled_features: Dict[str, Any],
    result: CompileResult
) -> Optional[Dict[str, Any]]:
    """
    Compile a Close operation: close a curve to form a region.

    Close requires exactly one operand: a curve feature.
    The curve must have its endpoints meeting (within tolerance) to be closeable.

    Returns:
        Dict with:
        - geometry: {"type": "Polygon", "coordinates": [[[x1,y1], [x2,y2], ...]]}
        - is_closed: True

        Or None if precondition fails (curve not closed)
    """
    # Validate operand count
    if len(op_expr.operands) != 1:
        result.add_gap(missing_parameter_gap(
            feature_id=node.id,
            operation="Close",
            parameter_name="operand",
            metadata={
                "expected_operands": 1,
                "actual_operands": len(op_expr.operands),
                "reason": "Close requires exactly one curve operand"
            }
        ))
        return None

    # Get operand (must be a node ID string)
    operand = op_expr.operands[0]
    if not isinstance(operand, str):
        result.add_gap(precondition_failed_gap(
            feature_id=node.id,
            operation="Close",
            precondition="operand must be a feature ID (string)",
            reason=f"Operand is {type(operand).__name__}, not str"
        ))
        return None

    # Check if operand has been compiled
    if operand not in compiled_features:
        result.add_gap(precondition_failed_gap(
            feature_id=node.id,
            operation="Close",
            precondition=f"operand '{operand}' must be compiled first",
            reason="Operand not found in compiled features"
        ))
        return None

    # Get compiled curve
    curve_data = compiled_features[operand]
    curve_geom = curve_data.get("geometry")

    if not curve_geom or curve_geom.get("type") != "LineString":
        result.add_gap(precondition_failed_gap(
            feature_id=node.id,
            operation="Close",
            precondition="operand must be a curve (LineString)",
            reason=f"Operand geometry type is {curve_geom.get('type') if curve_geom else 'None'}"
        ))
        return None

    # Extract coordinates
    coords = curve_geom.get("coordinates", [])
    if len(coords) < 2:
        result.add_gap(precondition_failed_gap(
            feature_id=node.id,
            operation="Close",
            precondition="curve must have at least 2 points",
            reason=f"Curve has {len(coords)} points"
        ))
        return None

    # Check if curve is closed (first and last points are equal within tolerance)
    first_point = tuple(coords[0])
    last_point = tuple(coords[-1])

    if not points_equal(first_point, last_point):
        result.add_gap(precondition_failed_gap(
            feature_id=node.id,
            operation="Close",
            precondition="curve endpoints must meet",
            reason=f"Start point {first_point} does not match end point {last_point}",
            metadata={
                "start_point": list(first_point),
                "end_point": list(last_point),
                "distance": math.sqrt((first_point[0]-last_point[0])**2 + (first_point[1]-last_point[1])**2)
            }
        ))
        return None

    # Curve is closed - convert to polygon
    # Polygon coordinates must be closed (first == last), so ensure that
    polygon_coords = coords if points_equal(tuple(coords[0]), tuple(coords[-1])) else coords + [coords[0]]

    polygon_geometry = {
        "type": "Polygon",
        "coordinates": [polygon_coords]  # Outer ring
    }

    return {
        "geometry": polygon_geometry,
        "is_closed": True,
        "source_curve_id": operand
    }


# ============================================================================
# MAIN COMPILER
# ============================================================================

def compile_node(
    node: FeatureNode,
    graph: FeatureGraph,
    compiled_features: Dict[str, Any],
    previous_point: Optional[Tuple[float, float]],
    result: CompileResult
) -> Optional[Any]:
    """
    Compile a single feature node.

    Returns the compiled result, or None if compilation failed.
    Gaps are recorded in the result object.
    """
    # If node already has direct geometry, return it
    if node.geometry:
        return {
            "geometry": node.geometry,
            "source": "direct"
        }

    # If node has no op_expr, it cannot be compiled
    if not node.op_expr:
        result.add_warning(f"Node {node.id} has no geometry and no op_expr, skipping")
        return None

    op_expr = node.op_expr
    op_name = op_expr.op_name

    # Check if operation is supported
    if not is_supported_operation(op_name):
        op_def = get_operation_def(op_name)
        reason = "Not yet implemented" if op_def else "Operation not in registry"
        result.add_gap(unsupported_operation_gap(
            feature_id=node.id,
            operation=op_name,
            reason=reason,
            metadata={"params": op_expr.params, "operands": op_expr.operands}
        ))
        return None

    # Dispatch to operation-specific compiler
    if op_name == "LineStep":
        return compile_line_step(node, op_expr, previous_point, result)
    elif op_name == "Close":
        return compile_close(node, op_expr, graph, compiled_features, result)
    else:
        # Registered as supported but no compiler implementation (should not happen)
        result.add_gap(unsupported_operation_gap(
            feature_id=node.id,
            operation=op_name,
            reason=f"Compiler implementation missing for '{op_name}'",
            metadata={"params": op_expr.params}
        ))
        return None


def compile_graph(graph: FeatureGraph) -> CompileResult:
    """
    Compile a feature graph into concrete geometry outputs.

    This is a best-effort compiler: it produces partial results with typed gaps
    for unsupported operations or missing parameters.

    Compilation order:
    1. Nodes with direct geometry (no computation needed)
    2. Nodes with op_expr, in topological order (dependencies first)
    3. For traverse operations, maintain "previous point" context for chaining

    Args:
        graph: The feature graph to compile

    Returns:
        CompileResult with compiled_features, gaps, and warnings
    """
    result = CompileResult()
    compiled_features = result.compiled_features

    # Track previous point for traverse chaining
    # (in a full implementation, this would follow edge relationships)
    previous_point: Optional[Tuple[float, float]] = None

    # Pass 1: compile nodes with direct geometry
    for node in graph.nodes:
        if node.geometry:
            compiled_features[node.id] = {
                "geometry": node.geometry,
                "source": "direct"
            }

    # Pass 2: compile nodes with op_expr
    # (In a full implementation, we'd do topological sort based on edges)
    # For now, we process in order and handle missing operands gracefully
    for node in graph.nodes:
        if node.id in compiled_features:
            continue  # Already compiled (had direct geometry)

        if not node.op_expr:
            result.add_warning(f"Node {node.id} has no geometry and no op_expr, skipping")
            continue

        # Compile this node
        compiled = compile_node(node, graph, compiled_features, previous_point, result)

        if compiled:
            compiled_features[node.id] = compiled

            # Update previous point for traverse chaining
            # (use end_point if available)
            if "end_point" in compiled:
                previous_point = tuple(compiled["end_point"])

    return result
