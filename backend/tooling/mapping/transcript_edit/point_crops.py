"""Point-crop template computation and rendering (pure, side-effect free).

The ``transform_artifact`` handler owns ref minting, persistence, and descriptors.
This module computes geometry, crops, and the master overlay in memory only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .coordinate_lattice import (
    DEFAULT_MAJOR_STEP_NORM,
    DEFAULT_MINOR_STEP_NORM,
    OVERLAY_ROLE_POINT_CROP_MASTER,
    OVERLAY_ROLE_POINT_CROP_PLACEMENT_SCAFFOLD,
    OVERLAY_ROLE_POINT_CROP_VIEW,
    build_reference_cell_overlay_metadata,
    draw_reference_cell_coordinate_foundation,
)
from .root_projection import copy_projection_fields

# Normalized box sizes centered on ``point_norm``.
_POINT_CROP_TEMPLATES: dict[str, dict[str, tuple[float, float]]] = {
    "small": {
        "wide": (0.32, 0.18),
        "square": (0.18, 0.18),
        "portrait": (0.18, 0.24),
    },
    "small_plus": {
        "wide": (0.48, 0.13),
        "square": (0.24, 0.24),
        "portrait": (0.24, 0.32),
    },
    "medium": {
        "wide": (0.62, 0.30),
        "square": (0.30, 0.30),
        "portrait": (0.30, 0.42),
    },
    "large": {
        "wide": (0.82, 0.48),
        "square": (0.48, 0.48),
        "portrait": (0.48, 0.82),
    },
}

# Stable readable colors for A, B, C... within one overlay call.
_POINT_COLORS: list[tuple[int, int, int]] = [
    (255, 200, 0),
    (0, 200, 220),
    (255, 100, 180),
    (140, 255, 120),
    (255, 160, 80),
    (160, 140, 255),
]

MAX_POINT_CROP_COUNT = 16
DEFAULT_SHOW = ["pin", "letter"]
ALLOWED_SHOW = frozenset({"pin", "box", "letter"})
ALLOWED_SIZES = frozenset({"small", "small_plus", "medium", "large"})
_SIZE_OPTIONS_TEXT = "small|small_plus|medium|large"
_SIZE_LEGEND_ORDER = ("small", "small_plus", "medium", "large")
ALLOWED_SHAPES = frozenset({"wide", "portrait", "square"})
MIN_EXPLICIT_DIM_NORM = 0.02
MAX_EXPLICIT_DIM_NORM = 1.0
MAX_GRAPH_REF_KEYS = 8
MAX_GRAPH_REF_VALUE_CHARS = 120
MIN_ZOOM_FACTOR = 1.0
MAX_ZOOM_FACTOR = 6.0
MIN_AXIS_SCALE = 0.5
MAX_AXIS_SCALE = 3.0
MAX_CROP_OUTPUT_DIMENSION = 3200
DEFAULT_ZOOM_BY_SIZE: dict[str, float] = {
    "small": 3.0,
    "small_plus": 2.75,
    "medium": 2.25,
    "large": 1.5,
}
_ZOOM_METADATA_KEYS = (
    "zoom_factor",
    "unzoomed_width_height",
    "output_width_height",
    "zoom_cap_applied",
    "requested_zoom_factor",
    "max_output_dimension",
)

OVERLAY_GRID_MAJOR_STEP_NORM = DEFAULT_MAJOR_STEP_NORM
OVERLAY_GRID_MINOR_STEP_NORM = DEFAULT_MINOR_STEP_NORM
OVERLAY_LEGEND_HEIGHT = 120
_BOX_FILL_ALPHA = 48
_BOX_OUTLINE_WIDTH = 4
_PIN_RADIUS = 12
_PIN_HALO_PADDING = 5
_PIN_FILL_ALPHA = 225
_PIN_HALO_RGBA = (255, 255, 255, 245)
_PIN_RING_RGBA = (35, 35, 35, 255)
_LETTER_PAD = 5
_LETTER_BG_RGBA = (255, 255, 255, 245)
_LETTER_TEXT_RGBA = (15, 15, 15, 255)
_LETTER_OUTLINE_RGBA = (30, 30, 30, 255)
_LETTER_FONT_SIZE = 14
_LETTER_BOX_PX = 18
_LEGEND_SIZE_COLORS: dict[str, tuple[int, int, int]] = {
    "small": (220, 70, 70),
    "small_plus": (245, 166, 35),
    "medium": (70, 130, 220),
    "large": (80, 180, 100),
}
_LEGEND_SQUARE_PX = {"small": 14, "small_plus": 17, "medium": 20, "large": 28}
_LEGEND_EXTENSION_PX = 18


class PointCropParamError(Exception):
    """Fixable param problem discovered during compute (after image open)."""

    def __init__(self, message: str, *, repair_hint: str | None = None) -> None:
        super().__init__(message)
        self.repair_hint = repair_hint


def validate_point_crops_params(params: dict[str, Any]) -> str | None:
    """Return an error message when ``params`` is invalid; otherwise ``None``.

    Normalizes mixed-case ``size`` / ``shape`` on each point in-place.
    """
    points = params.get("points")
    if not isinstance(points, list) or not points:
        return "point_crops requires params.points as a non-empty list of point objects."
    seen_aliases: set[str] = set()
    for i, p in enumerate(points):
        if not isinstance(p, dict):
            return f"params.points[{i}] must be an object."
        alias = str(p.get("alias") or "").strip()
        if not alias:
            return f"params.points[{i}].alias is required and non-empty."
        if alias in seen_aliases:
            return f"Duplicate alias {alias!r} in params.points."
        seen_aliases.add(alias)
        pn = p.get("point_norm")
        if not isinstance(pn, (list, tuple)) or len(pn) != 2:
            return f"params.points[{i}].point_norm must be [x, y] in [0,1]."
        try:
            if not (0.0 <= float(pn[0]) <= 1.0 and 0.0 <= float(pn[1]) <= 1.0):
                raise ValueError
        except Exception:
            return f"params.points[{i}].point_norm values must be in [0.0, 1.0]."
        size = str(p.get("size") or "").strip().lower()
        shape = str(p.get("shape") or "").strip().lower()
        if size not in ALLOWED_SIZES:
            return f"params.points[{i}].size must be {_SIZE_OPTIONS_TEXT}."
        if shape not in ALLOWED_SHAPES:
            return f"params.points[{i}].shape must be wide|portrait|square."
        p["size"] = size
        p["shape"] = shape
        if "graph_ref" in p:
            try:
                normalized_graph_ref = validate_graph_ref(
                    p.get("graph_ref"),
                    field_prefix=f"params.points[{i}].graph_ref",
                )
            except PointCropParamError as exc:
                return str(exc)
            if normalized_graph_ref is None:
                p.pop("graph_ref", None)
            else:
                p["graph_ref"] = normalized_graph_ref
    if len(points) > MAX_POINT_CROP_COUNT:
        return "point_crops point count exceeds safety cap (16)."
    global_zoom_err = _validate_zoom_factor_raw(params.get("zoom_factor"), "params.zoom_factor")
    if global_zoom_err:
        return global_zoom_err
    if params.get("zoom_factor") is not None:
        params["zoom_factor"] = _normalize_zoom_factor(params["zoom_factor"])
    for axis in ("scale_x", "scale_y"):
        scale_err = _validate_axis_scale_raw(params.get(axis), f"params.{axis}")
        if scale_err:
            return scale_err
        if params.get(axis) is not None:
            params[axis] = _normalize_axis_scale(params[axis])
    for i, p in enumerate(points):
        if "zoom_factor" in p:
            point_zoom_err = _validate_zoom_factor_raw(
                p.get("zoom_factor"),
                f"params.points[{i}].zoom_factor",
            )
            if point_zoom_err:
                return point_zoom_err
            p["zoom_factor"] = _normalize_zoom_factor(p["zoom_factor"])
        for axis in ("scale_x", "scale_y"):
            if axis not in p:
                continue
            scale_err = _validate_axis_scale_raw(p.get(axis), f"params.points[{i}].{axis}")
            if scale_err:
                return scale_err
            p[axis] = _normalize_axis_scale(p[axis])
        dim_err = _validate_point_explicit_dimensions(p, f"params.points[{i}]")
        if dim_err:
            return dim_err
    return _validate_show_param(params) or None


def point_crops_repair_hint_for(message: str) -> str | None:
    if "non-empty list" in message:
        return (
            'Provide params.points = [{"alias": "...", "point_norm": [x,y], '
            f'"size": "{_SIZE_OPTIONS_TEXT}", "shape": "wide|portrait|square", '
            '"width_norm?: number, height_norm?: number (both required together), '
            '"scale_x?: number, scale_y?: number}, ...]'
        )
    if "exceeds safety cap" in message:
        return "Reduce the number of points in a single call."
    if "width_norm" in message or "height_norm" in message:
        return (
            f"Provide width_norm and height_norm together, each between "
            f"{MIN_EXPLICIT_DIM_NORM} and {MAX_EXPLICIT_DIM_NORM}."
        )
    if "zoom_factor" in message:
        return f"Use zoom_factor between {MIN_ZOOM_FACTOR} and {MAX_ZOOM_FACTOR} (global or per-point)."
    if "scale_x" in message or "scale_y" in message:
        return (
            f"Use scale_x/scale_y between {MIN_AXIS_SCALE} and {MAX_AXIS_SCALE} "
            "(global or per-point)."
        )
    return None


def _validate_zoom_factor_raw(raw: Any, field_name: str) -> str | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return f"{field_name} must be a numeric zoom factor."
    if not (MIN_ZOOM_FACTOR <= value <= MAX_ZOOM_FACTOR):
        return (
            f"{field_name} must be between {MIN_ZOOM_FACTOR} and {MAX_ZOOM_FACTOR}."
        )
    return None


def _normalize_zoom_factor(raw: Any) -> float:
    return round(float(raw), 4)


def _validate_axis_scale_raw(raw: Any, field_name: str) -> str | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return f"{field_name} must be a numeric axis scale."
    if not (MIN_AXIS_SCALE <= value <= MAX_AXIS_SCALE):
        return f"{field_name} must be between {MIN_AXIS_SCALE} and {MAX_AXIS_SCALE}."
    return None


def _normalize_axis_scale(raw: Any) -> float:
    return round(float(raw), 4)


def _normalize_explicit_dim(raw: Any) -> float:
    return round(float(raw), 6)


def _validate_explicit_dim_raw(raw: Any, field_name: str) -> str | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return f"{field_name} must be a numeric normalized dimension."
    if not (MIN_EXPLICIT_DIM_NORM <= value <= MAX_EXPLICIT_DIM_NORM):
        return (
            f"{field_name} must be between {MIN_EXPLICIT_DIM_NORM} and {MAX_EXPLICIT_DIM_NORM}."
        )
    return None


def _validate_point_explicit_dimensions(point: dict[str, Any], field_prefix: str) -> str | None:
    has_w = point.get("width_norm") is not None
    has_h = point.get("height_norm") is not None
    if has_w != has_h:
        return f"{field_prefix} must include both width_norm and height_norm together."
    if not has_w:
        return None
    for key in ("width_norm", "height_norm"):
        err = _validate_explicit_dim_raw(point.get(key), f"{field_prefix}.{key}")
        if err:
            return err
        point[key] = _normalize_explicit_dim(point[key])
    return None


def _explicit_dims_from_point(point: Mapping[str, Any]) -> tuple[float | None, float | None]:
    explicit = point.get("explicit_width_height_norm")
    if isinstance(explicit, (list, tuple)) and len(explicit) == 2:
        return float(explicit[0]), float(explicit[1])
    if point.get("width_norm") is not None and point.get("height_norm") is not None:
        return float(point["width_norm"]), float(point["height_norm"])
    return None, None


def _explicit_dimensions_equal(
    prior_w: float | None,
    prior_h: float | None,
    new_w: float | None,
    new_h: float | None,
) -> bool:
    if prior_w is None and prior_h is None and new_w is None and new_h is None:
        return True
    if prior_w is None or prior_h is None or new_w is None or new_h is None:
        return False
    return (
        _normalize_explicit_dim(prior_w) == _normalize_explicit_dim(new_w)
        and _normalize_explicit_dim(prior_h) == _normalize_explicit_dim(new_h)
    )


def resolve_point_axis_scale(
    *,
    global_scale_x: float | None = None,
    global_scale_y: float | None = None,
    point_scale_x: float | None = None,
    point_scale_y: float | None = None,
) -> tuple[float, float]:
    """Resolve axis scale: per-point override wins per axis, else global, else 1.0."""
    scale_x = float(global_scale_x) if global_scale_x is not None else 1.0
    scale_y = float(global_scale_y) if global_scale_y is not None else 1.0
    if point_scale_x is not None:
        scale_x = float(point_scale_x)
    if point_scale_y is not None:
        scale_y = float(point_scale_y)
    return _normalize_axis_scale(scale_x), _normalize_axis_scale(scale_y)


def resolve_point_zoom_factor(
    *,
    size: str,
    global_zoom: float | None = None,
    point_zoom: float | None = None,
) -> float:
    """Resolve requested zoom: per-point override, then global, then size default."""
    if point_zoom is not None:
        return _normalize_zoom_factor(point_zoom)
    if global_zoom is not None:
        return _normalize_zoom_factor(global_zoom)
    return _normalize_zoom_factor(DEFAULT_ZOOM_BY_SIZE[size])


def _apply_crop_zoom(crop_img: Any, requested_zoom: float) -> tuple[Any, dict[str, Any]]:
    """Resize a cropped region for legibility; geometry metadata stays source-based."""
    from PIL import Image  # type: ignore[import]

    unzoomed_w = int(crop_img.width)
    unzoomed_h = int(crop_img.height)
    requested = _normalize_zoom_factor(requested_zoom)
    target_w = max(1, int(round(unzoomed_w * requested)))
    target_h = max(1, int(round(unzoomed_h * requested)))

    zoom_cap_applied = False
    applied_zoom = requested
    if max(target_w, target_h) > MAX_CROP_OUTPUT_DIMENSION:
        scale = MAX_CROP_OUTPUT_DIMENSION / max(target_w, target_h)
        target_w = max(1, int(round(target_w * scale)))
        target_h = max(1, int(round(target_h * scale)))
        zoom_cap_applied = True
        applied_zoom = round(min(target_w / unzoomed_w, target_h / unzoomed_h), 4)

    zoomed = crop_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    meta: dict[str, Any] = {
        "zoom_factor": applied_zoom,
        "unzoomed_width_height": [unzoomed_w, unzoomed_h],
        "output_width_height": [target_w, target_h],
        "zoom_cap_applied": zoom_cap_applied,
    }
    if zoom_cap_applied:
        meta["requested_zoom_factor"] = requested
        meta["max_output_dimension"] = MAX_CROP_OUTPUT_DIMENSION
    return zoomed, meta


def _copy_zoom_metadata(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: source[key]
        for key in _ZOOM_METADATA_KEYS
        if key in source
    }


def validate_graph_ref(raw: Any, *, field_prefix: str = "graph_ref") -> dict[str, str] | None:
    """Validate optional bounded graph association metadata (stored verbatim)."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise PointCropParamError(
            f"{field_prefix} must be a flat object mapping string keys to string values.",
            repair_hint='Use graph_ref like {"item_id": "...", "covered_unit_id": "..."}.',
        )
    if len(raw) > MAX_GRAPH_REF_KEYS:
        raise PointCropParamError(
            f"{field_prefix} exceeds max key count ({MAX_GRAPH_REF_KEYS}).",
        )
    out: dict[str, str] = {}
    for key, value in raw.items():
        key_text = str(key).strip()[:64]
        if not key_text:
            continue
        if isinstance(value, (dict, list, tuple, set)):
            raise PointCropParamError(
                f"{field_prefix}.{key_text} must be a bounded string/scalar value, not nested data.",
            )
        value_text = str(value).strip()[:MAX_GRAPH_REF_VALUE_CHARS]
        if value_text:
            out[key_text] = value_text
    return out or None


