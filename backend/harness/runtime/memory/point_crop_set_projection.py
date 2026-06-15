"""Compact prompt/audit projection for point crop set tool outputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tooling.mapping.transcript_edit.point_crop_review_table import review_table_from_crop_set
from tooling.mapping.transcript_edit.point_crop_key_band import build_point_key_lines

MAX_POINT_CROP_SET_POINTS = 16
_MAX_PROJECTION_REASON_CHARS = 120
_POINT_CROP_SUB_ACTIONS = frozenset({
    "point_crops",
    "point_crops_scaffold",
    "point_crops_adjust",
    "point_crops_view",
})
_STRIP_POINT_KEYS = frozenset({
    "absolute_path",
    "b64",
    "crop_img",
    "color",
    "box_px",
    "local_box_px",
    "root_box_px",
    "unzoomed_width_height",
    "output_width_height",
    "projection_chain",
    "local_source_width_height",
    "root_source_width_height",
})


def _norm_pair(value: Any) -> list[float] | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return [round(float(value[0]), 4), round(float(value[1]), 4)]
        except (TypeError, ValueError):
            return None
    return None


def _norm_box(value: Any) -> list[float] | None:
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            return [round(float(v), 4) for v in value]
        except (TypeError, ValueError):
            return None
    return None


def _compact_point_row(point: Mapping[str, Any]) -> dict[str, Any]:
    point_norm = _norm_pair(point.get("point_norm")) or _norm_pair(point.get("local_point_norm"))
    box_norm = _norm_box(point.get("box_norm")) or _norm_box(point.get("local_box_norm"))

    row: dict[str, Any] = {
        "letter": point.get("letter"),
        "alias": point.get("alias"),
        "size": point.get("size"),
        "shape": point.get("shape"),
    }
    crop_intent = point.get("crop_intent")
    if isinstance(crop_intent, str) and crop_intent.strip():
        row["crop_intent"] = crop_intent.strip()
    if point.get("trim_to_text_block") is True:
        row["trim_to_text_block"] = True
        if point.get("trim_applied") is True:
            row["trim_applied"] = True
        elif point.get("trim_applied") is False:
            row["trim_applied"] = False
        trim_warning = point.get("trim_warning")
        if isinstance(trim_warning, str) and trim_warning.strip():
            row["trim_warning"] = trim_warning.strip()[:120]
        pre_trim = _norm_box(point.get("pre_trim_box_norm"))
        if pre_trim is not None:
            row["pre_trim_box_norm"] = pre_trim
        text_bounds = point.get("text_block_bounds_norm")
        if isinstance(text_bounds, (list, tuple)) and len(text_bounds) == 2:
            try:
                row["text_block_bounds_norm"] = [
                    round(float(text_bounds[0]), 4),
                    round(float(text_bounds[1]), 4),
                ]
            except (TypeError, ValueError):
                pass
    elif point.get("trim_to_text_block") is False:
        row["trim_to_text_block"] = False
    if point_norm is not None:
        row["point_norm"] = point_norm
    if box_norm is not None:
        row["box_norm"] = box_norm

    crop_ref = point.get("crop_ref")
    if isinstance(crop_ref, str) and crop_ref.strip():
        row["crop_ref"] = crop_ref.strip()

    zoom_factor = point.get("zoom_factor")
    if zoom_factor is not None:
        try:
            row["zoom_factor"] = round(float(zoom_factor), 4)
        except (TypeError, ValueError):
            pass

    graph_ref = point.get("graph_ref")
    if isinstance(graph_ref, Mapping) and graph_ref:
        row["graph_ref"] = {
            str(k): str(v)
            for k, v in list(graph_ref.items())[:8]
            if str(k).strip() and str(v).strip()
        }

    projection_available = point.get("projection_available")
    if projection_available is True:
        row["projection_available"] = True
        root_source_ref = point.get("root_source_ref")
        if isinstance(root_source_ref, str) and root_source_ref.strip():
            row["root_source_ref"] = root_source_ref.strip()
        root_point_norm = _norm_pair(point.get("root_point_norm"))
        if root_point_norm is not None:
            row["root_point_norm"] = root_point_norm
        root_box_norm = _norm_box(point.get("root_box_norm"))
        if root_box_norm is not None:
            row["root_box_norm"] = root_box_norm
    elif projection_available is False:
        row["projection_available"] = False
        reason = str(point.get("projection_unavailable_reason") or "").strip()
        if reason:
            row["projection_unavailable_reason"] = reason[:_MAX_PROJECTION_REASON_CHARS]

    for key in (
        "crop_frame_room_norm",
        "crop_frame_touches_edge",
        "crop_frame_can_expand",
        "root_crop_frame_room_norm",
        "root_crop_frame_touches_edge",
        "root_crop_frame_can_expand",
    ):
        value = point.get(key)
        if value not in (None, "", [], {}):
            row[key] = value

    return {
        k: v
        for k, v in row.items()
        if k not in _STRIP_POINT_KEYS and v not in (None, "", [], {})
    }


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
        line = f"{letter} {alias} -> {crop_ref.strip()}"
        extras: list[str] = []
        root_point_norm = _norm_pair(point.get("root_point_norm"))
        if root_point_norm is not None:
            extras.append(f"root=[{root_point_norm[0]},{root_point_norm[1]}]")
        zoom_factor = point.get("zoom_factor")
        if zoom_factor is not None:
            try:
                extras.append(f"zoom={round(float(zoom_factor), 4)}")
            except (TypeError, ValueError):
                pass
        if extras:
            line = f"{line} {' '.join(extras)}"
        lines.append(line)
    return lines


def _compact_coordinate_lattice(crop_set: Mapping[str, Any]) -> dict[str, Any] | None:
    lattice = crop_set.get("coordinate_lattice")
    if not isinstance(lattice, Mapping):
        return None
    compact: dict[str, Any] = {}
    for key in ("major_step_norm", "minor_step_norm"):
        if lattice.get(key) is not None:
            compact[key] = lattice[key]
    return compact or None


def _compact_overlay_markers(crop_set: Mapping[str, Any]) -> dict[str, Any]:
    markers: dict[str, Any] = {}
    lattice = _compact_coordinate_lattice(crop_set)
    if lattice:
        markers["coordinate_lattice"] = lattice
    grid = crop_set.get("grid")
    if isinstance(grid, Mapping) and grid.get("enabled") is True:
        markers["grid"] = {
            "enabled": True,
            "divisions": grid.get("divisions"),
            "coordinate_space": grid.get("coordinate_space"),
        }
    legend = crop_set.get("legend")
    if isinstance(legend, Mapping) and legend.get("size_colors"):
        size_colors = legend.get("size_colors")
        if isinstance(size_colors, Mapping):
            markers["legend"] = {"size_colors": sorted(str(k) for k in size_colors.keys())}
    return markers


def _overlay_role_for_summary(
    outputs: Mapping[str, Any],
    crop_set: Mapping[str, Any],
    *,
    sub_action: str,
) -> str:
    for container in (crop_set, outputs):
        role = container.get("overlay_role")
        if isinstance(role, str) and role.strip():
            return role.strip()
    if sub_action == "point_crops_scaffold":
        return "point_crop_placement_scaffold"
    if sub_action == "point_crops_view":
        return "point_crop_view"
    return "point_crop_master"


def _ref_field(container: Mapping[str, Any], key: str) -> str | None:
    raw = container.get(key)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _compact_source_lineage_fields(
    outputs: Mapping[str, Any],
    crop_set: Mapping[str, Any],
) -> dict[str, Any]:
    placement_surface_ref = _ref_field(crop_set, "placement_surface_ref") or _ref_field(
        outputs, "placement_surface_ref"
    )
    source_unwrapped_from_ref = _ref_field(crop_set, "source_unwrapped_from_ref") or _ref_field(
        outputs, "source_unwrapped_from_ref"
    )
    legacy_source_repaired = crop_set.get("legacy_source_repaired")
    if legacy_source_repaired is None:
        legacy_source_repaired = outputs.get("legacy_source_repaired")
    legacy_source_repair_warning = _ref_field(crop_set, "legacy_source_repair_warning") or _ref_field(
        outputs, "legacy_source_repair_warning"
    )

    fields: dict[str, Any] = {}
    if placement_surface_ref:
        fields["placement_surface_ref"] = placement_surface_ref
    if source_unwrapped_from_ref:
        fields["source_unwrapped_from_ref"] = source_unwrapped_from_ref
    if legacy_source_repaired is True:
        fields["legacy_source_repaired"] = True
    if legacy_source_repair_warning:
        fields["legacy_source_repair_warning"] = legacy_source_repair_warning[:_MAX_PROJECTION_REASON_CHARS]

    source_ref = _ref_field(crop_set, "source_ref") or _ref_field(outputs, "parent_ref_id")
    lineage_parts: list[str] = []
    if placement_surface_ref:
        lineage_parts.append(f"placed_from={placement_surface_ref}")
    if source_ref:
        lineage_parts.append(f"cropped_from={source_ref}")
    if lineage_parts and placement_surface_ref and source_ref and placement_surface_ref != source_ref:
        fields["source_lineage_line"] = " · ".join(lineage_parts)
    return fields


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
    if not isinstance(raw_points, list):
        return None

    points = [
        _compact_point_row(pt)
        for pt in raw_points[:MAX_POINT_CROP_SET_POINTS]
        if isinstance(pt, Mapping)
    ]
    point_count_raw = crop_set.get("point_count", outputs.get("point_count"))
    if sub_action == "point_crops_scaffold":
        if points:
            return None
        try:
            point_count = int(point_count_raw if point_count_raw is not None else 0)
        except (TypeError, ValueError):
            point_count = 0
        if point_count != 0:
            return None
    elif not points:
        return None
    else:
        point_count = len(points)

    summary: dict[str, Any] = {
        "kind": "point_crop_set",
        "sub_action": sub_action,
        "overlay_role": _overlay_role_for_summary(outputs, crop_set, sub_action=sub_action),
        "master_overlay_ref": master_overlay_ref.strip(),
        "source_ref": str(source_ref).strip() if source_ref else None,
        "point_count": point_count,
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

    summary.update(_compact_source_lineage_fields(outputs, crop_set))

    overlay_markers = _compact_overlay_markers(crop_set)
    summary.update(overlay_markers)

    adjustments = outputs.get("adjustments_applied") or crop_set.get("adjustments_applied")
    if isinstance(adjustments, list) and adjustments:
        summary["adjustments_applied"] = adjustments[:MAX_POINT_CROP_SET_POINTS]

    delegation_lines = build_delegation_lines(points)
    if delegation_lines:
        summary["delegation_lines"] = delegation_lines

    review_table = review_table_from_crop_set(crop_set)
    review_lines = review_table.get("review_lines")
    if isinstance(review_lines, list) and review_lines:
        summary["review_lines"] = review_lines[:MAX_POINT_CROP_SET_POINTS]

    point_key_lines = crop_set.get("point_key_lines")
    if not isinstance(point_key_lines, list) or not point_key_lines:
        key_table = build_point_key_lines(raw_points)
        point_key_lines = key_table.get("point_key_lines")
    if isinstance(point_key_lines, list) and point_key_lines:
        summary["point_key_lines"] = point_key_lines[:MAX_POINT_CROP_SET_POINTS]

    return {k: v for k, v in summary.items() if v not in (None, "", [], {})}


def compact_crop_identity_from_summary(
    crop_summary: Mapping[str, Any] | None,
) -> dict[str, str]:
    """Bounded identity refs from a projected point-crop summary row."""
    compact: dict[str, str] = {}
    if not isinstance(crop_summary, Mapping):
        return compact
    master = crop_summary.get("master_overlay_ref")
    if isinstance(master, str) and master.strip():
        compact["derived_ref_id"] = master.strip()
    overlay_role = crop_summary.get("overlay_role")
    if isinstance(overlay_role, str) and overlay_role.strip():
        compact["overlay_role"] = overlay_role.strip()
    return compact
