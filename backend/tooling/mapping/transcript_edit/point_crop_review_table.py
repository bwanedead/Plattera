"""Compact text review table for point-crop sets (mechanical coordinates only)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .coordinate_lattice import (
    DEFAULT_MAJOR_STEP_NORM,
    major_step_from_metadata,
    nearest_lattice_anchor,
    offset_from_anchor,
)
from .point_crops import MAX_POINT_CROP_COUNT
from .source_window import (
    attach_crop_frame_edge_room_to_point,
    build_crop_frame_edge_room,
    format_crop_frame_edge_room_compact,
)

MAX_REVIEW_ROWS = MAX_POINT_CROP_COUNT
_DECIMALS = 3

_STRIP_REVIEW_KEYS = frozenset(
    {
        "absolute_path",
        "b64",
        "base64",
        "bytes",
        "crop_img",
        "box_px",
        "pin_px",
        "color",
        "projection_chain",
        "local_source_width_height",
        "root_source_width_height",
        "unzoomed_width_height",
        "output_width_height",
        "prompt",
        "raw_prompt",
    }
)


def build_review_row(
    point: Mapping[str, Any],
    *,
    major_step: float = DEFAULT_MAJOR_STEP_NORM,
) -> dict[str, Any]:
    """Structured review row for one crop-set point (bounded, no media payloads)."""
    letter = str(point.get("letter") or "").strip()
    alias = str(point.get("alias") or "").strip()
    point_norm = _norm_pair(point.get("point_norm")) or _norm_pair(point.get("local_point_norm"))
    if point_norm is None:
        point_norm = [0.0, 0.0]

    anchor = nearest_lattice_anchor(point_norm, major_step_norm=major_step)
    offset = offset_from_anchor(point_norm, anchor)

    row: dict[str, Any] = {
        "letter": letter,
        "alias": alias,
        "point_norm": point_norm,
        "nearest_major_anchor": anchor,
        "offset_from_anchor": offset,
    }

    crop_ref = point.get("crop_ref")
    if isinstance(crop_ref, str) and crop_ref.strip():
        row["crop_ref"] = crop_ref.strip()

    box_norm = _norm_box(point.get("box_norm")) or _norm_box(point.get("local_box_norm"))
    if box_norm is not None:
        row["box_norm"] = box_norm

    size = str(point.get("size") or "").strip()
    shape = str(point.get("shape") or "").strip()
    if size:
        row["size"] = size
    if shape:
        row["shape"] = shape

    crop_intent = str(point.get("crop_intent") or "").strip()
    if crop_intent:
        row["crop_intent"] = crop_intent

    if point.get("trim_to_text_block") is True:
        row["trim_to_text_block"] = True
        trim_axis = str(point.get("trim_axis") or "x").strip()
        if trim_axis:
            row["trim_axis"] = trim_axis
        if point.get("trim_applied") is True:
            row["trim_applied"] = True
        elif point.get("trim_applied") is False:
            row["trim_applied"] = False
        trim_warning = str(point.get("trim_warning") or "").strip()
        if trim_warning:
            row["trim_warning"] = trim_warning
        if point.get("trim_padding_norm") is not None:
            try:
                row["trim_padding_norm"] = round(float(point["trim_padding_norm"]), _DECIMALS)
            except (TypeError, ValueError):
                pass
        pre_trim = _norm_box(point.get("pre_trim_box_norm"))
        if pre_trim is not None:
            row["pre_trim_box_norm"] = pre_trim
        text_bounds = point.get("text_block_bounds_norm")
        if isinstance(text_bounds, (list, tuple)) and len(text_bounds) == 2:
            try:
                row["text_block_bounds_norm"] = [
                    _round_coord(text_bounds[0]),
                    _round_coord(text_bounds[1]),
                ]
            except (TypeError, ValueError):
                pass
    elif point.get("trim_to_text_block") is False:
        row["trim_to_text_block"] = False

    zoom_factor = point.get("zoom_factor")
    if zoom_factor is not None:
        try:
            row["zoom_factor"] = round(float(zoom_factor), _DECIMALS)
        except (TypeError, ValueError):
            pass

    if point.get("projection_available") is True:
        row["projection_available"] = True
        root_point_norm = _norm_pair(point.get("root_point_norm"))
        if root_point_norm is not None:
            row["root_point_norm"] = root_point_norm
        root_box_norm = _norm_box(point.get("root_box_norm"))
        if root_box_norm is not None:
            row["root_box_norm"] = root_box_norm
    elif point.get("projection_available") is False:
        row["projection_available"] = False
        reason = str(point.get("projection_unavailable_reason") or "").strip()
        if reason:
            row["projection_unavailable_reason"] = reason[:120]

    _attach_crop_frame_fields_to_review_row(row, point=point, box_norm=box_norm)
    return _strip_review_row(row)


def _attach_crop_frame_fields_to_review_row(
    row: dict[str, Any],
    *,
    point: Mapping[str, Any],
    box_norm: list[float] | None,
) -> None:
    frame = _crop_frame_fields_from_point(point, box_norm=box_norm)
    if frame:
        row.update(frame)


def _crop_frame_fields_from_point(
    point: Mapping[str, Any],
    *,
    box_norm: list[float] | None,
) -> dict[str, Any]:
    if point.get("crop_frame_room_norm"):
        out: dict[str, Any] = {}
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
                out[key] = value
        return out
    if box_norm is None:
        return {}
    root_box_norm = _norm_box(point.get("root_box_norm"))
    return build_crop_frame_edge_room(
        box_norm=box_norm,
        root_box_norm=root_box_norm,
    )


def render_review_line(row: Mapping[str, Any]) -> str:
    """Single compact review-table line for prompts and timeline."""
    letter = str(row.get("letter") or "?").strip()
    alias = str(row.get("alias") or "?").strip()
    crop_ref = str(row.get("crop_ref") or "").strip()
    point_norm = row.get("point_norm") or [0.0, 0.0]
    box_norm = row.get("box_norm")
    size = str(row.get("size") or "").strip()
    shape = str(row.get("shape") or "").strip()
    size_shape = f"{size}/{shape}" if size and shape else (size or shape or "?")

    parts = [
        f"{letter} {alias} ->",
        f"crop={crop_ref or '?'}",
        f"point={_fmt_pair(point_norm)}",
    ]
    if isinstance(box_norm, (list, tuple)) and len(box_norm) == 4:
        parts.append(f"box={_fmt_box(box_norm)}")
    edge_room = format_crop_frame_edge_room_compact(
        room=row.get("crop_frame_room_norm"),
        touches=row.get("crop_frame_touches_edge"),
    )
    if edge_room:
        parts.append(edge_room)
    parts.append(f"size={size_shape}")
    crop_intent = str(row.get("crop_intent") or "").strip()
    if crop_intent:
        parts.append(f"intent={crop_intent}")
    if row.get("trim_to_text_block") is True:
        trim_axis = str(row.get("trim_axis") or "x").strip()
        trim_part = f"trim={trim_axis}"
        if row.get("trim_applied") is True:
            trim_part = f"{trim_part} applied"
        elif row.get("trim_warning"):
            trim_part = f"{trim_part} skipped"
        if row.get("trim_padding_norm") is not None:
            trim_part = f"{trim_part} padding={row.get('trim_padding_norm')}"
        warning = str(row.get("trim_warning") or "").strip()
        if warning:
            trim_part = f"{trim_part} warning={warning}"
        parts.append(trim_part)
    if row.get("zoom_factor") is not None:
        parts.append(f"zoom={row.get('zoom_factor')}")
    anchor = row.get("nearest_major_anchor")
    offset = row.get("offset_from_anchor")
    if isinstance(anchor, (list, tuple)) and len(anchor) == 2:
        parts.append(f"anchor={_fmt_pair(anchor)}")
    if isinstance(offset, (list, tuple)) and len(offset) == 2:
        parts.append(f"offset={_fmt_signed_pair(offset)}")
    if row.get("projection_available") is True:
        root_point = row.get("root_point_norm")
        if isinstance(root_point, (list, tuple)) and len(root_point) == 2:
            parts.append(f"root={_fmt_pair(root_point)}")
    return " ".join(parts)


def build_crop_set_review_table(
    points: Sequence[Mapping[str, Any]],
    *,
    overlay_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build bounded ``review_rows`` and ``review_lines`` for a crop set."""
    major_step = major_step_from_metadata(overlay_metadata)
    rows: list[dict[str, Any]] = []
    lines: list[str] = []
    for point in points[:MAX_REVIEW_ROWS]:
        if not isinstance(point, Mapping):
            continue
        row = build_review_row(point, major_step=major_step)
        if not row.get("letter") and not row.get("alias"):
            continue
        rows.append(row)
        lines.append(render_review_line(row))
    if not rows:
        return {}
    return {"review_rows": rows, "review_lines": lines}