def _legend_size_label(size: str) -> str:
    return "small+" if size == "small_plus" else size


def _compute_single_point_geometry(
    img: Any,
    *,
    point_norm: list[float],
    size: str,
    shape: str,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    width_norm: float | None = None,
    height_norm: float | None = None,
) -> dict[str, Any]:
    x, y = float(point_norm[0]), float(point_norm[1])
    template_w, template_h = _POINT_CROP_TEMPLATES[size][shape]
    if width_norm is not None and height_norm is not None:
        base_w = float(width_norm)
        base_h = float(height_norm)
        explicit_dims = [_normalize_explicit_dim(base_w), _normalize_explicit_dim(base_h)]
    else:
        base_w = template_w
        base_h = template_h
        explicit_dims = None
    w = base_w * scale_x
    h = base_h * scale_y

    desired_w = w * img.width
    desired_h = h * img.height

    left = x * img.width - desired_w / 2
    top = y * img.height - desired_h / 2
    right = left + desired_w
    bottom = top + desired_h

    if left < 0:
        right -= left
        left = 0
    if top < 0:
        bottom -= top
        top = 0
    if right > img.width:
        left -= right - img.width
        right = img.width
    if bottom > img.height:
        top -= bottom - img.height
        bottom = img.height

    left = max(0, min(left, img.width - 1))
    top = max(0, min(top, img.height - 1))
    right = max(left + 1, min(right, img.width))
    bottom = max(top + 1, min(bottom, img.height))

    box = (int(left), int(top), int(right), int(bottom))
    pin_px = [int(round(x * img.width)), int(round(y * img.height))]
    result: dict[str, Any] = {
        "point_norm": [round(x, 6), round(y, 6)],
        "pin_px": pin_px,
        "box_px": [box[0], box[1], box[2], box[3]],
        "box_norm": [
            round(left / img.width, 6),
            round(top / img.height, 6),
            round(right / img.width, 6),
            round(bottom / img.height, 6),
        ],
        "box": box,
        "scale_x": _normalize_axis_scale(scale_x),
        "scale_y": _normalize_axis_scale(scale_y),
        "template_width_height_norm": [round(template_w, 6), round(template_h, 6)],
        "resolved_width_height_norm": [round(w, 6), round(h, 6)],
    }
    if explicit_dims is not None:
        result["explicit_width_height_norm"] = explicit_dims
    return result


