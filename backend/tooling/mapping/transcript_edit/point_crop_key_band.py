"""Point key line text utilities and PIL key-band rendering for point-crop overlays."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

MAX_POINT_KEY_ROWS = 16
KEY_BAND_ROW_HEIGHT = 16
KEY_BAND_PAD_Y = 5
KEY_BAND_TEXT_COLOR = (25, 25, 25)
KEY_BAND_BG_COLOR = (248, 248, 248)
_KEY_BAND_SEPARATOR_COLOR = (190, 190, 190)
_DECIMALS = 3


from .point_crop_target_mapping import format_target_mapping_parts


def compact_size_shape_label(
    size: str | None,
    shape: str | None,
    *,
    crop_intent: str | None = None,
) -> str:
    """Compact size/shape or intent label for control-surface key rows."""
    intent = str(crop_intent or "").strip()
    if intent:
        return intent
    size_label = _compact_size_label(size)
    shape_label = str(shape or "").strip()
    if size_label and shape_label:
        return f"{size_label}/{shape_label}"
    return size_label or shape_label


def render_point_key_line(point: Mapping[str, Any]) -> str:
    """Single compact point-key line for prompts, timeline, and image band."""
    letter = str(point.get("letter") or "?").strip()
    alias = str(point.get("alias") or "?").strip()
    point_norm = point.get("point_norm") or point.get("local_point_norm") or [0.0, 0.0]
    try:
        x = float(point_norm[0])
        y = float(point_norm[1])
    except (TypeError, ValueError, IndexError):
        x, y = 0.0, 0.0

    parts = [letter, alias]
    parts.extend(format_target_mapping_parts(point))
    parts.append(f"point=[{x:.{_DECIMALS}f},{y:.{_DECIMALS}f}]")
    extra = compact_size_shape_label(
        str(point.get("size") or "").strip() or None,
        str(point.get("shape") or "").strip() or None,
        crop_intent=str(point.get("crop_intent") or "").strip() or None,
    )
    if extra:
        parts.append(extra)
    return " ".join(parts)


def build_point_key_lines(points: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Bounded point-key lines with overflow marker when capped."""
    lines: list[str] = []
    for point in points[:MAX_POINT_KEY_ROWS]:
        if not isinstance(point, Mapping):
            continue
        lines.append(render_point_key_line(point))
    overflow = max(0, len(points) - MAX_POINT_KEY_ROWS)
    if overflow:
        lines.append(f"+{overflow} more")
    if not lines:
        return {}
    return {
        "point_key_lines": lines,
        "point_key_row_count": min(len(points), MAX_POINT_KEY_ROWS),
        "point_key_overflow_count": overflow,
    }


def compute_point_key_band_height(point_count: int) -> int:
    """Pixel height of the display-only key band below the template legend."""
    if point_count <= 0:
        return 0
    rows = min(point_count, MAX_POINT_KEY_ROWS)
    overflow_row = 1 if point_count > MAX_POINT_KEY_ROWS else 0
    return KEY_BAND_PAD_Y * 2 + rows * KEY_BAND_ROW_HEIGHT + overflow_row * KEY_BAND_ROW_HEIGHT


def draw_point_key_band(
    draw: Any,
    *,
    img_w: int,
    y_start: int,
    points: Sequence[Mapping[str, Any]],
) -> int:
    """Draw the key band; returns rendered band height in pixels."""
    if not points:
        return 0

    table = build_point_key_lines(points)
    lines = table.get("point_key_lines")
    if not isinstance(lines, list) or not lines:
        return 0

    band_h = compute_point_key_band_height(len(points))
    draw.rectangle(
        [0, y_start, img_w, y_start + band_h],
        fill=KEY_BAND_BG_COLOR,
    )
    draw.line(
        [(0, y_start), (img_w, y_start)],
        fill=_KEY_BAND_SEPARATOR_COLOR,
        width=1,
    )

    font = _key_band_font()
    row_y = y_start + KEY_BAND_PAD_Y
    for line in lines:
        draw.text((8, row_y), line, fill=KEY_BAND_TEXT_COLOR, font=font)
        row_y += KEY_BAND_ROW_HEIGHT
    return band_h


def attach_point_key_lines_to_crop_set(crop_set: dict[str, Any]) -> None:
    """Attach bounded point_key_lines to an in-memory crop_set dict."""
    points = crop_set.get("points")
    if not isinstance(points, list) or not points:
        return
    table = build_point_key_lines(points)
    if table:
        crop_set.update(table)


def _compact_size_label(size: str | None) -> str:
    raw = str(size or "").strip().lower()
    if raw == "small_plus":
        return "small+"
    return raw


def _key_band_font() -> Any:
    from PIL import ImageFont  # type: ignore[import]

    size = 11
    candidates = (
        "arial.ttf",
        "Arial.ttf",
        "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()
