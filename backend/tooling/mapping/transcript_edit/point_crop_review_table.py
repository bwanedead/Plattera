"""Compact text review table for point-crop sets (mechanical coordinates only)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .point_crops import MAX_POINT_CROP_COUNT, OVERLAY_GRID_MAJOR_STEP_NORM

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


def major_step_from_overlay(overlay_metadata: Mapping[str, Any] | None) -> float:
    """Read major grid step from overlay metadata when present."""
    if not isinstance(overlay_metadata, Mapping):
        return OVERLAY_GRID_MAJOR_STEP_NORM
    grid = overlay_metadata.get("grid")
    if isinstance(grid, Mapping):
        raw = grid.get("major_step_norm")
        if raw is not None:
            try:
                step = float(raw)
                if step > 0.0:
                    return step
            except (TypeError, ValueError):
                pass
    return OVERLAY_GRID_MAJOR_STEP_NORM


def nearest_major_anchor(
    point_norm: Sequence[float],
    *,
    major_step: float = OVERLAY_GRID_MAJOR_STEP_NORM,
) -> list[float]:
    """Nearest major grid intersection in normalized source-image space."""
    try:
        x = float(point_norm[0])
        y = float(point_norm[1])
    except (TypeError, ValueError, IndexError):
        return [0.0, 0.0]
    ax = _clamp01(_snap_to_step(x, major_step))
    ay = _clamp01(_snap_to_step(y, major_step))
    return [_round_coord(ax), _round_coord(ay)]


def offset_from_anchor(
    point_norm: Sequence[float],
    anchor: Sequence[float],
) -> list[float]:
    """``point_norm - anchor`` for review-table adjustment hints."""
    try:
        dx = float(point_norm[0]) - float(anchor[0])
        dy = float(point_norm[1]) - float(anchor[1])
    except (TypeError, ValueError, IndexError):
        return [0.0, 0.0]
    return [_round_coord(dx), _round_coord(dy)]


def build_review_row(
    point: Mapping[str, Any],
    *,
    major_step: float = OVERLAY_GRID_MAJOR_STEP_NORM,
) -> dict[str, Any]:
    """Structured review row for one crop-set point (bounded, no media payloads)."""
    letter = str(point.get("letter") or "").strip()
    alias = str(point.get("alias") or "").strip()
    point_norm = _norm_pair(point.get("point_norm")) or _norm_pair(point.get("local_point_norm"))
    if point_norm is None:
        point_norm = [0.0, 0.0]

    anchor = nearest_major_anchor(point_norm, major_step=major_step)
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

    return _strip_review_row(row)


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
    parts.append(f"size={size_shape}")
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
    major_step = major_step_from_overlay(overlay_metadata)
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


def _snap_to_step(value: float, step: float) -> float:
    if step <= 0.0:
        return value
    return round(value / step) * step


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


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