ALLOWED_SCAFFOLD_SHOW = frozenset({"grid"})


def validate_point_crops_scaffold_params(params: dict[str, Any]) -> str | None:
    """Return an error message when scaffold params are invalid; otherwise ``None``."""
    show_raw = params.get("show")
    if show_raw is None:
        return None
    if not isinstance(show_raw, list):
        return "point_crops_scaffold params.show must be a JSON array when provided."
    for index, entry in enumerate(show_raw):
        if not isinstance(entry, str) or entry.strip().lower() not in ALLOWED_SCAFFOLD_SHOW:
            return (
                f"params.show[{index}] must be 'grid' when provided; "
                "point_crops_scaffold does not render pins, letters, or crop boxes."
            )
    return None


def point_crops_scaffold_repair_hint_for(message: str) -> str:
    lowered = message.lower()
    if "show" in lowered:
        return "Omit params.show or pass show: ['grid'] for the coordinate lattice only."
    return "Use ref_id of the source image and sub_action point_crops_scaffold with optional params.show."


def build_scaffold_overlay_render_metadata() -> dict[str, Any]:
    """Mechanical metadata for zero-point placement scaffold overlays."""
    return build_reference_cell_overlay_metadata(
        overlay_role=OVERLAY_ROLE_POINT_CROP_PLACEMENT_SCAFFOLD,
        extra={
            "legend": {
                "kind": "placement_scaffold",
                "point_count": 0,
            },
        },
    )


def build_overlay_render_metadata(
    *,
    overlay_role: str = OVERLAY_ROLE_POINT_CROP_MASTER,
) -> dict[str, Any]:
    """Mechanical metadata for point-crop master overlay grid/legend rendering."""
    meta = build_reference_cell_overlay_metadata(overlay_role=overlay_role)
    meta.update({
        "box_render": {
            "fill_alpha": _BOX_FILL_ALPHA,
            "outline_width": _BOX_OUTLINE_WIDTH,
            "color_matches_point": True,
        },
        "pin_render": {
            "radius_px": _PIN_RADIUS,
            "halo_padding_px": _PIN_HALO_PADDING,
            "halo_rgba": list(_PIN_HALO_RGBA),
            "ring_rgba": list(_PIN_RING_RGBA),
            "fill_alpha": _PIN_FILL_ALPHA,
            "outline_width_px": 3,
            "anchor": "point_norm",
        },
        "letter_render": {
            "pad_px": _LETTER_PAD,
            "font_size_px": _LETTER_FONT_SIZE,
            "bg_rgba": list(_LETTER_BG_RGBA),
            "text_rgba": list(_LETTER_TEXT_RGBA),
            "outline_rgba": list(_LETTER_OUTLINE_RGBA),
            "placement": "upper_right_of_pin",
        },
        "legend": {
            "size_colors": {
                size: list(_LEGEND_SIZE_COLORS[size])
                for size in _SIZE_LEGEND_ORDER
            },
            "size_labels": {
                size: _legend_size_label(size)
                for size in _SIZE_LEGEND_ORDER
            },
        },
    })
    return meta


def _draw_dashed_line(
    draw: Any,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    fill: tuple[int, int, int],
    width: int = 1,
    dash_len: int = 4,
    gap_len: int = 3,
) -> None:
    x0, y0 = start
    x1, y1 = end
    if x0 == x1:
        step = dash_len + gap_len
        y = min(y0, y1)
        y_end = max(y0, y1)
        while y < y_end:
            seg_end = min(y + dash_len, y_end)
            draw.line([(x0, y), (x1, seg_end)], fill=fill, width=width)
            y += step
        return
    if y0 == y1:
        step = dash_len + gap_len
        x = min(x0, x1)
        x_end = max(x0, x1)
        while x < x_end:
            seg_end = min(x + dash_len, x_end)
            draw.line([(x, y0), (seg_end, y1)], fill=fill, width=width)
            x += step
        return
    draw.line([start, end], fill=fill, width=width)


