"""Pure in-memory rendering for transcript-edit generic derived images.

Sole implementation used by production generic transforms and reconstruction audits.
Performs no filesystem writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .coordinate_lattice import (
    DEFAULT_REFERENCE_COLS,
    DEFAULT_REFERENCE_ROWS,
    OVERLAY_ROLE_PLAIN_COORDINATE_REFERENCE,
    build_reference_cell_overlay_metadata,
    draw_reference_cell_coordinate_foundation,
)
from .evidence_locator_rendering import build_locator_render_plan, summarize_locator

RENDERER_ID = "transcript_edit.pillow.v1"

GENERIC_SUB_ACTIONS = frozenset(
    {
        "crop",
        "expand",
        "zoom",
        "annotate",
        "reference_overlay",
        "render_evidence_locators",
    }
)


@dataclass(frozen=True)
class RenderedDerivedImage:
    image: Any
    width_height: tuple[int, int]
    transform_metadata: dict[str, Any]


def pillow_version() -> str:
    try:
        import PIL  # type: ignore[import]

        return str(getattr(PIL, "__version__", "unknown"))
    except Exception:
        return "unknown"


def compute_image_identity(
    path_or_pil: Any = None,
    *,
    path: Path | None = None,
    image: Any = None,
) -> dict[str, Any]:
    """Compute byte and pixel identity for a path and/or in-memory PIL image.

    Accepts either positional ``path_or_pil`` or keyword ``path`` / ``image``.
    """
    import hashlib
    from PIL import Image  # type: ignore[import]

    if path_or_pil is not None:
        if isinstance(path_or_pil, (str, Path)):
            path = Path(path_or_pil)
        else:
            image = path_or_pil

    size_bytes: int | None = None
    content_sha256: str | None = None
    if path is not None:
        data = Path(path).read_bytes()
        size_bytes = len(data)
        content_sha256 = hashlib.sha256(data).hexdigest()
        if image is None:
            image = Image.open(path)
            image.load()
    if image is None:
        raise ValueError("compute_image_identity requires path or image")
    load = getattr(image, "load", None)
    if callable(load):
        load()
    mode = str(image.mode)
    wh = (int(image.width), int(image.height))
    pixel_payload = f"{mode}\n{wh[0]}x{wh[1]}\n".encode("utf-8") + image.tobytes()
    pixel_sha256 = hashlib.sha256(pixel_payload).hexdigest()
    return {
        "size_bytes": size_bytes,
        "content_sha256": content_sha256,
        "mode": mode,
        "width_height": [wh[0], wh[1]],
        "pixel_sha256": pixel_sha256,
    }


class TransformParamError(Exception):
    """Raised by the shared generic renderer for fixable param problems."""

    def __init__(self, message: str, *, repair_hint: str | None = None) -> None:
        super().__init__(message)
        self.repair_hint = repair_hint


def _coerce_pixel_integer(v: Any) -> int | None:
    """Return ``v`` as an integer pixel value, or ``None`` if it is not a clean integer.

    Accepts: ``int`` (excluding bool), ``float`` that ``is_integer()`` (so JSON's
    loose ``5`` vs ``5.0`` distinction does not break agents).

    Rejects: ``bool`` (subclass of ``int``), fractional floats (``20.9``), strings
    (even numeric-looking like ``"5"``), and any other type.  Used to keep pixel
    geometry honest: fractional pixel coordinates would silently truncate and
    erase agent intent.  For fractional/normalized intent, the agent should use
    ``box_norm`` + ``adjust_norm``.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return None


