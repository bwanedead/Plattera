"""Atomic plain and gzip I/O for kernel resume snapshots.

Storage transport only: serialization encoding, suffix-aware loading, and
stable failure codes. Snapshot schema build/parse stays in ``resume_snapshot``.
"""

from __future__ import annotations

import gzip
import json
import os
import tempfile
import zlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

GZIP_COMPRESSLEVEL = 6
_COMPACT_SEPARATORS = (",", ":")

# Load failure codes (stable).
RESUME_SNAPSHOT_PATH_UNREADABLE = "resume_snapshot_path_unreadable"
RESUME_SNAPSHOT_JSON_INVALID = "resume_snapshot_json_invalid"
RESUME_SNAPSHOT_ROOT_NOT_OBJECT = "resume_snapshot_root_not_object"
RESUME_SNAPSHOT_GZIP_INVALID = "resume_snapshot_gzip_invalid"


def dumps_pretty_latest_json(snapshot: Mapping[str, Any]) -> str:
    """Pretty JSON for ``kernel_resume.json`` (unchanged latest-resume shape)."""
    return json.dumps(dict(snapshot), ensure_ascii=False, indent=2, sort_keys=True)


def dumps_compact_checkpoint_bytes(snapshot: Mapping[str, Any]) -> bytes:
    """UTF-8 compact JSON bytes for historical compressed checkpoints."""
    text = json.dumps(
        dict(snapshot),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=_COMPACT_SEPARATORS,
    )
    return text.encode("utf-8")


def gzip_compress_deterministic(raw: bytes) -> bytes:
    """gzip level 6 with ``mtime=0`` for byte-stable historical checkpoints."""
    return gzip.compress(raw, compresslevel=GZIP_COMPRESSLEVEL, mtime=0)


def write_plain_json_atomic(path: Path, *, text: str) -> None:
    """Atomically write UTF-8 plain JSON (temp file + ``os.replace``)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_resume_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_gzip_json_atomic(path: Path, *, snapshot: Mapping[str, Any]) -> None:
    """Atomically write a deterministic ``.json.gz`` historical checkpoint.

    Does not write an intermediate uncompressed historical file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = gzip_compress_deterministic(dumps_compact_checkpoint_bytes(snapshot))
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_resume_", suffix=".json.gz")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def path_looks_like_gzip_checkpoint(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(".json.gz") or path.suffix.lower() == ".gz"


def load_kernel_resume_snapshot_from_path(
    path: Path | str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Read a plain or gzip resume snapshot; return ``(parsed_dict, error_reason_code)``.

    Suffix-aware: ``.json.gz`` / ``.gz`` paths are never interpreted as plain JSON.
    """
    p = Path(path)
    if path_looks_like_gzip_checkpoint(p):
        return _load_gzip_snapshot(p)
    return _load_plain_snapshot(p)


def _load_plain_snapshot(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, RESUME_SNAPSHOT_PATH_UNREADABLE
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        return None, RESUME_SNAPSHOT_JSON_INVALID
    if not isinstance(doc, dict):
        return None, RESUME_SNAPSHOT_ROOT_NOT_OBJECT
    return doc, None


def _load_gzip_snapshot(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with path.open("rb") as handle:
            compressed = handle.read()
    except OSError:
        return None, RESUME_SNAPSHOT_PATH_UNREADABLE
    try:
        raw = gzip.decompress(compressed)
    except (OSError, EOFError, gzip.BadGzipFile, zlib.error):
        return None, RESUME_SNAPSHOT_GZIP_INVALID
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, RESUME_SNAPSHOT_GZIP_INVALID
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        return None, RESUME_SNAPSHOT_JSON_INVALID
    if not isinstance(doc, dict):
        return None, RESUME_SNAPSHOT_ROOT_NOT_OBJECT
    return doc, None
