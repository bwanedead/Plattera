"""Per-checkpoint mutation transaction for legacy resume checkpoint compression.

Staging write → verify → quiescence recheck → no-clobber promote → legacy delete.
Scan/planning/accounting lives in ``resume_checkpoint_compress``.
"""

from __future__ import annotations

import errno
import os
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from harness.runtime.memory.resume_snapshot import parse_kernel_resume_snapshot

# Stable reason codes for skipped / refused checkpoint rows.
REASON_PATH_IS_SYMLINK = "path_is_symlink"
REASON_PATH_NOT_REGULAR_FILE = "path_not_regular_file"
REASON_CHECKPOINT_TURN_MISMATCH = "checkpoint_turn_mismatch"
REASON_CANONICAL_CONFLICT = "canonical_document_conflict"
REASON_CANONICAL_SYMLINK = "canonical_path_is_symlink"
REASON_WRITE_FAILED = "canonical_write_failed"
REASON_VERIFICATION_FAILED = "canonical_verification_failed"
REASON_DELETE_FAILED = "legacy_delete_failed"
REASON_CANONICAL_JSON_NOT_SERIALIZABLE = "canonical_json_not_serializable"
REASON_STAGING_CLEANUP_FAILED = "staging_cleanup_failed"
REASON_PROMOTE_FAILED = "canonical_promote_failed"
REASON_RUN_NOT_QUIESCENT = "run_not_quiescent"
REASON_RUN_ACTIVITY_UNKNOWN = "run_activity_unknown"

WriteGzipFn = Callable[[Path, Mapping[str, Any]], None]
DeleteFn = Callable[[Path], None]
LoadFn = Callable[[Path | str], tuple[dict[str, Any] | None, str | None]]
QuiescenceFn = Callable[[], str | None]
StagingPathFn = Callable[[Path], Path]
CheckpointRowFn = Callable[..., dict[str, Any]]


def new_unique_staging_path(canonical: Path) -> Path:
    """Per-attempt staging identity so concurrent migrations cannot share or delete each other."""
    token = uuid.uuid4().hex
    name = canonical.name
    if name.endswith(".json.gz"):
        base = name[: -len(".json.gz")]
        return canonical.with_name(f"{base}.{token}.staging.json.gz")
    return canonical.with_name(f"{canonical.stem}.{token}.staging{canonical.suffix}")


def path_lexists(path: Path) -> bool:
    """True if a directory entry exists, including broken symlinks."""
    return os.path.lexists(path)


def file_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def regular_non_symlink_file(path: Path) -> str | None:
    if path.is_symlink():
        return REASON_PATH_IS_SYMLINK
    if not path.is_file():
        return REASON_PATH_NOT_REGULAR_FILE
    return None


def best_effort_remove_path(path: Path, *, delete_fn: DeleteFn) -> bool:
    """Remove a path entry. Success requires the entry is gone, including broken symlinks."""
    try:
        if path_lexists(path):
            delete_fn(path)
        return not path_lexists(path)
    except Exception:
        return not path_lexists(path)


def verify_loaded_snapshot(
    *,
    doc: dict[str, Any],
    reloaded: dict[str, Any] | None,
    load_err: str | None,
    turn: int,
) -> str | None:
    if load_err or reloaded is None or reloaded != doc:
        return REASON_VERIFICATION_FAILED
    _, _, parse_err = parse_kernel_resume_snapshot(reloaded)
    if parse_err:
        return REASON_VERIFICATION_FAILED
    if reloaded.get("next_iteration") != turn + 1:
        return REASON_VERIFICATION_FAILED
    return None


def _is_exist_error(exc: OSError) -> bool:
    if isinstance(exc, FileExistsError):
        return True
    if exc.errno in {errno.EEXIST, getattr(errno, "EISDIR", -1)}:
        return True
    if getattr(exc, "winerror", None) == 183:
        return True
    return False


def promote_staging_no_clobber(staging: Path, canonical: Path) -> str | None:
    """Atomically create ``canonical`` from ``staging`` without replacing an existing file."""
    try:
        os.link(staging, canonical)
    except OSError as exc:
        if _is_exist_error(exc):
            return REASON_CANONICAL_CONFLICT
        return REASON_PROMOTE_FAILED
    return None


