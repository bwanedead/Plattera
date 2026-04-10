"""``transform_artifact`` capability for transcript-edit image refs.

Applies spatial and annotation transforms to source or derived image artifacts,
materializes a new derived ref, and persists the result for later hydration.

Crop geometry accepted forms:
  params.box      = [x1, y1, x2, y2]  (absolute pixel coordinates)
  params.box_norm = [x1, y1, x2, y2]  (normalized 0..1 relative to source dimensions)

Retryable param failures carry ``retryable=True, blocked_by_invariant=False`` and a
``repair_hint`` so the agent can self-correct on the next turn without terminating the run.
"""

from __future__ import annotations

import json
import uuid as _uuid_mod
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .image_loading import hydrate_source_image_context
from .paths import (
    UnsafeArtifactPathSegmentError,
    transcript_edit_derived_images_dir,
)
from .artifact_hydration import _load_derived_image_descriptor

_IMAGE_ASSOC_PREFIX = "image:assoc:"
_IMAGE_DERIVED_PREFIX = "image:derived:"
_SUPPORTED_SUB_ACTIONS = frozenset({"crop", "expand", "zoom", "annotate", "reference_overlay"})


def make_transform_artifact_handler(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str | None,
) -> Callable[[Any], Any]:
    """Return a handler for ``transform_artifact`` closed over the run scope."""

    def handler(request: Any) -> Any:
        if not workspace_key:
            return _error_result("workspace_required", "workspace_id or run_id is required to create derived artifacts.")

        inputs: dict[str, Any] = dict(request.inputs) if hasattr(request, "inputs") else dict(request) if isinstance(request, dict) else {}
        ref_id = str(inputs.get("ref_id") or "").strip()
        if not ref_id:
            return _error_result("ref_id_required", "ref_id is required.")

        sub_action = str(inputs.get("sub_action") or "").strip().lower()
        if sub_action not in _SUPPORTED_SUB_ACTIONS:
            return _error_result(
                "unsupported_sub_action",
                f"sub_action must be one of: {', '.join(sorted(_SUPPORTED_SUB_ACTIONS))}.",
            )

        params = inputs.get("params") or {}
        if not isinstance(params, dict):
            return _error_result("params_invalid", "params must be a JSON object.")

        # Pre-validate sub-action params before touching disk; fixable shape errors are retryable.
        param_error = _validate_params(sub_action, params)
        if param_error is not None:
            return param_error

        # Resolve source image path
        source_path, resolve_error = _resolve_source_path(
            ref_id=ref_id,
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_key=workspace_key,
        )
        if resolve_error:
            return _error_result(resolve_error["code"], resolve_error["message"])
        assert source_path is not None

        # Apply transform
        try:
            derived_path, width_height = _apply_transform(source_path, sub_action, params)
        except _TransformParamError as exc:
            # Param errors discovered at transform time (e.g. after image open) are retryable.
            return _param_error("invalid_transform_params", str(exc), repair_hint=exc.repair_hint)
        except Exception as exc:
            return _error_result("transform_failed", f"Transform failed: {exc}")

        # Persist derived descriptor
        derived_uuid = _uuid_mod.uuid4().hex
        derived_ref_id = f"{_IMAGE_DERIVED_PREFIX}{derived_uuid}"
        descriptor: dict[str, Any] = {
            "ref_id": derived_ref_id,
            "parent_ref_id": ref_id,
            "sub_action": sub_action,
            "params": params,
            "absolute_path": str(derived_path.resolve()),
            "basename": derived_path.name,
            "size_bytes": derived_path.stat().st_size if derived_path.exists() else None,
            "width_height": width_height,
        }
        try:
            derived_dir = transcript_edit_derived_images_dir(dossier_id, transcription_id, workspace_key)
            derived_dir.mkdir(parents=True, exist_ok=True)
            desc_path = derived_dir / f"{derived_uuid}.json"
            desc_path.write_text(json.dumps(descriptor, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            return _error_result("derived_persist_failed", f"Could not save derived descriptor: {exc}")

        return {
            "executed": True,
            "artifact_refs": [derived_ref_id],
            "outputs": {
                "derived_ref_id": derived_ref_id,
                "parent_ref_id": ref_id,
                "sub_action": sub_action,
                "basename": derived_path.name,
                "width_height": width_height,
            },
        }

    return handler


class _TransformParamError(Exception):
    """Raised inside ``_apply_transform`` for fixable param problems."""

    def __init__(self, message: str, *, repair_hint: str | None = None) -> None:
        super().__init__(message)
        self.repair_hint = repair_hint


def _validate_box(box: Any, *, field: str = "params.box") -> str | None:
    """Return an error message string if *box* is not a valid 4-element list, else None."""
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return f"{field} must be a list of exactly 4 numbers [x1, y1, x2, y2]."
    try:
        vals = [int(v) for v in box]
    except (TypeError, ValueError):
        return f"{field} values must be numeric integers."
    if vals[0] >= vals[2] or vals[1] >= vals[3]:
        return f"{field} requires x1 < x2 and y1 < y2; got {vals}."
    return None


def _validate_box_norm(box_norm: Any) -> str | None:
    """Return an error message string if *box_norm* is not a valid normalized 4-element list."""
    if not isinstance(box_norm, (list, tuple)) or len(box_norm) != 4:
        return "params.box_norm must be a list of exactly 4 numbers [x1, y1, x2, y2] in range 0..1."
    try:
        vals = [float(v) for v in box_norm]
    except (TypeError, ValueError):
        return "params.box_norm values must be numeric."
    if any(v < 0.0 or v > 1.0 for v in vals):
        return f"params.box_norm values must be in [0.0, 1.0]; got {vals}."
    if vals[0] >= vals[2] or vals[1] >= vals[3]:
        return f"params.box_norm requires x1 < x2 and y1 < y2; got {vals}."
    return None


def _validate_params(sub_action: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Return a retryable param-error result dict if params are fixably wrong, else None."""
    if sub_action == "crop":
        box = params.get("box")
        box_norm = params.get("box_norm")
        if box is None and box_norm is None:
            return _param_error(
                "invalid_transform_params",
                "crop requires either params.box = [x1, y1, x2, y2] (pixel coordinates) "
                "or params.box_norm = [x1, y1, x2, y2] (normalized 0..1 relative to source dimensions).",
                repair_hint=(
                    "Provide params.box with absolute pixel coordinates, e.g. {\"box\": [100, 200, 400, 600]}, "
                    "or params.box_norm with normalized coordinates where 0.0 is the start and 1.0 is the end of that axis, "
                    "e.g. {\"box_norm\": [0.0, 0.5, 1.0, 1.0]} crops the bottom half."
                ),
            )
        if box is not None:
            err = _validate_box(box, field="params.box")
            if err:
                return _param_error(
                    "invalid_transform_params",
                    err,
                    repair_hint="Use params.box = [x1, y1, x2, y2] with integer pixel coordinates.",
                )
        if box_norm is not None:
            err = _validate_box_norm(box_norm)
            if err:
                return _param_error(
                    "invalid_transform_params",
                    err,
                    repair_hint=(
                        "Use params.box_norm = [x1, y1, x2, y2] where all values are between 0.0 and 1.0 "
                        "and x1 < x2, y1 < y2. Example: [0.0, 0.5, 1.0, 1.0] crops the bottom half."
                    ),
                )
    return None


def _resolve_source_path(
    *,
    ref_id: str,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str,
) -> tuple[Path | None, dict[str, Any] | None]:
    if ref_id.startswith(_IMAGE_ASSOC_PREFIX):
        raw = hydrate_source_image_context(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            ref_id=ref_id,
        )
        if raw.get("status") != "ok":
            return None, {"code": raw.get("code", "source_error"), "message": raw.get("message", "")}
        if not raw.get("exists"):
            return None, {"code": "source_image_not_found", "message": f"Source image file does not exist: {raw.get('absolute_path')}"}
        return Path(raw["absolute_path"]), None

    if ref_id.startswith(_IMAGE_DERIVED_PREFIX):
        desc = _load_derived_image_descriptor(dossier_id, transcription_id, workspace_key, ref_id)
        if desc is None:
            return None, {"code": "derived_ref_not_found", "message": "Derived image ref not found."}
        p = Path(str(desc.get("absolute_path") or ""))
        if not p.is_file():
            return None, {"code": "derived_image_missing", "message": str(p)}
        return p, None

    return None, {"code": "unsupported_ref_kind", "message": "transform_artifact only supports image:assoc:* and image:derived:* refs."}


def _apply_transform(
    source: Path,
    sub_action: str,
    params: dict[str, Any],
) -> tuple[Path, tuple[int, int] | None]:
    """Apply a PIL transform and save result to a temp path alongside the source; return (path, wh)."""
    from PIL import Image, ImageDraw, ImageFont  # type: ignore[import]

    img = Image.open(source)

    if sub_action == "crop":
        box = params.get("box")
        box_norm = params.get("box_norm")
        if box is None and box_norm is not None:
            # Convert normalized [0..1] coordinates to pixel coordinates using source dimensions.
            vals = [float(v) for v in box_norm]
            box = [
                int(vals[0] * img.width),
                int(vals[1] * img.height),
                int(vals[2] * img.width),
                int(vals[3] * img.height),
            ]
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            raise _TransformParamError(
                "crop requires params.box = [x1, y1, x2, y2] or params.box_norm = [x1, y1, x2, y2].",
                repair_hint="Provide params.box (pixel coords) or params.box_norm (normalized 0..1 coords).",
            )
        img = img.crop(tuple(int(v) for v in box))

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
        box = params.get("box")
        if box and isinstance(box, (list, tuple)) and len(box) == 4:
            img = img.crop(tuple(int(v) for v in box))
        else:
            factor = float(params.get("factor", 2.0))
            new_w = max(1, int(img.width * factor))
            new_h = max(1, int(img.height * factor))
            img = img.resize((new_w, new_h), Image.LANCZOS)  # type: ignore[attr-defined]

    elif sub_action == "reference_overlay":
        # Draw a deterministic grid with labeled coordinates so the model can select
        # an explicit box or box_norm region for a later crop.
        # params.cols (int, default 4): number of vertical divisions.
        # params.rows (int, default 4): number of horizontal divisions.
        # params.line_color (list [R,G,B], default [200,200,200]): grid line color.
        # params.label_color (list [R,G,B], default [255,0,0]): label text color.
        # Returns the overlay with grid lines and cell labels like "(1,1)".
        cols = max(2, int(params.get("cols", 4)))
        rows = max(2, int(params.get("rows", 4)))
        line_color_raw = params.get("line_color", [200, 200, 200])
        label_color_raw = params.get("label_color", [255, 0, 0])
        if isinstance(line_color_raw, list) and len(line_color_raw) >= 3:
            line_color: tuple[int, ...] = tuple(int(v) for v in line_color_raw[:3])
        else:
            line_color = (200, 200, 200)
        if isinstance(label_color_raw, list) and len(label_color_raw) >= 3:
            label_color: tuple[int, ...] = tuple(int(v) for v in label_color_raw[:3])
        else:
            label_color = (255, 0, 0)

        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)
        w, h = img.width, img.height
        cell_w = w / cols
        cell_h = h / rows

        # Draw vertical grid lines
        for c in range(1, cols):
            x = int(c * cell_w)
            draw.line([(x, 0), (x, h)], fill=line_color, width=1)

        # Draw horizontal grid lines
        for r in range(1, rows):
            y = int(r * cell_h)
            draw.line([(0, y), (w, y)], fill=line_color, width=1)

        # Label each cell with (col, row) and the normalized center coordinates.
        # Columns are 1-indexed left-to-right; rows 1-indexed top-to-bottom.
        for r in range(rows):
            for c in range(cols):
                cx = int((c + 0.5) * cell_w)
                cy = int((r + 0.5) * cell_h)
                # Normalized coordinates of the cell bounds
                x1_n = round(c / cols, 2)
                y1_n = round(r / rows, 2)
                x2_n = round((c + 1) / cols, 2)
                y2_n = round((r + 1) / rows, 2)
                label = f"({c + 1},{r + 1})\n[{x1_n},{y1_n},{x2_n},{y2_n}]"
                # Split label onto two lines for readability
                parts = label.split("\n")
                for i, part in enumerate(parts):
                    draw.text((cx - 2, cy - 8 + i * 12), part, fill=label_color)

    elif sub_action == "annotate":
        annotations = params.get("annotations", [])
        if not isinstance(annotations, list):
            raise ValueError("annotate requires params.annotations = list of annotation objects")
        img = img.convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for ann in annotations:
            if not isinstance(ann, dict):
                continue
            ann_type = str(ann.get("type") or "").lower()
            box = ann.get("box")
            if not box or not isinstance(box, (list, tuple)) or len(box) != 4:
                continue
            b = tuple(int(v) for v in box)
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
        img = Image.alpha_composite(img, overlay).convert("RGB")

    out_suffix = ".png"
    out_path = source.parent / (source.stem + f"_derived_{_uuid_mod.uuid4().hex[:8]}{out_suffix}")
    img.save(out_path)
    wh: tuple[int, int] | None = (img.width, img.height)
    return out_path, wh


def _param_error(code: str, message: str, repair_hint: str | None = None) -> dict[str, Any]:
    """Retryable failure: the request shape is fixable; the run should continue."""
    error_payload: dict[str, Any] = {"code": code, "message": message}
    if repair_hint:
        error_payload["repair_hint"] = repair_hint
    return {
        "executed": False,
        "refusal": {
            "reason_code": code,
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {"error": error_payload},
    }


def _error_result(code: str, message: str) -> dict[str, Any]:
    """Non-retryable failure: a real invariant or missing-resource condition."""
    return {
        "executed": False,
        "refusal": {
            "reason_code": code,
            "retryable": False,
            "blocked_by_invariant": True,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {"error": {"code": code, "message": message}},
    }
