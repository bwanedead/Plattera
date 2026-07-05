"""Tests for mechanical geometry sanity metrics."""

from __future__ import annotations

from feature_graph.artifacts import create_compile_artifact
from feature_graph.compiler import compile_graph
from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr
from feature_graph.provenance import ProvenanceAttachment, SourceEntityLink
from feature_graph.rendering.sanity_metrics import compute_feature_geometry_metrics


def _parcel1_courses(*, leg2_distance: float) -> list[dict]:
    return [
        {
            "bearing": 68.5,
            "distance": 542.0,
            "bearing_raw": "N. 68° 30' E.",
            "distance_raw": "542 feet",
        },
        {
            "bearing": 267.583333,
            "distance": leg2_distance,
            "bearing_raw": "S. 87° 35' W.",
            "distance_raw": f"{int(leg2_distance)} feet",
        },
        {
            "bearing": 176.0,
            "distance": 180.0,
            "bearing_raw": "S. 4°00' E.",
            "distance_raw": "180 feet",
        },
    ]


def _parcel1_graph(*, leg2_distance: float) -> FeatureGraph:
    return FeatureGraph(
        graph_id="parcel1_scope",
        nodes=[
            FeatureNode(
                id="pob",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            ),
            FeatureNode(
                id="parcel_1_traverse",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    operands=["pob"],
                    params={"courses": _parcel1_courses(leg2_distance=leg2_distance)},
                ),
                provenance=ProvenanceAttachment(
                    source_entity_links=[
                        SourceEntityLink(
                            entity_id="p1_call1_bearing",
                            entity_type="bearing",
                            source_ref="transcript_edit:resolution_state:test",
                        ),
                        SourceEntityLink(
                            entity_id="p1_call1_distance",
                            entity_type="distance",
                            source_ref="transcript_edit:resolution_state:test",
                        ),
                        SourceEntityLink(
                            entity_id="p1_call2_bearing",
                            entity_type="bearing",
                            source_ref="transcript_edit:resolution_state:test",
                        ),
                        SourceEntityLink(
                            entity_id="p1_call2_distance",
                            entity_type="distance",
                            source_ref="transcript_edit:resolution_state:test",
                        ),
                        SourceEntityLink(
                            entity_id="p1_call3_bearing",
                            entity_type="bearing",
                            source_ref="transcript_edit:resolution_state:test",
                        ),
                        SourceEntityLink(
                            entity_id="p1_call3_distance",
                            entity_type="distance",
                            source_ref="transcript_edit:resolution_state:test",
                        ),
                    ]
                ),
            ),
        ],
        edges=[],
    )


def _traverse_endpoint_displacement(*, leg2_distance: float) -> float:
    graph = _parcel1_graph(leg2_distance=leg2_distance)
    compiled = compile_graph(graph).compiled_features["parcel_1_traverse"]
    metric = compute_feature_geometry_metrics(
        feature_id="parcel_1_traverse",
        compiled_entry=compiled,
    )
    assert metric.get("skipped") is not True
    return float(metric["endpoint_displacement"])


def test_correct_518ft_traverse_endpoint_displacement_near_2_85() -> None:
    displacement = _traverse_endpoint_displacement(leg2_distance=518.0)
    assert 2.5 <= displacement <= 3.2


def test_corrupted_618ft_traverse_endpoint_displacement_near_100_85() -> None:
    displacement = _traverse_endpoint_displacement(leg2_distance=618.0)
    assert 95.0 <= displacement <= 106.0


def test_metrics_include_mechanical_fields_only() -> None:
    graph = _parcel1_graph(leg2_distance=518.0)
    compile_artifact = create_compile_artifact(
        artifact_id="compile_metrics",
        graph_id=graph.graph_id,
        compiled_features=compile_graph(graph).compiled_features,
    )
    entry = compile_artifact.compiled_features["parcel_1_traverse"]
    metric = compute_feature_geometry_metrics(feature_id="parcel_1_traverse", compiled_entry=entry)
    assert "wrong" not in str(metric).lower()
    assert "sane" not in str(metric).lower()
    assert metric["geometry_type"] == "LineString"
    assert metric["vertex_count"] == 4
    assert isinstance(metric["bbox"], dict)


def test_metrics_skip_invalid_linestring_coordinates() -> None:
    metric = compute_feature_geometry_metrics(
        feature_id="bad_traverse",
        compiled_entry={
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], ["north", 0.0]],
            }
        },
    )
    assert metric.get("skipped") is True
    assert metric.get("reason") == "invalid_coordinates"


def test_metrics_skip_non_finite_polygon_coordinates() -> None:
    metric = compute_feature_geometry_metrics(
        feature_id="bad_region",
        compiled_entry={
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0.0, 0.0], [float("inf"), 0.0], [0.0, 10.0], [0.0, 0.0]]],
            }
        },
    )
    assert metric.get("skipped") is True
    assert metric.get("reason") == "invalid_coordinates"