def cleanup_staging_or_row(
    *,
    staging: Path,
    delete_fn: DeleteFn,
    row_fn: CheckpointRowFn,
    turn: int,
    legacy_bytes: int,
    primary_reason: str,
) -> dict[str, Any]:
    if not best_effort_remove_path(staging, delete_fn=delete_fn):
        return row_fn(
            turn=turn,
            status="skipped",
            reason_code=REASON_STAGING_CLEANUP_FAILED,
            legacy_bytes=legacy_bytes,
            canonical_bytes=0,
            staging_path=str(staging),
        )
    return row_fn(
        turn=turn,
        status="skipped",
        reason_code=primary_reason,
        legacy_bytes=legacy_bytes,
        canonical_bytes=0,
    )


def migrate_legacy_only_checkpoint(
    *,
    turn: int,
    legacy: Path,
    canonical: Path,
    doc: dict[str, Any],
    apply: bool,
    estimated_canonical_bytes: int,
    write_gzip_fn: WriteGzipFn,
    delete_fn: DeleteFn,
    load_fn: LoadFn,
    quiescence_fn: QuiescenceFn,
    staging_path_fn: StagingPathFn,
    row_fn: CheckpointRowFn,
    handle_both_present_fn: Callable[..., tuple[dict[str, Any], int, int]],
) -> tuple[dict[str, Any], int, int]:
    """Migrate when canonical is absent. Returns (row, bytes_reclaimed, legacy_bytes_removed)."""
    legacy_bytes = file_size(legacy)

    if not apply:
        return (
            row_fn(
                turn=turn,
                status="would_migrate",
                reason_code=None,
                legacy_bytes=legacy_bytes,
                canonical_bytes=estimated_canonical_bytes,
            ),
            0,
            0,
        )

    staging = staging_path_fn(canonical)

    try:
        write_gzip_fn(staging, doc)
    except Exception:
        if path_lexists(staging):
            if not best_effort_remove_path(staging, delete_fn=delete_fn):
                return (
                    row_fn(
                        turn=turn,
                        status="skipped",
                        reason_code=REASON_STAGING_CLEANUP_FAILED,
                        legacy_bytes=legacy_bytes,
                        canonical_bytes=0,
                        staging_path=str(staging),
                    ),
                    0,
                    0,
                )
        return (
            row_fn(
                turn=turn,
                status="skipped",
                reason_code=REASON_WRITE_FAILED,
                legacy_bytes=legacy_bytes,
                canonical_bytes=0,
            ),
            0,
            0,
        )

    reloaded, load_err = load_fn(staging)
    verify_err = verify_loaded_snapshot(doc=doc, reloaded=reloaded, load_err=load_err, turn=turn)
    if verify_err is not None:
        return (
            cleanup_staging_or_row(
                staging=staging,
                delete_fn=delete_fn,
                row_fn=row_fn,
                turn=turn,
                legacy_bytes=legacy_bytes,
                primary_reason=verify_err,
            ),
            0,
            0,
        )

    q_err = quiescence_fn()
    if q_err is not None:
        return (
            cleanup_staging_or_row(
                staging=staging,
                delete_fn=delete_fn,
                row_fn=row_fn,
                turn=turn,
                legacy_bytes=legacy_bytes,
                primary_reason=q_err,
            ),
            0,
            0,
        )

    promote_err = promote_staging_no_clobber(staging, canonical)
    if promote_err == REASON_CANONICAL_CONFLICT:
        if not best_effort_remove_path(staging, delete_fn=delete_fn):
            return (
                row_fn(
                    turn=turn,
                    status="skipped",
                    reason_code=REASON_STAGING_CLEANUP_FAILED,
                    legacy_bytes=legacy_bytes,
                    canonical_bytes=file_size(canonical) if path_lexists(canonical) else 0,
                    staging_path=str(staging),
                ),
                0,
                0,
            )
        if path_lexists(canonical):
            return handle_both_present_fn(
                turn=turn,
                legacy=legacy,
                canonical=canonical,
                legacy_doc=doc,
                apply=True,
            )
        return (
            row_fn(
                turn=turn,
                status="skipped",
                reason_code=REASON_PROMOTE_FAILED,
                legacy_bytes=legacy_bytes,
                canonical_bytes=0,
            ),
            0,
            0,
        )
    if promote_err is not None:
        return (
            cleanup_staging_or_row(
                staging=staging,
                delete_fn=delete_fn,
                row_fn=row_fn,
                turn=turn,
                legacy_bytes=legacy_bytes,
                primary_reason=promote_err,
            ),
            0,
            0,
        )

    try:
        if path_lexists(staging):
            os.unlink(staging)
    except OSError:
        if path_lexists(staging):
            return (
                row_fn(
                    turn=turn,
                    status="skipped",
                    reason_code=REASON_STAGING_CLEANUP_FAILED,
                    legacy_bytes=legacy_bytes,
                    canonical_bytes=file_size(canonical),
                    staging_path=str(staging),
                ),
                0,
                0,
            )

    canonical_bytes = file_size(canonical)
    q_err = quiescence_fn()
    if q_err is not None:
        return (
            row_fn(
                turn=turn,
                status="skipped",
                reason_code=q_err,
                legacy_bytes=legacy_bytes,
                canonical_bytes=canonical_bytes,
            ),
            0,
            0,
        )

    try:
        delete_fn(legacy)
    except Exception:
        return (
            row_fn(
                turn=turn,
                status="skipped",
                reason_code=REASON_DELETE_FAILED,
                legacy_bytes=legacy_bytes,
                canonical_bytes=canonical_bytes,
            ),
            0,
            0,
        )

    net = max(0, legacy_bytes - canonical_bytes)
    return (
        row_fn(
            turn=turn,
            status="migrated",
            reason_code=None,
            legacy_bytes=legacy_bytes,
            canonical_bytes=canonical_bytes,
        ),
        net,
        legacy_bytes,
    )