def _validate_box(box: Any, *, field: str = "params.box") -> str | None:
    """Return an error message string if *box* is not a valid 4-element pixel box."""
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return f"{field} must be a list of exactly 4 numbers [x1, y1, x2, y2]."
    vals: list[int] = []
    for v in box:
        coerced = _coerce_pixel_integer(v)
        if coerced is None:
            return (
                f"{field} values must be integer pixel coordinates (no fractional pixels, no bools, "
                f"no strings); got {v!r}.  Use {field.replace('.box', '.box_norm')} with normalized "
                "[0..1] values for fractional or sub-pixel-precision geometry."
            )
        vals.append(coerced)
    if vals[0] >= vals[2] or vals[1] >= vals[3]:
        return f"{field} requires x1 < x2 and y1 < y2; got {vals}."
    return None


def _validate_box_norm(box_norm: Any, *, field: str = "params.box_norm") -> str | None:
    """Return an error message string if *box_norm* is not a valid normalized 4-element list."""
    if not isinstance(box_norm, (list, tuple)) or len(box_norm) != 4:
        return f"{field} must be a list of exactly 4 numbers [x1, y1, x2, y2] in range 0..1."
    try:
        vals = [float(v) for v in box_norm]
    except (TypeError, ValueError):
        return f"{field} values must be numeric."
    if any(v < 0.0 or v > 1.0 for v in vals):
        return f"{field} values must be in [0.0, 1.0]; got {vals}."
    if vals[0] >= vals[2] or vals[1] >= vals[3]:
        return f"{field} requires x1 < x2 and y1 < y2; got {vals}."
    return None


_ADJUST_KEYS: frozenset[str] = frozenset({"expand_x", "expand_y", "shift_x", "shift_y"})

# Annotation types the renderer can actually draw.  An unknown type would
# otherwise resolve geometry, render nothing, and still appear in
# resolved_annotations — misleading the next turn about what was drawn.
_ANNOTATION_TYPES: frozenset[str] = frozenset({"highlight", "bbox", "label"})


def _validate_adjust(adjust: Any, *, field: str, require_integer: bool = False) -> str | None:
    """Validate an adjust_norm or adjust_px object shape (does not range-check).

    When ``require_integer`` is True (used for ``adjust_px``), fractional values
    are rejected: pixel units are naturally whole, and silently truncating a
    fractional value (e.g. ``shift_x: 0.9`` → ``0``) would erase agent intent.
    Integer-valued floats like ``5.0`` are accepted to handle JSON's loose
    int/float distinction.
    """
    if adjust is None:
        return None
    if not isinstance(adjust, dict):
        return f"{field} must be a JSON object with optional expand_x, expand_y, shift_x, shift_y."
    for k, v in adjust.items():
        if k not in _ADJUST_KEYS:
            return f"{field} has unknown key {k!r}; allowed: {sorted(_ADJUST_KEYS)}."
        # Booleans are a subclass of int in Python; reject them explicitly so
        # adjust values cannot accidentally smuggle non-numeric intent.
        if isinstance(v, bool):
            return f"{field}.{k} must be numeric, not bool."
        try:
            float(v)
        except (TypeError, ValueError):
            return f"{field}.{k} must be numeric."
        if require_integer and _coerce_pixel_integer(v) is None:
            return (
                f"{field}.{k} must be an integer pixel value (no fractional pixels); got {v!r}.  "
                f"Use {field.replace('adjust_px', 'adjust_norm')} with a box_norm for sub-pixel-precision "
                "normalized nudges."
            )
    return None


