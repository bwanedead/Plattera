"""Run-owned persistence for transcript-edit ``image:derived:*`` artifacts.

Canonical dossier/source images are never written beside. All new derived PNG
bytes and descriptors belong under the owning workspace ``derived_images/``.
"""

from __future__ import annotations

import errno
import json
import os
import re
import tempfile
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import transcript_edit_derived_images_dir
from .derived_image_recipe import (
    RecipeValidationError,
    assert_recipe_descriptor_coherence,
    assert_recipe_output_identity,
)
from .derived_image_rendering import compute_image_identity

REASON_DERIVED_PERSIST_FAILED = "derived_persist_failed"
REASON_RECIPE_REQUIRED = "derived_recipe_required"
REASON_RECIPE_INVALID = "derived_recipe_invalid"
REASON_RECIPE_FINGERPRINT_MISMATCH = "derived_recipe_fingerprint_mismatch"
REASON_RECIPE_DESCRIPTOR_MISMATCH = "derived_recipe_descriptor_mismatch"
REASON_RECIPE_OUTPUT_MISMATCH = "derived_recipe_output_mismatch"

_RECIPE_CODE_MAP = {
    "recipe_fingerprint_mismatch": REASON_RECIPE_FINGERPRINT_MISMATCH,
    "recipe_descriptor_mismatch": REASON_RECIPE_DESCRIPTOR_MISMATCH,
    "recipe_output_mismatch": REASON_RECIPE_OUTPUT_MISMATCH,
}

