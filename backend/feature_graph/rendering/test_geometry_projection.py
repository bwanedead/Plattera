"""Tests for geometry projection."""

from __future__ import annotations

from feature_graph.artifacts import create_compile_artifact
from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr
from feature_graph.rendering.geometry_projection import project_compiled_geometry


def _graph_with_mixed_features() -> FeatureGraph:
    return FeatureGraph(
        graph_id="g_proj",
        nodes=[
            FeatureNode(
                id="p1",
                kind=FeatureKind.POINT,
                label="origin",
                geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            ),
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                geometry={"type": "LineString", "coordinates": [[0.0, 0.0], [100.0, 0.0]]},
            ),
            FeatureNode(
                id="region1",
                kind=FeatureKind.REGION,
                geometry={
                    "type": "Polygon",
                    "coordinates": [[[0.0, 0.0], [100.0, 0.0], [100.0, 50.0], [0.0, 0.0]]],
                },
            ),
            FeatureNode(
                id="group1",
                kind=FeatureKind.ANNOTATION,
                op_expr=OpExpr(op_name="Collection", operands=["p1"]),
            ),
            FeatureNode(
                id="missing1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(op_name="Buffer", operands=["line1"], params={"distance": 5.0}),
            ),
        ],
        edges=[],
    )


def test_project_point_linestring_and_polygon() -> None:
    graph = _graph_with_mixed_features()
    compile_artifact = create_compile_artifact(
        artifact_id="compile_g_proj",
        graph_id=graph.graph_id,
        compiled_features={
            "p1": {"geometry": graph.nodes[0].geometry, "source": "direct"},
            "line1": {"geometry": graph.nodes[1].geometry, "source": "direct"},
            "region1": {"geometry": graph.nodes[2].geometry, "source": "direct"},
            "group1": {"source": "semantic_group", "group_kind": "collection", "members": []},
        },
        gaps=[{"kind": "unsupported_operation", "feature_id": "missing1", "message": "unsupported"}],
    )
    projection = project_compiled_geometry(graph=graph, compile_artifact=compile_artifact)
    features = projection.feature_collection["features"]
    assert [feature["properties"]["node_id"] for feature in features] == ["p1", "line1", "region1"]
    assert projection.rendered_feature_ids == ["p1", "line1", "region1"]
    assert {item.reason for item in projection.skipped_features} == {"semantic_group", "not_compiled"}
    assert projection.coordinate_space == "unspecified_local"


def test_project_preserves_exact_coordinates_and_order() -> None:
    graph = _graph_with_mixed_features()
    compile_artifact = create_compile_artifact(
        artifact_id="compile_g_proj",
        graph_id=graph.graph_id,
        compiled_features={
            "p1": {"geometry": graph.nodes[0].geometry, "source": "direct"},
            "line1": {"geometry": graph.nodes[1].geometry, "source": "direct"},
            "region1": {"geometry": graph.nodes[2].geometry, "source": "direct"},
        },
    )
    projection = project_compiled_geometry(graph=graph, compile_artifact=compile_artifact)
    line = projection.feature_collection["features"][1]
    assert line["geometry"]["coordinates"] == [[0.0, 0.0], [100.0, 0.0]]
    assert line["properties"]["graph_id"] == "g_proj"
    assert line["properties"]["render_order"] == 1


def test_malformed_geometry_produces_invalid_coordinates_skip() -> None:
    graph = FeatureGraph(
        graph_id="g_invalid_coords",
        nodes=[
            FeatureNode(
                id="good",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            ),
            FeatureNode(
                id="bad_point",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": ["x", 1.0]},
            ),
            FeatureNode(
                id="bad_nan",
                kind=FeatureKind.CURVE,
                geometry={"type": "LineString", "coordinates": [[0.0, 0.0], [float("nan"), 1.0]]},
            ),
        ],
        edges=[],
    )
    compile_artifact = create_compile_artifact(
        artifact_id="compile_invalid_coords",
        graph_id=graph.graph_id,
        compiled_features={
            "good": {"geometry": graph.nodes[0].geometry, "source": "direct"},
            "bad_point": {"geometry": graph.nodes[1].geometry, "source": "direct"},
            "bad_nan": {"geometry": graph.nodes[2].geometry, "source": "direct"},
        },
    )
    projection = project_compiled_geometry(graph=graph, compile_artifact=compile_artifact)
    assert projection.rendered_feature_ids == ["good"]
    assert {item.node_id for item in projection.skipped_features} == {"bad_point", "bad_nan"}
    assert all(item.reason == "invalid_geometry_coordinates" for item in projection.skipped_features)
