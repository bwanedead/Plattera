"""Validation-first migration of legacy ``turn_NNNN.json`` resume checkpoints to ``.json.gz``.

Mechanical storage reclaim only: does not alter snapshot semantics, active runs,
``kernel_resume.json``, audit artifacts, or retention policy.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from harness.runtime.memory.resume_snapshot import parse_kernel_resume_snapshot
from harness.runtime.memory.resume_snapshot_storage import (
    dumps_compact_checkpoint_bytes,
    gzip_compress_deterministic,
    load_kernel_resume_snapshot_from_path,
    write_gzip_json_atomic,
)

from ._process_util import is_pid_alive
from .resume_checkpoint_migrate import (
    REASON_CANONICAL_CONFLICT,
    REASON_CANONICAL_JSON_NOT_SERIALIZABLE,
    REASON_CANONICAL_SYMLINK,
    REASON_CHECKPOINT_TURN_MISMATCH,
    REASON_DELETE_FAILED,
    REASON_PATH_IS_SYMLINK,
    REASON_PATH_NOT_REGULAR_FILE,
    REASON_PROMOTE_FAILED,
    REASON_RUN_ACTIVITY_UNKNOWN,
    REASON_RUN_NOT_QUIESCENT,
    REASON_STAGING_CLEANUP_FAILED,
    REASON_VERIFICATION_FAILED,
    REASON_WRITE_FAILED,
    DeleteFn,
    LoadFn,
    QuiescenceFn,
    StagingPathFn,
    WriteGzipFn,
    file_size,
    migrate_legacy_only_checkpoint,
    new_unique_staging_path,
    path_lexists,
    regular_non_symlink_file,
    remove_equivalent_legacy_checkpoint,
)
from .resume_paths import (
    TURN_CHECKPOINTS_DIRNAME,
    turn_checkpoint_canonical_path,
)
from .run_layout import RunLayoutError, resolve_run_directory
from .run_state import read_state

LEGACY_TURN_FILENAME_RE = re.compile(r"^turn_([0-9]{4})\.json$")
MAX_CHECKPOINT_DETAIL_ROWS = 64
REASON_CHECKPOINTS_DIR_UNSAFE = "resume_checkpoints_dir_unsafe"

# Re-export stable reason codes for CLI/tests.
__all__ = [
    "REASON_CANONICAL_CONFLICT",
    "REASON_CANONICAL_JSON_NOT_SERIALIZABLE",
    "REASON_CANONICAL_SYMLINK",
    "REASON_CHECKPOINT_TURN_MISMATCH",
    "REASON_CHECKPOINTS_DIR_UNSAFE",
    "REASON_DELETE_FAILED",
    "REASON_PATH_IS_SYMLINK",
    "REASON_PROMOTE_FAILED",
    "REASON_RUN_ACTIVITY_UNKNOWN",
    "REASON_RUN_NOT_QUIESCENT",
    "REASON_STAGING_CLEANUP_FAILED",
    "REASON_VERIFICATION_FAILED",
    "REASON_WRITE_FAILED",
    "compress_run_legacy_checkpoints",
    "estimate_canonical_bytes",
    "try_estimate_canonical_bytes",
]


def estimate_canonical_bytes(snapshot: Mapping[str, Any]) -> int:
    return len(gzip_compress_deterministic(dumps_compact_checkpoint_bytes(snapshot)))


def try_estimate_canonical_bytes(snapshot: Mapping[str, Any]) -> tuple[int | None, str | None]:
    """Return ``(byte_count, None)`` or ``(None, reason_code)`` if not strict-JSON serializable."""
    try:
        return estimate_canonical_bytes(snapshot), None
    except (ValueError, TypeError, OverflowError):
        return None, REASON_CANONICAL_JSON_NOT_SERIALIZABLE


def assess_run_quiescence(run_id: str) -> str | None:
    """Return ``None`` when the run is safe to mutate; else a stable refuse reason."""
    state = read_state(run_id)
    if state is None:
        return REASON_RUN_ACTIVITY_UNKNOWN
    try:
        pid = int(state.pid)
    except (TypeError, ValueError):
        return REASON_RUN_ACTIVITY_UNKNOWN
    if pid <= 0:
        return None
    try:
        alive = is_pid_alive(pid)
    except Exception:
        return REASON_RUN_ACTIVITY_UNKNOWN
    if alive:
        return REASON_RUN_NOT_QUIESCENT
    return None


def _empty_totals(*, run_id: str, apply: bool, status: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": status,
        "run_id": run_id,
        "apply": bool(apply),
        "legacy_checkpoint_count": 0,
        "migrated_count": 0,
        "equivalent_legacy_removed_count": 0,
        "skipped_count": 0,
        "legacy_bytes": 0,
        "canonical_bytes": 0,
        "bytes_reclaimed": 0,
        "legacy_bytes_removed": 0,
        "checkpoints": [],
        "checkpoints_omitted_count": 0,
    }
    out.update(extra)
    return out


def _refuse_run(*, run_id: str, apply: bool, reason_code: str) -> dict[str, Any]:
    return _empty_totals(run_id=run_id, apply=apply, status="refused", reason_code=reason_code)


def _row(
    *,
    turn: int,
    status: str,
    reason_code: str | None,
    legacy_bytes: int,
    canonical_bytes: int,
    staging_path: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "turn": turn,
        "status": status,
        "reason_code": reason_code,
        "legacy_bytes": int(legacy_bytes),
        "canonical_bytes": int(canonical_bytes),
    }
    if staging_path is not None:
        row["staging_path"] = staging_path
    return row


def _load_and_parse_legacy(
    legacy: Path,
    *,
    turn: int,
    load_fn: LoadFn,
) -> tuple[dict[str, Any] | None, str | None]:
    doc, load_err = load_fn(legacy)
    if load_err or doc is None:
        return None, load_err or REASON_PATH_NOT_REGULAR_FILE
    _, _, parse_err = parse_kernel_resume_snapshot(doc)
    if parse_err:
        return None, parse_err
    if doc.get("next_iteration") != turn + 1:
        return None, REASON_CHECKPOINT_TURN_MISMATCH
    return doc, None


def compress_run_legacy_checkpoints(
    *,
    run_id: str,
    apply: bool = False,
    write_gzip_fn: WriteGzipFn | None = None,
    delete_fn: DeleteFn | None = None,
    load_fn: LoadFn | None = None,
    quiescence_fn: QuiescenceFn | None = None,
    staging_path_fn: StagingPathFn | None = None,
) -> dict[str, Any]:
    """Plan or apply legacy→canonical resume-checkpoint compression for one run."""
    rid = str(run_id or "").strip()
    if not rid:
        return _refuse_run(run_id=rid, apply=apply, reason_code="run_id_required")

    try:
        resolved = resolve_run_directory(rid)
    except RunLayoutError as exc:
        return _refuse_run(run_id=rid, apply=apply, reason_code=exc.code)

    check_quiescence: QuiescenceFn = quiescence_fn or (lambda: assess_run_quiescence(rid))
    if apply:
        q_err = check_quiescence()
        if q_err is not None:
            return _refuse_run(run_id=rid, apply=apply, reason_code=q_err)

    run_path = resolved.path
    checkpoints_dir = run_path / TURN_CHECKPOINTS_DIRNAME
    write_gzip = write_gzip_fn or (lambda path, snapshot: write_gzip_json_atomic(path, snapshot=snapshot))
    delete_path = delete_fn or (lambda path: path.unlink())
    load_snapshot = load_fn or load_kernel_resume_snapshot_from_path
    make_staging = staging_path_fn or new_unique_staging_path

    if not checkpoints_dir.exists():
        return _empty_totals(
            run_id=rid,
            apply=apply,
            status="applied" if apply else "planned",
            run_dir=str(run_path),
            run_collection=resolved.run_collection,
        )

    if checkpoints_dir.is_symlink() or not checkpoints_dir.is_dir():
        return _refuse_run(run_id=rid, apply=apply, reason_code=REASON_CHECKPOINTS_DIR_UNSAFE)

    try:
        names = sorted(os.listdir(checkpoints_dir))
    except OSError:
        return _refuse_run(run_id=rid, apply=apply, reason_code=REASON_CHECKPOINTS_DIR_UNSAFE)

    rows: list[dict[str, Any]] = []
    legacy_checkpoint_count = 0
    migrated_count = 0
    equivalent_removed = 0
    skipped_count = 0
    legacy_bytes_total = 0
    canonical_bytes_total = 0
    bytes_reclaimed = 0
    legacy_bytes_removed = 0
    any_failure = False

    def _handle_both_present(
        *,
        turn: int,
        legacy: Path,
        canonical: Path,
        legacy_doc: dict[str, Any],
        apply: bool,
    ) -> tuple[dict[str, Any], int, int]:
        return remove_equivalent_legacy_checkpoint(
            turn=turn,
            legacy=legacy,
            canonical=canonical,
            legacy_doc=legacy_doc,
            apply=apply,
            delete_fn=delete_path,
            load_fn=load_snapshot,
            quiescence_fn=check_quiescence,
            row_fn=_row,
        )

    for name in names:
        match = LEGACY_TURN_FILENAME_RE.fullmatch(name)
        if match is None:
            continue
        turn = int(match.group(1))
        if turn < 1:
            continue
        legacy_checkpoint_count += 1
        legacy = checkpoints_dir / name
        reclaimed = 0
        removed = 0

        unsafe = regular_non_symlink_file(legacy)
        if unsafe is not None:
            row = _row(
                turn=turn,
                status="skipped",
                reason_code=unsafe,
                legacy_bytes=file_size(legacy) if path_lexists(legacy) else 0,
                canonical_bytes=0,
            )
        else:
            doc, err = _load_and_parse_legacy(legacy, turn=turn, load_fn=load_snapshot)
            if err or doc is None:
                row = _row(
                    turn=turn,
                    status="skipped",
                    reason_code=err,
                    legacy_bytes=file_size(legacy),
                    canonical_bytes=0,
                )
            else:
                estimated, ser_err = try_estimate_canonical_bytes(doc)
                if ser_err or estimated is None:
                    row = _row(
                        turn=turn,
                        status="skipped",
                        reason_code=ser_err or REASON_CANONICAL_JSON_NOT_SERIALIZABLE,
                        legacy_bytes=file_size(legacy),
                        canonical_bytes=0,
                    )
                else:
                    canonical = turn_checkpoint_canonical_path(run_dir=run_path, from_turn=turn)
                    if path_lexists(canonical):
                        row, reclaimed, removed = _handle_both_present(
                            turn=turn,
                            legacy=legacy,
                            canonical=canonical,
                            legacy_doc=doc,
                            apply=apply,
                        )
                    else:
                        row, reclaimed, removed = migrate_legacy_only_checkpoint(
                            turn=turn,
                            legacy=legacy,
                            canonical=canonical,
                            doc=doc,
                            apply=apply,
                            estimated_canonical_bytes=estimated,
                            write_gzip_fn=write_gzip,
                            delete_fn=delete_path,
                            load_fn=load_snapshot,
                            quiescence_fn=check_quiescence,
                            staging_path_fn=make_staging,
                            row_fn=_row,
                            handle_both_present_fn=_handle_both_present,
                        )

        rows.append(row)
        legacy_bytes_total += int(row["legacy_bytes"])
        canonical_bytes_total += int(row["canonical_bytes"])
        bytes_reclaimed += reclaimed
        legacy_bytes_removed += removed
        status = row["status"]
        if status == "migrated":
            migrated_count += 1
        elif status == "removed_equivalent":
            equivalent_removed += 1
        elif status == "skipped":
            skipped_count += 1
            any_failure = True

    if apply:
        overall = "partial" if any_failure else "applied"
    else:
        overall = "planned"

    omitted = 0
    if len(rows) > MAX_CHECKPOINT_DETAIL_ROWS:
        omitted = len(rows) - MAX_CHECKPOINT_DETAIL_ROWS
        rows = rows[:MAX_CHECKPOINT_DETAIL_ROWS]

    return {
        "status": overall,
        "run_id": rid,
        "apply": bool(apply),
        "run_dir": str(run_path),
        "run_collection": resolved.run_collection,
        "legacy_checkpoint_count": legacy_checkpoint_count,
        "migrated_count": migrated_count,
        "equivalent_legacy_removed_count": equivalent_removed,
        "skipped_count": skipped_count,
        "legacy_bytes": legacy_bytes_total,
        "canonical_bytes": canonical_bytes_total,
        "bytes_reclaimed": bytes_reclaimed,
        "legacy_bytes_removed": legacy_bytes_removed,
        "checkpoints": rows,
        "checkpoints_omitted_count": omitted,
    }
