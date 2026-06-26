"""Tests for ReferenceFrame compilation and Close snap/tolerance behavior."""

from __future__ import annotations

from feature_graph.compiler import compile_graph
from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr


def test_reference_frame_compiles_without_gap():
    graph = FeatureGraph(
        graph_id="frame_test",
        nodes=[
            FeatureNode(
                id="plss_context",
                kind=FeatureKind.FRAME,
                op_expr=OpExpr(
                    op_name="ReferenceFrame",
                    params={
                        "frame_type": "plss",
                        "section": "12",
                        "township": "3N",
                        "range": "2W",
                        "meridian": "Principal Meridian",
                        "raw_text": "Section 12, Township 3 North, Range 2 West",
                    },
                ),
            )
        ],
        edges=[],
    )
    result = compile_graph(graph)
    assert not result.gaps
    compiled = result.compiled_features["plss_context"]
    assert compiled["non_rendered"] is True
    assert compiled["frame_descriptor"]["frame_type"] == "plss"
    assert compiled.get("geometry") is None


def test_close_snap_to_start_within_tolerance():
    graph = FeatureGraph(
        graph_id="close_snap",
        nodes=[
            FeatureNode(
                id="origin",
                kind=FeatureKind.POINT,
                op_expr=OpExpr(op_name="TiedPoint", params={}, operands=[]),
            ),
            FeatureNode(
                id="traverse",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    operands=["origin"],
                    params={
                        "courses": [
                            {"bearing": 90.0, "distance": 100.0},
                            {"bearing": 180.0, "distance": 100.0},
                            {"bearing": 270.0, "distance": 100.0},
                            {"bearing": 0.0, "distance": 99.98},
                        ]
                    },
                ),
            ),
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(
                    op_name="Close",
                    operands=["traverse"],
                    params={"closure_mode": "snap_to_start", "closure_tolerance": 5.0},
                ),
            ),
        ],
        edges=[],
    )
    strict_graph = FeatureGraph(
        graph_id="close_strict",
        nodes=[
            graph.nodes[0],
            graph.nodes[1],
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Close", operands=["traverse"], params={}),
            ),
        ],
        edges=[],
    )
    strict_result = compile_graph(strict_graph)
    assert any(gap.kind.value == "precondition_failed" for gap in strict_result.gaps)

    snap_result = compile_graph(graph)
    close_gaps = [gap for gap in snap_result.gaps if gap.feature_id == "region"]
    assert not close_gaps
    region = snap_result.compiled_features["region"]
    assert region["geometry"]["type"] == "Polygon"
    assert region.get("closure_snapped") is True
    assert region.get("closure_error_distance", 0) > 0.01


def test_close_snap_requires_closure_tolerance_param():
    graph = FeatureGraph(
        graph_id="close_snap_missing_tol",
        nodes=[
            FeatureNode(
                id="start",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            ),
            FeatureNode(
                id="curve",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    operands=["start"],
                    params={"bearing": 45.0, "distance": 10.0},
                ),
            ),
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(
                    op_name="Close",
                    operands=["curve"],
                    params={"closure_mode": "snap_to_start"},
                ),
            ),
        ],
        edges=[],
    )
    result = compile_graph(graph)
    assert any(
        gap.kind.value == "missing_parameter"
        and gap.metadata.get("parameter_name") == "closure_tolerance"
        for gap in result.gaps
    )
