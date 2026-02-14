"""
Feature Graph Judge Engine
===========================

Deterministic validation engine that analyzes feature graphs and produces
typed gap records.

The judge engine performs these validations:
- Missing anchors: features with no global frame reference
- Missing operands: operations referencing non-existent features
- Missing parameters: operations with missing required parameters
- Unsupported operations: operations not yet implemented by compiler
- Precondition failures: operations with invalid preconditions

Design principles:
- Deterministic: same input always produces same gaps
- Comprehensive: catches all known failure modes
- Provenance-aware: gaps cite source evidence when available
- No silent failure: every issue produces a typed gap
"""

from __future__ import annotations

from typing import List, Dict, Any, Set, Optional

from .models import FeatureGraph, FeatureNode, FeatureKind, OpExpr
from .gaps import (
    FeatureGap,
    JudgeReport,
    missing_anchor_gap,
    missing_operand_gap,
    missing_parameter_gap,
    unsupported_operation_gap,
    precondition_failed_gap,
)
from .operations import get_operation_def, is_supported_operation
from .provenance import Citation


# ============================================================================
# JUDGE ENGINE
# ============================================================================

def judge_missing_anchors(
    graph: FeatureGraph,
    gaps: List[FeatureGap],
    global_placement_required: bool = False
):
    """
    Detect features that lack global frame references (anchoring).

    Features that need anchoring typically include:
    - POINT features without explicit coordinates
    - CURVE features that are local but not anchored to a frame
    - REGION features that are local but not anchored

    A feature is considered anchored if:
    - It has explicit geometry (direct coordinates)
    - It references a FRAME feature
    - It has a FeatureRef with external anchoring

    Args:
        graph: Feature graph to validate
        gaps: List to append gaps to
    """
    # Build set of anchored features
    anchored_ids: Set[str] = set()
    frame_ids: Set[str] = set()

    # Pass 1: identify frames and directly anchored features
    for node in graph.nodes:
        if node.kind == FeatureKind.FRAME:
            frame_ids.add(node.id)
            anchored_ids.add(node.id)
        elif node.geometry:
            # Direct geometry means it's anchored
            anchored_ids.add(node.id)

    # Pass 2: check for features that need anchoring but lack it
    for node in graph.nodes:
        if node.id in anchored_ids:
            continue  # Already anchored

        # Local-first default: only require global anchors if explicitly requested.
        node_requires_global = bool(node.metadata.get("requires_global_placement", False))
        needs_anchor = (
            node.kind in [FeatureKind.POINT, FeatureKind.CURVE, FeatureKind.REGION]
            and (global_placement_required or node_requires_global)
        )

        if needs_anchor:
            # Check if it references a frame or anchored feature
            has_frame_ref = False
            if node.op_expr:
                # Check if any operands reference frames
                for operand in node.op_expr.operands:
                    if isinstance(operand, str) and operand in frame_ids:
                        has_frame_ref = True
                        break

            if not has_frame_ref:
                # Extract citations if available
                citations = []
                if node.provenance and node.provenance.citations:
                    citations = node.provenance.citations

                gaps.append(missing_anchor_gap(
                    feature_id=node.id,
                    message=f"Feature '{node.id}' ({node.kind.value}) lacks global frame reference",
                    citations=citations,
                    metadata={
                        "feature_kind": node.kind.value,
                        "has_geometry": bool(node.geometry),
                        "has_op_expr": bool(node.op_expr)
                    }
                ))


def judge_missing_operands(graph: FeatureGraph, gaps: List[FeatureGap]):
    """
    Detect operations that reference non-existent features.

    Validates that all operand references (feature IDs) actually exist
    in the graph.

    Args:
        graph: Feature graph to validate
        gaps: List to append gaps to
    """
    # Build set of valid node IDs
    valid_ids = {node.id for node in graph.nodes}

    # Check each node's op_expr operands
    for node in graph.nodes:
        if not node.op_expr:
            continue

        op_expr = node.op_expr
        for i, operand in enumerate(op_expr.operands):
            # Only check string operands (feature ID references)
            # OpExpr operands are inline expressions, not references
            if isinstance(operand, str):
                if operand not in valid_ids:
                    # Extract citations if available
                    citations = []
                    if node.provenance and node.provenance.citations:
                        citations = node.provenance.citations

                    gaps.append(missing_operand_gap(
                        feature_id=node.id,
                        operation=op_expr.op_name,
                        missing_operand=operand,
                        citations=citations,
                        metadata={
                            "operand_index": i,
                            "total_operands": len(op_expr.operands)
                        }
                    ))


