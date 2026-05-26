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
    if len(points) > MAX_POINT_CROP_COUNT:
        return "point_crops point count exceeds safety cap (16)."
    show = params.get("show")
    if show is not None:
        if not isinstance(show, list):
            return "params.show must be a list or omitted."
        for s in show:
            if s not in ALLOWED_SHOW:
                return f"params.show may only contain {sorted(ALLOWED_SHOW)}."
    return None


def point_crops_repair_hint_for(message: str) -> str | None:
    if "non-empty list" in message:
        return (
            'Provide params.points = [{"alias": "...", "point_norm": [x,y], '
            '"size": "small|medium|large", "shape": "wide|portrait|square"}, ...]'
        )
    if "exceeds safety cap" in message:
        return "Reduce the number of points in a single call."
    return None


def compute_point_crops(img: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Compute master overlay and per-point crops in memory.

    Returns a metadata dict consumed by the ``point_crops`` handler branch.
    """
    from PIL import Image, ImageDraw  # type: ignore[import]

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
        x, y = float(p["point_norm"][0]), float(p["point_norm"][1])
        w, h = _POINT_CROP_TEMPLATES[p["size"]][p["shape"]]

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
        crop_img = img.crop(box)

        per_point_data.append(
            {
                "alias": alias,
                "letter": letters[i],
                "color": list(colors[i]),
                "point_norm": [round(x, 6), round(y, 6)],
                "box_px": [box[0], box[1], box[2], box[3]],
                "box_norm": [
                    round(left / img.width, 6),
                    round(top / img.height, 6),
                    round(right / img.width, 6),
                    round(bottom / img.height, 6),
                ],
                "crop_img": crop_img,
                "size": p["size"],
                "shape": p["shape"],
            }
        )

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

    return {
        "master_pil": canvas,
        "per_point": per_point_data,
        "show": show,
        "legend_height": legend_h,
        "source_width_height": [img.width, img.height],
        "point_count": len(points),
    }


def build_crop_set_point_record(point: dict[str, Any], *, crop_ref: str) -> dict[str, Any]:
    """Compact recoverable point row for crop-set sidecar and master metadata."""
    return {
        "alias": point["alias"],
        "letter": point["letter"],
        "color": point["color"],
        "crop_ref": crop_ref,
        "point_norm": point["point_norm"],
        "box_px": point["box_px"],
        "box_norm": point["box_norm"],
        "size": point["size"],
        "shape": point["shape"],
    }
