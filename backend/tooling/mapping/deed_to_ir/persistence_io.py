"""Shared append-only JSON persistence helpers for deed-to-IR output and preview."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .output_package_validation import (
    PublishPayloadValidationError,
    PUBLISH_PAYLOAD_VALIDATION_FAILED,
)


def resolve_workspace_key(*, workspace_id: str | None, run_id: str | None) -> str | None:
    workspace = str(workspace_id or "").strip()
    if workspace:
        return workspace
    run = str(run_id or "").strip()
    return run or None


def rollback_revision_file(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def next_revision_digits(*, revision_dir: Path) -> str:
    highest = 0
    for path in revision_dir.glob("rev_*.json"):
        stem = path.stem.replace("rev_", "")
        if len(stem) == 4 and stem.isdigit():
            highest = max(highest, int(stem))
    return f"{highest + 1:04d}"


@contextmanager
def workspace_publish_lock(revision_dir: Path) -> Iterator[None]:
    revision_dir.mkdir(parents=True, exist_ok=True)
    lock_path = revision_dir / ".publish.lock"
    handle = open(lock_path, "a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise ValueError("publication_in_progress") from exc
    try:
        yield
    finally:
        try:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix="deed_output_",
        suffix=".json",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, str(path))
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def refusal(code: str, message: str) -> dict[str, Any]:
    return {
        "executed": False,
        "refusal": {
            "reason_code": code,
            "retryable": False,
            "blocked_by_invariant": True,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {"error": {"code": code, "message": message}},
    }


def mapping_ir_lineage_mismatch_refusal(
    *,
    expected_ir_artifact_ref: str,
    actual_ir_artifact_ref: str,
) -> dict[str, Any]:
    code = "mapping_ir_lineage_mismatch"
    return {
        "executed": False,
        "reason_codes": [code],
        "refusal": {
            "reason_code": code,
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "error": {
                "code": code,
                "message": "mapping artifact was not produced from expected IR",
            },
            "expected_ir_artifact_ref": expected_ir_artifact_ref,
            "actual_ir_artifact_ref": actual_ir_artifact_ref,
            "repair_hint": (
                "Submit the expected IR for mapping, then publish the returned mapping artifact."
            ),
        },
    }


def final_package_preview_stale_refusal(
    *,
    preview_ir_artifact_ref: str,
    current_ir_artifact_ref: str,
) -> dict[str, Any]:
    code = "final_package_preview_stale"
    return {
        "executed": False,
        "reason_codes": [code],
        "refusal": {
            "reason_code": code,
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "error": {
                "code": code,
                "message": "final package preview mapping lineage is stale",
            },
            "preview_ir_artifact_ref": preview_ir_artifact_ref,
            "current_ir_artifact_ref": current_ir_artifact_ref,
            "repair_hint": "Prepare a new final package preview from the current mapping revision.",
        },
    }


def validation_failure_refusal(exc: PublishPayloadValidationError) -> dict[str, Any]:
    reason_code = exc.reason_code or PUBLISH_PAYLOAD_VALIDATION_FAILED
    validation_errors = list(exc.validation_errors)
    return {
        "executed": False,
        "reason_codes": [reason_code],
        "refusal": {
            "reason_code": reason_code,
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "error": {
                "code": PUBLISH_PAYLOAD_VALIDATION_FAILED,
                "message": "publish payload validation failed",
            },
            "validation_errors": validation_errors,
        },
    }
