"""Mechanical source-window edge metadata for crop and boxed-zoom transforms."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .root_projection import ProjectionContext, compose_box_norm_to_root

_EDGE_EPSILON = 1e-4
_ROUND = 6
_STRIP_SOURCE_WINDOW_KEYS = frozenset({
    "absolute_path",
    "b64",
    "base64",
    "bytes",
    "crop_img",
    "prompt",
    "raw_prompt",
})


def build_source_window(
    *,
    local_source_ref: str,
    local_box_norm: list[float],
    projection_ctx: ProjectionContext,
) -> dict[str, Any]:
    """Build source-window metadata for one crop/boxed-zoom window."""
    local_box = _round_box(local_box_norm)
    local_touches, local_room, local_expand = _edge_facts(local_box)
    local_position = _position_label(local_touches)

    window: dict[str, Any] = {
        "local_source_ref": str(local_source_ref or "").strip(),
        "local_box_norm": local_box,
        "touches_source_edge": local_touches,
        "room_to_source_edge_norm": local_room,
        "can_expand": local_expand,
        "position_label": local_position,
        "projection_available": bool(projection_ctx.projection_available),
    }

    root_ref = projection_ctx.root_source_ref
    if isinstance(root_ref, str) and root_ref.strip():
        window["root_source_ref"] = root_ref.strip()

    if projection_ctx.projection_available and projection_ctx.root_source_ref:
        root_box = compose_box_norm_to_root(local_box, projection_ctx.projection_chain)
        if root_box is not None:
            root_touches, root_room, root_expand = _edge_facts(root_box)
            window["root_box_norm"] = root_box
            window["touches_root_source_edge"] = root_touches
            window["room_to_root_source_edge_norm"] = root_room
            window["can_expand_root"] = root_expand
            window["root_position_label"] = _position_label(root_touches)
            window["edge_summary"] = _edge_summary(
                local_touches=local_touches,
                local_expand=local_expand,
                root_touches=root_touches,
                root_expand=root_expand,
            )
            return _strip_source_window(window)

    reason = projection_ctx.projection_unavailable_reason
    if reason:
        window["projection_unavailable_reason"] = str(reason)[:160]
    window["edge_summary"] = _edge_summary(
        local_touches=local_touches,
        local_expand=local_expand,
    )
    return _strip_source_window(window)


def compact_source_window_for_projection(source_window: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Bounded source-window fields for prompt/audit projection."""
    if not isinstance(source_window, Mapping):
        return None
    compact: dict[str, Any] = {}
    for key in (
        "root_box_norm",
        "local_box_norm",
        "touches_source_edge",
        "touches_root_source_edge",
        "room_to_source_edge_norm",
        "room_to_root_source_edge_norm",
        "can_expand",
        "can_expand_root",
        "position_label",
        "root_position_label",
        "edge_summary",
        "projection_available",
    ):
        value = source_window.get(key)
        if value not in (None, "", [], {}):
            compact[key] = value
    return compact or None


def render_source_window_timeline_line(source_window: Mapping[str, Any] | None) -> str | None:
    """Compact audit line for human timeline rendering."""
    if not isinstance(source_window, Mapping):
        return None
    position = str(source_window.get("position_label") or "unknown").strip()
    touches = source_window.get("touches_source_edge")
    if not isinstance(touches, Mapping):
        return f"source_window: {position}"

    touched = [name for name in ("left", "top", "right", "bottom") if touches.get(name) is True]
    room = source_window.get("room_to_source_edge_norm")
    can_expand = source_window.get("can_expand")

    if not touched and isinstance(room, Mapping):
        left = room.get("left")
        top = room.get("top")
        right = room.get("right")
        bottom = room.get("bottom")
        return (
            f"source_window: {position}; "
            f"room=[L{left},T{top},R{right},B{bottom}]"
        )

    parts = [f"source_window: {position}"]
    if touched:
        parts.append(f"touches={','.join(touched)}")
    if isinstance(room, Mapping) and touches.get("bottom") is True:
        parts.append(f"room_down={room.get('bottom')}")
    if isinstance(can_expand, Mapping) and touches.get("bottom") is True:
        parts.append(f"can_expand_down={str(can_expand.get('down')).lower()}")

    root_touches = source_window.get("touches_root_source_edge")
    if isinstance(root_touches, Mapping) and root_touches != touches:
        root_touched = [name for name in ("left", "top", "right", "bottom") if root_touches.get(name) is True]
        if root_touched:
            parts.append(f"root_touches={','.join(root_touched)}")
    return "; ".join(parts)


