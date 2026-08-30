"""STORAGE-BR-004 derived-image storage audit coordinator (read-only).

Public entry point: ``run_derived_image_storage_audit()``.

Inventory, reconstruction, and reference analysis live in sibling modules.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from config import paths as config_paths

from .derived_image_storage_inventory import (
    flag_conflicting_identity,
    iter_derived_images_dirs,
    scan_derived_images_dir,
    scan_originals,
)
from .derived_image_storage_reconstruction import attempt_reconstruction
from .derived_image_storage_references import assign_reference_postures, build_reference_index
from .paths import UnsafeArtifactPathSegmentError, require_safe_path_segment

SCHEMA_VERSION = "transcript_edit.derived_image_storage_audit.v1"

_RECONSTRUCTION_POSTURES = frozenset(
    {
        "verified_pixel_exact",
        "verified_pixel_mismatch",
        "not_attempted_missing_source",
        "not_attempted_incomplete_recipe",
        "not_attempted_unsupported_sub_action",
        "not_attempted_renderer_unknown",
        "render_failed",
        "stored_image_unreadable",
    }
)
_REFERENCE_POSTURES = frozenset(
    {
        "externally_referenced",
        "descriptor_only",
        "unreferenced_observed",
        "reference_ambiguous",
    }
)


class StorageAuditScopeError(Exception):
    """Raised for an invalid or unsafe audit scope specification."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = str(code or "scope_invalid")
        self.message = str(message or "")
        super().__init__(f"{self.code}: {self.message}" if self.message else self.code)


def _ensure_complete_postures(records: list[dict[str, Any]]) -> None:
    """Every artifact row must carry fixed-vocabulary reconstruction + reference postures."""
    for rec in records:
        rp = rec.get("reconstruction_posture")
        if rp not in _RECONSTRUCTION_POSTURES:
            rec["reconstruction_posture"] = "not_attempted_incomplete_recipe"
        refp = rec.get("reference_posture")
        if refp not in _REFERENCE_POSTURES:
            rec["reference_posture"] = "unreferenced_observed"
        if rec.get("recipe_source") not in {"persisted", "inferred", "unavailable"}:
            rec["recipe_source"] = "unavailable"


def _build_duplicate_groups(
    records: list[dict[str, Any]],
    max_groups: int,
) -> tuple[list[dict[str, Any]], int, int]:
    sha_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        cs = rec.get("content_sha256")
        if cs:
            sha_groups[cs].append(rec)

    total_group_count = 0
    total_wasted_bytes = 0
    groups: list[dict[str, Any]] = []

    for sha, recs in sorted(sha_groups.items()):
        if len(recs) < 2:
            continue
        total_group_count += 1
        size = recs[0].get("size_bytes") or 0
        wasted = (len(recs) - 1) * size
        total_wasted_bytes += wasted
        if len(groups) < max_groups:
            groups.append(
                {
                    "content_sha256": sha,
                    "pixel_sha256": recs[0].get("pixel_sha256"),
                    "member_count": len(recs),
                    "size_bytes_each": size,
                    "wasted_bytes": wasted,
                    "members": [
                        {
                            "relative_image_path": r.get("relative_image_path"),
                            "relative_descriptor_path": r.get("relative_descriptor_path"),
                            "ref_id": r.get("ref_id"),
                        }
                        for r in recs
                    ],
                }
            )

    return groups, total_group_count, total_wasted_bytes


def _to_artifact_row(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref_id": rec.get("ref_id"),
        "storage_posture": rec.get("storage_posture"),
        "reconstruction_posture": rec.get("reconstruction_posture"),
        "reference_posture": rec.get("reference_posture"),
        "reference_source_kind": rec.get("_reference_source_kind"),
        "relative_image_path": rec.get("relative_image_path"),
        "relative_descriptor_path": rec.get("relative_descriptor_path"),
        "content_sha256": rec.get("content_sha256"),
        "pixel_sha256": rec.get("pixel_sha256"),
        "size_bytes": rec.get("size_bytes"),
        "sub_action": rec.get("sub_action"),
        "byte_equal_to_reconstruction": rec.get("byte_equal_to_reconstruction"),
        "recipe_fingerprint": rec.get("recipe_fingerprint"),
        "recipe_source": rec.get("recipe_source") or "unavailable",
        "parent_ref_id": rec.get("parent_ref_id"),
    }


