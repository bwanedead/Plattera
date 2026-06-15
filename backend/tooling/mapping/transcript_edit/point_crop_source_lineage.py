"""Resolve clean source refs for point-crop generation (never crop control-overlay pixels)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .artifact_hydration import _load_derived_image_descriptor
from .coordinate_lattice import (
    OVERLAY_ROLE_POINT_CROP_MASTER,
    OVERLAY_ROLE_POINT_CROP_PLACEMENT_SCAFFOLD,
    OVERLAY_ROLE_POINT_CROP_VIEW,
)

_IMAGE_ASSOC_PREFIX = "image:assoc:"
_IMAGE_DERIVED_PREFIX = "image:derived:"

CONTROL_OVERLAY_ROLES = frozenset({
    OVERLAY_ROLE_POINT_CROP_PLACEMENT_SCAFFOLD,
    OVERLAY_ROLE_POINT_CROP_MASTER,
    OVERLAY_ROLE_POINT_CROP_VIEW,
})

_LEGACY_REPAIR_WARNING = (
    "legacy_polluted_source_ref_repaired: prior source_ref pointed at a control overlay; "
    "unwrapped to clean source for crop generation."
)


@dataclass(frozen=True)
class PointCropSourceLineage:
    """Clean source lineage for point-crop pixel generation."""

    clean_source_ref: str
    placement_surface_ref: str | None = None
    source_unwrapped_from_ref: str | None = None
    legacy_source_repaired: bool = False
    legacy_source_repair_warning: str | None = None


def overlay_role_from_descriptor(desc: Mapping[str, Any]) -> str | None:
    """Return overlay_role from a derived-image descriptor."""
    meta = desc.get("transform_metadata")
    if isinstance(meta, Mapping):
        overlay = meta.get("overlay")
        if isinstance(overlay, Mapping):
            role = overlay.get("overlay_role")
            if isinstance(role, str) and role.strip():
                return role.strip()
        role = meta.get("overlay_role")
        if isinstance(role, str) and role.strip():
            return role.strip()
    crop_set = meta.get("crop_set") if isinstance(meta, Mapping) else None
    if isinstance(crop_set, Mapping):
        role = crop_set.get("overlay_role")
        if isinstance(role, str) and role.strip():
            return role.strip()
    return None


def is_control_overlay_role(role: str | None) -> bool:
    return isinstance(role, str) and role.strip() in CONTROL_OVERLAY_ROLES


def resolve_point_crop_source_lineage(
    *,
    ref_id: str,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str,
    loader: Callable[[str, str, str, str], dict[str, Any] | None] = _load_derived_image_descriptor,
) -> tuple[PointCropSourceLineage | None, dict[str, str] | None]:
    """Resolve the clean source ref to open for point-crop pixel generation."""
    clean_ref = str(ref_id or "").strip()
    if not clean_ref:
        return None, {"code": "ref_id_required", "message": "ref_id is required."}

    if clean_ref.startswith(_IMAGE_ASSOC_PREFIX):
        return PointCropSourceLineage(clean_source_ref=clean_ref), None

    if not clean_ref.startswith(_IMAGE_DERIVED_PREFIX):
        return None, {
            "code": "invalid_transform_params",
            "message": "point_crops ref_id must be an image:assoc:* or image:derived:* ref.",
        }

    return _resolve_derived_point_crop_source(
        ref_id=clean_ref,
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_key=workspace_key,
        loader=loader,
        placement_surface_ref=clean_ref,
        source_unwrapped_from_ref=clean_ref,
        legacy_repaired=False,
        visited=frozenset(),
    )


def repair_stored_point_crop_source_ref(
    source_ref: str,
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str,
    placement_surface_ref: str | None = None,
    loader: Callable[[str, str, str, str], dict[str, Any] | None] = _load_derived_image_descriptor,
) -> tuple[PointCropSourceLineage | None, dict[str, str] | None]:
    """Unwrap a stored crop-set source_ref when legacy metadata pointed at control overlays."""
    clean_ref = str(source_ref or "").strip()
    if not clean_ref:
        return None, {
            "code": "invalid_transform_params",
            "message": "point_crops metadata is missing source_ref.",
        }

    if clean_ref.startswith(_IMAGE_ASSOC_PREFIX):
        return PointCropSourceLineage(
            clean_source_ref=clean_ref,
            placement_surface_ref=placement_surface_ref,
        ), None

    if not clean_ref.startswith(_IMAGE_DERIVED_PREFIX):
        return None, {
            "code": "invalid_transform_params",
            "message": "Stored point_crops source_ref is not a supported image ref.",
        }

    desc = loader(dossier_id, transcription_id, workspace_key, clean_ref)
    if desc is None:
        return None, {"code": "derived_ref_not_found", "message": "Derived image ref not found."}

    role = overlay_role_from_descriptor(desc)
    if not is_control_overlay_role(role):
        return PointCropSourceLineage(
            clean_source_ref=clean_ref,
            placement_surface_ref=placement_surface_ref,
        ), None

    lineage, error = _resolve_derived_point_crop_source(
        ref_id=clean_ref,
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_key=workspace_key,
        loader=loader,
        placement_surface_ref=placement_surface_ref or clean_ref,
        source_unwrapped_from_ref=clean_ref,
        legacy_repaired=True,
        visited=frozenset(),
    )
    if error or lineage is None:
        return lineage, error
    return PointCropSourceLineage(
        clean_source_ref=lineage.clean_source_ref,
        placement_surface_ref=lineage.placement_surface_ref or placement_surface_ref,
        source_unwrapped_from_ref=lineage.source_unwrapped_from_ref,
        legacy_source_repaired=True,
        legacy_source_repair_warning=_LEGACY_REPAIR_WARNING,
    ), None


def _resolve_derived_point_crop_source(
    *,
    ref_id: str,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str,
    loader: Callable[[str, str, str, str], dict[str, Any] | None],
    placement_surface_ref: str | None,
    source_unwrapped_from_ref: str | None,
    legacy_repaired: bool,
    visited: frozenset[str],
) -> tuple[PointCropSourceLineage | None, dict[str, str] | None]:
    if ref_id in visited:
        return None, {
            "code": "invalid_transform_params",
            "message": "Could not resolve a clean source ref from the control overlay lineage.",
        }

    desc = loader(dossier_id, transcription_id, workspace_key, ref_id)
    if desc is None:
        return None, {"code": "derived_ref_not_found", "message": "Derived image ref not found."}

    role = overlay_role_from_descriptor(desc)
    if not is_control_overlay_role(role):
        return PointCropSourceLineage(
            clean_source_ref=ref_id,
            placement_surface_ref=None,
            source_unwrapped_from_ref=None,
            legacy_source_repaired=legacy_repaired,
            legacy_source_repair_warning=_LEGACY_REPAIR_WARNING if legacy_repaired else None,
        ), None

    next_visited = visited | {ref_id}
    for candidate in _clean_source_candidates(desc, ref_id=ref_id):
        if candidate.startswith(_IMAGE_ASSOC_PREFIX):
            return PointCropSourceLineage(
                clean_source_ref=candidate,
                placement_surface_ref=placement_surface_ref or ref_id,
                source_unwrapped_from_ref=source_unwrapped_from_ref or ref_id,
                legacy_source_repaired=legacy_repaired,
                legacy_source_repair_warning=_LEGACY_REPAIR_WARNING if legacy_repaired else None,
            ), None

        if not candidate.startswith(_IMAGE_DERIVED_PREFIX):
            continue

        child_desc = loader(dossier_id, transcription_id, workspace_key, candidate)
        if child_desc is None:
            continue
        child_role = overlay_role_from_descriptor(child_desc)
        if is_control_overlay_role(child_role):
            lineage, error = _resolve_derived_point_crop_source(
                ref_id=candidate,
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_key=workspace_key,
                loader=loader,
                placement_surface_ref=placement_surface_ref or ref_id,
                source_unwrapped_from_ref=source_unwrapped_from_ref or ref_id,
                legacy_repaired=legacy_repaired or candidate != ref_id,
                visited=next_visited,
            )
            if lineage is not None:
                return lineage, None
            if error:
                continue
            continue

        return PointCropSourceLineage(
            clean_source_ref=candidate,
            placement_surface_ref=placement_surface_ref or ref_id,
            source_unwrapped_from_ref=source_unwrapped_from_ref or ref_id,
            legacy_source_repaired=legacy_repaired,
            legacy_source_repair_warning=_LEGACY_REPAIR_WARNING if legacy_repaired else None,
        ), None

    return None, {
        "code": "clean_source_unavailable",
        "message": (
            "Could not resolve a clean source image for point_crops from the supplied control overlay ref."
        ),
    }


def _clean_source_candidates(desc: Mapping[str, Any], *, ref_id: str) -> list[str]:
    meta = desc.get("transform_metadata")
    meta_map = meta if isinstance(meta, Mapping) else {}
    candidates: list[str] = []

    def _add(value: Any) -> None:
        if not isinstance(value, str):
            return
        cleaned = value.strip()
        if cleaned and cleaned != ref_id and cleaned not in candidates:
            candidates.append(cleaned)

    _add(meta_map.get("source_ref"))
    _add(desc.get("root_source_ref"))
    _add(meta_map.get("root_source_ref"))
    _add(desc.get("parent_ref_id"))
    return candidates
