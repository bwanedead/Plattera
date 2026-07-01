"""Read-only bridge: hydrate transcript-edit source evidence refs from deed-to-IR."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tooling.mapping.transcript_edit.image_loading import (
    hydrate_source_image_context,
    image_evidence_from_path,
)
from tooling.mapping.transcript_edit.paths import UnsafeArtifactPathSegmentError
from tooling.mapping.transcript_edit import paths as transcript_edit_paths

_IMAGE_ASSOC_PREFIX = "image:assoc:"
_IMAGE_DERIVED_PREFIX = "image:derived:"
_RESOLUTION_STATE_REF_PREFIX = "transcript_edit:resolution_state:"
_PATH_KEYS = frozenset({"absolute_path", "path", "descriptor_file"})


def transcript_edit_workspace_from_handoff(handoff_context: Mapping[str, Any] | None) -> str | None:
    """Mechanically derive upstream transcript-edit workspace id from resolution_state_ref."""
    if not isinstance(handoff_context, Mapping):
        return None
    ref = handoff_context.get("resolution_state_ref")
    if not isinstance(ref, str) or not ref.startswith(_RESOLUTION_STATE_REF_PREFIX):
        return None
    suffix = ref[len(_RESOLUTION_STATE_REF_PREFIX) :].strip()
    return suffix or None


def hydrate_upstream_source_evidence_ref(
    *,
    dossier_id: str,
    transcription_id: str | None,
    ref_id: str,
    handoff_context: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Hydrate one image:assoc or image:derived ref. Returns (row, error, image_evidence)."""
    text = str(ref_id or "").strip()
    if not text:
        return None, {"ref_id": ref_id, "reason": "empty_ref_id"}, None

    if text.startswith(_IMAGE_ASSOC_PREFIX):
        return _hydrate_assoc_ref(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            ref_id=text,
        )
    if text.startswith(_IMAGE_DERIVED_PREFIX):
        workspace_id = transcript_edit_workspace_from_handoff(handoff_context)
        if not workspace_id:
            return None, {
                "ref_id": text,
                "reason": "transcript_edit_workspace_unavailable",
            }, None
        if not transcription_id:
            return None, {"ref_id": text, "reason": "transcription_id_required"}, None
        return _hydrate_derived_ref(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            ref_id=text,
        )
    return None, {"ref_id": text, "reason": "unsupported_upstream_evidence_ref"}, None


def _hydrate_assoc_ref(
    *,
    dossier_id: str,
    transcription_id: str | None,
    ref_id: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    if not transcription_id:
        return None, {"ref_id": ref_id, "reason": "transcription_id_required"}, None
    raw = hydrate_source_image_context(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        ref_id=ref_id,
    )
    if raw.get("status") != "ok":
        return None, {
            "ref_id": ref_id,
            "reason": str(raw.get("code") or "hydration_error"),
        }, None
    row = {
        "ref_id": ref_id,
        "kind": "upstream_source_image",
        "exists": raw.get("exists"),
        "size_bytes": raw.get("size_bytes"),
        "width_height": raw.get("width_height"),
        "basename": raw.get("basename"),
        "role": raw.get("role"),
    }
    evidence = None
    b64 = raw.get("image_b64")
    if b64:
        evidence = {
            "ref_id": ref_id,
            "b64": b64,
            "media_type": raw.get("image_media_type", "image/jpeg"),
        }
    return row, None, evidence


def _hydrate_derived_ref(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    ref_id: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    uuid = ref_id[len(_IMAGE_DERIVED_PREFIX) :]
    if not uuid or "/" in uuid or "\\" in uuid or ".." in uuid:
        return None, {"ref_id": ref_id, "reason": "invalid_ref_id"}, None
    try:
        derived_dir = transcript_edit_paths.transcript_edit_derived_images_dir(
            dossier_id, transcription_id, workspace_id
        )
    except UnsafeArtifactPathSegmentError:
        return None, {"ref_id": ref_id, "reason": "invalid_workspace_path"}, None

    descriptor = _load_derived_image_descriptor_file(derived_dir=derived_dir, uuid=uuid)
    if descriptor is None:
        return None, {"ref_id": ref_id, "reason": "not_found"}, None

    png_path, path_reason = _resolve_safe_derived_png_path(
        derived_dir=derived_dir,
        uuid=uuid,
        descriptor=descriptor,
    )
    if path_reason is not None:
        return None, {"ref_id": ref_id, "reason": path_reason}, None

    row = _path_free_mapping(descriptor)
    row["ref_id"] = ref_id
    row["kind"] = "upstream_derived_image"

    evidence = None
    if png_path is not None and png_path.is_file():
        evidence = image_evidence_from_path(ref_id, png_path)
    return row, None, evidence


def _load_derived_image_descriptor_file(*, derived_dir: Path, uuid: str) -> dict[str, Any] | None:
    desc_path = derived_dir / f"{uuid}.json"
    if not desc_path.is_file():
        return None
    try:
        data = json.loads(desc_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _resolve_safe_derived_png_path(
    *,
    derived_dir: Path,
    uuid: str,
    descriptor: Mapping[str, Any],
) -> tuple[Path | None, str | None]:
    """Return (png_path, error_reason). Rejects descriptor paths outside derived_dir."""
    derived_resolved = derived_dir.resolve()
    expected = (derived_resolved / f"{uuid}.png").resolve()
    abs_path = descriptor.get("absolute_path")
    if isinstance(abs_path, str) and abs_path.strip():
        candidate = Path(abs_path).resolve()
        try:
            candidate.relative_to(derived_resolved)
        except ValueError:
            return None, "derived_image_path_outside_workspace"
        if candidate != expected:
            return None, "derived_image_path_mismatch"
        return candidate, None if candidate.is_file() else "derived_image_missing"
    if expected.is_file():
        return expected, None
    return None, "derived_image_missing"


def _load_derived_image_descriptor(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    ref_id: str,
) -> dict[str, Any] | None:
    uuid = ref_id[len(_IMAGE_DERIVED_PREFIX) :]
    if not uuid or "/" in uuid or "\\" in uuid or ".." in uuid:
        return None
    try:
        derived_dir = transcript_edit_paths.transcript_edit_derived_images_dir(
            dossier_id, transcription_id, workspace_id
        )
    except UnsafeArtifactPathSegmentError:
        return None
    return _load_derived_image_descriptor_file(derived_dir=derived_dir, uuid=uuid)


def _path_free_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(k): v for k, v in value.items() if str(k) not in _PATH_KEYS}