_CONTENT_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DerivedImagePersistError(Exception):
    """Stable persistence refusal for derived image + descriptor writes."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code or REASON_DERIVED_PERSIST_FAILED)
        self.message = str(message or "Derived image persistence failed.")


@dataclass(frozen=True)
class PersistedDerivedImage:
    absolute_path: Path
    basename: str
    size_bytes: int
    width_height: tuple[int, int]
    descriptor_path: Path


def _path_lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _best_effort_unlink(path: Path) -> None:
    try:
        if _path_lexists(path):
            path.unlink()
    except OSError:
        pass


def _is_exist_error(exc: OSError) -> bool:
    if isinstance(exc, FileExistsError):
        return True
    if exc.errno in {errno.EEXIST}:
        return True
    if getattr(exc, "winerror", None) == 183:
        return True
    return False


def _unlink_required(path: Path, *, failure_message: str) -> None:
    """Remove ``path`` or raise a stable persistence failure if it remains."""
    try:
        if _path_lexists(path):
            path.unlink()
        if _path_lexists(path):
            raise DerivedImagePersistError(REASON_DERIVED_PERSIST_FAILED, failure_message)
    except DerivedImagePersistError:
        raise
    except OSError as exc:
        raise DerivedImagePersistError(REASON_DERIVED_PERSIST_FAILED, failure_message) from exc


def _staged_image_identity(
    path: Path, *, expected_wh: tuple[int, int] | None
) -> tuple[tuple[int, int], dict[str, Any]]:
    """Single open: verify readable staged image and return (wh, identity)."""
    try:
        identity = compute_image_identity(path=path)
    except Exception as exc:
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Staged derived image could not be verified as a readable image.",
        ) from exc
    wh_raw = identity.get("width_height")
    if not isinstance(wh_raw, list) or len(wh_raw) != 2:
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Staged derived image could not be verified as a readable image.",
        )
    wh = (int(wh_raw[0]), int(wh_raw[1]))
    if expected_wh is not None and wh != (int(expected_wh[0]), int(expected_wh[1])):
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Staged derived image dimensions did not match the rendered result.",
        )
    return wh, identity


def _write_image_staging(staging: Path, image: Any) -> None:
    staging.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=staging.parent,
        prefix=".tmp_derived_img_",
        suffix=".png",
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            image.save(handle, format="PNG")
        os.replace(tmp_path, staging)
    except Exception:
        _best_effort_unlink(tmp_path)
        _best_effort_unlink(staging)
        raise


def _promote_no_clobber(
    staging: Path,
    final: Path,
    *,
    exist_message: str,
    promote_message: str,
    cleanup_message: str,
) -> None:
    """Create ``final`` from ``staging`` without replacement; require staging cleanup."""
    try:
        os.link(staging, final)
    except OSError as exc:
        if _is_exist_error(exc):
            raise DerivedImagePersistError(
                REASON_DERIVED_PERSIST_FAILED,
                exist_message,
            ) from exc
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            promote_message,
        ) from exc
    try:
        _unlink_required(staging, failure_message=cleanup_message)
    except DerivedImagePersistError:
        # Roll back only the entry created by this promotion.
        _best_effort_unlink(final)
        raise


def _serialize_descriptor(descriptor: Mapping[str, Any]) -> str:
    try:
        return json.dumps(dict(descriptor), ensure_ascii=False, indent=2, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Derived image descriptor is not JSON-serializable.",
        ) from exc


def _verify_staged_descriptor(staging: Path, *, expected_text: str) -> None:
    try:
        raw = staging.read_text(encoding="utf-8")
        loaded = json.loads(raw)
    except Exception as exc:
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Staged derived descriptor could not be verified as readable JSON.",
        ) from exc
    if not isinstance(loaded, dict):
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Staged derived descriptor did not parse to an object.",
        )
    try:
        expected = json.loads(expected_text)
    except Exception as exc:
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Staged derived descriptor could not be verified as readable JSON.",
        ) from exc
    if loaded != expected:
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Staged derived descriptor did not match the rendered descriptor.",
        )


def _write_descriptor_atomic(path: Path, descriptor: Mapping[str, Any]) -> None:
    """Stage → verify → create-only promote descriptor; never replace an existing file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = _serialize_descriptor(descriptor)
    token = uuid.uuid4().hex
    staging = path.parent / f".{path.stem}.{token}.staging.json"
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=".tmp_derived_desc_",
            suffix=".json",
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp_path, staging)
        except Exception as exc:
            _best_effort_unlink(tmp_path)
            _best_effort_unlink(staging)
            raise DerivedImagePersistError(
                REASON_DERIVED_PERSIST_FAILED,
                "Could not stage derived image descriptor.",
            ) from exc

        _verify_staged_descriptor(staging, expected_text=text)
        _promote_no_clobber(
            staging,
            path,
            exist_message="Derived descriptor path already exists; refusing to overwrite.",
            promote_message="Could not promote staged derived descriptor into the run workspace.",
            cleanup_message="Could not clean up staged derived descriptor after promotion.",
        )
    except DerivedImagePersistError:
        _best_effort_unlink(staging)
        raise
    except Exception as exc:
        _best_effort_unlink(staging)
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Could not persist derived image descriptor.",
        ) from exc


def _map_recipe_error(exc: RecipeValidationError) -> DerivedImagePersistError:
    code = _RECIPE_CODE_MAP.get(exc.code, REASON_RECIPE_INVALID)
    message = str(exc.message or "Derived image recipe validation failed.")
    # Never leak host paths into agent-facing persistence refusals.
    if "\\" in message or (":/" in message) or message.count("/") > 2:
        message = "Derived image recipe validation failed."
    return DerivedImagePersistError(code, message)