def judge_missing_parameters(graph: FeatureGraph, gaps: List[FeatureGap]):
    """
    Detect operations with missing required parameters.

    Validates that all required parameters (per operation registry) are present
    in the OpExpr params dict.

    Args:
        graph: Feature graph to validate
        gaps: List to append gaps to
    """
    for node in graph.nodes:
        if not node.op_expr:
            continue

        op_expr = node.op_expr
        op_name = op_expr.op_name

        # Get operation definition from registry
        op_def = get_operation_def(op_name)
        if not op_def:
            # Operation not in registry - will be caught by unsupported_operation check
            continue

        # Check required parameters
        required_params = op_def.get_required_parameters()
        for param_name in required_params:
            if param_name not in op_expr.params:
                # Extract citations if available
                citations = []
                if node.provenance and node.provenance.citations:
                    citations = node.provenance.citations

                gaps.append(missing_parameter_gap(
                    feature_id=node.id,
                    operation=op_name,
                    parameter_name=param_name,
                    citations=citations,
                    metadata={
                        "provided_params": list(op_expr.params.keys()),
                        "required_params": required_params
                    }
                ))

        # Check operand count
        operand_count = len(op_expr.operands)
        if not op_def.validate_operand_count(operand_count):
            # Extract citations if available
            citations = []
            if node.provenance and node.provenance.citations:
                citations = node.provenance.citations

            # Create a precondition failed gap for operand count mismatch
            max_desc = f"{op_def.max_operands}" if op_def.max_operands is not None else "unlimited"
            gaps.append(precondition_failed_gap(
                feature_id=node.id,
                operation=op_name,
                precondition=f"operand count between {op_def.min_operands} and {max_desc}",
                reason=f"Got {operand_count} operands",
                citations=citations,
                metadata={
                    "operand_count": operand_count,
                    "min_operands": op_def.min_operands,
                    "max_operands": op_def.max_operands
                }
            ))


def judge_unsupported_operations(graph: FeatureGraph, gaps: List[FeatureGap]):
    """
    Detect operations that are not yet supported by the compiler.

    Checks the operation registry to determine if each operation is marked
    as supported.

    Args:
        graph: Feature graph to validate
        gaps: List to append gaps to
    """
    for node in graph.nodes:
        if not node.op_expr:
            continue

        op_expr = node.op_expr
        op_name = op_expr.op_name

        # Check if operation is in registry
        op_def = get_operation_def(op_name)

        if not op_def:
            # Operation not in registry at all
            citations = []
            if node.provenance and node.provenance.citations:
                citations = node.provenance.citations

            gaps.append(unsupported_operation_gap(
                feature_id=node.id,
                operation=op_name,
                reason="Operation not found in registry",
                citations=citations,
                metadata={
                    "params": op_expr.params,
                    "operands": [str(op) for op in op_expr.operands]
                }
            ))
        elif not op_def.supported:
            # Operation in registry but not yet supported
            citations = []
            if node.provenance and node.provenance.citations:
                citations = node.provenance.citations

            gaps.append(unsupported_operation_gap(
                feature_id=node.id,
                operation=op_name,
                reason=f"Operation '{op_name}' not yet implemented in compiler",
                citations=citations,
                metadata={
                    "category": op_def.category.value,
                    "description": op_def.description,
                    "params": op_expr.params,
                    "operands": [str(op) for op in op_expr.operands]
                }
            ))


def judge_graph(graph: FeatureGraph, include_warnings: bool = True) -> JudgeReport:
    """
    Run full judge validation on a feature graph.

    The judge performs these checks:
    - Missing anchors (features without global frame references)
    - Missing operands (operations referencing non-existent features)
    - Missing parameters (operations with missing required params)
    - Unsupported operations (operations not yet implemented)

    Args:
        graph: Feature graph to validate
        include_warnings: Whether to include non-error diagnostics (default: True)

    Returns:
        JudgeReport with all typed gaps discovered
    """
    gaps: List[FeatureGap] = []
    warnings: List[str] = []

    requires_global_placement = bool(graph.metadata.get("global_placement_required", False))

    # Run all judge checks
    judge_missing_anchors(graph, gaps, global_placement_required=requires_global_placement)
    judge_missing_operands(graph, gaps)
    judge_missing_parameters(graph, gaps)
    judge_unsupported_operations(graph, gaps)

    # Add warnings for empty graph
    if not graph.nodes:
        warnings.append("Graph contains no nodes")

    # Add warnings for disconnected nodes
    if graph.nodes and not graph.edges:
        node_count = len(graph.nodes)
        if node_count > 1:
            warnings.append(f"Graph has {node_count} nodes but no edges (disconnected)")

    # Build metadata
    metadata = {
        "graph_id": graph.graph_id,
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "gap_count": len(gaps),
        "error_count": sum(1 for gap in gaps if gap.severity == "error"),
        "warning_count": len(warnings)
    }

    # Create report
    report = JudgeReport(
        graph_id=graph.graph_id,
        gaps=gaps,
        warnings=warnings if include_warnings else [],
        artifacts={},
        metadata=metadata
    )

    return report