def attach_review_table_to_crop_set(
    crop_set: dict[str, Any],
    *,
    overlay_metadata: Mapping[str, Any] | None = None,
) -> None:
    """Attach review table fields to an in-memory ``crop_set`` dict."""
    points = crop_set.get("points")
    if not isinstance(points, list):
        return
    table = build_crop_set_review_table(points, overlay_metadata=overlay_metadata)
    if table:
        crop_set.update(table)


def review_table_from_crop_set(crop_set: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return review table payload from crop_set or reconstruct from points."""
    if not isinstance(crop_set, Mapping):
        return {}
    review_lines = crop_set.get("review_lines")
    review_rows = crop_set.get("review_rows")
    if isinstance(review_lines, list) and review_lines:
        out: dict[str, Any] = {"review_lines": list(review_lines)[:MAX_REVIEW_ROWS]}
        if isinstance(review_rows, list) and review_rows:
            out["review_rows"] = list(review_rows)[:MAX_REVIEW_ROWS]
        return out
    points = crop_set.get("points")
    if isinstance(points, list) and points:
        return build_crop_set_review_table(
            points,
            overlay_metadata=crop_set,
        )
    return {}


def _round_coord(value: float) -> float:
    return round(float(value), _DECIMALS)


def _norm_pair(value: Any) -> list[float] | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return [_round_coord(value[0]), _round_coord(value[1])]
        except (TypeError, ValueError):
            return None
    return None


def _norm_box(value: Any) -> list[float] | None:
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            return [_round_coord(v) for v in value]
        except (TypeError, ValueError):
            return None
    return None


def _fmt_pair(pair: Sequence[float]) -> str:
    return f"[{pair[0]},{pair[1]}]"


def _fmt_box(box: Sequence[float]) -> str:
    return f"[{box[0]},{box[1]},{box[2]},{box[3]}]"


def _fmt_signed_pair(pair: Sequence[float]) -> str:
    return f"[{_fmt_signed_component(pair[0])},{_fmt_signed_component(pair[1])}]"


def _fmt_signed_component(value: Any) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "+0.000"
    rounded = _round_coord(num)
    if rounded >= 0:
        return f"+{rounded:.{_DECIMALS}f}"
    return f"{rounded:.{_DECIMALS}f}"


def _strip_review_row(row: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key in _STRIP_REVIEW_KEYS:
            continue
        if isinstance(value, str) and any(part in key.lower() for part in ("path", "prompt", "b64")):
            continue
        out[key] = value
    return out
