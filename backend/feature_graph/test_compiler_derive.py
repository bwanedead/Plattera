"""Tests for Feature Graph Compiler derive operations (Close/Buffer)."""

from backend.feature_graph.compiler import compile_graph
from backend.feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr
from backend.feature_graph.gaps import GapKind


def test_close_on_closed_curve_produces_polygon() -> None:
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="closed_curve",
                kind=FeatureKind.CURVE,
                geometry={
                    "type": "LineString",
                    "coordinates": [[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]],
                },
            ),
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Close", operands=["closed_curve"]),
            ),
        ],
        edges=[],
    )

    result = compile_graph(graph)

    assert result.gaps == []
    assert "region" in result.compiled_features
    region_data = result.compiled_features["region"]
    assert region_data["geometry"]["type"] == "Polygon"
    assert region_data["is_closed"] is True
    assert region_data["source_curve_id"] == "closed_curve"


def test_close_on_open_curve_emits_precondition_failed() -> None:
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="open_curve",
                kind=FeatureKind.CURVE,
                geometry={"type": "LineString", "coordinates": [[0, 0], [100, 0], [100, 100]]},
            ),
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Close", operands=["open_curve"]),
            ),
        ],
        edges=[],
    )

    result = compile_graph(graph)

    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.kind == GapKind.PRECONDITION_FAILED
    assert gap.feature_id == "region"
    assert gap.metadata["operation"] == "Close"
    assert "curve endpoints must meet" in gap.metadata["precondition"]


def test_close_with_missing_operand_emits_gap() -> None:
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Close", operands=[]),
            )
        ],
        edges=[],
    )

    result = compile_graph(graph)

    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.kind == GapKind.MISSING_PARAMETER
    assert gap.feature_id == "region"
    assert gap.metadata["operation"] == "Close"
    assert gap.metadata["parameter_name"] == "operand"


def test_close_with_uncompiled_operand_emits_precondition_failed() -> None:
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Close", operands=["missing_curve"]),
            )
        ],
        edges=[],
    )

    result = compile_graph(graph)

    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.kind == GapKind.PRECONDITION_FAILED
    assert gap.feature_id == "region"
    assert "must be compiled first" in gap.metadata["precondition"]


def test_buffer_emits_unsupported_operation() -> None:
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="line",
                kind=FeatureKind.CURVE,
                geometry={"type": "LineString", "coordinates": [[0, 0], [100, 0]]},
            ),
            FeatureNode(
                id="buffered",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(
                    op_name="Buffer",
                    params={"distance": 50, "side": "both"},
                    operands=["line"],
                ),
            ),
        ],
        edges=[],
    )

    result = compile_graph(graph)

    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.kind == GapKind.UNSUPPORTED_OPERATION
    assert gap.feature_id == "buffered"
    assert gap.metadata["operation"] == "Buffer"
    assert gap.metadata["params"]["distance"] == 50
    assert gap.metadata["operands"] == ["line"]


def test_close_succeeds_and_buffer_fails_in_same_graph() -> None:
    graph = FeatureGraph(
        graph_id="test-graph",
        nodes=[
            FeatureNode(
                id="closed_curve",
                kind=FeatureKind.CURVE,
                geometry={"type": "LineString", "coordinates": [[0, 0], [50, 0], [50, 50], [0, 50], [0, 0]]},
            ),
            FeatureNode(
                id="region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Close", operands=["closed_curve"]),
            ),
            FeatureNode(
                id="buffered_region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Buffer", params={"distance": 10}, operands=["region"]),
            ),
        ],
        edges=[],
    )

    result = compile_graph(graph)

    assert len(result.gaps) == 1
    assert result.gaps[0].kind == GapKind.UNSUPPORTED_OPERATION
    assert "region" in result.compiled_features
    assert "buffered_region" not in result.compiled_features
