"""STORAGE-BR-009: read-only derived-image cache reclamation planning.

Pure planning over complete internal audit records. Never authorizes deletion,
never writes bytes, and never rescans storage independently of the audit pipeline.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .derived_image_descriptor import classify_coordinates_image, resolve_derived_image_coordinates
from .derived_image_rendering import GENERIC_SUB_ACTIONS
from .derived_image_resolution import (
    DerivedImageResolutionError,
    resolve_derived_image_for_read,
)

SCHEMA_VERSION = "transcript_edit.derived_image_reclamation_plan.v1"
RECLAMATION_POSTURE = "candidate_pending_quiescence"

_CONTENT_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_CANONICAL_OR_LEGACY_POSTURES = frozenset({"canonical_source", "legacy_source_adjacent"})
_EXCLUDED_STORAGE_POSTURES = frozenset(
    {
        "missing_descriptor",
        "conflicting_identity",
        "external_or_unsafe",
        "missing_image",
    }
)

_POINT_CROP_SUB_ACTIONS = frozenset(
    {
        "point_crops",
        "point_crops_crop",
        "point_crops_scaffold",
        "point_crops_view",
        "point_crops_adjust",
    }
)


def _is_canonical_content_sha256(value: Any) -> bool:
    return type(value) is str and bool(_CONTENT_SHA256_RE.fullmatch(value.strip()))


def _descriptor_has_durable_content_identity(rec: dict[str, Any]) -> bool:
    obj = rec.get("_obj")
    if not isinstance(obj, dict):
        return False
    return _is_canonical_content_sha256(obj.get("content_sha256"))


def _descriptor_path_safe(rec: dict[str, Any]) -> bool:
    desc_path = rec.get("_abs_descriptor_path")
    if not isinstance(desc_path, Path):
        return False
    if not desc_path.is_file() or desc_path.is_symlink() or os.path.islink(desc_path):
        return False
    return True


def _image_path_safe_run_owned(rec: dict[str, Any]) -> bool:
    image_path = rec.get("_abs_image_path")
    if not isinstance(image_path, Path):
        return False
    if not image_path.is_file() or image_path.is_symlink() or os.path.islink(image_path):
        return False
    dossier_id = str(rec.get("_dossier_id") or "")
    tx_id = str(rec.get("_tx_id") or "")
    ws_id = str(rec.get("_ws_id") or "")
    ref_id = rec.get("ref_id")
    if type(ref_id) is not str or not dossier_id or not tx_id or not ws_id:
        return False
    try:
        coords = resolve_derived_image_coordinates(
            dossier_id=dossier_id,
            transcription_id=tx_id,
            workspace_id=ws_id,
            ref_id=ref_id,
        )
    except Exception:
        return False
    return classify_coordinates_image(coords) == "safe_regular_file"


def _verify_resolver_for_candidate(rec: dict[str, Any]) -> bool:
    """Canonical read resolver must prove stored bytes + descriptor content coordinate."""
    dossier_id = str(rec.get("_dossier_id") or "")
    tx_id = str(rec.get("_tx_id") or "")
    ws_id = str(rec.get("_ws_id") or "")
    ref_id = rec.get("ref_id")
    if type(ref_id) is not str:
        return False
    try:
        resolved = resolve_derived_image_for_read(
            dossier_id=dossier_id,
            transcription_id=tx_id,
            workspace_id=ws_id,
            ref_id=ref_id,
        )
    except DerivedImageResolutionError:
        return False
    if resolved.representation_kind != "stored_bytes":
        return False
    if resolved.content_identity_posture != "stored_bytes_verified":
        return False
    physical = rec.get("content_sha256")
    if not _is_canonical_content_sha256(physical):
        return False
    if resolved.content_sha256 != physical.strip():
        return False
    obj = rec.get("_obj")
    if not isinstance(obj, dict):
        return False
    descriptor_coord = obj.get("content_sha256")
    if not _is_canonical_content_sha256(descriptor_coord):
        return False
    if resolved.content_sha256 != descriptor_coord.strip():
        return False
    if resolved.pixel_sha256 != rec.get("pixel_sha256"):
        return False
    return True


def reclamation_exclusion_reason(rec: dict[str, Any]) -> str | None:
    """Return a stable exclusion reason, or None when the record is a candidate."""
    return _exclusion_reason(rec)


def _descriptor_bytes_digest(rec: dict[str, Any]) -> str | None:
    desc_path = rec.get("_abs_descriptor_path")
    if not isinstance(desc_path, Path):
        return None
    try:
        return hashlib.sha256(desc_path.read_bytes()).hexdigest()
    except OSError:
        return None


def build_reclamation_candidate_contract(rec: dict[str, Any]) -> dict[str, Any]:
    """Bounded mechanical identity for BR-009 planning and BR-010 revalidation."""
    row = _candidate_row(rec)
    row["descriptor_bytes_digest"] = _descriptor_bytes_digest(rec)
    row["pixel_sha256"] = rec.get("pixel_sha256")
    row["sub_action"] = rec.get("sub_action")
    return row


def collect_reclamation_candidates_from_records(
    records: list[dict[str, Any]],
    *,
    dossier_id: str,
    workspace_id: str,
    transcription_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return eligible candidates in deterministic full-coordinate order."""
    candidates: list[dict[str, Any]] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if str(rec.get("_dossier_id") or "") != dossier_id:
            continue
        if str(rec.get("_ws_id") or "") != workspace_id:
            continue
        if transcription_id and str(rec.get("_tx_id") or "") != transcription_id:
            continue
        if reclamation_exclusion_reason(rec) is not None:
            continue
        contract = build_reclamation_candidate_contract(rec)
        digest = contract.get("descriptor_bytes_digest")
        if type(digest) is not str or not _CONTENT_SHA256_RE.fullmatch(digest):
            continue
        candidates.append(contract)
    candidates.sort(
        key=lambda row: (
            str(row.get("dossier_id") or ""),
            str(row.get("transcription_id") or ""),
            str(row.get("workspace_id") or ""),
            str(row.get("ref_id") or ""),
        )
    )
    return candidates


