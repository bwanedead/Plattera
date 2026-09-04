"""STORAGE-BR-010: quiescence-gated derived-image PNG cache reclamation apply.

Deletes only reconstructible generic run-owned PNG bytes. Descriptors and recipes
remain durable. Never imports harness modules; callers inject quiescence checks.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .derived_image_descriptor import (
    classify_coordinates_image,
    resolve_derived_image_coordinates,
)
from .derived_image_reclamation_plan import (
    build_reclamation_candidate_contract,
    collect_reclamation_candidates_from_records,
    reclamation_exclusion_reason,
)
from .derived_image_rendering import compute_image_identity
from .derived_image_resolution import (
    DerivedImageResolutionError,
    reconstruct_generic_from_persisted_recipe,
    resolve_derived_image_for_read,
)
from .derived_image_storage_audit import (
    StorageAuditScopeError,
    collect_derived_image_storage_records,
    validate_derived_image_storage_audit_scope,
)

SCHEMA_VERSION = "transcript_edit.derived_image_reclamation_apply.v1"
MAX_ARTIFACT_ROWS = 64

_CONTENT_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

REASON_RUN_NOT_QUIESCENT = "run_not_quiescent"
REASON_RUN_ACTIVITY_UNKNOWN = "run_activity_unknown"
REASON_RUN_SCOPE_UNKNOWN = "run_scope_unknown"
REASON_QUIESCENCE_CALLBACK_REQUIRED = "quiescence_callback_required"
REASON_APPLY_INVALID_TYPE = "apply_invalid_type"
REASON_CANDIDATE_NO_LONGER_ELIGIBLE = "candidate_no_longer_eligible"
REASON_CANDIDATE_IDENTITY_CHANGED = "candidate_identity_changed"
REASON_CANDIDATE_PATH_UNSAFE = "candidate_path_unsafe"
REASON_CANDIDATE_IS_SYMLINK = "candidate_is_symlink"
REASON_CANDIDATE_DELETE_FAILED = "candidate_delete_failed"
REASON_CANDIDATE_DELETE_VERIFICATION_FAILED = "candidate_delete_verification_failed"
REASON_DESCRIPTOR_CHANGED = "descriptor_changed"
REASON_POST_DELETE_RECONSTRUCTION_FAILED = "post_delete_reconstruction_failed"
REASON_DELETION_BUDGET_INVALID = "deletion_budget_invalid"

QuiescenceFn = Callable[[], str | None]
DeleteFn = Callable[[Path], None]

RecordKey = tuple[str, str, str, str]

_RECOGNIZED_QUIESCENCE_REASONS = frozenset(
    {
        REASON_RUN_NOT_QUIESCENT,
        REASON_RUN_ACTIVITY_UNKNOWN,
    }
)


def _evaluate_quiescence(quiescence_fn: QuiescenceFn) -> str | None:
    """Fail-closed quiescence evaluation.

    Exactly ``None`` means quiescent. Recognized nonblank reason strings are returned.
    Exceptions and every other value become ``run_activity_unknown``.
    """
    try:
        result = quiescence_fn()
    except Exception:
        return REASON_RUN_ACTIVITY_UNKNOWN
    if result is None:
        return None
    if type(result) is str:
        text = result.strip()
        if text in _RECOGNIZED_QUIESCENCE_REASONS:
            return text
        return REASON_RUN_ACTIVITY_UNKNOWN
    return REASON_RUN_ACTIVITY_UNKNOWN


def _validate_apply_scope_types(
    *,
    dossier_id: Any,
    workspace_id: Any,
    transcription_id: Any,
    run_id: Any,
) -> str | None:
    """Strict runtime scope types before shared validator coercion can apply."""
    if type(dossier_id) is not str or not dossier_id.strip():
        return REASON_RUN_SCOPE_UNKNOWN
    if type(workspace_id) is not str or not workspace_id.strip():
        return REASON_RUN_SCOPE_UNKNOWN
    if transcription_id is not None:
        if type(transcription_id) is not str or not transcription_id.strip():
            return REASON_RUN_SCOPE_UNKNOWN
    if run_id is not None:
        if type(run_id) is not str or not run_id.strip():
            return REASON_RUN_SCOPE_UNKNOWN
    return None


def _validate_max_deletions(max_deletions: int) -> str | None:
    if not isinstance(max_deletions, int) or isinstance(max_deletions, bool) or max_deletions < 0:
        return REASON_DELETION_BUDGET_INVALID
    return None


def _record_key_from_rec(rec: dict[str, Any]) -> RecordKey | None:
    ref_id = rec.get("ref_id")
    dossier_id = rec.get("_dossier_id")
    tx_id = rec.get("_tx_id")
    ws_id = rec.get("_ws_id")
    if not (
        type(ref_id) is str
        and type(dossier_id) is str
        and type(tx_id) is str
        and type(ws_id) is str
    ):
        return None
    return (dossier_id, tx_id, ws_id, ref_id)


def _record_key_from_candidate(candidate: dict[str, Any]) -> RecordKey | None:
    ref_id = candidate.get("ref_id")
    dossier_id = candidate.get("dossier_id")
    tx_id = candidate.get("transcription_id")
    ws_id = candidate.get("workspace_id")
    if not (
        type(ref_id) is str
        and type(dossier_id) is str
        and type(tx_id) is str
        and type(ws_id) is str
    ):
        return None
    return (dossier_id, tx_id, ws_id, ref_id)


def _records_by_coords(records: list[dict[str, Any]]) -> dict[RecordKey, dict[str, Any]]:
    out: dict[RecordKey, dict[str, Any]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        key = _record_key_from_rec(rec)
        if key is None:
            continue
        out[key] = rec
    return out


def _empty_result(
    *,
    apply: bool,
    run_id: str | None,
    dossier_id: str | None,
    transcription_id: str | None,
    workspace_id: str | None,
    status: str,
    reason_code: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "authorization_posture": "operator_apply_required",
        "apply": apply,
        "status": status,
        "scope": {
            "run_id": run_id,
            "dossier_id": dossier_id,
            "transcription_id": transcription_id,
            "workspace_id": workspace_id,
        },
        "eligible_count": 0,
        "eligible_bytes": 0,
        "selected_count": 0,
        "not_selected_count": 0,
        "deleted_count": 0,
        "bytes_reclaimed": 0,
        "skipped_count": 0,
        "aborted_count": 0,
        "artifacts": [],
        "artifacts_omitted_count": 0,
    }
    if reason_code:
        out["reason_code"] = reason_code
    return out


def _artifact_row(
    *,
    ref_id: str,
    status: str,
    reason_code: str | None = None,
    size_bytes: int | None = None,
    relative_image_path: str | None = None,
    relative_descriptor_path: str | None = None,
    reclamation_posture: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"ref_id": ref_id, "status": status}
    if reason_code:
        row["reason_code"] = reason_code
    if size_bytes is not None:
        row["size_bytes"] = size_bytes
    if relative_image_path:
        row["relative_image_path"] = relative_image_path
    if relative_descriptor_path:
        row["relative_descriptor_path"] = relative_descriptor_path
    if reclamation_posture:
        row["reclamation_posture"] = reclamation_posture
    return row


def _descriptor_digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _identity_matches(candidate: dict[str, Any], fresh: dict[str, Any]) -> bool:
    contract = build_reclamation_candidate_contract(fresh)
    keys = (
        "size_bytes",
        "content_sha256",
        "pixel_sha256",
        "recipe_fingerprint",
        "descriptor_bytes_digest",
    )
    return all(candidate.get(k) == contract.get(k) for k in keys)


def _mechanical_png_path(candidate: dict[str, Any]) -> Path | None:
    """Derive the PNG path from scope/ref identity. Does not trust candidate relative paths."""
    ref_id = candidate.get("ref_id")
    if type(ref_id) is not str:
        return None
    try:
        coords = resolve_derived_image_coordinates(
            dossier_id=str(candidate.get("dossier_id") or ""),
            transcription_id=str(candidate.get("transcription_id") or ""),
            workspace_id=str(candidate.get("workspace_id") or ""),
            ref_id=ref_id,
        )
    except Exception:
        return None
    return coords.image_path


def _fresh_recipe_pixel_sha256(candidate: dict[str, Any], desc_path: Path) -> str | None:
    """Execute the current persisted recipe; return reconstructed pixel identity."""
    try:
        descriptor = json.loads(desc_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(descriptor, dict):
        return None
    try:
        recon = reconstruct_generic_from_persisted_recipe(
            dossier_id=str(candidate.get("dossier_id") or ""),
            transcription_id=str(candidate.get("transcription_id") or ""),
            workspace_id=str(candidate.get("workspace_id") or ""),
            ref_id=str(candidate.get("ref_id") or ""),
            descriptor=descriptor,
        )
    except DerivedImageResolutionError:
        return None
    pixel = recon.pixel_sha256
    return pixel if type(pixel) is str and pixel else None


def _pre_delete_validate(
    candidate: dict[str, Any],
    rec: dict[str, Any],
    png_path: Path,
) -> str | None:
    """Revalidate against live bytes and a fresh recipe render immediately before unlink."""
    digest = candidate.get("descriptor_bytes_digest")
    if type(digest) is not str or not _CONTENT_SHA256_RE.fullmatch(digest):
        return REASON_CANDIDATE_NO_LONGER_ELIGIBLE

    if png_path.is_symlink() or os.path.islink(png_path):
        return REASON_CANDIDATE_IS_SYMLINK

    try:
        coords = resolve_derived_image_coordinates(
            dossier_id=str(candidate.get("dossier_id") or ""),
            transcription_id=str(candidate.get("transcription_id") or ""),
            workspace_id=str(candidate.get("workspace_id") or ""),
            ref_id=str(candidate.get("ref_id") or ""),
        )
    except Exception:
        return REASON_CANDIDATE_PATH_UNSAFE
    if coords.image_path != png_path:
        return REASON_CANDIDATE_PATH_UNSAFE
    if classify_coordinates_image(coords) != "safe_regular_file":
        return REASON_CANDIDATE_PATH_UNSAFE
    if not png_path.is_file():
        return REASON_CANDIDATE_NO_LONGER_ELIGIBLE

    desc_path = rec.get("_abs_descriptor_path")
    if not isinstance(desc_path, Path):
        return REASON_CANDIDATE_PATH_UNSAFE
    if desc_path.is_symlink() or os.path.islink(desc_path) or not desc_path.is_file():
        return REASON_CANDIDATE_PATH_UNSAFE

    live_digest = _descriptor_digest(desc_path)
    if live_digest != digest:
        return REASON_DESCRIPTOR_CHANGED

    try:
        live = compute_image_identity(path=png_path)
    except Exception:
        return REASON_CANDIDATE_NO_LONGER_ELIGIBLE
    if live.get("content_sha256") != candidate.get("content_sha256"):
        return REASON_CANDIDATE_IDENTITY_CHANGED
    if live.get("pixel_sha256") != candidate.get("pixel_sha256"):
        return REASON_CANDIDATE_IDENTITY_CHANGED
    if live.get("size_bytes") != candidate.get("size_bytes"):
        return REASON_CANDIDATE_IDENTITY_CHANGED

    if reclamation_exclusion_reason(rec) is not None:
        return REASON_CANDIDATE_NO_LONGER_ELIGIBLE
    if not _identity_matches(candidate, rec):
        return REASON_CANDIDATE_IDENTITY_CHANGED

    try:
        resolved = resolve_derived_image_for_read(
            dossier_id=str(candidate.get("dossier_id") or ""),
            transcription_id=str(candidate.get("transcription_id") or ""),
            workspace_id=str(candidate.get("workspace_id") or ""),
            ref_id=str(candidate.get("ref_id") or ""),
        )
    except DerivedImageResolutionError:
        return REASON_CANDIDATE_NO_LONGER_ELIGIBLE
    if resolved.representation_kind != "stored_bytes":
        return REASON_CANDIDATE_NO_LONGER_ELIGIBLE
    if resolved.content_identity_posture != "stored_bytes_verified":
        return REASON_CANDIDATE_NO_LONGER_ELIGIBLE
    if resolved.content_sha256 != candidate.get("content_sha256"):
        return REASON_CANDIDATE_IDENTITY_CHANGED
    if resolved.pixel_sha256 != candidate.get("pixel_sha256"):
        return REASON_CANDIDATE_IDENTITY_CHANGED

    # Fresh recipe execution: prove reconstruction still matches before unlink.
    recipe_pixel = _fresh_recipe_pixel_sha256(candidate, desc_path)
    if recipe_pixel is None:
        return REASON_CANDIDATE_NO_LONGER_ELIGIBLE
    if recipe_pixel != candidate.get("pixel_sha256"):
        return REASON_CANDIDATE_IDENTITY_CHANGED
    return None


def _post_delete_validate(candidate: dict[str, Any], desc_path: Path, png_path: Path) -> str | None:
    """Validate after unlink. Caller must already confirm the PNG entry is absent."""
    digest = _descriptor_digest(desc_path)
    if digest != candidate.get("descriptor_bytes_digest"):
        return REASON_DESCRIPTOR_CHANGED
    try:
        resolved = resolve_derived_image_for_read(
            dossier_id=str(candidate.get("dossier_id") or ""),
            transcription_id=str(candidate.get("transcription_id") or ""),
            workspace_id=str(candidate.get("workspace_id") or ""),
            ref_id=str(candidate.get("ref_id") or ""),
        )
    except DerivedImageResolutionError:
        return REASON_POST_DELETE_RECONSTRUCTION_FAILED
    if resolved.representation_kind != "reconstructed_recipe":
        return REASON_POST_DELETE_RECONSTRUCTION_FAILED
    if resolved.pixel_sha256 != candidate.get("pixel_sha256"):
        return REASON_POST_DELETE_RECONSTRUCTION_FAILED
    return None


def apply_derived_image_reclamation(
    *,
    dossier_id: str,
    workspace_id: str,
    transcription_id: str | None = None,
    apply: bool = False,
    max_deletions: int = 100,
    quiescence_fn: QuiescenceFn | None = None,
    run_id: str | None = None,
    delete_fn: DeleteFn | None = None,
) -> dict[str, Any]:
    """Plan or apply PNG cache reclamation for one exact dossier/workspace scope."""
    if type(apply) is not bool:
        return _empty_result(
            apply=False,
            run_id=run_id if type(run_id) is str else None,
            dossier_id=dossier_id if type(dossier_id) is str else None,
            transcription_id=transcription_id if type(transcription_id) is str else None,
            workspace_id=workspace_id if type(workspace_id) is str else None,
            status="refused",
            reason_code=REASON_APPLY_INVALID_TYPE,
        )

    scope_type_err = _validate_apply_scope_types(
        dossier_id=dossier_id,
        workspace_id=workspace_id,
        transcription_id=transcription_id,
        run_id=run_id,
    )
    if scope_type_err:
        return _empty_result(
            apply=apply,
            run_id=run_id if type(run_id) is str else None,
            dossier_id=dossier_id if type(dossier_id) is str else None,
            transcription_id=transcription_id if type(transcription_id) is str else None,
            workspace_id=workspace_id if type(workspace_id) is str else None,
            status="refused",
            reason_code=scope_type_err,
        )

    base = _empty_result(
        apply=apply,
        run_id=run_id,
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        status="planned",
    )

    budget_err = _validate_max_deletions(max_deletions)
    if budget_err:
        base["status"] = "refused"
        base["reason_code"] = budget_err
        return base

    try:
        validate_derived_image_storage_audit_scope(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            all_dossiers=False,
        )
    except StorageAuditScopeError as exc:
        base["status"] = "refused"
        base["reason_code"] = exc.code
        return base

    if apply and quiescence_fn is None:
        base["status"] = "refused"
        base["reason_code"] = REASON_QUIESCENCE_CALLBACK_REQUIRED
        return base

    if apply:
        q_err = _evaluate_quiescence(quiescence_fn)  # type: ignore[arg-type]
        if q_err is not None:
            base["status"] = "refused"
            base["reason_code"] = q_err
            return base

    records, _diagnostics = collect_derived_image_storage_records(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        all_dossiers=False,
    )
    eligible = collect_reclamation_candidates_from_records(
        records,
        dossier_id=dossier_id,
        workspace_id=workspace_id,
        transcription_id=transcription_id,
    )
    eligible_count = len(eligible)
    eligible_bytes = sum(int(c.get("size_bytes") or 0) for c in eligible)
    selected = eligible[:max_deletions]
    selected_count = len(selected)
    not_selected_count = max(0, eligible_count - selected_count)

    base["eligible_count"] = eligible_count
    base["eligible_bytes"] = eligible_bytes
    base["selected_count"] = selected_count
    base["not_selected_count"] = not_selected_count

    if not apply:
        artifacts = [
            _artifact_row(
                ref_id=str(c["ref_id"]),
                status="would_delete",
                size_bytes=int(c.get("size_bytes") or 0),
                relative_image_path=c.get("relative_image_path"),
                relative_descriptor_path=c.get("relative_descriptor_path"),
                reclamation_posture="candidate_pending_quiescence",
            )
            for c in selected
        ]
        omitted = max(0, len(artifacts) - MAX_ARTIFACT_ROWS)
        base["status"] = "planned"
        base["artifacts"] = artifacts[:MAX_ARTIFACT_ROWS]
        base["artifacts_omitted_count"] = omitted
        return base

    q_err = _evaluate_quiescence(quiescence_fn)  # type: ignore[arg-type]
    if q_err is not None:
        base["status"] = "refused"
        base["reason_code"] = q_err
        return base

    unlink = delete_fn or (lambda path: path.unlink())
    records_map = _records_by_coords(records)
    artifacts: list[dict[str, Any]] = []
    deleted_count = 0
    bytes_reclaimed = 0
    skipped_count = 0
    aborted_count = 0
    stopped = False
    post_delete_failed = False

    for candidate in selected:
        ref_id = str(candidate.get("ref_id") or "")
        q_err = _evaluate_quiescence(quiescence_fn)  # type: ignore[arg-type]
        if q_err is not None:
            aborted_count += 1
            artifacts.append(
                _artifact_row(ref_id=ref_id, status="aborted", reason_code=q_err)
            )
            stopped = True
            break

        key = _record_key_from_candidate(candidate)
        rec = records_map.get(key) if key is not None else None
        if rec is None and key is not None:
            records, _ = collect_derived_image_storage_records(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_id=workspace_id,
                all_dossiers=False,
            )
            records_map = _records_by_coords(records)
            rec = records_map.get(key)

        png_path = _mechanical_png_path(candidate)
        if rec is None or png_path is None or key is None:
            skipped_count += 1
            artifacts.append(
                _artifact_row(
                    ref_id=ref_id,
                    status="skipped",
                    reason_code=REASON_CANDIDATE_NO_LONGER_ELIGIBLE,
                )
            )
            continue

        pre_err = _pre_delete_validate(candidate, rec, png_path)
        if pre_err:
            skipped_count += 1
            artifacts.append(
                _artifact_row(ref_id=ref_id, status="skipped", reason_code=pre_err)
            )
            continue

        desc_path = rec.get("_abs_descriptor_path")
        assert isinstance(desc_path, Path)
        try:
            size_bytes = int(png_path.stat().st_size)
        except OSError:
            skipped_count += 1
            artifacts.append(
                _artifact_row(
                    ref_id=ref_id,
                    status="skipped",
                    reason_code=REASON_CANDIDATE_PATH_UNSAFE,
                )
            )
            continue

        try:
            unlink(png_path)
        except OSError:
            skipped_count += 1
            artifacts.append(
                _artifact_row(
                    ref_id=ref_id,
                    status="skipped",
                    reason_code=REASON_CANDIDATE_DELETE_FAILED,
                )
            )
            continue

        if os.path.lexists(png_path):
            skipped_count += 1
            artifacts.append(
                _artifact_row(
                    ref_id=ref_id,
                    status="skipped",
                    reason_code=REASON_CANDIDATE_DELETE_VERIFICATION_FAILED,
                )
            )
            continue

        # Unlink verified: physical bytes are gone — count them before post-delete checks.
        deleted_count += 1
        bytes_reclaimed += size_bytes

        post_err = _post_delete_validate(candidate, desc_path, png_path)
        if post_err:
            artifacts.append(
                _artifact_row(
                    ref_id=ref_id,
                    status="deleted_reconstruction_failed",
                    reason_code=post_err,
                    size_bytes=size_bytes,
                    relative_image_path=candidate.get("relative_image_path"),
                    relative_descriptor_path=candidate.get("relative_descriptor_path"),
                )
            )
            post_delete_failed = True
            stopped = True
            break

        artifacts.append(
            _artifact_row(
                ref_id=ref_id,
                status="deleted",
                size_bytes=size_bytes,
                relative_image_path=candidate.get("relative_image_path"),
                relative_descriptor_path=candidate.get("relative_descriptor_path"),
            )
        )

    omitted = max(0, len(artifacts) - MAX_ARTIFACT_ROWS)
    base["artifacts"] = artifacts[:MAX_ARTIFACT_ROWS]
    base["artifacts_omitted_count"] = omitted
    base["deleted_count"] = deleted_count
    base["bytes_reclaimed"] = bytes_reclaimed
    base["skipped_count"] = skipped_count
    base["aborted_count"] = aborted_count

    if post_delete_failed:
        base["status"] = "partially_applied"
        base["reason_code"] = REASON_POST_DELETE_RECONSTRUCTION_FAILED
    elif stopped:
        base["status"] = "partially_applied" if deleted_count else "refused"
    elif deleted_count == selected_count and selected_count > 0:
        base["status"] = "applied"
    elif deleted_count > 0:
        base["status"] = "partially_applied"
    else:
        base["status"] = "applied" if selected_count == 0 else "partially_applied"
    return base


__all__ = [
    "MAX_ARTIFACT_ROWS",
    "REASON_APPLY_INVALID_TYPE",
    "REASON_CANDIDATE_DELETE_FAILED",
    "REASON_CANDIDATE_DELETE_VERIFICATION_FAILED",
    "REASON_CANDIDATE_IDENTITY_CHANGED",
    "REASON_CANDIDATE_IS_SYMLINK",
    "REASON_CANDIDATE_NO_LONGER_ELIGIBLE",
    "REASON_CANDIDATE_PATH_UNSAFE",
    "REASON_DELETION_BUDGET_INVALID",
    "REASON_DESCRIPTOR_CHANGED",
    "REASON_POST_DELETE_RECONSTRUCTION_FAILED",
    "REASON_QUIESCENCE_CALLBACK_REQUIRED",
    "REASON_RUN_ACTIVITY_UNKNOWN",
    "REASON_RUN_NOT_QUIESCENT",
    "REASON_RUN_SCOPE_UNKNOWN",
    "SCHEMA_VERSION",
    "apply_derived_image_reclamation",
]
