"""Timeline rendering helpers for point crop set tool outputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MAX_POINT_CROP_TIMELINE_POINTS = 16


def render_point_crop_set_tool_output(outputs: Mapping[str, Any]) -> list[str]:
    """Mechanically render point_crops / point_crops_adjust / point_crops_view outputs."""
    sub_action = str(outputs.get("sub_action") or "").strip()
    if sub_action not in {"point_crops", "point_crops_adjust", "point_crops_view"}:
        return []

    crop_set = outputs.get("crop_set")
    if not isinstance(crop_set, Mapping):
        return []

    lines = ["Point Crop Set"]
    lines.append(f"  sub_action: {sub_action}")
    master_ref = outputs.get("derived_ref_id") or crop_set.get("master_overlay_ref")
    if master_ref:
        lines.append(f"  master_overlay_ref: {master_ref}")
    source_ref = crop_set.get("source_ref") or outputs.get("parent_ref_id")
    if source_ref:
        lines.append(f"  source_ref: {source_ref}")

    previous = crop_set.get("previous_crop_set_overlay_ref") or outputs.get(
        "previous_crop_set_overlay_ref"
    )
    if previous:
        lines.append(f"  previous_crop_set_overlay_ref: {previous}")
    view_of = crop_set.get("view_of_crop_set_overlay_ref") or outputs.get(
        "view_of_crop_set_overlay_ref"
    )
    if view_of:
        lines.append(f"  view_of_crop_set_overlay_ref: {view_of}")

    points = crop_set.get("points") or outputs.get("crop_records") or []
    if isinstance(points, list):
        lines.append(f"  point_count: {len(points)}")
        for pt in points[:MAX_POINT_CROP_TIMELINE_POINTS]:
            if not isinstance(pt, Mapping):
                continue
            letter = pt.get("letter") or "?"
            alias = pt.get("alias") or "?"
            size = pt.get("size") or "?"
            shape = pt.get("shape") or "?"
            crop_ref = pt.get("crop_ref") or "none"
            point_norm = pt.get("point_norm")
            box_px = pt.get("box_px")
            graph_ref = pt.get("graph_ref")
            lines.append(
                f"    - {letter} | {alias} | {size} {shape} | crop_ref: {crop_ref}"
            )
            if isinstance(point_norm, list) and len(point_norm) == 2:
                lines.append(f"      point_norm: [{point_norm[0]}, {point_norm[1]}]")
            if isinstance(box_px, list) and len(box_px) == 4:
                lines.append(f"      box_px: [{box_px[0]}, {box_px[1]}, {box_px[2]}, {box_px[3]}]")
            if isinstance(graph_ref, Mapping) and graph_ref:
                pairs = ", ".join(f"{k}={v}" for k, v in list(graph_ref.items())[:4])
                lines.append(f"      graph_ref: {pairs}")

    adjustments = outputs.get("adjustments_applied") or crop_set.get("adjustments_applied")
    if isinstance(adjustments, list) and adjustments:
        lines.append("  adjustments_applied:")
        for adj in adjustments[:MAX_POINT_CROP_TIMELINE_POINTS]:
            if not isinstance(adj, Mapping):
                continue
            target = adj.get("target") or {}
            target_label = target.get("letter") or target.get("alias") or "?"
            prior = adj.get("prior_point_norm")
            new = adj.get("new_point_norm")
            lines.append(
                f"    - target: {target_label} | "
                f"prior_point_norm: {prior} -> new_point_norm: {new} | "
                f"size: {adj.get('prior_size')}->{adj.get('new_size')} | "
                f"shape: {adj.get('prior_shape')}->{adj.get('new_shape')}"
            )
            if adj.get("shift_norm") is not None:
                lines.append(f"      shift_norm: {adj.get('shift_norm')}")

    lines.append("")
    return lines
