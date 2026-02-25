"""Compiler serviceable-path tests for metes-and-bounds authoring."""

from __future__ import annotations

import sys
from pathlib import Path

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