def _exclusion_reason(rec: dict[str, Any]) -> str | None:
    """Return a stable exclusion reason, or None when the record is a candidate."""
    posture = rec.get("storage_posture")
    if posture in _CANONICAL_OR_LEGACY_POSTURES:
        return "canonical_or_legacy_source"
    if posture in _EXCLUDED_STORAGE_POSTURES:
        if posture == "missing_descriptor":
            return "missing_descriptor_or_orphan"
        if posture == "conflicting_identity":
            return "conflicting_or_ambiguous_identity"
        if posture == "external_or_unsafe":
            return "external_or_unsafe_path"
        if posture == "missing_image":
            return "missing_png"
        return str(posture)
    if posture != "run_owned":
        return "not_run_owned"

    sub_action = rec.get("sub_action")
    if sub_action in _POINT_CROP_SUB_ACTIONS:
        return "point_crop_family"
    if type(sub_action) is not str or sub_action not in GENERIC_SUB_ACTIONS:
        return "unsupported_or_unknown_sub_action"

    if not _descriptor_path_safe(rec):
        return "descriptor_unsafe_or_absent"
    if not _image_path_safe_run_owned(rec):
        return "unsafe_or_unreadable_png"

    size = rec.get("size_bytes")
    if type(size) is not int or size <= 0:
        return "missing_or_invalid_physical_size"

    if not _is_canonical_content_sha256(rec.get("content_sha256")):
        return "missing_or_invalid_physical_content_sha256"
    if type(rec.get("pixel_sha256")) is not str or not rec.get("pixel_sha256"):
        return "missing_or_invalid_pixel_sha256"

    if rec.get("recipe_source") != "persisted":
        return "recipe_not_persisted"

    recon = rec.get("reconstruction_posture")
    if recon == "verified_pixel_mismatch":
        return "pixel_mismatch"
    if recon != "verified_pixel_exact":
        return "reconstruction_not_verified_pixel_exact"

    if not _descriptor_has_durable_content_identity(rec):
        return "descriptor_missing_durable_content_sha256"

    if not _verify_resolver_for_candidate(rec):
        return "resolver_verification_failed"

    return None


