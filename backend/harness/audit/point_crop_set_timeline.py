"""Timeline rendering helpers for point crop set tool outputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MAX_POINT_CROP_TIMELINE_POINTS = 16


def _fmt_pair(value: Any) -> str | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return f"[{value[0]}, {value[1]}]"
    return None


def _fmt_box(value: Any) -> str | None:
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return f"[{value[0]}, {value[1]}, {value[2]}, {value[3]}]"
    return None


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
        lines.append(f"  local_source_ref: {source_ref}")

    grid = crop_set.get("grid")
    if isinstance(grid, Mapping) and grid.get("enabled") is True:
        divisions = grid.get("divisions")
        lines.append(f"  overlay_grid: enabled divisions={divisions}")
    legend = crop_set.get("legend")
    if isinstance(legend, Mapping) and legend.get("size_colors"):
        lines.append("  overlay_legend: size_colors present")

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
            zoom_factor = pt.get("zoom_factor")
            zoom_text = f" zoom={zoom_factor}" if zoom_factor is not None else ""
            lines.append(
                f"    - {letter} | {alias} | {size} {shape}{zoom_text} | crop_ref: {crop_ref}"
            )
            point_norm = _fmt_pair(pt.get("point_norm")) or _fmt_pair(pt.get("local_point_norm"))
            if point_norm:
                lines.append(f"      local_point_norm: {point_norm}")
            box_norm = _fmt_box(pt.get("box_norm")) or _fmt_box(pt.get("local_box_norm"))
            if box_norm:
                lines.append(f"      local_box_norm: {box_norm}")

            if pt.get("projection_available") is True:
                root_source_ref = pt.get("root_source_ref")
                if root_source_ref:
                    lines.append(f"      root_source_ref: {root_source_ref}")
                root_point_norm = _fmt_pair(pt.get("root_point_norm"))
                if root_point_norm:
                    lines.append(f"      root_point_norm: {root_point_norm}")
                root_box_norm = _fmt_box(pt.get("root_box_norm"))
                if root_box_norm:
                    lines.append(f"      root_box_norm: {root_box_norm}")
            elif pt.get("projection_available") is False:
                reason = str(pt.get("projection_unavailable_reason") or "").strip()
                if reason:
                    lines.append(f"      projection_unavailable: {reason[:120]}")

            graph_ref = pt.get("graph_ref")
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
            zoom_part = ""
            if adj.get("prior_zoom_factor") is not None or adj.get("new_zoom_factor") is not None:
                zoom_part = (
                    f" | zoom: {adj.get('prior_zoom_factor')}->{adj.get('new_zoom_factor')}"
                )
            lines.append(
                f"    - target: {target_label} | "
                f"prior_point_norm: {prior} -> new_point_norm: {new} | "
                f"size: {adj.get('prior_size')}->{adj.get('new_size')} | "
                f"shape: {adj.get('prior_shape')}->{adj.get('new_shape')}{zoom_part}"
            )
            if adj.get("shift_norm") is not None:
                lines.append(f"      shift_norm: {adj.get('shift_norm')}")

    lines.append("")
    return lines