def _overlay_letter_font() -> Any:
    from PIL import ImageFont  # type: ignore[import]

    candidates = (
        "arialbd.ttf",
        "Arialbd.ttf",
        "arial.ttf",
        "Arial.ttf",
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, _LETTER_FONT_SIZE)
        except OSError:
            continue
    return ImageFont.load_default()


def _pin_center_px(pt: Mapping[str, Any]) -> tuple[int, int]:
    pin_px = pt.get("pin_px")
    if isinstance(pin_px, (list, tuple)) and len(pin_px) == 2:
        return int(pin_px[0]), int(pin_px[1])
    b = tuple(pt["box_px"])
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _letter_position_near_pin(cx: int, cy: int, *, img_w: int, img_h: int) -> tuple[int, int]:
    lx = min(cx + _PIN_RADIUS + 6, max(2, img_w - _LETTER_BOX_PX - _LETTER_PAD * 2 - 4))
    ly = max(2, cy - _PIN_RADIUS - _LETTER_BOX_PX - _LETTER_PAD)
    return lx, ly


def _draw_point_pin(
    draw: Any,
    *,
    cx: int,
    cy: int,
    color: tuple[int, int, int],
    outline: tuple[int, int, int],
) -> None:
    r = _PIN_RADIUS
    halo = _PIN_HALO_PADDING
    draw.ellipse(
        [cx - r - halo, cy - r - halo, cx + r + halo, cy + r + halo],
        fill=_PIN_HALO_RGBA,
    )
    draw.ellipse(
        [cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1],
        outline=_PIN_RING_RGBA,
        width=1,
    )
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=(*color, _PIN_FILL_ALPHA),
        outline=(*outline, 255),
        width=3,
    )


def _draw_point_letter(
    draw: Any,
    *,
    cx: int,
    cy: int,
    letter: str,
    color: tuple[int, int, int],
    outline: tuple[int, int, int],
    img_w: int,
    img_h: int,
) -> None:
    lx, ly = _letter_position_near_pin(cx, cy, img_w=img_w, img_h=img_h)
    pad = _LETTER_PAD
    font = _overlay_letter_font()
    bbox = draw.textbbox((lx, ly), letter, font=font)
    letter_draw_box = [bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad]
    draw.rectangle(
        letter_draw_box,
        fill=_LETTER_BG_RGBA,
        outline=_LETTER_OUTLINE_RGBA,
        width=2,
    )
    draw.rectangle(
        letter_draw_box,
        outline=(*outline, 255),
        width=1,
    )
    draw.text((lx, ly), letter, fill=_LETTER_TEXT_RGBA, font=font)


