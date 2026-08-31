"""Reconstruction attempts for STORAGE-BR-004 (read-only, in-memory only)."""
from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path
from typing import Any

from .derived_image_recipe import (
    RecipeValidationError,
    build_derived_image_recipe,
    is_json_native,
    recipe_fingerprint,
)
from .derived_image_rendering import (
    GENERIC_SUB_ACTIONS,
    TransformParamError,
    compute_image_identity,
    pillow_version as _pillow_version,
    render_generic_derived_image,
)
from .derived_image_resolution import (
    DerivedImageResolutionError,
    reconstruct_generic_from_persisted_recipe,
)

_ASSOC_REF_RE = re.compile(r"^image:assoc:([^:]+):original$")

# Production point-crop family (artifact_transform / point_crops).
_POINT_CROP_SUB_ACTIONS = frozenset(
    {
        "point_crops",
        "point_crops_crop",
        "point_crops_scaffold",
        "point_crops_view",
        "point_crops_adjust",
    }
)
_POINT_CROP_CROP_ONLY = "point_crops_crop"


def resolve_assoc_source(parent_ref_id: str, dossier_id: str) -> Path | None:
    """Resolve ``image:assoc:<tx>:original`` to a readable file path, or None."""
    from .image_loading import hydrate_source_image_context

    m = _ASSOC_REF_RE.match(parent_ref_id)
    if not m:
        return None
    tx_id = m.group(1)
    try:
        ctx = hydrate_source_image_context(
            dossier_id=dossier_id,
            transcription_id=tx_id,
            ref_id=parent_ref_id,
        )
    except Exception:
        return None
    if ctx.get("status") != "ok" or not ctx.get("exists"):
        return None
    abs_str = ctx.get("absolute_path")
    if abs_str:
        fp = Path(abs_str)
        return fp if fp.is_file() else None
    return None


def resolve_source(
    parent_ref_id: str,
    dossier_id: str,
    records_by_ref: dict[str, dict[str, Any]],
) -> tuple[Path | None, str | None]:
    """
    Resolve immediate source bytes and detect parent-lineage cycles.

    The first hop supplies reconstruction pixels. Further ``parent_ref_id`` hops
    are walked only to detect cycles — grandparents are never used as a fallback
    when the immediate derived parent image is missing.

    Returns ``(path, None)`` on success, ``(None, \"cycle\")`` on a ref cycle,
    or ``(None, None)`` when the immediate source cannot be located.
    """
    visited: set[str] = set()
    current = parent_ref_id
    source_path: Path | None = None
    saw_immediate = False

    while current:
        if current in visited:
            return None, "cycle"
        visited.add(current)

        if current.startswith("image:assoc:"):
            path = resolve_assoc_source(current, dossier_id)
            if not saw_immediate:
                source_path = path
                saw_immediate = True
            break

        if current.startswith("image:derived:"):
            parent_rec = records_by_ref.get(current)
            if parent_rec is None:
                if not saw_immediate:
                    return None, None
                break
            pp = parent_rec.get("_abs_image_path")
            if not saw_immediate:
                saw_immediate = True
                if isinstance(pp, Path) and pp.is_file():
                    source_path = pp
                else:
                    source_path = None
            next_parent = parent_rec.get("parent_ref_id")
            if not isinstance(next_parent, str) or not next_parent.strip():
                break
            current = next_parent.strip()
            continue

        return None, None

    if source_path is None:
        return None, None
    return source_path, None


def _png_content_sha256(image: Any) -> str | None:
    """Encode *image* as PNG in memory and return content sha256, or None on failure."""
    try:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return hashlib.sha256(buf.getvalue()).hexdigest()
    except Exception:
        return None


def _box_px_from_descriptor(rec: dict[str, Any]) -> list[Any] | tuple[Any, ...] | None:
    """Production stores crop geometry on ``transform_metadata.box_px``, not ``params``."""
    meta = rec.get("_transform_metadata")
    if isinstance(meta, dict):
        box = meta.get("box_px")
        if isinstance(box, (list, tuple)) and len(box) == 4:
            return box
    return None