def _edge_facts(box_norm: list[float]) -> tuple[dict[str, bool], dict[str, float], dict[str, bool]]:
    x1, y1, x2, y2 = (float(v) for v in box_norm)
    touches = {
        "left": x1 <= _EDGE_EPSILON,
        "top": y1 <= _EDGE_EPSILON,
        "right": x2 >= 1.0 - _EDGE_EPSILON,
        "bottom": y2 >= 1.0 - _EDGE_EPSILON,
    }
    room = {
        "left": _round_coord(x1),
        "top": _round_coord(y1),
        "right": _round_coord(1.0 - x2),
        "bottom": _round_coord(1.0 - y2),
    }
    can_expand = {
        "left": room["left"] > _EDGE_EPSILON,
        "up": room["top"] > _EDGE_EPSILON,
        "right": room["right"] > _EDGE_EPSILON,
        "down": room["bottom"] > _EDGE_EPSILON,
    }
    return touches, room, can_expand


def _position_label(touches: Mapping[str, bool]) -> str:
    top = bool(touches.get("top"))
    bottom = bool(touches.get("bottom"))
    left = bool(touches.get("left"))
    right = bool(touches.get("right"))
    count = sum((top, bottom, left, right))
    if count == 0:
        return "middle"
    if count == 4:
        return "full_window"
    if bottom and left and right and not top:
        return "bottom_full_width"
    if top and left and right and not bottom:
        return "top_full_width"
    if bottom and not top and not left and not right:
        return "bottom_edge"
    if top and not bottom and not left and not right:
        return "top_edge"
    if left and not right and not top and not bottom:
        return "left_edge"
    if right and not left and not top and not bottom:
        return "right_edge"
    if bottom and right and not top and not left:
        return "bottom_right"
    if bottom and left and not top and not right:
        return "bottom_left"
    if top and right and not bottom and not left:
        return "top_right"
    if top and left and not bottom and not right:
        return "top_left"
    return "partial_edge"


def _edge_summary(
    *,
    local_touches: Mapping[str, bool],
    local_expand: Mapping[str, bool],
    root_touches: Mapping[str, bool] | None = None,
    root_expand: Mapping[str, bool] | None = None,
) -> str:
    parts: list[str] = []
    if local_touches.get("bottom") and not local_expand.get("down"):
        parts.append(
            "Touches bottom edge of available source image; "
            "cannot expand farther down from this source artifact."
        )
    elif local_touches.get("bottom"):
        parts.append("Touches bottom edge of available source image.")
    if local_touches.get("top") and not local_expand.get("up"):
        parts.append(
            "Touches top edge of available source image; "
            "cannot expand farther up from this source artifact."
        )
    if local_touches.get("left") and not local_expand.get("left"):
        parts.append(
            "Touches left edge of available source image; "
            "cannot expand farther left from this source artifact."
        )
    if local_touches.get("right") and not local_expand.get("right"):
        parts.append(
            "Touches right edge of available source image; "
            "cannot expand farther right from this source artifact."
        )
    if not parts and not any(local_touches.values()):
        parts.append("Window is interior to the available source image on all sides.")

    if isinstance(root_touches, Mapping) and isinstance(root_expand, Mapping):
        if root_touches != local_touches:
            if root_touches.get("bottom") and not root_expand.get("down"):
                parts.append(
                    "Root window touches bottom edge of original source image; "
                    "cannot expand farther down on the root source artifact."
                )
            elif not root_touches.get("bottom") and local_touches.get("bottom"):
                parts.append(
                    "Touches bottom of immediate source artifact only; "
                    "root source window still has room below."
                )
    return " ".join(parts)


def _round_box(box_norm: list[float]) -> list[float]:
    return [_round_coord(v) for v in box_norm]


def _round_coord(value: float) -> float:
    return round(float(value), _ROUND)


def _strip_source_window(payload: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _STRIP_SOURCE_WINDOW_KEYS:
            continue
        if isinstance(value, str) and any(part in key.lower() for part in ("path", "prompt", "b64")):
            continue
        out[key] = value
    return out