def _apply_adjust_norm(
    box_norm: list[float],
    adjust: dict[str, Any] | None,
) -> tuple[list[float], dict[str, float]]:
    """Apply normalized adjustments to a box_norm.  Returns (new_box_norm, applied_dict).

    Semantics (mirroring brief):
      - expand_x grows both left and right by the given amount (negative shrinks)
      - expand_y grows both top and bottom by the given amount (negative shrinks)
      - shift_x positive moves right, negative moves left
      - shift_y positive moves down, negative moves up
    Clamping to [0,1] happens after, in the resolver.
    """
    applied: dict[str, float] = {}
    if not isinstance(adjust, dict):
        return list(box_norm), applied
    expand_x = float(adjust.get("expand_x", 0.0) or 0.0)
    expand_y = float(adjust.get("expand_y", 0.0) or 0.0)
    shift_x = float(adjust.get("shift_x", 0.0) or 0.0)
    shift_y = float(adjust.get("shift_y", 0.0) or 0.0)
    x1, y1, x2, y2 = (float(v) for v in box_norm)
    x1 = x1 - expand_x + shift_x
    x2 = x2 + expand_x + shift_x
    y1 = y1 - expand_y + shift_y
    y2 = y2 + expand_y + shift_y
    if expand_x:
        applied["expand_x"] = expand_x
    if expand_y:
        applied["expand_y"] = expand_y
    if shift_x:
        applied["shift_x"] = shift_x
    if shift_y:
        applied["shift_y"] = shift_y
    return [x1, y1, x2, y2], applied


def _apply_adjust_px(
    box: list[int],
    adjust: dict[str, Any] | None,
) -> tuple[list[int], dict[str, int]]:
    """Apply pixel adjustments to a box.  Returns (new_box, applied_dict)."""
    applied: dict[str, int] = {}
    if not isinstance(adjust, dict):
        return list(box), applied
    expand_x = int(adjust.get("expand_x", 0) or 0)
    expand_y = int(adjust.get("expand_y", 0) or 0)
    shift_x = int(adjust.get("shift_x", 0) or 0)
    shift_y = int(adjust.get("shift_y", 0) or 0)
    x1, y1, x2, y2 = (int(v) for v in box)
    x1 = x1 - expand_x + shift_x
    x2 = x2 + expand_x + shift_x
    y1 = y1 - expand_y + shift_y
    y2 = y2 + expand_y + shift_y
    if expand_x:
        applied["expand_x"] = expand_x
    if expand_y:
        applied["expand_y"] = expand_y
    if shift_x:
        applied["shift_x"] = shift_x
    if shift_y:
        applied["shift_y"] = shift_y
    return [x1, y1, x2, y2], applied