def _point_crop_is_simple_box_reconstructable(rec: dict[str, Any]) -> bool:
    """True only when stored metadata is a plain parent box crop (no zoom/scale materialization)."""
    meta = rec.get("_transform_metadata")
    if not isinstance(meta, dict):
        return False
    box = meta.get("box_px")
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return False
    zoom = meta.get("zoom_factor")
    if zoom is not None:
        try:
            if abs(float(zoom) - 1.0) > 1e-9:
                return False
        except (TypeError, ValueError):
            return False
    out_wh = meta.get("output_width_height")
    if isinstance(out_wh, (list, tuple)) and len(out_wh) == 2:
        try:
            x1, y1, x2, y2 = (int(v) for v in box)
            if int(out_wh[0]) != (x2 - x1) or int(out_wh[1]) != (y2 - y1):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _append_persisted_recipe_diagnostic(
    diagnostics: list[dict[str, Any]],
    *,
    ref_id: Any,
    code: str,
) -> None:
    diagnostics.append({"code": code, "detail": {"ref_id": ref_id}})


def _attempt_persisted_recipe_reconstruction(
    rec: dict[str, Any],
    diagnostics: list[dict[str, Any]],
    *,
    stored_pixel_sha256: str | None,
    stored_content_sha256: str | None,
    abs_image: Path | None,
) -> bool:
    """Use the BR-006 reconstruction seam for generic persisted recipes.

    Returns True when this path fully handled the record (caller should return).
    Malformed persisted recipes never fall back to inferred legacy recipes.
    """
    dossier_id = str(rec.get("_dossier_id") or "")
    tx_id = str(rec.get("_tx_id") or "")
    ws_id = str(rec.get("_ws_id") or "")
    ref_id = rec.get("ref_id")
    obj = rec.get("_obj") if isinstance(rec.get("_obj"), dict) else {}
    if type(ref_id) is not str or not dossier_id or not tx_id or not ws_id:
        rec["reconstruction_posture"] = "not_attempted_incomplete_recipe"
        rec["byte_equal_to_reconstruction"] = None
        return True

    try:
        recon = reconstruct_generic_from_persisted_recipe(
            dossier_id=dossier_id,
            transcription_id=tx_id,
            workspace_id=ws_id,
            ref_id=ref_id,
            descriptor=obj,
        )
    except (DerivedImageResolutionError, Exception) as exc:
        code = (
            f"persisted_recipe_{exc.code}"
            if isinstance(exc, DerivedImageResolutionError)
            else "persisted_recipe_invalid"
        )
        _append_persisted_recipe_diagnostic(diagnostics, ref_id=ref_id, code=code)
        rec["reconstruction_posture"] = "not_attempted_incomplete_recipe"
        rec["byte_equal_to_reconstruction"] = None
        return True

    rec["recipe_fingerprint"] = obj.get("recipe_fingerprint")
    if abs_image is None or not abs_image.is_file():
        # missing_image + exact recipe reconstruction
        rec["reconstruction_posture"] = "verified_pixel_exact"
        rec["byte_equal_to_reconstruction"] = None
        # Expose logical descriptor content coordinate; size_bytes stay unset (0 stored).
        if recon.content_sha256:
            rec["content_sha256"] = recon.content_sha256
        return True

    pixel_match: bool | None = (
        (recon.pixel_sha256 == stored_pixel_sha256) if stored_pixel_sha256 else None
    )
    recon_content = _png_content_sha256(recon.image)
    if recon_content is not None and stored_content_sha256:
        rec["byte_equal_to_reconstruction"] = recon_content == stored_content_sha256
    else:
        rec["byte_equal_to_reconstruction"] = None

    if pixel_match is True:
        rec["reconstruction_posture"] = "verified_pixel_exact"
    elif pixel_match is False:
        rec["reconstruction_posture"] = "verified_pixel_mismatch"
    else:
        rec["reconstruction_posture"] = "not_attempted_incomplete_recipe"
    return True


