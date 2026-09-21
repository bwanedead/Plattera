"""Point-anchored window extents geometry for point_crops (BR-039).

Resolves agent-authored left/right/up/down extents relative to ``point_norm``.
Clamps only out-of-image sides — does not shift the window to preserve size.
"""

from __future__ import annotations

import math
from typing import Any

WINDOW_EXTENTS_KEYS = ("left", "right", "up", "down")
GEOMETRY_FORM_WINDOW_EXTENTS = "window_extents"

# Zoom default when no template size is present (matches medium).
DEFAULT_WINDOW_EXTENTS_ZOOM = 2.25

# Soft upper bound per side (full image); values above refuse.
MAX_EXTENT_NORM = 1.0

_CENTERED_GEOMETRY_KEYS = frozenset(
    {"size", "shape", "width_norm", "height_norm", "scale_x", "scale_y"}
)
_TRIM_CONFLICT_KEYS = frozenset({"trim_to_text_block", "trim_axis", "trim_padding_norm"})
# Request-level controls incompatible with any extents point (key presence).
_GLOBAL_EXTENTS_CONFLICT_KEYS = frozenset(
    {"scale_x", "scale_y", "trim_to_text_block", "trim_axis", "trim_padding_norm"}
)
_POINT_EXTENTS_CONFLICT_KEYS = _CENTERED_GEOMETRY_KEYS | _TRIM_CONFLICT_KEYS


class WindowExtentsError(Exception):
    """Invalid or conflicting window_extents_norm request."""

    def __init__(self, message: str, *, repair_hint: str | None = None) -> None:
        super().__init__(message)
        self.repair_hint = repair_hint


def is_finite_number(value: Any) -> bool:
    if type(value) is bool:
        return False
    if type(value) is not int and type(value) is not float:
        return False
    return math.isfinite(float(value))


def point_has_window_extents(point: dict[str, Any]) -> bool:
    return "window_extents_norm" in point and point.get("window_extents_norm") is not None


def conflicting_keys_present(source: dict[str, Any], keys: frozenset[str]) -> list[str]:
    """Exact key-presence conflicts (value may be null / empty / any)."""
    return sorted(k for k in keys if k in source)


def validate_window_extents_object(
    raw: Any,
    *,
    field_prefix: str,
) -> dict[str, float]:
    """Parse and validate ``window_extents_norm``; return normalized extents."""
    if type(raw) is not dict:
        raise WindowExtentsError(
            f"{field_prefix} must be an object with left, right, up, and down.",
            repair_hint=(
                'Provide window_extents_norm as {"left": n, "right": n, "up": n, "down": n} '
                "with non-negative finite numbers."
            ),
        )
    unknown = sorted(set(raw) - set(WINDOW_EXTENTS_KEYS))
    if unknown:
        raise WindowExtentsError(
            f"{field_prefix} unknown fields: {unknown}.",
            repair_hint="window_extents_norm only accepts left, right, up, and down.",
        )
    missing = [k for k in WINDOW_EXTENTS_KEYS if k not in raw]
    if missing:
        raise WindowExtentsError(
            f"{field_prefix} missing directions: {missing}.",
            repair_hint=(
                "Include all four directions: left, right, up, and down "
                "(zero is allowed on a side when the opposite axis span is positive)."
            ),
        )
    out: dict[str, float] = {}
    for key in WINDOW_EXTENTS_KEYS:
        value = raw[key]
        if not is_finite_number(value):
            raise WindowExtentsError(
                f"{field_prefix}.{key} must be a finite number (not bool, string, NaN, or infinity).",
                repair_hint=(
                    "Use plain JSON numbers for each extent "
                    '(e.g. "left": 0.08), never strings or booleans.'
                ),
            )
        extent = float(value)
        if extent < 0.0:
            raise WindowExtentsError(
                f"{field_prefix}.{key} must be >= 0.",
                repair_hint="Extents are non-negative fractions of the source image width/height.",
            )
        if extent > MAX_EXTENT_NORM:
            raise WindowExtentsError(
                f"{field_prefix}.{key} must be <= {MAX_EXTENT_NORM}.",
                repair_hint=f"Keep each extent between 0 and {MAX_EXTENT_NORM}.",
            )
        out[key] = round(extent, 6)

    if out["left"] + out["right"] <= 0.0:
        raise WindowExtentsError(
            f"{field_prefix} horizontal span (left+right) must be > 0.",
            repair_hint="Set left and/or right so the window has positive width.",
        )
    if out["up"] + out["down"] <= 0.0:
        raise WindowExtentsError(
            f"{field_prefix} vertical span (up+down) must be > 0.",
            repair_hint="Set up and/or down so the window has positive height.",
        )
    return out


def reject_conflicting_geometry_controls(
    point: dict[str, Any],
    *,
    field_prefix: str,
    global_params: dict[str, Any] | None = None,
) -> None:
    """Refuse when window_extents_norm coexists with centered/template/trim controls.

    Conflict is by exact key presence — null / empty values still refuse.
    """
    if not point_has_window_extents(point):
        return
    conflicts = conflicting_keys_present(point, _POINT_EXTENTS_CONFLICT_KEYS)
    if conflicts:
        raise WindowExtentsError(
            f"{field_prefix} cannot combine window_extents_norm with {conflicts}.",
            repair_hint=(
                "Use window_extents_norm alone for this point, or use size/shape "
                "(and optional width_norm/height_norm), not both. "
                "Omit scale_*/trim_* keys entirely when using extents."
            ),
        )
    if global_params is not None:
        global_conflicts = conflicting_keys_present(global_params, _GLOBAL_EXTENTS_CONFLICT_KEYS)
        if global_conflicts:
            raise WindowExtentsError(
                f"{field_prefix} cannot use window_extents_norm when global {global_conflicts} is set.",
                repair_hint=(
                    "Omit global scale_x/scale_y and trim_* keys "
                    "when any point uses window_extents_norm."
                ),
            )