def _resolve_box_geometry(
    *,
    box: Any = None,
    box_norm: Any = None,
    adjust_px: Any = None,
    adjust_norm: Any = None,
    image_width: int,
    image_height: int,
    field_prefix: str = "params",
) -> tuple[list[int], dict[str, Any]]:
    """Resolve final pixel box from inputs and return (box_px, resolved_geometry_dict).

    Accepts either pixel ``box`` or normalized ``box_norm`` (not both — that is an
    explicit retryable error).  Optionally applies ``adjust_px`` (pixel-form box)
    or ``adjust_norm`` (norm-form box).  Clamps to image bounds, then validates
    the final box has strictly positive width and height.  Returns both pixel and
    normalized forms plus the metadata an agent needs to refine the call.

    Raises ``TransformParamError`` (retryable) on conflicting inputs, missing
    inputs, or post-adjustment collapse.
    """
    if box is not None and box_norm is not None:
        raise TransformParamError(
            f"{field_prefix}: provide either box or box_norm, not both.",
            repair_hint=f"Choose one geometry form: remove {field_prefix}.box or {field_prefix}.box_norm.",
        )
    if box is None and box_norm is None:
        raise TransformParamError(
            f"{field_prefix} requires box or box_norm.",
            repair_hint=(
                f"Provide {field_prefix}.box = [x1, y1, x2, y2] (pixel) or "
                f"{field_prefix}.box_norm = [x1, y1, x2, y2] (normalized 0..1)."
            ),
        )

    original_input: dict[str, Any] = {}
    adjustments_applied: dict[str, Any] = {}

    if box_norm is not None:
        vals_n = [float(v) for v in box_norm]
        original_input["box_norm"] = list(vals_n)
        if adjust_norm is not None:
            vals_n, applied_norm = _apply_adjust_norm(vals_n, adjust_norm)
            if applied_norm:
                adjustments_applied["adjust_norm"] = applied_norm
        # Clamp to [0,1]
        vals_n = [max(0.0, min(1.0, v)) for v in vals_n]
        # Check positive area in norm space before converting
        if vals_n[0] >= vals_n[2] or vals_n[1] >= vals_n[3]:
            raise TransformParamError(
                f"{field_prefix}: adjusted box_norm collapsed to zero/negative area; got {vals_n}.",
                repair_hint=(
                    "Reduce shrink magnitudes (negative expand_*) or shift magnitudes so the final "
                    "box keeps x1<x2 and y1<y2 after clamping to [0,1]."
                ),
            )
        # ``round()`` (not ``int``) tolerates floating-point noise from adjust math
        # (e.g. 0.3 - 0.1 = 0.19999999999...) and preserves the agent's intended
        # box edges.  Truncation here would silently shift edges by 1 px under FP drift.
        px = [
            round(vals_n[0] * image_width),
            round(vals_n[1] * image_height),
            round(vals_n[2] * image_width),
            round(vals_n[3] * image_height),
        ]
    else:
        px = [int(v) for v in box]
        original_input["box"] = list(px)
        if adjust_px is not None:
            px, applied_px = _apply_adjust_px(px, adjust_px)
            if applied_px:
                adjustments_applied["adjust_px"] = applied_px
        # Clamp to image bounds
        px = [
            max(0, min(image_width, px[0])),
            max(0, min(image_height, px[1])),
            max(0, min(image_width, px[2])),
            max(0, min(image_height, px[3])),
        ]

    if px[0] >= px[2] or px[1] >= px[3]:
        raise TransformParamError(
            f"{field_prefix}: resolved pixel box collapsed to zero/negative area after clamping; got {px}.",
            repair_hint=(
                "Choose a region inside the image with strictly positive width and height after "
                "any adjustments.  Image bounds are [0,0,width,height]."
            ),
        )

    # Compute resolved normalized form from the final pixel box (canonical roundtrip).
    safe_w = image_width if image_width > 0 else 1
    safe_h = image_height if image_height > 0 else 1
    resolved_norm = [
        round(px[0] / safe_w, 6),
        round(px[1] / safe_h, 6),
        round(px[2] / safe_w, 6),
        round(px[3] / safe_h, 6),
    ]

    geometry: dict[str, Any] = {
        "box": list(px),
        "box_norm": resolved_norm,
        "source_width_height": [image_width, image_height],
        "input": original_input,
    }
    if adjustments_applied:
        geometry["adjustments_applied"] = adjustments_applied
    return list(px), geometry