def remove_equivalent_legacy_checkpoint(
    *,
    turn: int,
    legacy: Path,
    canonical: Path,
    legacy_doc: dict[str, Any],
    apply: bool,
    delete_fn: DeleteFn,
    load_fn: LoadFn,
    quiescence_fn: QuiescenceFn,
    row_fn: CheckpointRowFn,
) -> tuple[dict[str, Any], int, int]:
    """When canonical exists: never overwrite; remove legacy only if documents match."""
    legacy_bytes = file_size(legacy)
    unsafe = regular_non_symlink_file(canonical)
    if unsafe == REASON_PATH_IS_SYMLINK:
        unsafe = REASON_CANONICAL_SYMLINK
    if unsafe == REASON_CANONICAL_SYMLINK:
        return (
            row_fn(
                turn=turn,
                status="skipped",
                reason_code=REASON_CANONICAL_SYMLINK,
                legacy_bytes=legacy_bytes,
                canonical_bytes=0,
            ),
            0,
            0,
        )
    if unsafe is not None:
        return (
            row_fn(
                turn=turn,
                status="skipped",
                reason_code=unsafe,
                legacy_bytes=legacy_bytes,
                canonical_bytes=0,
            ),
            0,
            0,
        )

    canonical_bytes = file_size(canonical)
    canon_doc, load_err = load_fn(canonical)
    if load_err or canon_doc is None:
        return (
            row_fn(
                turn=turn,
                status="skipped",
                reason_code=load_err or REASON_PATH_NOT_REGULAR_FILE,
                legacy_bytes=legacy_bytes,
                canonical_bytes=canonical_bytes,
            ),
            0,
            0,
        )
    _, _, parse_err = parse_kernel_resume_snapshot(canon_doc)
    if parse_err:
        return (
            row_fn(
                turn=turn,
                status="skipped",
                reason_code=parse_err,
                legacy_bytes=legacy_bytes,
                canonical_bytes=canonical_bytes,
            ),
            0,
            0,
        )
    if canon_doc != legacy_doc:
        return (
            row_fn(
                turn=turn,
                status="skipped",
                reason_code=REASON_CANONICAL_CONFLICT,
                legacy_bytes=legacy_bytes,
                canonical_bytes=canonical_bytes,
            ),
            0,
            0,
        )

    if not apply:
        return (
            row_fn(
                turn=turn,
                status="would_remove_equivalent",
                reason_code=None,
                legacy_bytes=legacy_bytes,
                canonical_bytes=canonical_bytes,
            ),
            0,
            0,
        )

    q_err = quiescence_fn()
    if q_err is not None:
        return (
            row_fn(
                turn=turn,
                status="skipped",
                reason_code=q_err,
                legacy_bytes=legacy_bytes,
                canonical_bytes=canonical_bytes,
            ),
            0,
            0,
        )

    try:
        delete_fn(legacy)
    except Exception:
        return (
            row_fn(
                turn=turn,
                status="skipped",
                reason_code=REASON_DELETE_FAILED,
                legacy_bytes=legacy_bytes,
                canonical_bytes=canonical_bytes,
            ),
            0,
            0,
        )

    return (
        row_fn(
            turn=turn,
            status="removed_equivalent",
            reason_code=None,
            legacy_bytes=legacy_bytes,
            canonical_bytes=canonical_bytes,
        ),
        legacy_bytes,
        legacy_bytes,
    )
