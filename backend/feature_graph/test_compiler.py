"""Compiler serviceable-path tests for metes-and-bounds authoring."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.feature_graph.compiler import compile_graph
from backend.feature_graph.judge import judge_graph
from backend.feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr


def test_compile_course_traverse_and_close_produces_linestring_and_polygon() -> None:
    graph = FeatureGraph(
        graph_id="g_course_close",
        nodes=[
            FeatureNode(id="pob", kind=FeatureKind.POINT, op_expr=OpExpr(op_name="TiedPoint", params={"tie": "schematic"})),
            FeatureNode(
                id="parcel1_traverse",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    operands=["pob"],
                    params={
                        "courses": [
                            {"bearing": 90, "distance": 10, "bearing_raw": "E", "distance_raw": "10 ft"},
                            {"bearing": 180, "distance": 10},
                            {"bearing": 270, "distance": 10},
                            {"bearing": 0, "distance": 10},
                        ]
                    },
                ),
            ),
            FeatureNode(id="parcel1", kind=FeatureKind.REGION, op_expr=OpExpr(op_name="Close", operands=["parcel1_traverse"])),
        ],
        edges=[],
        metadata={"dossier_id": "D_TEST"},
    )

    compiled = compile_graph(graph)

    assert "pob" in compiled.compiled_features
    assert "parcel1_traverse" in compiled.compiled_features
    assert "parcel1" in compiled.compiled_features
    assert compiled.compiled_features["pob"]["geometry"]["type"] == "Point"
    assert compiled.compiled_features["parcel1_traverse"]["geometry"]["type"] == "LineString"
    assert compiled.compiled_features["parcel1"]["geometry"]["type"] == "Polygon"
    assert any("schematic point" in w for w in compiled.warnings)

    judge = judge_graph(graph, include_warnings=True)
    unsupported = [g for g in judge.gaps if g.kind.value == "unsupported_operation"]
    assert not unsupported


def test_compile_independent_course_traverse_uses_explicit_start_operand() -> None:
    """Second parcel traverse must start at its explicit anchor, not the prior endpoint."""
    import math

    graph = FeatureGraph(
        graph_id="g_multi_parcel",
        nodes=[
            FeatureNode(
                id="parcel_1_pob",
                kind=FeatureKind.POINT,
                op_expr=OpExpr(op_name="TiedPoint", params={"tie": "schematic"}),
            ),
            FeatureNode(
                id="parcel_1_traverse",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    operands=["parcel_1_pob"],
                    params={
                        "courses": [
                            {"bearing": 90, "distance": 10},
                            {"bearing": 180, "distance": 5},
                        ]
                    },
                ),
            ),
            FeatureNode(
                id="parcel_2_pob_anchor",
                kind=FeatureKind.POINT,
                op_expr=OpExpr(op_name="TiedPoint", params={"tie": "schematic"}),
            ),
            FeatureNode(
                id="parcel_2_visible_traverse",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    operands=["parcel_2_pob_anchor"],
                    params={"courses": [{"bearing": 0, "distance": 8}]},
                ),
            ),
        ],
        edges=[],
    )

    compiled = compile_graph(graph)
    assert not compiled.gaps

    parcel_1 = compiled.compiled_features["parcel_1_traverse"]
    parcel_2 = compiled.compiled_features["parcel_2_visible_traverse"]
    parcel_2_anchor = compiled.compiled_features["parcel_2_pob_anchor"]

    assert parcel_2["start_point"] == parcel_2_anchor["geometry"]["coordinates"]
    assert parcel_2["start_point"] == [0.0, 0.0]
    assert parcel_2["start_point"] != parcel_1["end_point"]
    assert not math.isclose(parcel_1["end_point"][0], 0.0, abs_tol=1e-6) or not math.isclose(
        parcel_1["end_point"][1], 0.0, abs_tol=1e-6
    )


def test_compile_course_traverse_without_operand_still_chains_previous_point() -> None:
    graph = FeatureGraph(
        graph_id="g_chained_traverse",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 0, "distance": 100},
                ),
            ),
            FeatureNode(
                id="traverse2",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    params={"courses": [{"bearing": 90, "distance": 50}]},
                ),
            ),
        ],
        edges=[],
    )

    compiled = compile_graph(graph)
    assert not compiled.gaps
    line1 = compiled.compiled_features["line1"]
    traverse2 = compiled.compiled_features["traverse2"]
    assert traverse2["start_point"] == line1["end_point"]


def test_compile_course_traverse_unresolved_explicit_operand_does_not_chain() -> None:
    from backend.feature_graph.gaps import GapKind

    graph = FeatureGraph(
        graph_id="g_missing_operand",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 90, "distance": 10},
                ),
            ),
            FeatureNode(
                id="parcel_2_traverse",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    operands=["missing_anchor"],
                    params={"courses": [{"bearing": 0, "distance": 5}]},
                ),
            ),
        ],
        edges=[],
    )

    compiled = compile_graph(graph)
    assert "parcel_2_traverse" not in compiled.compiled_features
    assert len(compiled.gaps) == 1
    gap = compiled.gaps[0]
    assert gap.kind == GapKind.PRECONDITION_FAILED
    assert gap.metadata["operand_id"] == "missing_anchor"


def _chained_traverse_with_explicit_operand_graph(*, operands: list[Any]) -> FeatureGraph:
    return FeatureGraph(
        graph_id="g_explicit_operand_edge",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    params={"bearing": 90, "distance": 10},
                ),
            ),
            FeatureNode(
                id="parcel_2_traverse",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    operands=operands,
                    params={"courses": [{"bearing": 0, "distance": 5}]},
                ),
            ),
        ],
        edges=[],
    )


def test_compile_course_traverse_blank_operand_does_not_chain() -> None:
    from backend.feature_graph.gaps import GapKind

    compiled = compile_graph(_chained_traverse_with_explicit_operand_graph(operands=[""]))
    assert "parcel_2_traverse" not in compiled.compiled_features
    assert len(compiled.gaps) == 1
    gap = compiled.gaps[0]
    assert gap.kind == GapKind.PRECONDITION_FAILED
    assert gap.metadata["reason_code"] == "invalid_start_operand"
    line1_end = compiled.compiled_features["line1"]["end_point"]
    assert line1_end != [0.0, 0.0]


def test_compile_course_traverse_non_string_operand_does_not_chain() -> None:
    from backend.feature_graph.compiler import CompileResult, compile_course_traverse
    from backend.feature_graph.gaps import GapKind

    node = FeatureNode(
        id="parcel_2_traverse",
        kind=FeatureKind.CURVE,
        op_expr=OpExpr(op_name="CourseTraverse", params={"courses": [{"bearing": 0, "distance": 5}]}),
    )
    op_expr = OpExpr.model_construct(
        op_name="CourseTraverse",
        operands=[{"feature_id": "nested"}],
        params={"courses": [{"bearing": 0, "distance": 5}]},
    )
    result = CompileResult()
    compiled = compile_course_traverse(
        node,
        op_expr,
        {},
        previous_point=(10.0, 20.0),
        result=result,
    )
    assert compiled is None
    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.kind == GapKind.PRECONDITION_FAILED
    assert gap.metadata["reason_code"] == "invalid_start_operand"
    assert gap.metadata["operand_type"] == "dict"


def test_duplicate_schematic_tied_points_emit_warning_not_gap() -> None:
    graph = FeatureGraph(
        graph_id="g_overlap_anchors",
        nodes=[
            FeatureNode(
                id="parcel_1_pob",
                kind=FeatureKind.POINT,
                op_expr=OpExpr(op_name="TiedPoint", params={"tie": "schematic"}),
            ),
            FeatureNode(
                id="parcel_2_pob_anchor",
                kind=FeatureKind.POINT,
                op_expr=OpExpr(op_name="TiedPoint", params={"tie": "schematic"}),
            ),
        ],
        edges=[],
    )

    compiled = compile_graph(graph)
    assert "parcel_1_pob" in compiled.compiled_features
    assert "parcel_2_pob_anchor" in compiled.compiled_features
    assert not compiled.gaps
    assert any("share coordinates" in warning for warning in compiled.warnings)


def test_compile_collection_is_semantic_group_without_geometry() -> None:
    graph = FeatureGraph(
        graph_id="g_collection",
        nodes=[
            FeatureNode(id="a", kind=FeatureKind.POINT, geometry={"type": "Point", "coordinates": [0, 0]}),
            FeatureNode(id="b", kind=FeatureKind.POINT, geometry={"type": "Point", "coordinates": [1, 1]}),
            FeatureNode(
                id="group_1",
                kind=FeatureKind.ANNOTATION,
                op_expr=OpExpr(op_name="Collection", operands=["a", "b"]),
            ),
        ],
        edges=[],
    )

    compiled = compile_graph(graph)
    group = compiled.compiled_features.get("group_1")
    assert isinstance(group, dict)
    assert group.get("source") == "semantic_group"
    assert "geometry" not in group
    assert isinstance(group.get("members"), list) and len(group["members"]) == 2

    judge = judge_graph(graph)
    unsupported = [g for g in judge.gaps if g.kind.value == "unsupported_operation"]
    assert not unsupported