def _require_persistence_recipe(descriptor: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    recipe = descriptor.get("recipe")
    fingerprint = descriptor.get("recipe_fingerprint")
    if recipe is None or fingerprint is None:
        raise DerivedImagePersistError(
            REASON_RECIPE_REQUIRED,
            "Generic derived images require recipe and recipe_fingerprint.",
        )
    try:
        normalized = assert_recipe_descriptor_coherence(
            recipe=recipe,
            recipe_fingerprint_value=fingerprint,
            parent_ref_id=descriptor.get("parent_ref_id"),
            sub_action=descriptor.get("sub_action"),
            params=descriptor.get("params"),
        )
    except RecipeValidationError as exc:
        raise _map_recipe_error(exc) from exc
    return normalized, str(fingerprint)


def persist_derived_image(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    derived_uuid: str,
    image: Any,
    descriptor: Mapping[str, Any],
    expected_width_height: tuple[int, int] | None = None,
) -> PersistedDerivedImage:
    """Persist a rendered derived PNG + descriptor under the run-owned derived directory.

    Transaction: validate recipe → stage image → verify output identity →
    no-clobber promote → atomic descriptor.
    Never writes beside or modifies the transform source.
    """
    uid = str(derived_uuid or "").strip()
    if not uid or "/" in uid or "\\" in uid or ".." in uid:
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Derived image identity is invalid.",
        )

    recipe_norm, _fp = _require_persistence_recipe(descriptor)

    try:
        derived_dir = transcript_edit_derived_images_dir(dossier_id, transcription_id, workspace_id)
        derived_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Could not resolve the run-owned derived images directory.",
        ) from exc

    final_image = derived_dir / f"{uid}.png"
    descriptor_path = derived_dir / f"{uid}.json"
    if _path_lexists(final_image) or _path_lexists(descriptor_path):
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Derived image path already exists; refusing to overwrite.",
        )

    token = uuid.uuid4().hex
    staging = derived_dir / f".{uid}.{token}.staging.png"
    promoted = False
    try:
        try:
            _write_image_staging(staging, image)
        except DerivedImagePersistError:
            raise
        except Exception as exc:
            raise DerivedImagePersistError(
                REASON_DERIVED_PERSIST_FAILED,
                "Could not stage derived image bytes.",
            ) from exc

        wh, staged_identity = _staged_image_identity(staging, expected_wh=expected_width_height)
        try:
            assert_recipe_output_identity(
                recipe_norm,
                pixel_sha256=str(staged_identity.get("pixel_sha256") or ""),
                mode=str(staged_identity.get("mode") or ""),
                width_height=wh,
                already_validated=True,
            )
        except RecipeValidationError as exc:
            raise _map_recipe_error(exc) from exc

        _promote_no_clobber(
            staging,
            final_image,
            exist_message="Derived image path already exists; refusing to overwrite.",
            promote_message="Could not promote staged derived image into the run workspace.",
            cleanup_message="Could not clean up staged derived image after promotion.",
        )
        # Promotion + staging cleanup both succeeded; outer rollback may remove this image
        # only if descriptor persistence fails.
        promoted = True

        size_bytes = int(final_image.stat().st_size)
        content_sha256 = staged_identity.get("content_sha256")
        if type(content_sha256) is not str or not _CONTENT_SHA256_RE.fullmatch(content_sha256):
            raise DerivedImagePersistError(
                REASON_DERIVED_PERSIST_FAILED,
                "Staged derived image content identity could not be established.",
            )
        payload = dict(descriptor)
        # Persistence owns content_sha256; never trust a caller-supplied value.
        payload["content_sha256"] = content_sha256
        payload["recipe"] = recipe_norm
        payload["recipe_fingerprint"] = _fp
        payload["absolute_path"] = str(final_image.resolve())
        payload["basename"] = final_image.name
        payload["size_bytes"] = size_bytes
        payload["width_height"] = [wh[0], wh[1]]

        try:
            _write_descriptor_atomic(descriptor_path, payload)
        except DerivedImagePersistError:
            _best_effort_unlink(final_image)
            raise

        return PersistedDerivedImage(
            absolute_path=final_image,
            basename=final_image.name,
            size_bytes=size_bytes,
            width_height=wh,
            descriptor_path=descriptor_path,
        )
    except Exception as exc:
        _best_effort_unlink(staging)
        if promoted and not _path_lexists(descriptor_path):
            _best_effort_unlink(final_image)
        if isinstance(exc, DerivedImagePersistError):
            raise
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Derived image persistence failed.",
        ) from exc
