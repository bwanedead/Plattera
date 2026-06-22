"""Project compiled feature-graph outputs into deterministic GeoJSON."""

from __future__ import annotations

import math
from typing import Any

from feature_graph.artifacts import CompileArtifact
from feature_graph.models import FeatureGraph

from .contracts import (
    SUPPORTED_GEOMETRY_TYPES,
    GeometryProjection,
    SkippedFeature,
    WorldBounds,
    bounds_from_coordinates,
    merge_bounds,
    resolve_coordinate_space,
)


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _parse_coord_pair(item: Any) -> tuple[float, float] | None:
    if not isinstance(item, (list, tuple)) or len(item) < 2:
        return None
    x = _finite_float(item[0])
    y = _finite_float(item[1])
    if x is None or y is None:
        return None
    return (x, y)


def _collect_geometry_coords(geometry: dict[str, Any]) -> tuple[list[tuple[float, float]], str | None]:
    geom_type = geometry.get("type")
    coords_raw = geometry.get("coordinates")
    points: list[tuple[float, float]] = []

    if geom_type == "Point":
        pair = _parse_coord_pair(coords_raw)
        if pair is None:
            return [], "invalid_geometry_coordinates"
        return [pair], None

    if geom_type == "LineString":
        if not isinstance(coords_raw, list):
            return [], "invalid_geometry_coordinates"
        for item in coords_raw:
            pair = _parse_coord_pair(item)
            if pair is None:
                return [], "invalid_geometry_coordinates"
            points.append(pair)
        return points, None

    if geom_type == "Polygon":
        if not isinstance(coords_raw, list) or not coords_raw:
            return [], "invalid_geometry_coordinates"
        for ring in coords_raw:
            if not isinstance(ring, list) or len(ring) < 3:
                return [], "invalid_geometry_coordinates"
            for item in ring:
                pair = _parse_coord_pair(item)
                if pair is None:
                    return [], "invalid_geometry_coordinates"
                points.append(pair)
        return points, None

    return [], "invalid_geometry_coordinates"


def _compiled_entry(compiled_features: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    entry = compiled_features.get(node_id)
    return entry if isinstance(entry, dict) else None


def project_compiled_geometry(
    *,
    graph: FeatureGraph,
    compile_artifact: CompileArtifact,
) -> GeometryProjection:
    compiled_features = compile_artifact.compiled_features or {}
    features: list[dict[str, Any]] = []
    rendered_feature_ids: list[str] = []
    skipped_features: list[SkippedFeature] = []
    bounds: WorldBounds | None = None

    for index, node in enumerate(graph.nodes):
        entry = _compiled_entry(compiled_features, node.id)
        if entry is None:
            skipped_features.append(
                SkippedFeature(
                    node_id=node.id,
                    graph_id=graph.graph_id,
                    kind=node.kind.value,
                    reason="not_compiled",
                )
            )
            continue

        if entry.get("source") == "semantic_group":
            skipped_features.append(
                SkippedFeature(
                    node_id=node.id,
                    graph_id=graph.graph_id,
                    kind=node.kind.value,
                    reason="semantic_group",
                    metadata={"group_kind": entry.get("group_kind")},
                )
            )
            continue

        geometry = entry.get("geometry")
        if not isinstance(geometry, dict):
            skipped_features.append(
                SkippedFeature(
                    node_id=node.id,
                    graph_id=graph.graph_id,
                    kind=node.kind.value,
                    reason="missing_geometry",
                )
            )
            continue

        geom_type = geometry.get("type")
        if geom_type not in SUPPORTED_GEOMETRY_TYPES:
            skipped_features.append(
                SkippedFeature(
                    node_id=node.id,
                    graph_id=graph.graph_id,
                    kind=node.kind.value,
                    reason="unsupported_geometry_type",
                    metadata={"geometry_type": geom_type},
                )
            )
            continue

        coord_points, coord_error = _collect_geometry_coords(geometry)
        if coord_error is not None:
            skipped_features.append(
                SkippedFeature(
                    node_id=node.id,
                    graph_id=graph.graph_id,
                    kind=node.kind.value,
                    reason=coord_error,
                    metadata={"geometry_type": geom_type},
                )
            )
            continue
        if not coord_points:
            skipped_features.append(
                SkippedFeature(
                    node_id=node.id,
                    graph_id=graph.graph_id,
                    kind=node.kind.value,
                    reason="empty_geometry",
                    metadata={"geometry_type": geom_type},
                )
            )
            continue

        feature_bounds = bounds_from_coordinates(coord_points)
        if feature_bounds is not None:
            bounds = feature_bounds if bounds is None else merge_bounds(bounds, feature_bounds)

        properties: dict[str, Any] = {
            "graph_id": graph.graph_id,
            "node_id": node.id,
            "kind": node.kind.value,
            "render_order": index,
        }
        if node.label:
            properties["label"] = node.label
        if entry.get("start_point") is not None:
            properties["start_point"] = entry.get("start_point")
        if entry.get("end_point") is not None:
            properties["end_point"] = entry.get("end_point")
        if isinstance(entry.get("courses"), list):
            properties["courses"] = entry.get("courses")

        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": properties,
            }
        )
        rendered_feature_ids.append(node.id)

    if bounds is None:
        bounds = WorldBounds(min_x=0.0, min_y=0.0, max_x=0.0, max_y=0.0)

    coordinate_space = resolve_coordinate_space(
        graph.metadata,
        compile_artifact.compilation_metadata,
    )

    return GeometryProjection(
        feature_collection={
            "type": "FeatureCollection",
            "features": features,
        },
        rendered_feature_ids=rendered_feature_ids,
        skipped_features=skipped_features,
        world_bounds=bounds,
        coordinate_space=coordinate_space,
    )