def _candidate_row(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref_id": rec.get("ref_id"),
        "dossier_id": rec.get("_dossier_id"),
        "transcription_id": rec.get("_tx_id"),
        "workspace_id": rec.get("_ws_id"),
        "relative_image_path": rec.get("relative_image_path"),
        "relative_descriptor_path": rec.get("relative_descriptor_path"),
        "size_bytes": rec.get("size_bytes"),
        "content_sha256": rec.get("content_sha256"),
        "recipe_fingerprint": rec.get("recipe_fingerprint"),
        "reference_posture": rec.get("reference_posture"),
        "reclamation_posture": RECLAMATION_POSTURE,
    }


def build_derived_image_reclamation_plan(
    records: list[dict[str, Any]],
    *,
    max_candidates: int = 500,
) -> dict[str, Any]:
    """Build a conservative reclamation plan from complete internal audit records."""
    if not isinstance(max_candidates, int) or isinstance(max_candidates, bool) or max_candidates < 0:
        raise ValueError("max_candidates must be a non-negative integer.")

    reason_counts: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []
    retained_run_owned_count = 0
    examined_count = 0

    for rec in records:
        if not isinstance(rec, dict):
            continue
        examined_count += 1
        reason = _exclusion_reason(rec)
        if reason is None:
            candidates.append(_candidate_row(rec))
        else:
            reason_counts[reason] += 1
            if rec.get("storage_posture") == "run_owned" and rec.get("ref_id"):
                retained_run_owned_count += 1

    candidate_count = len(candidates)
    retained_count = examined_count - candidate_count
    candidate_bytes = sum(int(c.get("size_bytes") or 0) for c in candidates)
    capped = candidates[:max_candidates]
    omitted = max(0, candidate_count - len(capped))

    return {
        "schema_version": SCHEMA_VERSION,
        "authorization_posture": "planning_only",
        "apply_supported": False,
        "examined_count": examined_count,
        "candidate_count": candidate_count,
        "candidate_bytes": candidate_bytes,
        "retained_count": retained_count,
        "retained_run_owned_count": retained_run_owned_count,
        "reason_counts": dict(sorted(reason_counts.items())),
        "candidates": capped,
        "candidates_omitted_count": omitted,
    }


def run_derived_image_reclamation_plan(
    *,
    dossier_id: str | None = None,
    transcription_id: str | None = None,
    workspace_id: str | None = None,
    all_dossiers: bool = False,
    harness_audit_roots: list[Path] | None = None,
    max_candidates: int = 500,
) -> dict[str, Any]:
    """Collect audit records once, then build the reclamation plan (read-only)."""
    from .derived_image_storage_audit import (
        StorageAuditScopeError,
        collect_derived_image_storage_records,
        validate_derived_image_storage_audit_scope,
    )

    validate_derived_image_storage_audit_scope(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        all_dossiers=all_dossiers,
    )
    if not isinstance(max_candidates, int) or isinstance(max_candidates, bool) or max_candidates < 0:
        raise StorageAuditScopeError(
            "bounds_invalid",
            "max_candidates must be a non-negative integer.",
        )

    records, _diagnostics = collect_derived_image_storage_records(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        all_dossiers=all_dossiers,
        harness_audit_roots=harness_audit_roots,
    )
    plan = build_derived_image_reclamation_plan(records, max_candidates=max_candidates)
    plan["scope"] = {
        "dossier_id": dossier_id,
        "transcription_id": transcription_id,
        "workspace_id": workspace_id,
        "all_dossiers": all_dossiers,
    }
    return plan


__all__ = [
    "RECLAMATION_POSTURE",
    "SCHEMA_VERSION",
    "build_derived_image_reclamation_plan",
    "build_reclamation_candidate_contract",
    "collect_reclamation_candidates_from_records",
    "reclamation_exclusion_reason",
    "run_derived_image_reclamation_plan",
]
