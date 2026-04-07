"""``transform_artifact`` capability for transcript-edit image refs.

Applies spatial and annotation transforms to source or derived image artifacts,
materializes a new derived ref, and persists the result for later hydration.
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
_SUPPORTED_SUB_ACTIONS = frozenset({"crop", "expand", "zoom", "annotate"})


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
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            raise ValueError("crop requires params.box = [x1, y1, x2, y2]")
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


def _error_result(code: str, message: str) -> dict[str, Any]:
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
