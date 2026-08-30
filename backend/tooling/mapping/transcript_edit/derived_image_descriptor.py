"""Canonical derived-image descriptor boundary (scope-bound coordinates + load).

Never trusts ``absolute_path`` from descriptor JSON as a lookup coordinate.
Does not expose host paths in error messages.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .paths import (
    UnsafeArtifactPathSegmentError,
    require_safe_path_segment,
    transcript_edit_derived_images_dir,
)

_IMAGE_DERIVED_PREFIX = "image:derived:"

MechanicalDerivedImageStatus = Literal["absent", "safe_regular_file", "unsafe"]


class DerivedImageDescriptorError(Exception):
    """Stable internal failure for derived-image descriptor / coordinate resolution."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)


@dataclass(frozen=True)
class DerivedImageCoordinates:
    """Mechanically derived workspace coordinates for one ``image:derived:*`` ref."""

    dossier_id: str
    transcription_id: str
    workspace_id: str
    ref_id: str
    opaque: str
    derived_dir: Path
    descriptor_path: Path
    image_path: Path


@dataclass(frozen=True)
class LoadedDerivedImageDescriptor:
    coordinates: DerivedImageCoordinates
    descriptor: dict[str, Any]


def parse_derived_image_ref(ref_id: str) -> str:
    """Return the opaque stem from ``image:derived:<opaque>``, or raise."""
    rid = str(ref_id or "").strip()
    if not rid.startswith(_IMAGE_DERIVED_PREFIX):
        raise DerivedImageDescriptorError(
            "invalid_derived_ref",
            "Expected an image:derived reference.",
        )
    opaque = rid[len(_IMAGE_DERIVED_PREFIX) :]
    if not opaque:
        raise DerivedImageDescriptorError(
            "invalid_derived_ref",
            "Derived image reference is missing its identity stem.",
        )
    try:
        require_safe_path_segment(opaque, field="derived_opaque")
    except UnsafeArtifactPathSegmentError as exc:
        raise DerivedImageDescriptorError(
            "invalid_derived_ref",
            "Derived image reference identity is unsafe.",
        ) from exc
    return opaque


def resolve_derived_image_coordinates(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    ref_id: str,
) -> DerivedImageCoordinates:
    """Derive descriptor/PNG paths from workspace + ref; never from descriptor absolute_path."""
    try:
        did = require_safe_path_segment(str(dossier_id).strip(), field="dossier_id")
        tid = require_safe_path_segment(str(transcription_id).strip(), field="transcription_id")
        wid = require_safe_path_segment(str(workspace_id).strip(), field="workspace_id")
    except UnsafeArtifactPathSegmentError as exc:
        raise DerivedImageDescriptorError(
            "invalid_derived_ref",
            "Derived image scope path is invalid.",
        ) from exc

    opaque = parse_derived_image_ref(ref_id)
    canonical_ref = f"{_IMAGE_DERIVED_PREFIX}{opaque}"
    try:
        derived_dir = transcript_edit_derived_images_dir(did, tid, wid)
    except UnsafeArtifactPathSegmentError as exc:
        raise DerivedImageDescriptorError(
            "invalid_derived_ref",
            "Derived image scope path is invalid.",
        ) from exc

    return DerivedImageCoordinates(
        dossier_id=did,
        transcription_id=tid,
        workspace_id=wid,
        ref_id=canonical_ref,
        opaque=opaque,
        derived_dir=derived_dir,
        descriptor_path=derived_dir / f"{opaque}.json",
        image_path=derived_dir / f"{opaque}.png",
    )


def is_unsafe_under_derived_dir(path: Path, *, under: Path) -> bool:
    """True iff *path* is a symlink or does not resolve inside *under*."""
    if path.is_symlink() or os.path.islink(os.fspath(path)):
        return True
    try:
        path.resolve().relative_to(under.resolve())
    except (ValueError, OSError):
        return True
    return False


def classify_mechanical_derived_image(
    *,
    image_path: Path,
    derived_dir: Path,
) -> MechanicalDerivedImageStatus:
    """Classify the mechanical PNG coordinate for safe consumer I/O.

    Returns:
      - ``absent``: no path entry (recipe reconstruction may be considered elsewhere)
      - ``safe_regular_file``: non-symlink regular file contained under ``derived_dir``
      - ``unsafe``: symlink (including broken), escape, or non-regular entry

    Uses ``os.path.lexists`` / ``lstat`` so callers never treat a symlink as a readable PNG.
    """
    png = Path(image_path)
    root = Path(derived_dir)
    if not os.path.lexists(os.fspath(png)):
        return "absent"
    # Reject all symlinks before any follow-symlink ``is_file`` / ``resolve`` target walk.
    if png.is_symlink() or os.path.islink(os.fspath(png)):
        return "unsafe"
    try:
        png.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return "unsafe"
    try:
        mode = os.lstat(os.fspath(png)).st_mode
    except OSError:
        return "unsafe"
    if not stat.S_ISREG(mode):
        return "unsafe"
    return "safe_regular_file"


def classify_coordinates_image(coords: DerivedImageCoordinates) -> MechanicalDerivedImageStatus:
    """Classify ``coords.image_path`` against ``coords.derived_dir``."""
    return classify_mechanical_derived_image(
        image_path=coords.image_path,
        derived_dir=coords.derived_dir,
    )


def load_derived_image_descriptor(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    ref_id: str,
) -> LoadedDerivedImageDescriptor:
    """Load and validate a derived-image descriptor at its mechanical workspace path."""
    coords = resolve_derived_image_coordinates(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        ref_id=ref_id,
    )
    desc_path = coords.descriptor_path
    if not desc_path.exists():
        raise DerivedImageDescriptorError(
            "descriptor_missing",
            "Derived image descriptor was not found.",
        )
    if is_unsafe_under_derived_dir(desc_path, under=coords.derived_dir):
        raise DerivedImageDescriptorError(
            "descriptor_invalid",
            "Derived image descriptor path is unsafe.",
        )
    if not desc_path.is_file():
        raise DerivedImageDescriptorError(
            "descriptor_invalid",
            "Derived image descriptor is not a readable file.",
        )
    try:
        raw = desc_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception as exc:
        raise DerivedImageDescriptorError(
            "descriptor_invalid",
            "Derived image descriptor could not be parsed as JSON.",
        ) from exc
    if type(data) is not dict:
        raise DerivedImageDescriptorError(
            "descriptor_invalid",
            "Derived image descriptor must be a JSON object.",
        )

    stored_ref = data.get("ref_id")
    if type(stored_ref) is not str or stored_ref != coords.ref_id:
        raise DerivedImageDescriptorError(
            "descriptor_invalid",
            "Descriptor ref_id does not agree with the requested derived reference.",
        )
    if desc_path.stem != coords.opaque:
        raise DerivedImageDescriptorError(
            "descriptor_invalid",
            "Descriptor filename stem does not agree with the derived reference.",
        )
    return LoadedDerivedImageDescriptor(coordinates=coords, descriptor=data)


def load_derived_image_descriptor_dict(
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    ref_id: str,
) -> dict[str, Any] | None:
    """Compatibility loader: return descriptor object or ``None`` (no host paths)."""
    try:
        return load_derived_image_descriptor(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            ref_id=ref_id,
        ).descriptor
    except DerivedImageDescriptorError:
        return None
