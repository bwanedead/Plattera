"""Transform-source resolution for assoc and derived images (STORAGE-BR-008).

Carries either a canonical on-disk source or an in-memory ``ResolvedDerivedImage``
without materializing reconstructed PNGs. Keeps recipe-building identity logic out
of ``artifact_transform.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .derived_image_resolution import (
    DerivedImageResolutionError,
    ResolvedDerivedImage,
    resolve_derived_image_for_read,
)
from .derived_image_rendering import compute_image_identity
from .image_loading import hydrate_source_image_context

_IMAGE_ASSOC_PREFIX = "image:assoc:"
_IMAGE_DERIVED_PREFIX = "image:derived:"
_CONTENT_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

REASON_SOURCE_CONTENT_IDENTITY_UNAVAILABLE = "source_content_identity_unavailable"

_ASSOC_SOURCE_ERROR_CODES = frozenset(
    {
        "invalid_ref",
        "transcription_mismatch",
        "invalid_scope_path",
        "association_missing",
        "association_read_error",
        "association_invalid",
        "association_row_missing",
        "metadata_missing",
        "images_missing",
        "path_missing",
    }
)

_ASSOC_SOURCE_ERROR_MESSAGES: dict[str, str] = {
    "invalid_ref": "Expected image:assoc:<transcription_id>:original.",
    "transcription_mismatch": "Ref transcription_id does not match request scope.",
    "invalid_scope_path": "Dossier scope path is invalid.",
    "association_missing": "Association metadata file is missing.",
    "association_read_error": "Association metadata could not be read.",
    "association_invalid": "Association metadata is invalid.",
    "association_row_missing": "Association row for this transcription is missing.",
    "metadata_missing": "Association metadata is incomplete.",
    "images_missing": "Association image metadata is missing.",
    "path_missing": "Original image path is missing from association metadata.",
    "source_error": "Canonical source image could not be resolved.",
}


@dataclass(frozen=True)
class TransformSourceImage:
    """In-memory transform input with durable identity coordinates when available."""

    ref_id: str
    image: Any
    content_sha256: str | None
    pixel_sha256: str
    mode: str
    width_height: list[int]
    representation_kind: str | None = None
    content_identity_posture: str | None = None
    source_identity_posture: str | None = None
    lineage_depth: int | None = None


def has_durable_content_identity(source: TransformSourceImage) -> bool:
    cs = source.content_sha256
    return type(cs) is str and bool(_CONTENT_SHA256_RE.fullmatch(cs))


def resolve_transform_source_image(
    *,
    ref_id: str,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str,
) -> tuple[TransformSourceImage | None, dict[str, Any] | None]:
    """Resolve a transform source to an in-memory image + identity coordinates.

    Never writes reconstructed bytes. Does not invent content hashes for
    reconstructed historical parents lacking a descriptor ``content_sha256``.
    """
    rid = str(ref_id or "").strip()
    if rid.startswith(_IMAGE_ASSOC_PREFIX):
        return _resolve_assoc_source(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            ref_id=rid,
        )
    if rid.startswith(_IMAGE_DERIVED_PREFIX):
        return _resolve_derived_source(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_key=workspace_key,
            ref_id=rid,
        )
    return None, {
        "code": "unsupported_ref_kind",
        "message": "transform_artifact only supports image:assoc:* and image:derived:* refs.",
    }


def _open_path_image(path: Path) -> Any:
    from PIL import Image  # type: ignore[import]

    img = Image.open(path)
    img.load()
    return img


def _assoc_source_refusal(raw: dict[str, Any]) -> dict[str, str]:
    """Map hydrate_source_image_context failures to path-free transform refusals."""
    code_raw = raw.get("code")
    if type(code_raw) is str and code_raw in _ASSOC_SOURCE_ERROR_CODES:
        code = code_raw
    else:
        code = "source_error"
    return {
        "code": code,
        "message": _ASSOC_SOURCE_ERROR_MESSAGES[code],
    }


def _resolve_assoc_source(
    *,
    dossier_id: str,
    transcription_id: str,
    ref_id: str,
) -> tuple[TransformSourceImage | None, dict[str, Any] | None]:
    raw = hydrate_source_image_context(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        ref_id=ref_id,
    )
    if raw.get("status") != "ok":
        return None, _assoc_source_refusal(raw)
    if not raw.get("exists"):
        return None, {
            "code": "source_image_not_found",
            "message": "Source image file does not exist.",
        }
    abs_str = raw.get("absolute_path")
    if type(abs_str) is not str or not abs_str.strip():
        return None, {
            "code": "source_image_not_found",
            "message": "Source image file does not exist.",
        }
    path = Path(abs_str)
    try:
        identity = compute_image_identity(path=path)
        image = _open_path_image(path)
    except Exception:
        return None, {
            "code": "source_image_not_found",
            "message": "Canonical source image could not be read.",
        }
    content = identity.get("content_sha256")
    pixel = identity.get("pixel_sha256")
    mode = identity.get("mode")
    wh = identity.get("width_height") or [0, 0]
    if type(content) is not str or type(pixel) is not str or type(mode) is not str:
        return None, {
            "code": "source_image_not_found",
            "message": "Canonical source identity could not be established.",
        }
    return (
        TransformSourceImage(
            ref_id=ref_id,
            image=image,
            content_sha256=content,
            pixel_sha256=pixel,
            mode=mode,
            width_height=[int(wh[0]), int(wh[1])],
            representation_kind="stored_bytes",
            content_identity_posture="stored_bytes_verified",
            source_identity_posture="content_and_pixel_verified",
            lineage_depth=0,
        ),
        None,
    )


def _from_resolved(resolved: ResolvedDerivedImage) -> TransformSourceImage:
    return TransformSourceImage(
        ref_id=resolved.ref_id,
        image=resolved.image,
        content_sha256=resolved.content_sha256,
        pixel_sha256=resolved.pixel_sha256,
        mode=resolved.mode,
        width_height=[int(resolved.width_height[0]), int(resolved.width_height[1])],
        representation_kind=resolved.representation_kind,
        content_identity_posture=resolved.content_identity_posture,
        source_identity_posture=resolved.source_identity_posture,
        lineage_depth=resolved.lineage_depth,
    )


def _resolve_derived_source(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str,
    ref_id: str,
) -> tuple[TransformSourceImage | None, dict[str, Any] | None]:
    try:
        resolved = resolve_derived_image_for_read(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_key,
            ref_id=ref_id,
        )
    except DerivedImageResolutionError as exc:
        return None, {"code": exc.code, "message": exc.message}
    return _from_resolved(resolved), None


__all__ = [
    "REASON_SOURCE_CONTENT_IDENTITY_UNAVAILABLE",
    "TransformSourceImage",
    "has_durable_content_identity",
    "resolve_transform_source_image",
]