def run_derived_image_storage_audit(
    *,
    dossier_id: str | None = None,
    transcription_id: str | None = None,
    workspace_id: str | None = None,
    all_dossiers: bool = False,
    harness_audit_roots: list[Path] | None = None,
    max_artifacts: int = 500,
    max_duplicate_groups: int = 100,
    max_diagnostics: int = 200,
) -> dict[str, Any]:
    """Run the STORAGE-BR-004 derived image storage audit (read-only)."""
    if all_dossiers and dossier_id:
        raise StorageAuditScopeError(
            "scope_conflict",
            "Provide dossier_id or all_dossiers=True, not both.",
        )
    if not all_dossiers and not dossier_id:
        raise StorageAuditScopeError(
            "scope_missing",
            "Provide dossier_id or set all_dossiers=True.",
        )
    for field, value in (
        ("max_artifacts", max_artifacts),
        ("max_duplicate_groups", max_duplicate_groups),
        ("max_diagnostics", max_diagnostics),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise StorageAuditScopeError(
                "bounds_invalid",
                f"{field} must be a non-negative integer.",
            )

    for field, value in (
        ("dossier_id", dossier_id),
        ("transcription_id", transcription_id),
        ("workspace_id", workspace_id),
    ):
        if value is not None:
            try:
                require_safe_path_segment(value, field=field)
            except UnsafeArtifactPathSegmentError as exc:
                raise StorageAuditScopeError(f"scope_unsafe_{field}", str(exc)) from exc

    dossiers_root = config_paths.dossiers_root()
    all_records: list[dict[str, Any]] = []
    all_diagnostics: list[dict[str, Any]] = []

    scope_dirs = iter_derived_images_dirs(
        dossier_id, transcription_id, workspace_id, all_dossiers
    )
    for did, tid, wid, di_dir in scope_dirs:
        recs, diags = scan_derived_images_dir(did, tid, wid, di_dir, dossiers_root)
        all_records.extend(recs)
        all_diagnostics.extend(diags)

    orig_recs, orig_diags = scan_originals(dossiers_root)
    all_records.extend(orig_recs)
    all_diagnostics.extend(orig_diags)

    flag_conflicting_identity(all_records, all_diagnostics)

    records_by_ref: dict[str, dict[str, Any]] = {
        rec["ref_id"]: rec for rec in all_records if rec.get("ref_id")
    }
    for rec in all_records:
        if rec.get("storage_posture") != "run_owned":
            continue
        attempt_reconstruction(rec, records_by_ref, all_diagnostics)

    ref_map = build_reference_index(
        all_records, scope_dirs, dossier_id, harness_audit_roots, dossiers_root
    )
    assign_reference_postures(all_records, ref_map, dossiers_root)
    _ensure_complete_postures(all_records)

    groups, total_group_count, total_wasted_bytes = _build_duplicate_groups(
        all_records, max_duplicate_groups
    )
    groups_omitted = max(0, total_group_count - len(groups))

    summary: dict[str, Any] = {
        "observed_image_count": len(all_records),
        "observed_bytes": sum(r.get("size_bytes") or 0 for r in all_records),
        "canonical_source_count": sum(
            1 for r in all_records if r["storage_posture"] == "canonical_source"
        ),
        "legacy_source_adjacent_count": sum(
            1 for r in all_records if r["storage_posture"] == "legacy_source_adjacent"
        ),
        "run_owned_count": sum(1 for r in all_records if r["storage_posture"] == "run_owned"),
        "missing_image_count": sum(
            1 for r in all_records if r["storage_posture"] == "missing_image"
        ),
        "missing_descriptor_count": sum(
            1 for r in all_records if r["storage_posture"] == "missing_descriptor"
        ),
        "conflicting_identity_count": sum(
            1 for r in all_records if r["storage_posture"] == "conflicting_identity"
        ),
        "verified_pixel_exact_count": sum(
            1 for r in all_records if r.get("reconstruction_posture") == "verified_pixel_exact"
        ),
        "pixel_mismatch_count": sum(
            1 for r in all_records if r.get("reconstruction_posture") == "verified_pixel_mismatch"
        ),
        "externally_referenced_count": sum(
            1 for r in all_records if r.get("reference_posture") == "externally_referenced"
        ),
        "exact_duplicate_group_count": total_group_count,
        "exact_duplicate_bytes": total_wasted_bytes,
    }

    artifacts_omitted = max(0, len(all_records) - max_artifacts)
    artifact_rows = [_to_artifact_row(r) for r in all_records[:max_artifacts]]
    diagnostics_omitted = max(0, len(all_diagnostics) - max_diagnostics)
    diagnostics_out = all_diagnostics[:max_diagnostics]

    return {
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "dossier_id": dossier_id,
            "transcription_id": transcription_id,
            "workspace_id": workspace_id,
            "all_dossiers": all_dossiers,
        },
        "summary": summary,
        "artifacts": artifact_rows,
        "duplicate_groups": groups,
        "diagnostics": diagnostics_out,
        "artifacts_omitted_count": artifacts_omitted,
        "duplicate_groups_omitted_count": groups_omitted,
        "diagnostics_omitted_count": diagnostics_omitted,
    }