def _saturate_outline_color(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    r, g, b = rgb
    peak = max(r, g, b)
    if peak <= 0:
        return rgb
    scale = 255.0 / peak
    return (
        min(255, int(r * scale * 0.92)),
        min(255, int(g * scale * 0.92)),
        min(255, int(b * scale * 0.92)),
    )


def _draw_coordinate_grid(draw: Any, img_w: int, img_h: int) -> None:
    """Shared coordinate/reference-cell foundation for scaffold and master overlays."""
    draw_reference_cell_coordinate_foundation(draw, img_w, img_h)


def _draw_template_legend(draw: Any, *, img_w: int, img_h: int) -> None:
    """Compact size/shape legend with distinct colors per size family."""
    title_y = img_h + 6
    draw.text((8, title_y), "Template sizes (square base + wide/portrait cues):", fill=(20, 20, 20))
    row_y = title_y + 18
    col_x = [8, 78, 148, 218]
    for idx, size in enumerate(_SIZE_LEGEND_ORDER):
        color = _LEGEND_SIZE_COLORS[size]
        x0 = col_x[idx]
        sq = _LEGEND_SQUARE_PX[size]
        top = row_y
        left = x0
        draw.rectangle([left, top, left + sq, top + sq], outline=color, fill=color, width=1)
        wide_end = left + sq + _LEGEND_EXTENSION_PX
        _draw_dashed_line(
            draw,
            (left + sq + 2, top + sq // 2),
            (wide_end, top + sq // 2),
            fill=color,
            width=1,
        )
        port_end = top + sq + _LEGEND_EXTENSION_PX
        _draw_dashed_line(
            draw,
            (left + sq // 2, top + sq + 2),
            (left + sq // 2, port_end),
            fill=color,
            width=1,
        )
        draw.text((left, top + sq + 8), _legend_size_label(size), fill=color)
        draw.text((left, top + sq + 20), "sq · wide · port", fill=(70, 70, 70))


def _render_placement_scaffold(img: Any) -> tuple[Any, dict[str, Any]]:
    from PIL import Image, ImageDraw  # type: ignore[import]

    canvas = img.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    _draw_coordinate_grid(draw, img.width, img.height)
    return canvas, build_scaffold_overlay_render_metadata()


def compute_point_crops_scaffold(img: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Render a zero-point coordinate scaffold over the source image."""
    canvas, overlay = _render_placement_scaffold(img)
    return {
        "master_pil": canvas,
        "per_point": [],
        "show": list(params.get("show") or []),
        "legend_height": 0,
        "source_width_height": [img.width, img.height],
        "point_count": 0,
        "overlay": overlay,
    }


def _render_master_overlay(
    img: Any,
    per_point_data: list[dict[str, Any]],
    show: list[str],
    *,
    overlay_role: str = OVERLAY_ROLE_POINT_CROP_MASTER,
) -> tuple[Any, int, dict[str, Any]]:
    from PIL import Image, ImageDraw  # type: ignore[import]

    legend_h = OVERLAY_LEGEND_HEIGHT
    canvas = Image.new("RGB", (img.width, img.height + legend_h), (255, 255, 255))
    canvas.paste(img, (0, 0))
    draw = ImageDraw.Draw(canvas)

    _draw_coordinate_grid(draw, img.width, img.height)

    rgba_base = canvas.convert("RGBA")
    box_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    box_draw = ImageDraw.Draw(box_layer)
    for pt in per_point_data:
        b = tuple(pt["box_px"])
        col = tuple(int(v) for v in pt["color"][:3])
        outline = _saturate_outline_color(col)
        if "box" in show:
            box_draw.rectangle(
                b,
                fill=(*col, _BOX_FILL_ALPHA),
                outline=(*outline, 255),
                width=_BOX_OUTLINE_WIDTH,
            )
        if "pin" in show:
            cx, cy = _pin_center_px(pt)
            _draw_point_pin(box_draw, cx=cx, cy=cy, color=col, outline=outline)

    composed = Image.alpha_composite(rgba_base, box_layer)

    letter_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    letter_draw = ImageDraw.Draw(letter_layer)
    for pt in per_point_data:
        if "letter" not in show:
            continue
        col = tuple(int(v) for v in pt["color"][:3])
        outline = _saturate_outline_color(col)
        cx, cy = _pin_center_px(pt)
        _draw_point_letter(
            letter_draw,
            cx=cx,
            cy=cy,
            letter=str(pt["letter"]),
            color=col,
            outline=outline,
            img_w=img.width,
            img_h=img.height,
        )

    composed = Image.alpha_composite(composed, letter_layer)
    canvas = composed.convert("RGB")

    draw = ImageDraw.Draw(canvas)
    _draw_template_legend(draw, img_w=img.width, img_h=img.height)
    return canvas, legend_h, build_overlay_render_metadata(overlay_role=overlay_role)


def compute_point_crops(img: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Compute master overlay and per-point crops in memory."""
    points = params.get("points") or []
    if len(points) > MAX_POINT_CROP_COUNT:
        raise PointCropParamError(
            "point_crops point count exceeds safety cap (16).",
            repair_hint="Reduce the number of points in a single call.",
        )

    show_raw = params.get("show")
    show = list(show_raw) if isinstance(show_raw, list) and show_raw else list(DEFAULT_SHOW)
    global_zoom = params.get("zoom_factor")
    global_zoom = float(global_zoom) if global_zoom is not None else None
    global_scale_x = params.get("scale_x")
    global_scale_x = float(global_scale_x) if global_scale_x is not None else None
    global_scale_y = params.get("scale_y")
    global_scale_y = float(global_scale_y) if global_scale_y is not None else None

    n = len(points)
    letters = [chr(ord("A") + i) for i in range(n)]
    colors = [_POINT_COLORS[i % len(_POINT_COLORS)] for i in range(n)]

    per_point_data: list[dict[str, Any]] = []
    for i, p in enumerate(points):
        alias = str(p.get("alias") or "").strip()
        point_scale_x = p.get("scale_x")
        point_scale_x = float(point_scale_x) if point_scale_x is not None else None
        point_scale_y = p.get("scale_y")
        point_scale_y = float(point_scale_y) if point_scale_y is not None else None
        scale_x, scale_y = resolve_point_axis_scale(
            global_scale_x=global_scale_x,
            global_scale_y=global_scale_y,
            point_scale_x=point_scale_x,
            point_scale_y=point_scale_y,
        )
        explicit_w, explicit_h = _explicit_dims_from_point(p)
        geo = _compute_single_point_geometry(
            img,
            point_norm=[float(p["point_norm"][0]), float(p["point_norm"][1])],
            size=p["size"],
            shape=p["shape"],
            scale_x=scale_x,
            scale_y=scale_y,
            width_norm=explicit_w,
            height_norm=explicit_h,
        )
        crop_img = img.crop(tuple(geo["box"]))
        point_zoom = p.get("zoom_factor")
        point_zoom = float(point_zoom) if point_zoom is not None else None
        requested_zoom = resolve_point_zoom_factor(
            size=p["size"],
            global_zoom=global_zoom,
            point_zoom=point_zoom,
        )
        zoomed_crop, zoom_meta = _apply_crop_zoom(crop_img, requested_zoom)
        row: dict[str, Any] = {
            "alias": alias,
            "letter": letters[i],
            "color": list(colors[i]),
            "point_norm": geo["point_norm"],
            "pin_px": geo["pin_px"],
            "box_px": geo["box_px"],
            "box_norm": geo["box_norm"],
            "crop_img": zoomed_crop,
            "size": p["size"],
            "shape": p["shape"],
            "scale_x": geo["scale_x"],
            "scale_y": geo["scale_y"],
            "template_width_height_norm": geo["template_width_height_norm"],
            "resolved_width_height_norm": geo["resolved_width_height_norm"],
            **zoom_meta,
        }
        if geo.get("explicit_width_height_norm") is not None:
            row["explicit_width_height_norm"] = geo["explicit_width_height_norm"]
        if isinstance(p.get("graph_ref"), dict):
            row["graph_ref"] = dict(p["graph_ref"])
        per_point_data.append(row)

    canvas, legend_h, overlay = _render_master_overlay(img, per_point_data, show)
    return {
        "master_pil": canvas,
        "per_point": per_point_data,
        "show": show,
        "legend_height": legend_h,
        "source_width_height": [img.width, img.height],
        "point_count": len(points),
        "overlay": overlay,
    }


def compute_point_crops_view(img: Any, points: list[dict[str, Any]], *, show: list[str]) -> dict[str, Any]:
    """Render a filtered crop-set overlay without minting new per-point crops."""
    if not points:
        raise PointCropParamError("point_crops_view requires at least one point to render.")
    if len(points) > MAX_POINT_CROP_COUNT:
        raise PointCropParamError("point_crops_view point count exceeds safety cap (16).")

    per_point_data: list[dict[str, Any]] = []
    for i, p in enumerate(points):
        alias = str(p.get("alias") or "").strip()
        letter = str(p.get("letter") or chr(ord("A") + i)).strip().upper()
        color_raw = p.get("color")
        if isinstance(color_raw, (list, tuple)) and len(color_raw) >= 3:
            color = [int(color_raw[0]), int(color_raw[1]), int(color_raw[2])]
        else:
            color = list(_POINT_COLORS[i % len(_POINT_COLORS)])
        scale_x = float(p["scale_x"]) if p.get("scale_x") is not None else 1.0
        scale_y = float(p["scale_y"]) if p.get("scale_y") is not None else 1.0
        explicit_w, explicit_h = _explicit_dims_from_point(p)
        geo = _compute_single_point_geometry(
            img,
            point_norm=[float(p["point_norm"][0]), float(p["point_norm"][1])],
            size=str(p["size"]),
            shape=str(p["shape"]),
            scale_x=scale_x,
            scale_y=scale_y,
            width_norm=explicit_w,
            height_norm=explicit_h,
        )
        row: dict[str, Any] = {
            "alias": alias,
            "letter": letter,
            "color": color,
            "point_norm": geo["point_norm"],
            "pin_px": geo["pin_px"],
            "box_px": geo["box_px"],
            "box_norm": geo["box_norm"],
            "size": p["size"],
            "shape": p["shape"],
            "scale_x": geo["scale_x"],
            "scale_y": geo["scale_y"],
            "template_width_height_norm": geo["template_width_height_norm"],
            "resolved_width_height_norm": geo["resolved_width_height_norm"],
        }
        if geo.get("explicit_width_height_norm") is not None:
            row["explicit_width_height_norm"] = geo["explicit_width_height_norm"]
        crop_ref = p.get("crop_ref")
        if isinstance(crop_ref, str) and crop_ref.strip():
            row["crop_ref"] = crop_ref.strip()
        if isinstance(p.get("graph_ref"), dict):
            row["graph_ref"] = dict(p["graph_ref"])
        per_point_data.append(row)

    canvas, legend_h, overlay = _render_master_overlay(
        img,
        per_point_data,
        show,
        overlay_role=OVERLAY_ROLE_POINT_CROP_VIEW,
    )
    return {
        "master_pil": canvas,
        "per_point": per_point_data,
        "show": show,
        "legend_height": legend_h,
        "source_width_height": [img.width, img.height],
        "point_count": len(points),
        "overlay": overlay,
    }


def build_crop_set_point_record(point: dict[str, Any], *, crop_ref: str | None = None) -> dict[str, Any]:
    """Compact recoverable point row for crop-set sidecar and master metadata."""
    row: dict[str, Any] = {
        "alias": point["alias"],
        "letter": point["letter"],
        "color": point["color"],
        "point_norm": point["point_norm"],
        "box_px": point["box_px"],
        "box_norm": point["box_norm"],
        "size": point["size"],
        "shape": point["shape"],
    }
    if crop_ref:
        row["crop_ref"] = crop_ref
    elif isinstance(point.get("crop_ref"), str) and point["crop_ref"].strip():
        row["crop_ref"] = point["crop_ref"].strip()
    if isinstance(point.get("graph_ref"), dict):
        row["graph_ref"] = dict(point["graph_ref"])
    row.update(_copy_zoom_metadata(point))
    row.update(_copy_scale_metadata(point))
    row.update(copy_projection_fields(point))
    return row


def _copy_scale_metadata(source: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in (
        "scale_x",
        "scale_y",
        "explicit_width_height_norm",
        "template_width_height_norm",
        "resolved_width_height_norm",
    ):
        if key in source:
            out[key] = source[key]
    return out


def _validate_show_param(params: dict[str, Any]) -> str | None:
    show = params.get("show")
    if show is not None:
        if not isinstance(show, list):
            return "params.show must be a list or omitted."
        for s in show:
            if s not in ALLOWED_SHOW:
                return f"params.show may only contain {sorted(ALLOWED_SHOW)}."
    return None


def _clamp_point_norm(x: float, y: float) -> list[float]:
    return [round(max(0.0, min(1.0, float(x))), 6), round(max(0.0, min(1.0, float(y))), 6)]


def extract_crop_set_from_master_descriptor(desc: dict[str, Any]) -> dict[str, Any]:
    """Return recoverable crop-set summary from a master overlay descriptor."""
    meta = desc.get("transform_metadata")
    if not isinstance(meta, dict):
        raise PointCropParamError(
            "Master overlay ref does not contain recoverable point_crops metadata.",
            repair_hint="Use ref_id of a prior point_crops master overlay (image:derived:*).",
        )
    crop_set = meta.get("crop_set")
    if not isinstance(crop_set, dict):
        raise PointCropParamError(
            "Master overlay ref does not contain recoverable point_crops metadata.",
            repair_hint="Use ref_id of a prior point_crops master overlay (image:derived:*).",
        )
    points = crop_set.get("points")
    if not isinstance(points, list) or not points:
        raise PointCropParamError(
            "Master overlay crop_set.points is missing or empty.",
            repair_hint="Create a point_crops set first, then adjust its master overlay ref.",
        )
    source_ref = str(meta.get("source_ref") or desc.get("parent_ref_id") or "").strip()
    if not source_ref:
        raise PointCropParamError(
            "Master overlay metadata is missing source_ref.",
            repair_hint="Use a master overlay produced by point_crops or point_crops_adjust.",
        )
    show_raw = meta.get("show")
    show = list(show_raw) if isinstance(show_raw, list) and show_raw else list(DEFAULT_SHOW)
    return {
        "source_ref": source_ref,
        "show": show,
        "legend_height": meta.get("legend_height"),
        "source_width_height": meta.get("source_width_height"),
        "points": list(points),
    }


def validate_point_crops_adjust_params(params: dict[str, Any]) -> str | None:
    """Basic shape validation before descriptor load (non-empty adjust list)."""
    adjust = params.get("adjust")
    if not isinstance(adjust, list) or not adjust:
        return "point_crops_adjust requires params.adjust as a non-empty list."
    show_err = _validate_show_param(params)
    if show_err:
        return show_err
    return None


def point_crops_adjust_repair_hint_for(message: str) -> str | None:
    if "non-empty list" in message and "adjust" in message:
        return (
            'Provide params.adjust = [{"letter": "B", "shift_norm": [0.015, 0.0]}, '
            '{"alias": "...", "size": "large", "shape": "wide"}]'
        )
    if "letter" in message and "alias" in message:
        return "Each adjustment row must target exactly one point via letter OR alias, not both."
    if "no actual change" in message:
        return (
            "Provide point_norm, shift_norm, size, shape, width_norm, height_norm, scale_x, scale_y, "
            "and/or zoom_factor values that change the target point."
        )
    if "width_norm" in message or "height_norm" in message:
        return (
            f"Provide width_norm and height_norm together, each between "
            f"{MIN_EXPLICIT_DIM_NORM} and {MAX_EXPLICIT_DIM_NORM}."
        )
    if "scale_x" in message or "scale_y" in message:
        return (
            f"Use scale_x/scale_y between {MIN_AXIS_SCALE} and {MAX_AXIS_SCALE} "
            "on each adjust row."
        )
    if "does not contain recoverable" in message:
        return "Set ref_id to the master overlay ref returned by a prior point_crops call."
    if "Unknown" in message or "not found in prior crop set" in message:
        return "Use a letter or alias from the prior crop_set.points metadata."
    return None


def prepare_point_crops_adjust(
    master_desc: dict[str, Any],
    params: dict[str, Any],
    *,
    adjustment_source_ref: str,
) -> dict[str, Any]:
    """Reconstruct prior points, apply adjustments, return compute-ready bundle."""
    prior = extract_crop_set_from_master_descriptor(master_desc)
    adjust = params.get("adjust")
    if not isinstance(adjust, list) or not adjust:
        raise PointCropParamError(
            "point_crops_adjust requires params.adjust as a non-empty list.",
            repair_hint=point_crops_adjust_repair_hint_for(
                "point_crops_adjust requires params.adjust as a non-empty list."
            ),
        )
    show_err = _validate_show_param(params)
    if show_err:
        raise PointCropParamError(show_err)

    show_raw = params.get("show")
    show = list(show_raw) if isinstance(show_raw, list) and show_raw else list(prior["show"])

    by_letter: dict[str, dict[str, Any]] = {}
    by_alias: dict[str, dict[str, Any]] = {}
    working_points: list[dict[str, Any]] = []
    for pt in prior["points"]:
        if not isinstance(pt, dict):
            raise PointCropParamError("Prior crop_set.points entries must be objects.")
        alias = str(pt.get("alias") or "").strip()
        letter = str(pt.get("letter") or "").strip().upper()
        if not alias or not letter:
            raise PointCropParamError("Prior crop_set point is missing alias or letter.")
        pn = pt.get("point_norm")
        if not isinstance(pn, (list, tuple)) or len(pn) != 2:
            raise PointCropParamError(f"Prior crop_set point {alias!r} has invalid point_norm.")
        size = str(pt.get("size") or "").strip().lower()
        shape = str(pt.get("shape") or "").strip().lower()
        if size not in ALLOWED_SIZES or shape not in ALLOWED_SHAPES:
            raise PointCropParamError(f"Prior crop_set point {alias!r} has invalid size/shape.")
        row = {
            "alias": alias,
            "letter": letter,
            "point_norm": [float(pn[0]), float(pn[1])],
            "size": size,
            "shape": shape,
        }
        if isinstance(pt.get("graph_ref"), dict):
            row["graph_ref"] = dict(pt["graph_ref"])
        prior_zoom = pt.get("zoom_factor")
        if prior_zoom is not None:
            try:
                row["zoom_factor"] = _normalize_zoom_factor(prior_zoom)
            except (TypeError, ValueError):
                pass
        for axis in ("scale_x", "scale_y"):
            prior_scale = pt.get(axis)
            if prior_scale is not None:
                try:
                    row[axis] = _normalize_axis_scale(prior_scale)
                except (TypeError, ValueError):
                    pass
        explicit_w, explicit_h = _explicit_dims_from_point(pt)
        if explicit_w is not None and explicit_h is not None:
            row["width_norm"] = explicit_w
            row["height_norm"] = explicit_h
        working_points.append(row)
        by_letter[letter] = row
        by_alias[alias] = row

    seen_targets: set[str] = set()
    adjustments_applied: list[dict[str, Any]] = []

    for i, adj in enumerate(adjust):
        if not isinstance(adj, dict):
            raise PointCropParamError(f"params.adjust[{i}] must be an object.")
        has_letter = bool(str(adj.get("letter") or "").strip())
        has_alias = bool(str(adj.get("alias") or "").strip())
        if has_letter and has_alias:
            raise PointCropParamError(
                f"params.adjust[{i}] must specify exactly one target via letter OR alias, not both.",
                repair_hint=point_crops_adjust_repair_hint_for(
                    "params.adjust letter and alias together"
                ),
            )
        if not has_letter and not has_alias:
            raise PointCropParamError(
                f"params.adjust[{i}] must specify exactly one target via letter or alias.",
            )
        if has_letter:
            letter = str(adj["letter"]).strip().upper()
            target_key = f"letter:{letter}"
            target_row = by_letter.get(letter)
            if target_row is None:
                raise PointCropParamError(
                    f"Unknown letter {letter!r} in params.adjust[{i}]; not found in prior crop set.",
                )
            target = {"letter": letter}
        else:
            alias = str(adj["alias"]).strip()
            target_key = f"alias:{alias}"
            target_row = by_alias.get(alias)
            if target_row is None:
                raise PointCropParamError(
                    f"Unknown alias {alias!r} in params.adjust[{i}]; not found in prior crop set.",
                )
            target = {"alias": alias}

        if target_key in seen_targets:
            raise PointCropParamError(
                f"Duplicate adjustment target in params.adjust: {target_key.split(':', 1)[1]!r}.",
                repair_hint="Adjust each letter or alias at most once per request.",
            )
        seen_targets.add(target_key)

        prior_point_norm = list(target_row["point_norm"])
        prior_size = target_row["size"]
        prior_shape = target_row["shape"]
        prior_zoom_factor = target_row.get("zoom_factor")
        prior_scale_x = float(target_row.get("scale_x", 1.0))
        prior_scale_y = float(target_row.get("scale_y", 1.0))
        prior_width_norm, prior_height_norm = _explicit_dims_from_point(target_row)
        new_point_norm = list(prior_point_norm)
        new_size = prior_size
        new_shape = prior_shape
        new_zoom_factor = prior_zoom_factor
        new_scale_x = prior_scale_x
        new_scale_y = prior_scale_y
        new_width_norm = prior_width_norm
        new_height_norm = prior_height_norm
        shift_applied: list[float] | None = None

        change_fields = (
            "point_norm",
            "shift_norm",
            "size",
            "shape",
            "zoom_factor",
            "scale_x",
            "scale_y",
            "width_norm",
            "height_norm",
        )
        if not any(field in adj for field in change_fields):
            raise PointCropParamError(
                f"params.adjust[{i}] specifies no actual change (need point_norm, shift_norm, size, shape, width_norm, height_norm, scale_x, scale_y, and/or zoom_factor).",
                repair_hint=point_crops_adjust_repair_hint_for("no actual change"),
            )

        if "point_norm" in adj:
            pn = adj["point_norm"]
            if not isinstance(pn, (list, tuple)) or len(pn) != 2:
                raise PointCropParamError(f"params.adjust[{i}].point_norm must be [x, y] in [0,1].")
            try:
                x, y = float(pn[0]), float(pn[1])
                if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                    raise ValueError
            except Exception:
                raise PointCropParamError(
                    f"params.adjust[{i}].point_norm values must be in [0.0, 1.0].",
                ) from None
            new_point_norm = [x, y]

        if "shift_norm" in adj:
            sn = adj["shift_norm"]
            if not isinstance(sn, (list, tuple)) or len(sn) != 2:
                raise PointCropParamError(f"params.adjust[{i}].shift_norm must be [dx, dy].")
            try:
                dx, dy = float(sn[0]), float(sn[1])
            except Exception:
                raise PointCropParamError(
                    f"params.adjust[{i}].shift_norm values must be numeric.",
                ) from None
            new_point_norm = [new_point_norm[0] + dx, new_point_norm[1] + dy]
            shift_applied = [round(dx, 6), round(dy, 6)]

        new_point_norm = _clamp_point_norm(new_point_norm[0], new_point_norm[1])

        if "size" in adj:
            size = str(adj.get("size") or "").strip().lower()
            if size not in ALLOWED_SIZES:
                raise PointCropParamError(f"params.adjust[{i}].size must be {_SIZE_OPTIONS_TEXT}.")
            new_size = size

        if "shape" in adj:
            shape = str(adj.get("shape") or "").strip().lower()
            if shape not in ALLOWED_SHAPES:
                raise PointCropParamError(f"params.adjust[{i}].shape must be wide|portrait|square.")
            new_shape = shape

        if "zoom_factor" in adj:
            zoom_err = _validate_zoom_factor_raw(
                adj.get("zoom_factor"),
                f"params.adjust[{i}].zoom_factor",
            )
            if zoom_err:
                raise PointCropParamError(zoom_err)
            new_zoom_factor = _normalize_zoom_factor(adj["zoom_factor"])

        if "scale_x" in adj:
            scale_err = _validate_axis_scale_raw(
                adj.get("scale_x"),
                f"params.adjust[{i}].scale_x",
            )
            if scale_err:
                raise PointCropParamError(scale_err)
            new_scale_x = _normalize_axis_scale(adj["scale_x"])
        if "scale_y" in adj:
            scale_err = _validate_axis_scale_raw(
                adj.get("scale_y"),
                f"params.adjust[{i}].scale_y",
            )
            if scale_err:
                raise PointCropParamError(scale_err)
            new_scale_y = _normalize_axis_scale(adj["scale_y"])

        if "width_norm" in adj or "height_norm" in adj:
            if "width_norm" not in adj or "height_norm" not in adj:
                raise PointCropParamError(
                    f"params.adjust[{i}] must include both width_norm and height_norm together.",
                    repair_hint=point_crops_adjust_repair_hint_for("width_norm"),
                )
            for key in ("width_norm", "height_norm"):
                dim_err = _validate_explicit_dim_raw(
                    adj.get(key),
                    f"params.adjust[{i}].{key}",
                )
                if dim_err:
                    raise PointCropParamError(dim_err)
            new_width_norm = _normalize_explicit_dim(adj["width_norm"])
            new_height_norm = _normalize_explicit_dim(adj["height_norm"])

        prior_zoom_effective = resolve_point_zoom_factor(
            size=prior_size,
            point_zoom=float(prior_zoom_factor) if prior_zoom_factor is not None else None,
        )
        new_zoom_effective = resolve_point_zoom_factor(
            size=new_size,
            point_zoom=float(new_zoom_factor) if new_zoom_factor is not None else None,
        )

        if (
            new_point_norm == [round(prior_point_norm[0], 6), round(prior_point_norm[1], 6)]
            and new_size == prior_size
            and new_shape == prior_shape
            and new_zoom_effective == prior_zoom_effective
            and _normalize_axis_scale(new_scale_x) == _normalize_axis_scale(prior_scale_x)
            and _normalize_axis_scale(new_scale_y) == _normalize_axis_scale(prior_scale_y)
            and _explicit_dimensions_equal(
                prior_width_norm,
                prior_height_norm,
                new_width_norm,
                new_height_norm,
            )
        ):
            raise PointCropParamError(
                f"params.adjust[{i}] specifies no actual change for the selected target.",
                repair_hint=point_crops_adjust_repair_hint_for("no actual change"),
            )

        target_row["point_norm"] = new_point_norm
        target_row["size"] = new_size
        target_row["shape"] = new_shape
        if new_zoom_factor is not None:
            target_row["zoom_factor"] = new_zoom_factor
        elif "zoom_factor" not in target_row and new_size != prior_size:
            target_row.pop("zoom_factor", None)
        if _normalize_axis_scale(new_scale_x) != 1.0:
            target_row["scale_x"] = _normalize_axis_scale(new_scale_x)
        else:
            target_row.pop("scale_x", None)
        if _normalize_axis_scale(new_scale_y) != 1.0:
            target_row["scale_y"] = _normalize_axis_scale(new_scale_y)
        else:
            target_row.pop("scale_y", None)
        if new_width_norm is not None and new_height_norm is not None:
            target_row["width_norm"] = _normalize_explicit_dim(new_width_norm)
            target_row["height_norm"] = _normalize_explicit_dim(new_height_norm)
        else:
            target_row.pop("width_norm", None)
            target_row.pop("height_norm", None)

        applied: dict[str, Any] = {
            "target": target,
            "prior_point_norm": [round(prior_point_norm[0], 6), round(prior_point_norm[1], 6)],
            "new_point_norm": new_point_norm,
            "prior_size": prior_size,
            "new_size": new_size,
            "prior_shape": prior_shape,
            "new_shape": new_shape,
        }
        if prior_zoom_effective != new_zoom_effective:
            applied["prior_zoom_factor"] = prior_zoom_effective
            applied["new_zoom_factor"] = new_zoom_effective
        if _normalize_axis_scale(prior_scale_x) != _normalize_axis_scale(new_scale_x):
            applied["prior_scale_x"] = _normalize_axis_scale(prior_scale_x)
            applied["new_scale_x"] = _normalize_axis_scale(new_scale_x)
        if _normalize_axis_scale(prior_scale_y) != _normalize_axis_scale(new_scale_y):
            applied["prior_scale_y"] = _normalize_axis_scale(prior_scale_y)
            applied["new_scale_y"] = _normalize_axis_scale(new_scale_y)
        if prior_width_norm != new_width_norm or prior_height_norm != new_height_norm:
            applied["prior_width_height_norm"] = (
                [_normalize_explicit_dim(prior_width_norm), _normalize_explicit_dim(prior_height_norm)]
                if prior_width_norm is not None and prior_height_norm is not None
                else None
            )
            applied["new_width_height_norm"] = (
                [_normalize_explicit_dim(new_width_norm), _normalize_explicit_dim(new_height_norm)]
                if new_width_norm is not None and new_height_norm is not None
                else None
            )
        if shift_applied is not None:
            applied["shift_norm"] = shift_applied
        adjustments_applied.append(applied)

    compute_points = []
    for pt in working_points:
        point_row = {
            "alias": pt["alias"],
            "point_norm": pt["point_norm"],
            "size": pt["size"],
            "shape": pt["shape"],
        }
        if isinstance(pt.get("graph_ref"), dict):
            point_row["graph_ref"] = dict(pt["graph_ref"])
        if pt.get("zoom_factor") is not None:
            point_row["zoom_factor"] = pt["zoom_factor"]
        for axis in ("scale_x", "scale_y"):
            if pt.get(axis) is not None:
                point_row[axis] = pt[axis]
        if pt.get("width_norm") is not None and pt.get("height_norm") is not None:
            point_row["width_norm"] = pt["width_norm"]
            point_row["height_norm"] = pt["height_norm"]
        compute_points.append(point_row)

    return {
        "source_ref": prior["source_ref"],
        "show": show,
        "points": compute_points,
        "previous_crop_set_overlay_ref": adjustment_source_ref,
        "adjustment_source_ref": adjustment_source_ref,
        "adjustments_applied": adjustments_applied,
    }


def validate_point_crops_view_params(params: dict[str, Any]) -> str | None:
    show_err = _validate_show_param(params)
    if show_err:
        return show_err
    filter_raw = params.get("filter")
    if filter_raw is None:
        return None
    if not isinstance(filter_raw, dict):
        return "params.filter must be an object when provided."
    letters = filter_raw.get("letters")
    aliases = filter_raw.get("aliases")
    if letters is not None:
        if not isinstance(letters, list) or not letters:
            return "params.filter.letters must be a non-empty list when provided."
    if aliases is not None:
        if not isinstance(aliases, list) or not aliases:
            return "params.filter.aliases must be a non-empty list when provided."
    if letters is None and aliases is None:
        return "params.filter must include letters and/or aliases when provided."
    return None


def point_crops_view_repair_hint_for(message: str) -> str | None:
    if "filter" in message and "letters" in message:
        return 'Use params.filter = {"letters": ["A", "C"]} or {"aliases": ["parcel_1_tie_bearing"]}.'
    if "does not contain recoverable" in message:
        return "Set ref_id to the master overlay ref returned by a prior point_crops call."
    if "Unknown letter" in message or "Unknown alias" in message:
        return "Filter targets must exist in the prior crop_set.points metadata."
    return None


def prepare_point_crops_view(
    master_desc: dict[str, Any],
    params: dict[str, Any],
    *,
    view_source_ref: str,
) -> dict[str, Any]:
    prior = extract_crop_set_from_master_descriptor(master_desc)
    show_err = _validate_show_param(params)
    if show_err:
        raise PointCropParamError(show_err)

    show_raw = params.get("show")
    show = list(show_raw) if isinstance(show_raw, list) and show_raw else list(prior["show"])

    filter_raw = params.get("filter")
    selected: list[dict[str, Any]] = []
    if isinstance(filter_raw, dict):
        letters_wanted = {
            str(v).strip().upper()
            for v in (filter_raw.get("letters") or [])
            if str(v).strip()
        }
        aliases_wanted = {
            str(v).strip()
            for v in (filter_raw.get("aliases") or [])
            if str(v).strip()
        }
        if not letters_wanted and not aliases_wanted:
            raise PointCropParamError("params.filter must include at least one letter or alias target.")

        known_letters = {
            str(pt.get("letter") or "").strip().upper()
            for pt in prior["points"]
            if isinstance(pt, dict)
        }
        known_aliases = {
            str(pt.get("alias") or "").strip()
            for pt in prior["points"]
            if isinstance(pt, dict)
        }
        for letter in letters_wanted:
            if letter not in known_letters:
                raise PointCropParamError(
                    f"Unknown letter {letter!r} in params.filter.letters; not found in prior crop set.",
                    repair_hint=point_crops_view_repair_hint_for("Unknown letter"),
                )
        for alias in aliases_wanted:
            if alias not in known_aliases:
                raise PointCropParamError(
                    f"Unknown alias {alias!r} in params.filter.aliases; not found in prior crop set.",
                    repair_hint=point_crops_view_repair_hint_for("Unknown alias"),
                )

        for pt in prior["points"]:
            if not isinstance(pt, dict):
                continue
            letter = str(pt.get("letter") or "").strip().upper()
            alias = str(pt.get("alias") or "").strip()
            if letter in letters_wanted or alias in aliases_wanted:
                selected.append(dict(pt))
        if not selected:
            raise PointCropParamError(
                "params.filter matched no points in the prior crop set.",
            )
    else:
        selected = [dict(pt) for pt in prior["points"] if isinstance(pt, dict)]

    return {
        "source_ref": prior["source_ref"],
        "show": show,
        "points": selected,
        "view_of_crop_set_overlay_ref": view_source_ref,
        "filter": dict(filter_raw) if isinstance(filter_raw, dict) else None,
    }

