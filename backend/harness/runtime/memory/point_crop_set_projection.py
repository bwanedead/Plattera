"""Compact prompt/audit projection for point crop set tool outputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MAX_POINT_CROP_SET_POINTS = 16
_POINT_CROP_SUB_ACTIONS = frozenset({"point_crops", "point_crops_adjust", "point_crops_view"})


def _compact_point_row(point: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "letter": point.get("letter"),
        "alias": point.get("alias"),
        "point_norm": point.get("point_norm"),
        "size": point.get("size"),
        "shape": point.get("shape"),
    }
    crop_ref = point.get("crop_ref")
    if isinstance(crop_ref, str) and crop_ref.strip():
        row["crop_ref"] = crop_ref.strip()
    graph_ref = point.get("graph_ref")
    if isinstance(graph_ref, Mapping) and graph_ref:
        row["graph_ref"] = {
            str(k): str(v)
            for k, v in list(graph_ref.items())[:8]
            if str(k).strip() and str(v).strip()
        }
    return {k: v for k, v in row.items() if v not in (None, "", [], {})}


def build_delegation_lines(points: list[Mapping[str, Any]]) -> list[str]:
    """Mechanical alias/letter -> crop_ref lines for delegate_subtask authoring."""
    lines: list[str] = []
    for point in points[:MAX_POINT_CROP_SET_POINTS]:
        if not isinstance(point, Mapping):
            continue
        letter = str(point.get("letter") or "").strip()
        alias = str(point.get("alias") or "").strip()
        crop_ref = point.get("crop_ref")
        if not letter or not alias or not isinstance(crop_ref, str) or not crop_ref.strip():
            continue
        lines.append(f"{letter} {alias} -> {crop_ref.strip()}")
    return lines


def project_point_crop_set_summary(outputs: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Extract a bounded crop-set summary from transform_artifact outputs."""
    if not isinstance(outputs, Mapping):
        return None
    sub_action = str(outputs.get("sub_action") or "").strip()
    if sub_action not in _POINT_CROP_SUB_ACTIONS:
        return None

    crop_set = outputs.get("crop_set")
    if not isinstance(crop_set, Mapping):
        return None

    master_overlay_ref = outputs.get("derived_ref_id") or crop_set.get("master_overlay_ref")
    if not isinstance(master_overlay_ref, str) or not master_overlay_ref.strip():
        return None

    source_ref = crop_set.get("source_ref") or outputs.get("parent_ref_id")
    raw_points = crop_set.get("points") or outputs.get("crop_records") or []
    if not isinstance(raw_points, list) or not raw_points:
        return None

    points = [
        _compact_point_row(pt)
        for pt in raw_points[:MAX_POINT_CROP_SET_POINTS]
        if isinstance(pt, Mapping)
    ]
    if not points:
        return None

    summary: dict[str, Any] = {
        "kind": "point_crop_set",
        "sub_action": sub_action,
        "master_overlay_ref": master_overlay_ref.strip(),
        "source_ref": str(source_ref).strip() if source_ref else None,
        "point_count": len(points),
        "points": points,
    }
    previous = crop_set.get("previous_crop_set_overlay_ref") or outputs.get(
        "previous_crop_set_overlay_ref"
    )
    if isinstance(previous, str) and previous.strip():
        summary["previous_crop_set_overlay_ref"] = previous.strip()
    view_of = crop_set.get("view_of_crop_set_overlay_ref") or outputs.get(
        "view_of_crop_set_overlay_ref"
    )
    if isinstance(view_of, str) and view_of.strip():
        summary["view_of_crop_set_overlay_ref"] = view_of.strip()

    adjustments = outputs.get("adjustments_applied") or crop_set.get("adjustments_applied")
    if isinstance(adjustments, list) and adjustments:
        summary["adjustments_applied"] = adjustments[:MAX_POINT_CROP_SET_POINTS]

    delegation_lines = build_delegation_lines(points)
    if delegation_lines:
        summary["delegation_lines"] = delegation_lines

    return {k: v for k, v in summary.items() if v not in (None, "", [], {})}