def attempt_reconstruction(
    rec: dict[str, Any],
    records_by_ref: dict[str, dict[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> None:
    """Mutate *rec* reconstruction fields. Never writes reconstructed bytes to disk."""
    sub_action = rec.get("sub_action")
    params = rec.get("_params")
    abs_image: Path | None = rec.get("_abs_image_path")
    parent_ref_id = rec.get("parent_ref_id")
    dossier_id: str = rec.get("_dossier_id") or ""
    stored_pixel_sha256 = rec.get("pixel_sha256")
    stored_content_sha256 = rec.get("content_sha256")
    obj = rec.get("_obj") if isinstance(rec.get("_obj"), dict) else None
    persisted_recipe = obj.get("recipe") if obj else None
    persisted_fp = obj.get("recipe_fingerprint") if obj else None
    has_persisted_recipe_fields = persisted_recipe is not None or persisted_fp is not None

    if has_persisted_recipe_fields:
        rec["recipe_source"] = "persisted"
    else:
        rec["recipe_source"] = "unavailable"

    image_present = bool(abs_image and abs_image.is_file())

    if not image_present:
        if (
            sub_action in GENERIC_SUB_ACTIONS
            and has_persisted_recipe_fields
            and isinstance(obj, dict)
        ):
            _attempt_persisted_recipe_reconstruction(
                rec,
                diagnostics,
                stored_pixel_sha256=stored_pixel_sha256,
                stored_content_sha256=stored_content_sha256,
                abs_image=None,
            )
            return
        rec["reconstruction_posture"] = "stored_image_unreadable"
        rec["byte_equal_to_reconstruction"] = None
        return

    if not sub_action:
        rec["reconstruction_posture"] = "not_attempted_incomplete_recipe"
        rec["byte_equal_to_reconstruction"] = None
        return

    if sub_action in GENERIC_SUB_ACTIONS:
        if not parent_ref_id or not isinstance(params, dict) or not is_json_native(params):
            rec["reconstruction_posture"] = "not_attempted_incomplete_recipe"
            rec["byte_equal_to_reconstruction"] = None
            return

        if has_persisted_recipe_fields and isinstance(obj, dict):
            # Shared seam owns recipe coherence + lineage; audit only compares to stored bytes.
            _attempt_persisted_recipe_reconstruction(
                rec,
                diagnostics,
                stored_pixel_sha256=stored_pixel_sha256,
                stored_content_sha256=stored_content_sha256,
                abs_image=abs_image,
            )
            return

        # Historical recipe-less inference (unchanged).
        source_path, err = resolve_source(parent_ref_id, dossier_id, records_by_ref)
        if err == "cycle":
            diagnostics.append(
                {
                    "code": "parent_cycle_detected",
                    "detail": {"ref_id": rec.get("ref_id"), "parent_ref_id": parent_ref_id},
                }
            )
            rec["reconstruction_posture"] = "not_attempted_incomplete_recipe"
            rec["byte_equal_to_reconstruction"] = None
            return
        if source_path is None:
            rec["reconstruction_posture"] = "not_attempted_missing_source"
            rec["byte_equal_to_reconstruction"] = None
            return

        try:
            src_id = compute_image_identity(path=source_path)
        except Exception:
            rec["reconstruction_posture"] = "not_attempted_missing_source"
            rec["byte_equal_to_reconstruction"] = None
            return

        try:
            rendered = render_generic_derived_image(
                source_path, sub_action, params, source_ref_id=parent_ref_id
            )
        except TransformParamError:
            rec["reconstruction_posture"] = "not_attempted_incomplete_recipe"
            rec["byte_equal_to_reconstruction"] = None
            return
        except Exception:
            rec["reconstruction_posture"] = "render_failed"
            rec["byte_equal_to_reconstruction"] = None
            return

        try:
            ren_id = compute_image_identity(image=rendered.image)
        except Exception:
            rec["reconstruction_posture"] = "render_failed"
            rec["byte_equal_to_reconstruction"] = None
            return

        pixel_match: bool | None = (
            (ren_id.get("pixel_sha256") == stored_pixel_sha256) if stored_pixel_sha256 else None
        )

        recon_content = _png_content_sha256(rendered.image)
        if recon_content is not None and stored_content_sha256:
            rec["byte_equal_to_reconstruction"] = recon_content == stored_content_sha256
        else:
            rec["byte_equal_to_reconstruction"] = None

        fp: str | None = None
        try:
            if all(
                src_id.get(k)
                for k in ("content_sha256", "pixel_sha256", "mode", "width_height")
            ) and all(ren_id.get(k) for k in ("pixel_sha256", "mode", "width_height")):
                recipe = build_derived_image_recipe(
                    source_ref_id=parent_ref_id,
                    source_content_sha256=src_id["content_sha256"],
                    source_pixel_sha256=src_id["pixel_sha256"],
                    source_mode=src_id["mode"],
                    source_width_height=src_id["width_height"],
                    sub_action=sub_action,
                    params=params,
                    pillow_version=_pillow_version(),
                    expected_pixel_sha256=ren_id["pixel_sha256"],
                    expected_mode=ren_id["mode"],
                    expected_width_height=ren_id["width_height"],
                )
                fp = recipe_fingerprint(recipe)
                rec["recipe_source"] = "inferred"
        except (RecipeValidationError, Exception):
            fp = None
            rec["recipe_source"] = "unavailable"
        rec["recipe_fingerprint"] = fp

        if pixel_match is True:
            rec["reconstruction_posture"] = "verified_pixel_exact"
        elif pixel_match is False:
            rec["reconstruction_posture"] = "verified_pixel_mismatch"
        else:
            rec["reconstruction_posture"] = "not_attempted_incomplete_recipe"
        return

    if sub_action == _POINT_CROP_CROP_ONLY:
        if not parent_ref_id or not _point_crop_is_simple_box_reconstructable(rec):
            # Zoomed / scaled crop materializations are not approximated.
            rec["reconstruction_posture"] = "not_attempted_unsupported_sub_action"
            rec["byte_equal_to_reconstruction"] = None
            return
        box_px = _box_px_from_descriptor(rec)
        if box_px is None:
            rec["reconstruction_posture"] = "not_attempted_incomplete_recipe"
            rec["byte_equal_to_reconstruction"] = None
            return

        source_path, err = resolve_source(parent_ref_id, dossier_id, records_by_ref)
        if err == "cycle":
            diagnostics.append(
                {
                    "code": "parent_cycle_detected",
                    "detail": {"ref_id": rec.get("ref_id"), "parent_ref_id": parent_ref_id},
                }
            )
            rec["reconstruction_posture"] = "not_attempted_incomplete_recipe"
            rec["byte_equal_to_reconstruction"] = None
            return
        if source_path is None:
            rec["reconstruction_posture"] = "not_attempted_missing_source"
            rec["byte_equal_to_reconstruction"] = None
            return

        try:
            from PIL import Image  # type: ignore[import]

            src_img = Image.open(source_path)
            src_img.load()
            x1, y1, x2, y2 = (int(v) for v in box_px)
            cropped = src_img.crop((x1, y1, x2, y2))
            ren_id = compute_image_identity(image=cropped)
        except Exception:
            rec["reconstruction_posture"] = "render_failed"
            rec["byte_equal_to_reconstruction"] = None
            return

        pixel_match = (
            (ren_id.get("pixel_sha256") == stored_pixel_sha256) if stored_pixel_sha256 else None
        )
        recon_content = _png_content_sha256(cropped)
        if recon_content is not None and stored_content_sha256:
            rec["byte_equal_to_reconstruction"] = recon_content == stored_content_sha256
        else:
            rec["byte_equal_to_reconstruction"] = None

        if pixel_match is True:
            rec["reconstruction_posture"] = "verified_pixel_exact"
        elif pixel_match is False:
            rec["reconstruction_posture"] = "verified_pixel_mismatch"
        else:
            rec["reconstruction_posture"] = "not_attempted_incomplete_recipe"
        return

    if sub_action in _POINT_CROP_SUB_ACTIONS:
        rec["reconstruction_posture"] = "not_attempted_unsupported_sub_action"
        rec["byte_equal_to_reconstruction"] = None
        return

    rec["reconstruction_posture"] = "not_attempted_renderer_unknown"
    rec["byte_equal_to_reconstruction"] = None
