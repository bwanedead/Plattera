"""Timeline rendering helpers for point crop set tool outputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tooling.mapping.transcript_edit.point_crop_target_mapping import format_target_mapping_parts
from tooling.mapping.transcript_edit.point_crop_review_table import (
    render_review_line,
    review_table_from_crop_set,
)
from tooling.mapping.transcript_edit.point_crop_key_band import build_point_key_lines

from harness.audit.artifact_ref_links import (
    ArtifactLinkContext,
    format_ref_with_link,
    inline_cap_notice,
    maybe_inline_thumbnail,
    resolve_artifact_image_link,
)

MAX_POINT_CROP_TIMELINE_POINTS = 16


def _fmt_pair(value: Any) -> str | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return f"[{value[0]}, {value[1]}]"
    return None


def _fmt_box(value: Any) -> str | None:
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return f"[{value[0]}, {value[1]}, {value[2]}, {value[3]}]"
    return None


def render_point_crop_set_tool_output(
    outputs: Mapping[str, Any],
    *,
    link_context: ArtifactLinkContext | None = None,
) -> list[str]:
    """Mechanically render point-crop transform outputs for audit timeline."""
    sub_action = str(outputs.get("sub_action") or "").strip()
    if sub_action not in {
        "point_crops",
        "point_crops_scaffold",
        "point_crops_adjust",
        "point_crops_view",
    }:
        return []

    crop_set = outputs.get("crop_set")
    if not isinstance(crop_set, Mapping):
        return []

    if sub_action == "point_crops_scaffold":
        lines = ["Point crop placement scaffold:"]
    else:
        lines = ["Point crop set:"]
    overlay_role = str(
        crop_set.get("overlay_role") or outputs.get("overlay_role") or ""
    ).strip()
    if overlay_role:
        lines.append(f"- overlay_role: {overlay_role}")

    lattice = crop_set.get("coordinate_lattice")
    if isinstance(lattice, Mapping):
        major = lattice.get("major_step_norm")
        minor = lattice.get("minor_step_norm")
        if major is not None and minor is not None:
            lines.append(f"- coordinate_lattice: major={major} minor={minor}")

    derived_ref = str(outputs.get("derived_ref_id") or crop_set.get("master_overlay_ref") or "").strip()
    if sub_action == "point_crops_view":
        if derived_ref:
            lines.append(
                f"- filtered view overlay: {_render_ref_line(derived_ref, link_context, label='open view')}"
            )
            if link_context is not None:
                view_link = resolve_artifact_image_link(derived_ref, link_context, link_label="open view")
                lines.extend(
                    maybe_inline_thumbnail(
                        derived_ref,
                        view_link,
                        link_context,
                        alt="point crop filtered view overlay",
                    )
                )
    elif sub_action == "point_crops_scaffold" and derived_ref:
        lines.append(
            f"- placement scaffold: {_render_ref_line(derived_ref, link_context, label='open scaffold')}"
        )
        if link_context is not None:
            scaffold_link = resolve_artifact_image_link(
                derived_ref, link_context, link_label="open scaffold"
            )
            lines.extend(
                maybe_inline_thumbnail(
                    derived_ref,
                    scaffold_link,
                    link_context,
                    alt="point crop placement scaffold",
                )
            )
    elif derived_ref:
        lines.append(f"- master overlay: {_render_ref_line(derived_ref, link_context, label='open overlay')}")
        if link_context is not None:
            master_link = resolve_artifact_image_link(derived_ref, link_context, link_label="open overlay")
            lines.extend(
                maybe_inline_thumbnail(
                    derived_ref,
                    master_link,
                    link_context,
                    alt="point crop master overlay",
                )
            )
        lines.extend(_render_point_key_section(crop_set, outputs))

    source_ref = str(crop_set.get("source_ref") or outputs.get("parent_ref_id") or "").strip()
    if source_ref:
        lines.append(f"- local source: {_render_ref_line(source_ref, link_context, label='open source')}")

    placement_surface_ref = str(
        crop_set.get("placement_surface_ref") or outputs.get("placement_surface_ref") or ""
    ).strip()
    if placement_surface_ref:
        lines.append(
            f"- placement_surface_ref: {_render_ref_line(placement_surface_ref, link_context, label='open placement surface')}"
        )

    source_unwrapped_from_ref = str(
        crop_set.get("source_unwrapped_from_ref") or outputs.get("source_unwrapped_from_ref") or ""
    ).strip()
    if source_unwrapped_from_ref and source_unwrapped_from_ref != placement_surface_ref:
        lines.append(
            f"- source_unwrapped_from_ref: {_render_ref_line(source_unwrapped_from_ref, link_context, label='open prior ref')}"
        )

    if placement_surface_ref and source_ref and placement_surface_ref != source_ref:
        lines.append(f"- source_lineage: placed_from={placement_surface_ref} · cropped_from={source_ref}")

    legacy_source_repaired = crop_set.get("legacy_source_repaired", outputs.get("legacy_source_repaired"))
    if legacy_source_repaired is True:
        warning = str(
            crop_set.get("legacy_source_repair_warning")
            or outputs.get("legacy_source_repair_warning")
            or ""
        ).strip()
        lines.append(f"- legacy_source_repaired: yes{f' · {warning[:120]}' if warning else ''}")

    point_count_raw = crop_set.get("point_count", outputs.get("point_count"))
    try:
        point_count = int(point_count_raw) if point_count_raw is not None else None
    except (TypeError, ValueError):
        point_count = None
    if point_count is not None:
        lines.append(f"- point_count: {point_count}")

    grid = crop_set.get("grid")
    legend = crop_set.get("legend")
    grid_enabled = isinstance(grid, Mapping) and grid.get("enabled") is True
    legend_present = isinstance(legend, Mapping) and bool(legend.get("size_colors"))
    if grid_enabled or legend_present:
        grid_text = "yes" if grid_enabled else "no"
        legend_text = "yes" if legend_present else "no"
        lines.append(f"- overlay grid: {grid_text} · legend: {legend_text}")

    previous = str(
        crop_set.get("previous_crop_set_overlay_ref")
        or outputs.get("previous_crop_set_overlay_ref")
        or ""
    ).strip()
    if previous:
        lines.append(
            f"- previous_crop_set_overlay_ref: {_render_ref_line(previous, link_context, label='open overlay')}"
        )

    view_of = str(
        crop_set.get("view_of_crop_set_overlay_ref")
        or outputs.get("view_of_crop_set_overlay_ref")
        or ""
    ).strip()
    if view_of:
        lines.append(
            f"- view_of_crop_set_overlay_ref: {_render_ref_line(view_of, link_context, label='open prior overlay')}"
        )

    points = crop_set.get("points") or outputs.get("crop_records") or []
    if isinstance(points, list) and points:
        lines.append("- points:")
        for pt in points[:MAX_POINT_CROP_TIMELINE_POINTS]:
            if not isinstance(pt, Mapping):
                continue
            lines.extend(_render_point_row(pt, link_context=link_context))

    if sub_action != "point_crops_scaffold":
        lines.extend(_render_review_table_section(crop_set, link_context=link_context))

    adjustments = outputs.get("adjustments_applied") or crop_set.get("adjustments_applied")
    if isinstance(adjustments, list) and adjustments:
        lines.append("- adjustments_applied:")
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
            scale_part = ""
            if adj.get("prior_scale_x") is not None or adj.get("new_scale_x") is not None:
                scale_part = (
                    f" | scale_x: {adj.get('prior_scale_x')}->{adj.get('new_scale_x')}"
                )
            if adj.get("prior_scale_y") is not None or adj.get("new_scale_y") is not None:
                scale_part = (
                    f"{scale_part} | scale_y: {adj.get('prior_scale_y')}->{adj.get('new_scale_y')}"
                )
            lines.append(
                f"  - target: {target_label} | "
                f"prior_point_norm: {prior} -> new_point_norm: {new} | "
                f"size: {adj.get('prior_size')}->{adj.get('new_size')} | "
                f"shape: {adj.get('prior_shape')}->{adj.get('new_shape')}{zoom_part}{scale_part}"
            )
            if adj.get("shift_norm") is not None:
                lines.append(f"    shift_norm: {adj.get('shift_norm')}")

    if link_context is not None:
        notice = inline_cap_notice(link_context)
        if notice:
            lines.append(notice)

    lines.append("")
    return lines


def _render_point_key_section(
    crop_set: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> list[str]:
    points = crop_set.get("points") or outputs.get("crop_records") or []
    point_key_lines = crop_set.get("point_key_lines")
    if not isinstance(point_key_lines, list) or not point_key_lines:
        if isinstance(points, list) and points:
            table = build_point_key_lines(points)
            point_key_lines = table.get("point_key_lines")
    if not isinstance(point_key_lines, list) or not point_key_lines:
        return []

    lines = ["Point key:"]
    for line in point_key_lines[:MAX_POINT_CROP_TIMELINE_POINTS]:
        lines.append(f"- {line}")
    return lines


def _render_review_table_section(
    crop_set: Mapping[str, Any],
    *,
    link_context: ArtifactLinkContext | None,
) -> list[str]:
    table = review_table_from_crop_set(crop_set)
    review_rows = table.get("review_rows")
    review_lines = table.get("review_lines")
    if not review_rows and not review_lines:
        return []

    lines = ["Review table:"]
    if isinstance(review_rows, list) and review_rows:
        for row in review_rows[:MAX_POINT_CROP_TIMELINE_POINTS]:
            if not isinstance(row, Mapping):
                continue
            line = render_review_line(row)
            crop_ref = str(row.get("crop_ref") or "").strip()
            if crop_ref and link_context is not None:
                linked = _render_ref_line(crop_ref, link_context, label="open crop")
                line = line.replace(f"crop={crop_ref}", f"crop: {linked}")
            lines.append(f"- {line}")
        return lines

    if isinstance(review_lines, list):
        for line in review_lines[:MAX_POINT_CROP_TIMELINE_POINTS]:
            lines.append(f"- {line}")
    return lines


def _render_point_row(
    pt: Mapping[str, Any],
    *,
    link_context: ArtifactLinkContext | None,
) -> list[str]:
    letter = pt.get("letter") or "?"
    alias = pt.get("alias") or "?"
    crop_ref = str(pt.get("crop_ref") or "").strip()
    root_point_norm = _fmt_pair(pt.get("root_point_norm"))
    zoom_factor = pt.get("zoom_factor")
    suffix_parts: list[str] = []
    if root_point_norm:
        suffix_parts.append(f"root={root_point_norm}")
    if zoom_factor is not None:
        suffix_parts.append(f"zoom={zoom_factor}")
    suffix = f" {' '.join(suffix_parts)}" if suffix_parts else ""
    crop_text = _render_ref_line(crop_ref, link_context, label="open crop") if crop_ref else "none"
    lines = [f"  - {letter} `{alias}` -> {crop_text}{suffix}"]
    target_parts = format_target_mapping_parts(pt)
    if target_parts:
        lines.append(f"    target_mapping: {' '.join(target_parts)}")

    point_norm = _fmt_pair(pt.get("point_norm")) or _fmt_pair(pt.get("local_point_norm"))
    if point_norm:
        lines.append(f"    local_point_norm: {point_norm}")
    box_norm = _fmt_box(pt.get("box_norm")) or _fmt_box(pt.get("local_box_norm"))
    if box_norm:
        lines.append(f"    local_box_norm: {box_norm}")

    if pt.get("projection_available") is True:
        root_source_ref = str(pt.get("root_source_ref") or "").strip()
        if root_source_ref:
            lines.append(
                f"    root_source_ref: {_render_ref_line(root_source_ref, link_context, label='open source')}"
            )
        root_point = _fmt_pair(pt.get("root_point_norm"))
        if root_point and "root=" not in suffix:
            lines.append(f"    root_point_norm: {root_point}")
        root_box = _fmt_box(pt.get("root_box_norm"))
        if root_box:
            lines.append(f"    root_box_norm: {root_box}")
    elif pt.get("projection_available") is False:
        reason = str(pt.get("projection_unavailable_reason") or "").strip()
        if reason:
            lines.append(f"    projection_unavailable: {reason[:120]}")

    graph_ref = pt.get("graph_ref")
    if isinstance(graph_ref, Mapping) and graph_ref:
        pairs = ", ".join(f"{k}={v}" for k, v in list(graph_ref.items())[:4])
        lines.append(f"    graph_ref: {pairs}")
    return lines


def _render_ref_line(
    ref_id: str,
    link_context: ArtifactLinkContext | None,
    *,
    label: str,
) -> str:
    if not ref_id:
        return "none"
    if link_context is None:
        return f"`{ref_id}`"
    link = resolve_artifact_image_link(ref_id, link_context, link_label=label)
    return format_ref_with_link(ref_id, link, link_label=label)
