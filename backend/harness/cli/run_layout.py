"""Canonical CLI run directory layout and discovery (control-plane only)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import config.paths as _paths

BY_LOOP_KIND_DIRNAME = "by_loop_kind"
LEGACY_FLAT_BUCKET = "legacy_flat"

_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")
_RUN_COLLECTION_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")

RunLayoutKind = Literal["legacy_flat", "by_loop_kind"]


class RunLayoutError(ValueError):
    """Raised when run layout resolution or allocation fails."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code or "run_layout_error")
        super().__init__(message or self.code)


@dataclass(frozen=True)
class ResolvedRunDirectory:
    run_id: str
    path: Path
    layout: RunLayoutKind
    run_collection: str | None


def cli_runs_root() -> Path:
    root = _paths.harness_cli_artifacts_root() / "cli_runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def by_loop_kind_root() -> Path:
    root = cli_runs_root() / BY_LOOP_KIND_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def normalize_run_id(run_id: str) -> str:
    text = str(run_id or "").strip()
    if not text:
        raise RunLayoutError("run_id_empty")
    if not _RUN_ID_PATTERN.fullmatch(text):
        raise RunLayoutError("run_id_unsafe")
    return text


def normalize_run_collection(run_collection: str) -> str:
    """Normalize a path-safe run-collection name (refuses blank/unsafe values)."""
    text = str(run_collection or "").strip()
    if not text:
        raise RunLayoutError("run_collection_empty")
    if not _RUN_COLLECTION_PATTERN.fullmatch(text):
        raise RunLayoutError("run_collection_unsafe")
    return text


def is_collection_directory_name(name: str) -> bool:
    text = str(name or "").strip()
    if not text or text == BY_LOOP_KIND_DIRNAME:
        return False
    return bool(_RUN_COLLECTION_PATTERN.fullmatch(text))


def allocate_run_directory(*, run_id: str, run_collection: str) -> Path:
    """Return a new namespaced run directory; reject duplicate global run IDs."""
    rid = normalize_run_id(run_id)
    collection = normalize_run_collection(run_collection)
    if find_run_directory_candidates(rid):
        raise RunLayoutError("run_id_already_exists")
    target = by_loop_kind_root() / collection / rid
    target.mkdir(parents=True, exist_ok=False)
    return target


def find_run_directory_candidates(run_id: str) -> list[ResolvedRunDirectory]:
    """Search legacy flat storage, then namespaced collections."""
    rid = normalize_run_id(run_id)
    matches: list[ResolvedRunDirectory] = []

    legacy = cli_runs_root() / rid
    if _looks_like_run_dir(legacy):
        matches.append(
            ResolvedRunDirectory(
                run_id=rid,
                path=legacy,
                layout="legacy_flat",
                run_collection=None,
            )
        )

    bk_root = cli_runs_root() / BY_LOOP_KIND_DIRNAME
    if bk_root.is_dir():
        for collection_dir in sorted(bk_root.iterdir(), key=lambda p: p.name):
            if not collection_dir.is_dir():
                continue
            if not is_collection_directory_name(collection_dir.name):
                continue
            candidate = collection_dir / rid
            if _looks_like_run_dir(candidate):
                matches.append(
                    ResolvedRunDirectory(
                        run_id=rid,
                        path=candidate,
                        layout="by_loop_kind",
                        run_collection=collection_dir.name,
                    )
                )
    return matches


def resolve_run_directory(run_id: str) -> ResolvedRunDirectory:
    matches = find_run_directory_candidates(run_id)
    if not matches:
        raise RunLayoutError("run_id_not_found")
    if len(matches) > 1:
        raise RunLayoutError("run_id_ambiguous")
    return matches[0]


def resolve_run_human_timeline_path(run_id: str) -> Path | None:
    """Return upstream timeline path when uniquely resolved and present."""
    matches = find_run_directory_candidates(run_id)
    if len(matches) != 1:
        return None
    timeline = matches[0].path / "audit" / "human" / "timeline.md"
    return timeline if timeline.is_file() else None


def iter_retention_buckets(root: Path | None = None) -> list[tuple[str, Path, bool]]:
    """Yield ``(bucket_id, bucket_root, legacy_flat)`` retention queues."""
    base = root or cli_runs_root()
    buckets: list[tuple[str, Path, bool]] = []
    if not base.is_dir():
        return buckets
    buckets.append((LEGACY_FLAT_BUCKET, base, True))
    bk = base / BY_LOOP_KIND_DIRNAME
    if bk.is_dir():
        for collection_dir in sorted(bk.iterdir(), key=lambda p: p.name):
            if collection_dir.is_dir() and is_collection_directory_name(collection_dir.name):
                buckets.append((f"by_loop_kind:{collection_dir.name}", collection_dir, False))
    return buckets


def list_run_dirs_in_bucket(bucket_root: Path, *, legacy_flat: bool) -> list[Path]:
    if not bucket_root.is_dir():
        return []
    if legacy_flat:
        return [
            d
            for d in bucket_root.iterdir()
            if d.is_dir() and d.name != BY_LOOP_KIND_DIRNAME and _looks_like_run_dir(d)
        ]
    return [d for d in bucket_root.iterdir() if d.is_dir() and _looks_like_run_dir(d)]


def is_safe_run_dir_in_bucket(run_dir: Path, bucket_root: Path) -> bool:
    try:
        run_dir.resolve().relative_to(bucket_root.resolve())
        return run_dir.parent.resolve() == bucket_root.resolve()
    except Exception:
        return False


def _looks_like_run_dir(path: Path) -> bool:
    return path.is_dir() and (path / "state.json").is_file()
