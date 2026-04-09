"""Resolve source image refs from association metadata (no ranking)."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from .paths import UnsafeArtifactPathSegmentError, association_path

_MEDIA_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
}


def _infer_media_type(suffix: str) -> str:
    return _MEDIA_TYPES.get(suffix.lower(), "image/jpeg")


def read_image_as_b64(path: Path) -> str | None:
    """Return base64-encoded image bytes, or None on any read failure."""
    try:
        return base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception:
        return None

_IMAGE_REF_RE = re.compile(
    r"^image:assoc:(?P<tid>[^:]+):(?P<slot>original)$",
)


def _try_image_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image

        with Image.open(path) as im:
            return int(im.width), int(im.height)
    except Exception:
        return None


def hydrate_source_image_context(
    *,
    dossier_id: str,
    transcription_id: str,
    ref_id: str,
) -> dict[str, Any]:
    """Return structured context for one ``image:assoc:<transcription_id>:original`` ref."""
    dossier_id = str(dossier_id).strip()
    transcription_id = str(transcription_id).strip()
    rid = str(ref_id).strip()
    m = _IMAGE_REF_RE.match(rid)
    if not m:
        return {"status": "error", "code": "invalid_ref", "message": "Expected image:assoc:<transcription_id>:original."}
    tid = m.group("tid")
    if tid != transcription_id:
        return {
            "status": "error",
            "code": "transcription_mismatch",
            "message": "Ref transcription_id does not match request scope.",
        }

    try:
        path_a = association_path(dossier_id)
    except UnsafeArtifactPathSegmentError as exc:
        return {
            "status": "error",
            "code": "invalid_scope_path",
            "message": str(exc),
        }
    if not path_a.is_file():
        return {"status": "error", "code": "association_missing", "message": str(path_a)}
    try:
        root = json.loads(path_a.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "error", "code": "association_read_error", "message": str(exc)}
    if not isinstance(root, dict):
        return {"status": "error", "code": "association_invalid", "message": "Root not object."}

    row: dict[str, Any] | None = None
    for item in root.get("associations") or []:
        if isinstance(item, dict) and str(item.get("transcription_id") or "").strip() == transcription_id:
            row = item
            break
    if row is None:
        return {"status": "error", "code": "association_row_missing", "message": transcription_id}

    meta = row.get("metadata")
    if not isinstance(meta, dict):
        return {"status": "error", "code": "metadata_missing", "message": transcription_id}
    images = meta.get("images")
    if not isinstance(images, dict):
        return {"status": "error", "code": "images_missing", "message": transcription_id}

    key = "original_path"
    fs_path = images.get(key)
    if not fs_path or not isinstance(fs_path, str):
        return {"status": "error", "code": "path_missing", "message": key}

    p = Path(fs_path)
    exists = p.is_file()
    size_bytes: int | None = None
    image_b64: str | None = None
    media_type = _infer_media_type(p.suffix)
    if exists:
        try:
            size_bytes = p.stat().st_size
        except OSError:
            size_bytes = None
        image_b64 = read_image_as_b64(p)

    return {
        "status": "ok",
        "ref_id": rid,
        "role": "source_original",
        "absolute_path": str(p.resolve()) if exists else fs_path,
        "exists": exists,
        "size_bytes": size_bytes,
        "width_height": _try_image_dimensions(p) if exists else None,
        "basename": p.name,
        "image_b64": image_b64,
        "image_media_type": media_type,
    }
