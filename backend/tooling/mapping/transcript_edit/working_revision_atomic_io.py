"""Atomic / create-only JSON write helpers for transcript-edit working revisions."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def compact_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)


def pretty_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
    ) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_sha256_of_doc(doc: dict[str, Any]) -> str:
    return sha256_text(compact_dumps(doc))


def is_exist_error(exc: OSError) -> bool:
    if isinstance(exc, FileExistsError):
        return True
    if exc.errno in {errno.EEXIST}:
        return True
    if getattr(exc, "winerror", None) == 183:
        return True
    return False


def best_effort_unlink(path: Path) -> None:
    try:
        if os.path.lexists(path):
            path.unlink()
    except OSError:
        pass


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Staged + verified atomic JSON write (temp in same dir, fsync, os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = pretty_dumps(payload)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".tmp_te_ptr_",
        suffix=".json",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        staged = Path(tmp_path).read_text(encoding="utf-8")
        if staged != body:
            raise OSError("staged pointer bytes did not match intended body")
        os.replace(tmp_path, str(path))
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


class RevisionCoordinateExists(Exception):
    """Create-only promotion found an existing revision coordinate."""


def promote_create_only(staging: Path, final: Path) -> None:
    """Create ``final`` from ``staging`` without replacing an existing file."""
    try:
        os.link(staging, final)
        best_effort_unlink(staging)
        return
    except OSError as exc:
        if is_exist_error(exc):
            raise RevisionCoordinateExists from exc
        # Fall through to O_EXCL copy when hardlink is unavailable.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        data = staging.read_bytes()
        fd = os.open(str(final), flags)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            best_effort_unlink(final)
            raise
        best_effort_unlink(staging)
    except OSError as exc:
        if is_exist_error(exc):
            raise RevisionCoordinateExists from exc
        raise


def create_only_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write revision JSON create-only (never overwrite an existing coordinate)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = pretty_dumps(payload)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".tmp_te_rev_",
        suffix=".json",
        dir=str(path.parent),
    )
    staging = Path(tmp_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        staged = staging.read_text(encoding="utf-8")
        if staged != body:
            raise OSError("staged revision bytes did not match intended body")
        if path.exists() or os.path.lexists(path):
            raise RevisionCoordinateExists()
        promote_create_only(staging, path)
    except RevisionCoordinateExists:
        best_effort_unlink(staging)
        raise
    except Exception:
        best_effort_unlink(staging)
        raise
    finally:
        best_effort_unlink(staging)
