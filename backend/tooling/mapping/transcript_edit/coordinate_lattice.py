"""Shared normalized coordinate lattice for point-crop and reference overlays."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

DEFAULT_MAJOR_STEP_NORM = 0.10
DEFAULT_MINOR_STEP_NORM = 0.025

# Backward-compatible aliases used across transcript-edit tooling.
OVERLAY_GRID_MAJOR_STEP_NORM = DEFAULT_MAJOR_STEP_NORM
OVERLAY_GRID_MINOR_STEP_NORM = DEFAULT_MINOR_STEP_NORM

_GRID_MINOR_COLOR = (235, 235, 235)
_GRID_MAJOR_COLOR = (115, 115, 115)
_GRID_MINOR_WIDTH = 1
_GRID_MAJOR_WIDTH = 2
_GRID_LABEL_COLOR = (25, 25, 25)
_GRID_LABEL_BG_COLOR = (255, 255, 255)
_GRID_LABEL_BG_ALPHA = 215
_GRID_LABEL_FONT_SIZE = 11
_GRID_LABEL_PAD_PX = 2

_DECIMALS = 3
_STRIP_LATTICE_KEYS = frozenset(
    {
        "absolute_path",
        "b64",
        "base64",
        "bytes",
        "prompt",
        "raw_prompt",
    }
)


def build_coordinate_lattice_metadata(
    *,
    major_step_norm: float = DEFAULT_MAJOR_STEP_NORM,
    minor_step_norm: float = DEFAULT_MINOR_STEP_NORM,
    cols: int | None = None,
    rows: int | None = None,
    cell_labels: bool = False,
) -> dict[str, Any]:
    """Canonical coordinate-lattice metadata for overlays and review tables."""
    lattice: dict[str, Any] = {
        "major_step_norm": major_step_norm,
        "minor_step_norm": minor_step_norm,
        "major_labels": major_norm_label_strings(major_step_norm),
        "minor_labels": False,
        "coordinate_space": "normalized_source_image",
        "origin": "top_left",
        "x_increases": "right",
        "y_increases": "down",
        "label_placement": {
            "major_x": ["top", "bottom"],
            "major_y": ["left", "right"],
            "minor": False,
        },
        "label_style": {
            "background": True,
            "opposite_margins": True,
            "font_size_px": _GRID_LABEL_FONT_SIZE,
        },
        "line_style": {
            "major_width_px": _GRID_MAJOR_WIDTH,
            "minor_width_px": _GRID_MINOR_WIDTH,
            "major_color": list(_GRID_MAJOR_COLOR),
            "minor_color": list(_GRID_MINOR_COLOR),
        },
    }
    if cols is not None and rows is not None:
        lattice["reference_cells"] = {
            "cols": cols,
            "rows": rows,
            "cell_labels": cell_labels,
        }
    return _strip_lattice_payload(lattice)


def build_compat_grid_metadata(
    lattice: Mapping[str, Any],
    *,
    enabled: bool = True,
    cols: int | None = None,
    rows: int | None = None,
    cell_labels: bool = False,
) -> dict[str, Any]:
    """Backward-compatible ``grid`` block mirroring lattice step semantics."""
    ref_cells = lattice.get("reference_cells")
    if isinstance(ref_cells, Mapping):
        cols = cols if cols is not None else ref_cells.get("cols")
        rows = rows if rows is not None else ref_cells.get("rows")
        cell_labels = cell_labels or bool(ref_cells.get("cell_labels"))

    grid: dict[str, Any] = {
        "enabled": enabled,
        "coordinate_space": "source_image_norm",
        "major_step_norm": lattice.get("major_step_norm", DEFAULT_MAJOR_STEP_NORM),
        "minor_step_norm": lattice.get("minor_step_norm", DEFAULT_MINOR_STEP_NORM),
        "major_line": {
            "color": list(_GRID_MAJOR_COLOR),
            "width": _GRID_MAJOR_WIDTH,
        },
        "minor_line": {
            "color": list(_GRID_MINOR_COLOR),
            "width": _GRID_MINOR_WIDTH,
        },
        "edge_labels": "major_only",
    }
    if cols is not None:
        grid["cols"] = cols
    if rows is not None:
        grid["rows"] = rows
    if cell_labels:
        grid["cell_labels"] = True
    return grid


def major_norm_label_strings(major_step_norm: float = DEFAULT_MAJOR_STEP_NORM) -> list[str]:
    """Major grid line labels in normalized space (excludes 0.0 and 1.0 edges)."""
    labels: list[str] = []
    frac = round(float(major_step_norm), 6)
    step = frac
    if step <= 0.0:
        return labels
    while frac < 1.0:
        labels.append(_norm_fraction_label(frac))
        frac = round(frac + step, 6)
    return labels


def major_step_from_metadata(container: Mapping[str, Any] | None) -> float:
    """Read major step from ``coordinate_lattice`` or legacy ``grid`` metadata."""
    if not isinstance(container, Mapping):
        return DEFAULT_MAJOR_STEP_NORM
    lattice = container.get("coordinate_lattice")
    if isinstance(lattice, Mapping):
        step = _coerce_positive_float(lattice.get("major_step_norm"))
        if step is not None:
            return step
    grid = container.get("grid")
    if isinstance(grid, Mapping):
        step = _coerce_positive_float(grid.get("major_step_norm"))
        if step is not None:
            return step
    step = _coerce_positive_float(container.get("major_step_norm"))
    if step is not None:
        return step
    return DEFAULT_MAJOR_STEP_NORM


def nearest_lattice_anchor(
    point_norm: Sequence[float],
    *,
    major_step_norm: float = DEFAULT_MAJOR_STEP_NORM,
) -> list[float]:
    """Nearest major lattice intersection in normalized source-image space."""
    try:
        x = float(point_norm[0])
        y = float(point_norm[1])
    except (TypeError, ValueError, IndexError):
        return [0.0, 0.0]
    ax = _clamp01(_snap_to_step(x, major_step_norm))
    ay = _clamp01(_snap_to_step(y, major_step_norm))
    return [_round_coord(ax), _round_coord(ay)]


def offset_from_anchor(
    point_norm: Sequence[float],
    anchor: Sequence[float],
) -> list[float]:
    """``point_norm - anchor`` for grid-relative review rows."""
    try:
        dx = float(point_norm[0]) - float(anchor[0])
        dy = float(point_norm[1]) - float(anchor[1])
    except (TypeError, ValueError, IndexError):
        return [0.0, 0.0]
    return [_round_coord(dx), _round_coord(dy)]


def draw_coordinate_lattice(
    draw: Any,
    img_w: int,
    img_h: int,
    *,
    major_step_norm: float = DEFAULT_MAJOR_STEP_NORM,
    minor_step_norm: float = DEFAULT_MINOR_STEP_NORM,
    edge_labels: bool = True,
    opposite_margin_labels: bool = True,
) -> None:
    """Draw major/minor lattice lines with readable margin labels."""
    minor_step = float(minor_step_norm)
    major_step = float(major_step_norm)

    frac = minor_step
    while frac < 1.0:
        if not _is_major_fraction(frac, major_step):
            x = int(round(frac * img_w))
            y = int(round(frac * img_h))
            draw.line(
                [(x, 0), (x, img_h)],
                fill=_GRID_MINOR_COLOR,
                width=_GRID_MINOR_WIDTH,
            )
            draw.line(
                [(0, y), (img_w, y)],
                fill=_GRID_MINOR_COLOR,
                width=_GRID_MINOR_WIDTH,
            )
        frac = round(frac + minor_step, 6)

    frac = major_step
    while frac < 1.0:
        x = int(round(frac * img_w))
        y = int(round(frac * img_h))
        draw.line(
            [(x, 0), (x, img_h)],
            fill=_GRID_MAJOR_COLOR,
            width=_GRID_MAJOR_WIDTH,
        )
        draw.line(
            [(0, y), (img_w, y)],
            fill=_GRID_MAJOR_COLOR,
            width=_GRID_MAJOR_WIDTH,
        )
        if edge_labels:
            _draw_major_margin_labels(
                draw,
                img_w,
                img_h,
                frac=frac,
                x_px=x,
                y_px=y,
                opposite_margins=opposite_margin_labels,
            )
        frac = round(frac + major_step, 6)


def draw_norm_step_coordinate_grid(
    draw: Any,
    img_w: int,
    img_h: int,
    *,
    edge_labels: bool = True,
) -> None:
    """Backward-compatible entry point for lattice drawing."""
    draw_coordinate_lattice(
        draw,
        img_w,
        img_h,
        edge_labels=edge_labels,
        opposite_margin_labels=True,
    )


def _draw_major_margin_labels(
    draw: Any,
    img_w: int,
    img_h: int,
    *,
    frac: float,
    x_px: int,
    y_px: int,
    opposite_margins: bool,
) -> None:
    font = _lattice_font()
    x_label = _format_x_margin_label(frac)
    y_label = _format_y_margin_label(frac)
    x_bbox = _text_bbox(draw, x_label, font=font)
    y_bbox = _text_bbox(draw, y_label, font=font)
    x_text_w = x_bbox[2] - x_bbox[0]
    y_text_w = y_bbox[2] - y_bbox[0]

    top_x = min(max(2, x_px + 2), max(2, img_w - x_text_w - 4))
    _draw_margin_label(draw, (top_x, 2), x_label, font=font)
    _draw_margin_label(draw, (2, min(y_px + 2, max(2, img_h - (y_bbox[3] - y_bbox[1]) - 4))), y_label, font=font)
    if opposite_margins:
        bottom_y = max(2, img_h - (x_bbox[3] - x_bbox[1]) - 4)
        _draw_margin_label(draw, (top_x, bottom_y), x_label, font=font)
        right_x = max(2, img_w - y_text_w - 4)
        _draw_margin_label(
            draw,
            (right_x, min(y_px + 2, max(2, img_h - (y_bbox[3] - y_bbox[1]) - 4))),
            y_label,
            font=font,
        )


def _draw_margin_label(
    draw: Any,
    xy: tuple[int, int],
    text: str,
    *,
    font: Any,
) -> None:
    """Draw a lattice label with a small high-contrast background pad."""
    bbox = _text_bbox(draw, text, font=font, anchor_xy=xy)
    pad = _GRID_LABEL_PAD_PX
    draw.rectangle(
        [bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad],
        fill=_GRID_LABEL_BG_COLOR,
        outline=(60, 60, 60),
        width=1,
    )
    draw.text(xy, text, fill=_GRID_LABEL_COLOR, font=font)


def _lattice_font() -> Any:
    from PIL import ImageFont  # type: ignore[import]

    size = _GRID_LABEL_FONT_SIZE
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


def _text_bbox(
    draw: Any,
    text: str,
    *,
    font: Any,
    anchor_xy: tuple[int, int] | None = None,
) -> tuple[int, int, int, int]:
    if anchor_xy is None:
        return draw.textbbox((0, 0), text, font=font)
    return draw.textbbox(anchor_xy, text, font=font)


def _format_x_margin_label(frac: float) -> str:
    return f"x->{_norm_fraction_label(frac)}"


def _format_y_margin_label(frac: float) -> str:
    return f"y|{_norm_fraction_label(frac)}"


def _norm_fraction_label(frac: float) -> str:
    return f"{float(frac):.2f}"


def _is_major_fraction(frac: float, major_step: float) -> bool:
    major_tick = round(frac / major_step)
    return abs(frac - major_tick * major_step) < 1e-9


def _snap_to_step(value: float, step: float) -> float:
    if step <= 0.0:
        return value
    return round(value / step) * step


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _round_coord(value: float) -> float:
    return round(float(value), _DECIMALS)


def _coerce_positive_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        step = float(value)
    except (TypeError, ValueError):
        return None
    if step <= 0.0:
        return None
    return step


def _strip_lattice_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _STRIP_LATTICE_KEYS:
            continue
        if isinstance(value, str) and any(part in key.lower() for part in ("path", "prompt", "b64")):
            continue
        out[key] = value
    return out