def render_generic_derived_image(
    source: Path | Any,
    sub_action: str,
    params: dict[str, Any],
    *,
    source_ref_id: str,
) -> RenderedDerivedImage:
    """Apply a generic PIL transform in memory; never writes to disk."""
    from PIL import Image, ImageDraw  # type: ignore[import]

    if sub_action not in GENERIC_SUB_ACTIONS:
        raise ValueError(f"Unsupported transform sub_action for in-memory render: {sub_action!r}")

    if isinstance(source, Path):
        img = Image.open(source)
        img.load()
    else:
        img = source.copy() if hasattr(source, "copy") else source
    transform_metadata: dict[str, Any] = {}

    if sub_action == "crop":
        resolved_box, geo = _resolve_box_geometry(
            box=params.get("box"),
            box_norm=params.get("box_norm"),
            adjust_px=params.get("adjust_px"),
            adjust_norm=params.get("adjust_norm"),
            image_width=img.width,
            image_height=img.height,
            field_prefix="params",
        )
        img = img.crop(tuple(resolved_box))
        transform_metadata["resolved_geometry"] = geo

    elif sub_action == "expand":
        padding = params.get("padding", [0, 0, 0, 0])
        if isinstance(padding, int):
            padding = [padding] * 4
        if not isinstance(padding, (list, tuple)) or len(padding) != 4:
            raise ValueError("expand requires params.padding = [top, right, bottom, left] or single int")
        top, right, bottom, left = (int(v) for v in padding)
        fill = params.get("fill", "white")
        new_w = img.width + left + right
        new_h = img.height + top + bottom
        out = Image.new(img.mode, (new_w, new_h), fill)
        out.paste(img, (left, top))
        img = out

    elif sub_action == "zoom":
        # Three accepted shapes:
        #   1. box (+ optional adjust_px) + optional factor: crop to box, then scale by factor (default 1.0)
        #   2. box_norm (+ optional adjust_norm) + optional factor: crop to normalized box, then scale by factor
        #   3. factor only: scale the whole image (preserves prior factor-only behavior)
        box = params.get("box")
        box_norm = params.get("box_norm")
        factor_raw = params.get("factor")
        has_box_input = box is not None or box_norm is not None
        if has_box_input:
            resolved_box, geo = _resolve_box_geometry(
                box=box,
                box_norm=box_norm,
                adjust_px=params.get("adjust_px"),
                adjust_norm=params.get("adjust_norm"),
                image_width=img.width,
                image_height=img.height,
                field_prefix="params",
            )
            img = img.crop(tuple(resolved_box))
            # After cropping, optional factor scales the cropped region.
            zoom_factor = float(factor_raw) if factor_raw is not None else 1.0
            if zoom_factor != 1.0:
                new_w = max(1, int(img.width * zoom_factor))
                new_h = max(1, int(img.height * zoom_factor))
                img = img.resize((new_w, new_h), Image.LANCZOS)  # type: ignore[attr-defined]
                geo["factor_applied"] = zoom_factor
            transform_metadata["resolved_geometry"] = geo
        else:
            # Factor-only zoom — no box geometry to resolve.
            zoom_factor = float(factor_raw) if factor_raw is not None else 2.0
            new_w = max(1, int(img.width * zoom_factor))
            new_h = max(1, int(img.height * zoom_factor))
            img = img.resize((new_w, new_h), Image.LANCZOS)  # type: ignore[attr-defined]
            transform_metadata["factor_applied"] = zoom_factor

    elif sub_action == "reference_overlay":
        # Legacy compatibility path: reuse the shared reference-cell foundation.
        cols = max(2, int(params.get("cols", DEFAULT_REFERENCE_COLS)))
        rows = max(2, int(params.get("rows", DEFAULT_REFERENCE_ROWS)))
        line_color_raw = params.get("line_color", [140, 140, 140])
        label_color_raw = params.get("label_color", [180, 0, 0])
        if isinstance(line_color_raw, list) and len(line_color_raw) >= 3:
            line_color: tuple[int, int, int] = tuple(int(v) for v in line_color_raw[:3])  # type: ignore[assignment]
        else:
            line_color = (140, 140, 140)
        if isinstance(label_color_raw, list) and len(label_color_raw) >= 3:
            label_color: tuple[int, int, int] = tuple(int(v) for v in label_color_raw[:3])  # type: ignore[assignment]
        else:
            label_color = (180, 0, 0)

        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)
        draw_reference_cell_coordinate_foundation(
            draw,
            img.width,
            img.height,
            cols=cols,
            rows=rows,
            cell_line_color=line_color,
            cell_label_text_color=label_color,
        )
        transform_metadata["overlay"] = build_reference_cell_overlay_metadata(
            overlay_role=OVERLAY_ROLE_PLAIN_COORDINATE_REFERENCE,
            cols=cols,
            rows=rows,
        )

    elif sub_action == "annotate":
        annotations = params.get("annotations", [])
        if not isinstance(annotations, list):
            raise TransformParamError(
                "params.annotations must be a list of annotation objects.",
                repair_hint="Wrap annotation objects in a JSON array.",
            )
        img = img.convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        resolved_annotations: list[dict[str, Any]] = []
        for ann_idx, ann in enumerate(annotations):
            if not isinstance(ann, dict):
                continue
            ann_type = str(ann.get("type") or "").lower()
            has_box = ann.get("box") is not None
            has_box_norm = ann.get("box_norm") is not None
            if not has_box and not has_box_norm:
                # Skip annotations with no geometry — consistent with prior behavior.
                continue
            resolved_box, geo = _resolve_box_geometry(
                box=ann.get("box"),
                box_norm=ann.get("box_norm"),
                adjust_px=ann.get("adjust_px"),
                adjust_norm=ann.get("adjust_norm"),
                image_width=img.width,
                image_height=img.height,
                field_prefix=f"params.annotations[{ann_idx}]",
            )
            b = tuple(resolved_box)
            color = ann.get("color", (255, 255, 0))
            if isinstance(color, list):
                color = tuple(color)
            if ann_type == "highlight":
                alpha = int(ann.get("alpha", 100))
                fill_color = (*color[:3], alpha) if len(color) >= 3 else (255, 255, 0, alpha)  # type: ignore[misc]
                draw.rectangle(b, fill=fill_color)
            elif ann_type == "bbox":
                outline_color = (*color[:3], 255) if len(color) >= 3 else (255, 0, 0, 255)  # type: ignore[misc]
                width = int(ann.get("width", 2))
                draw.rectangle(b, outline=outline_color, width=width)
            elif ann_type == "label":
                text = str(ann.get("text", ""))
                if text:
                    draw.text((b[0], max(0, b[1] - 16)), text, fill=(255, 0, 0, 255))
            resolved_annotations.append({
                "index": ann_idx,
                "type": ann_type,
                "resolved_geometry": geo,
            })
        img = Image.alpha_composite(img, overlay).convert("RGB")
        if resolved_annotations:
            transform_metadata["resolved_annotations"] = resolved_annotations

    elif sub_action == "render_evidence_locators":
        plan = build_locator_render_plan(
            source_ref=source_ref_id,
            locators=list(params.get("locators") or []),
            image_width=img.width,
            image_height=img.height,
        )
        img = img.convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for ann in plan["annotations"]:
            b = tuple(int(v) for v in ann["box"])
            color = tuple(ann.get("color") or [255, 0, 0])
            ann_type = ann.get("type")
            if ann_type == "highlight":
                alpha = int(ann.get("alpha", 90))
                draw.rectangle(b, fill=(*color[:3], alpha))
            elif ann_type == "bbox":
                draw.rectangle(b, outline=(*color[:3], 255), width=int(ann.get("width", 3)))
            elif ann_type == "label" and ann.get("text"):
                draw.text((b[0], max(0, b[1] - 16)), str(ann["text"]), fill=(*color[:3], 255))
        img = Image.alpha_composite(img, overlay).convert("RGB")
        locator_summaries = [
            summarize_locator(locator, index=i)
            for i, locator in enumerate(params.get("locators") or [])
            if isinstance(locator, dict)
        ]
        transform_metadata = {
            "rendered_evidence_refs": [
                {
                    "source_ref": source_ref_id,
                    "rendered_ref": None,
                    "locator_count": len(params.get("locators") or []),
                    "rendered_locator_count": len(plan["rendered_locators"]),
                    "summary_only_locator_count": len(plan["summary_only_locators"]),
                    "unsupported_locator_count": len(plan["unsupported_locators"]),
                }
            ],
            "rendered_locators": plan["rendered_locators"],
            "summary_only_locators": plan["summary_only_locators"],
            "unsupported_locators": plan["unsupported_locators"],
            "locator_summaries": locator_summaries,
        }

    else:
        raise ValueError(f"Unsupported transform sub_action for in-memory render: {sub_action!r}")

    wh = (int(img.width), int(img.height))
    return RenderedDerivedImage(image=img, width_height=wh, transform_metadata=transform_metadata)


