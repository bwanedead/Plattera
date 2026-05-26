"""Point-crop template computation and rendering (pure, side-effect free).

The ``transform_artifact`` handler owns ref minting, persistence, and descriptors.
This module computes geometry, crops, and the master overlay in memory only.
"""

from __future__ import annotations

from typing import Any

# Normalized box sizes centered on ``point_norm``.
_POINT_CROP_TEMPLATES: dict[str, dict[str, tuple[float, float]]] = {
    "small": {
        "wide": (0.07, 0.028),
        "portrait": (0.028, 0.07),
        "square": (0.045, 0.045),
    },
    "medium": {
        "wide": (0.13, 0.045),
        "portrait": (0.045, 0.13),
        "square": (0.08, 0.08),
    },
    "large": {
        "wide": (0.22, 0.065),
        "portrait": (0.065, 0.22),
        "square": (0.13, 0.13),
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
DEFAULT_SHOW = ["pin", "box", "letter"]
ALLOWED_SHOW = frozenset({"pin", "box", "letter"})
ALLOWED_SIZES = frozenset({"small", "medium", "large"})
ALLOWED_SHAPES = frozenset({"wide", "portrait", "square"})
MAX_GRAPH_REF_KEYS = 8
MAX_GRAPH_REF_VALUE_CHARS = 120


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
            return f"params.points[{i}].size must be small|medium|large."
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
    return _validate_show_param(params) or None


def point_crops_repair_hint_for(message: str) -> str | None:
    if "non-empty list" in message:
        return (
            'Provide params.points = [{"alias": "...", "point_norm": [x,y], '
            '"size": "small|medium|large", "shape": "wide|portrait|square"}, ...]'
        )
    if "exceeds safety cap" in message:
        return "Reduce the number of points in a single call."
    return None


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


def _compute_single_point_geometry(
    img: Any,
    *,
    point_norm: list[float],
    size: str,
    shape: str,
) -> dict[str, Any]:
    x, y = float(point_norm[0]), float(point_norm[1])
    w, h = _POINT_CROP_TEMPLATES[size][shape]

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
    return {
        "point_norm": [round(x, 6), round(y, 6)],
        "box_px": [box[0], box[1], box[2], box[3]],
        "box_norm": [
            round(left / img.width, 6),
            round(top / img.height, 6),
            round(right / img.width, 6),
            round(bottom / img.height, 6),
        ],
        "box": box,
    }


def _render_master_overlay(img: Any, per_point_data: list[dict[str, Any]], show: list[str]) -> tuple[Any, int]:
    from PIL import Image, ImageDraw  # type: ignore[import]

    legend_h = 120
    canvas = Image.new("RGB", (img.width, img.height + legend_h), (255, 255, 255))
    canvas.paste(img, (0, 0))
    draw = ImageDraw.Draw(canvas)

    for pt in per_point_data:
        b = tuple(pt["box_px"])
        col = tuple(pt["color"])
        if "box" in show:
            draw.rectangle(b, outline=col, width=2)
        if "pin" in show:
            cx = (b[0] + b[2]) // 2
            cy = (b[1] + b[3]) // 2
            r = 5
            draw.line([(cx - r, cy), (cx + r, cy)], fill=col, width=2)
            draw.line([(cx, cy - r), (cx, cy + r)], fill=col, width=2)
        if "letter" in show:
            lx, ly = b[0] + 2, max(0, b[1] - 14)
            draw.rectangle([lx - 1, ly - 1, lx + 12, ly + 12], fill=(255, 255, 255))
            draw.text((lx, ly), pt["letter"], fill=col)

    ly = img.height + 6
    draw.text((8, ly), "Point Crop Templates (reference):", fill=(0, 0, 0))
    example_y = ly + 18
    ex = 10
    for sz in ("small", "medium", "large"):
        for sh in ("wide", "portrait", "square"):
            ew, eh = _POINT_CROP_TEMPLATES[sz][sh]
            ew_px = max(12, int(ew * 120))
            eh_px = max(8, int(eh * 120))
            draw.rectangle([ex, example_y, ex + ew_px, example_y + eh_px], outline=(80, 80, 80), width=1)
            draw.text((ex, example_y + eh_px + 1), f"{sz[0]}{sh[0]}", fill=(60, 60, 60))
            ex += ew_px + 18
        ex += 10
    return canvas, legend_h


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

    n = len(points)
    letters = [chr(ord("A") + i) for i in range(n)]
    colors = [_POINT_COLORS[i % len(_POINT_COLORS)] for i in range(n)]

    per_point_data: list[dict[str, Any]] = []
    for i, p in enumerate(points):
        alias = str(p.get("alias") or "").strip()
        geo = _compute_single_point_geometry(
            img,
            point_norm=[float(p["point_norm"][0]), float(p["point_norm"][1])],
            size=p["size"],
            shape=p["shape"],
        )
        crop_img = img.crop(tuple(geo["box"]))
        row: dict[str, Any] = {
            "alias": alias,
            "letter": letters[i],
            "color": list(colors[i]),
            "point_norm": geo["point_norm"],
            "box_px": geo["box_px"],
            "box_norm": geo["box_norm"],
            "crop_img": crop_img,
            "size": p["size"],
            "shape": p["shape"],
        }
        if isinstance(p.get("graph_ref"), dict):
            row["graph_ref"] = dict(p["graph_ref"])
        per_point_data.append(row)

    canvas, legend_h = _render_master_overlay(img, per_point_data, show)
    return {
        "master_pil": canvas,
        "per_point": per_point_data,
        "show": show,
        "legend_height": legend_h,
        "source_width_height": [img.width, img.height],
        "point_count": len(points),
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
        geo = _compute_single_point_geometry(
            img,
            point_norm=[float(p["point_norm"][0]), float(p["point_norm"][1])],
            size=str(p["size"]),
            shape=str(p["shape"]),
        )
        row: dict[str, Any] = {
            "alias": alias,
            "letter": letter,
            "color": color,
            "point_norm": geo["point_norm"],
            "box_px": geo["box_px"],
            "box_norm": geo["box_norm"],
            "size": p["size"],
            "shape": p["shape"],
        }
        crop_ref = p.get("crop_ref")
        if isinstance(crop_ref, str) and crop_ref.strip():
            row["crop_ref"] = crop_ref.strip()
        if isinstance(p.get("graph_ref"), dict):
            row["graph_ref"] = dict(p["graph_ref"])
        per_point_data.append(row)

    canvas, legend_h = _render_master_overlay(img, per_point_data, show)
    return {
        "master_pil": canvas,
        "per_point": per_point_data,
        "show": show,
        "legend_height": legend_h,
        "source_width_height": [img.width, img.height],
        "point_count": len(points),
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
    return row


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
        return "Provide point_norm, shift_norm, size, and/or shape values that change the target point."
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
        new_point_norm = list(prior_point_norm)
        new_size = prior_size
        new_shape = prior_shape
        shift_applied: list[float] | None = None

        change_fields = ("point_norm", "shift_norm", "size", "shape")
        if not any(field in adj for field in change_fields):
            raise PointCropParamError(
                f"params.adjust[{i}] specifies no actual change (need point_norm, shift_norm, size, and/or shape).",
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
                raise PointCropParamError(f"params.adjust[{i}].size must be small|medium|large.")
            new_size = size

        if "shape" in adj:
            shape = str(adj.get("shape") or "").strip().lower()
            if shape not in ALLOWED_SHAPES:
                raise PointCropParamError(f"params.adjust[{i}].shape must be wide|portrait|square.")
            new_shape = shape

        if (
            new_point_norm == [round(prior_point_norm[0], 6), round(prior_point_norm[1], 6)]
            and new_size == prior_size
            and new_shape == prior_shape
        ):
            raise PointCropParamError(
                f"params.adjust[{i}] specifies no actual change for the selected target.",
                repair_hint=point_crops_adjust_repair_hint_for("no actual change"),
            )

        target_row["point_norm"] = new_point_norm
        target_row["size"] = new_size
        target_row["shape"] = new_shape

        applied: dict[str, Any] = {
            "target": target,
            "prior_point_norm": [round(prior_point_norm[0], 6), round(prior_point_norm[1], 6)],
            "new_point_norm": new_point_norm,
            "prior_size": prior_size,
            "new_size": new_size,
            "prior_shape": prior_shape,
            "new_shape": new_shape,
        }
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

