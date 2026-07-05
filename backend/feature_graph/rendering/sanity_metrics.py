"""Mechanical geometry metrics for rendered feature-graph mapping outputs."""

from __future__ import annotations

import math
from typing import Any, Mapping

from .contracts import bounds_from_coordinates


def _euclidean_distance(start: list[float], end: list[float]) -> float:
    return math.hypot(float(end[0]) - float(start[0]), float(end[1]) - float(start[1]))


def _polyline_length(coords: list[list[float]]) -> float:
    total = 0.0
    for index in range(1, len(coords)):
        total += _euclidean_distance(coords[index - 1], coords[index])
    return total


def _round_point(point: list[float]) -> list[float]:
    return [round(float(point[0]), 4), round(float(point[1]), 4)]


def _parse_coord_pair(item: Any) -> list[float] | None:
    if not isinstance(item, list) or len(item) < 2:
        return None
    try:
        x = float(item[0])
        y = float(item[1])
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    return [x, y]


def compute_feature_geometry_metrics(
    *,
    feature_id: str,
    compiled_entry: Mapping[str, Any],
) -> dict[str, Any]:
    """Return mechanical geometry facts for one compiled feature entry."""
    geometry = compiled_entry.get("geometry")
    if not isinstance(geometry, Mapping):
        return {
            "feature_id": feature_id,
            "skipped": True,
            "reason": "missing_geometry",
        }

    geom_type = str(geometry.get("type") or "")
    coords_raw = geometry.get("coordinates")
    if geom_type == "LineString":
        if not isinstance(coords_raw, list) or len(coords_raw) < 2:
            return {
                "feature_id": feature_id,
                "skipped": True,
                "reason": "insufficient_coordinates",
            }
        coords: list[list[float]] = []
        for item in coords_raw:
            parsed = _parse_coord_pair(item)
            if parsed is None:
                return {
                    "feature_id": feature_id,
                    "skipped": True,
                    "reason": "invalid_coordinates",
                }
            coords.append(parsed)
        start = coords[0]
        end = coords[-1]
        endpoint_displacement = _euclidean_distance(start, end)
        total_length = _polyline_length(coords)
        bounds = bounds_from_coordinates([(c[0], c[1]) for c in coords])
        payload: dict[str, Any] = {
            "feature_id": feature_id,
            "geometry_type": geom_type,
            "vertex_count": len(coords),
            "start_point": _round_point(start),
            "end_point": _round_point(end),
            "endpoint_displacement": round(endpoint_displacement, 4),
            "total_length": round(total_length, 4),
        }
        if bounds is not None:
            payload["bbox"] = bounds.to_dict()
        return payload

    if geom_type == "Point":
        if not isinstance(coords_raw, list) or len(coords_raw) < 2:
            return {
                "feature_id": feature_id,
                "skipped": True,
                "reason": "invalid_coordinates",
            }
        point = _parse_coord_pair(coords_raw)
        if point is None:
            return {
                "feature_id": feature_id,
                "skipped": True,
                "reason": "invalid_coordinates",
            }
        bounds = bounds_from_coordinates([(point[0], point[1])])
        payload = {
            "feature_id": feature_id,
            "geometry_type": geom_type,
            "vertex_count": 1,
            "start_point": _round_point(point),
            "end_point": _round_point(point),
            "endpoint_displacement": 0.0,
            "total_length": 0.0,
        }
        if bounds is not None:
            payload["bbox"] = bounds.to_dict()
        return payload

    if geom_type == "Polygon":
        if not isinstance(coords_raw, list) or not coords_raw:
            return {
                "feature_id": feature_id,
                "skipped": True,
                "reason": "insufficient_coordinates",
            }
        ring = coords_raw[0]
        if not isinstance(ring, list) or len(ring) < 3:
            return {
                "feature_id": feature_id,
                "skipped": True,
                "reason": "insufficient_coordinates",
            }
        coords = []
        for item in ring:
            parsed = _parse_coord_pair(item)
            if parsed is None:
                return {
                    "feature_id": feature_id,
                    "skipped": True,
                    "reason": "invalid_coordinates",
                }
            coords.append(parsed)
        start = coords[0]
        end = coords[-1]
        endpoint_displacement = _euclidean_distance(start, end)
        total_length = _polyline_length(coords)
        bounds = bounds_from_coordinates([(c[0], c[1]) for c in coords])
        payload = {
            "feature_id": feature_id,
            "geometry_type": geom_type,
            "vertex_count": len(coords),
            "start_point": _round_point(start),
            "end_point": _round_point(end),
            "endpoint_displacement": round(endpoint_displacement, 4),
            "total_length": round(total_length, 4),
        }
        if bounds is not None:
            payload["bbox"] = bounds.to_dict()
        return payload

    return {
        "feature_id": feature_id,
        "skipped": True,
        "reason": "unsupported_geometry_type",
        "geometry_type": geom_type or None,
    }


def build_endpoint_displacement_candidates(
    feature_metrics: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Mechanically rank features by endpoint displacement (largest first)."""
    candidates: list[dict[str, Any]] = []
    for metric in feature_metrics:
        if metric.get("skipped"):
            continue
        displacement = metric.get("endpoint_displacement")
        if not isinstance(displacement, (int, float)):
            continue
        if displacement <= 1e-6:
            continue
        row: dict[str, Any] = {
            "feature_id": metric.get("feature_id"),
            "endpoint_displacement": displacement,
            "geometry_type": metric.get("geometry_type"),
        }
        total_length = metric.get("total_length")
        if isinstance(total_length, (int, float)):
            row["total_length"] = total_length
        candidates.append(row)
    candidates.sort(key=lambda item: float(item.get("endpoint_displacement") or 0.0), reverse=True)
    return candidates[:limit]