def reject_global_controls_with_extents_points(
    params: dict[str, Any],
    points: list[Any],
) -> None:
    """Refuse request-level scale/trim when any point uses window_extents_norm."""
    if not any(isinstance(p, dict) and point_has_window_extents(p) for p in points):
        return
    global_conflicts = conflicting_keys_present(params, _GLOBAL_EXTENTS_CONFLICT_KEYS)
    if global_conflicts:
        raise WindowExtentsError(
            f"Global {global_conflicts} cannot be set when any point uses window_extents_norm.",
            repair_hint=(
                "Omit global scale_x/scale_y and trim_* keys "
                "when any point uses window_extents_norm."
            ),
        )


def resolve_window_extents_geometry(
    img: Any,
    *,
    point_norm: list[float],
    extents: dict[str, float],
) -> dict[str, Any]:
    """Resolve requested extents to clamped pixel/norm boxes without size-preserving shifts."""
    if not (isinstance(point_norm, (list, tuple)) and len(point_norm) == 2):
        raise WindowExtentsError("point_norm must be [x, y].")
    if not is_finite_number(point_norm[0]) or not is_finite_number(point_norm[1]):
        raise WindowExtentsError("point_norm values must be finite numbers.")
    x = float(point_norm[0])
    y = float(point_norm[1])
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise WindowExtentsError("point_norm values must be in [0.0, 1.0].")

    left_e = float(extents["left"])
    right_e = float(extents["right"])
    up_e = float(extents["up"])
    down_e = float(extents["down"])

    requested = [
        round(x - left_e, 6),
        round(y - up_e, 6),
        round(x + right_e, 6),
        round(y + down_e, 6),
    ]

    res_x1, res_y1, res_x2, res_y2 = requested
    clipped: list[str] = []
    if res_x1 < 0.0:
        res_x1 = 0.0
        clipped.append("left")
    if res_y1 < 0.0:
        res_y1 = 0.0
        clipped.append("up")
    if res_x2 > 1.0:
        res_x2 = 1.0
        clipped.append("right")
    if res_y2 > 1.0:
        res_y2 = 1.0
        clipped.append("down")

    img_w = int(img.width)
    img_h = int(img.height)
    left = int(round(res_x1 * img_w))
    top = int(round(res_y1 * img_h))
    right = int(round(res_x2 * img_w))
    bottom = int(round(res_y2 * img_h))

    left = max(0, min(left, img_w - 1))
    top = max(0, min(top, img_h - 1))
    right = max(left + 1, min(right, img_w))
    bottom = max(top + 1, min(bottom, img_h))

    box = (left, top, right, bottom)
    box_norm = [
        round(left / img_w, 6),
        round(top / img_h, 6),
        round(right / img_w, 6),
        round(bottom / img_h, 6),
    ]
    pin_px = [int(round(x * img_w)), int(round(y * img_h))]
    pin_px[0] = max(0, min(pin_px[0], img_w - 1))
    pin_px[1] = max(0, min(pin_px[1], img_h - 1))

    # Point must remain inside the resolved crop (inclusive edges).
    if not (box_norm[0] <= x <= box_norm[2] and box_norm[1] <= y <= box_norm[3]):
        raise WindowExtentsError(
            "Resolved window_extents crop does not contain point_norm.",
            repair_hint="Reduce extents that clamp away from the anchor, or move point_norm inland.",
        )

    return {
        "geometry_form": GEOMETRY_FORM_WINDOW_EXTENTS,
        "point_norm": [round(x, 6), round(y, 6)],
        "pin_px": pin_px,
        "box": box,
        "box_px": [box[0], box[1], box[2], box[3]],
        "box_norm": box_norm,
        "window_extents_norm": {
            "left": round(left_e, 6),
            "right": round(right_e, 6),
            "up": round(up_e, 6),
            "down": round(down_e, 6),
        },
        "requested_box_norm": requested,
        "source_edge_clipping": clipped,
        "resolved_width_height_norm": [
            round(box_norm[2] - box_norm[0], 6),
            round(box_norm[3] - box_norm[1], 6),
        ],
    }


def copy_window_extents_metadata(source: dict[str, Any]) -> dict[str, Any]:
    """Copy durable window-extents fields for records/descriptors."""
    out: dict[str, Any] = {}
    if source.get("geometry_form") == GEOMETRY_FORM_WINDOW_EXTENTS:
        out["geometry_form"] = GEOMETRY_FORM_WINDOW_EXTENTS
    extents = source.get("window_extents_norm")
    if isinstance(extents, dict):
        out["window_extents_norm"] = {
            k: float(extents[k]) for k in WINDOW_EXTENTS_KEYS if k in extents
        }
    requested = source.get("requested_box_norm")
    if isinstance(requested, (list, tuple)) and len(requested) == 4:
        out["requested_box_norm"] = [float(v) for v in requested]
    clipping = source.get("source_edge_clipping")
    if isinstance(clipping, list):
        out["source_edge_clipping"] = [
            str(edge) for edge in clipping if str(edge) in {"left", "right", "up", "down"}
        ]
    return out
