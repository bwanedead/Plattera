"""Latest-N retention cleanup for harness CLI run directories.

Policy (per collection bucket):
- Keep the latest ``keep_n`` *unpinned* run directories in each bucket:
  - legacy flat runs directly under ``cli_runs/``
  - each ``cli_runs/by_loop_kind/<run_collection>/`` queue independently
- Pinned runs are never auto-deleted.
- Collection directories themselves are never deleted as runs.
- Transcript-edit workspace dirs are deleted by referenced workspace_id only after
  the last surviving run reference is gone, and never while an active or
  activity-unknown run still references them. Uncertain reference discovery
  skips workspace cleanup.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from time import time

from harness.audit.retention_workspace_cleanup import (
    assess_run_activity,
    collect_workspace_reference_index,
    delete_transcript_edit_workspaces,
    iter_all_cli_run_dirs,
    workspace_ids_safe_to_delete,
)
from harness.cli import run_layout
from harness.cli.run_layout import (
    BY_LOOP_KIND_DIRNAME,
    is_safe_run_dir_in_bucket,
    iter_retention_buckets,
    list_run_dirs_in_bucket,
    resolve_run_directory,
)

_LOG = logging.getLogger(__name__)

_CLEANUP_POLICY_VERSION = "v2"


def write_run_retention_json(run_id: str, *, pinned: bool = False) -> None:
    """Write ``retention.json`` inside the resolved CLI run directory."""
    try:
        path = resolve_run_directory(run_id).path / "retention.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "pinned": pinned,
                    "created_at_epoch_seconds": time(),
                    "cleanup_policy_version": _CLEANUP_POLICY_VERSION,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        _LOG.warning("write_run_retention_json failed for run_id=%s", run_id, exc_info=True)


def purge_all_cli_runs() -> list[str]:
    """Delete every CLI run directory in all buckets (blank-slate reset)."""
    try:
        root = run_layout.cli_runs_root()
    except Exception:
        _LOG.warning("purge_all_cli_runs: could not resolve cli_runs_root", exc_info=True)
        return []

    run_dirs: list[Path] = []
    for _bucket_id, bucket_root, legacy_flat in iter_retention_buckets(root):
        for run_path in list_run_dirs_in_bucket(bucket_root, legacy_flat=legacy_flat):
            if not is_safe_run_dir_in_bucket(run_path, bucket_root):
                _LOG.warning("purge_all_cli_runs: skipping unsafe path %s", run_path)
                continue
            run_dirs.append(run_path)
    index, uncertain = collect_workspace_reference_index(run_dirs)
    activity = None
    if not uncertain and index is not None:
        activity = assess_run_activity(
            [path.name for path in run_dirs],
            required_run_ids=set(index),
        )
        if activity is None:
            uncertain = True

    surviving = {path.name for path in run_dirs}
    referenced_by_deleted: set[str] = set()
    purged: list[str] = []
    for run_path in run_dirs:
        run_id = run_path.name
        if _delete_run_dir(run_path):
            purged.append(run_id)
            surviving.discard(run_id)
            if index is not None:
                referenced_by_deleted.update(index.get(run_id, frozenset()))

    if not uncertain and index is not None and activity is not None:
        delete_transcript_edit_workspaces(
            workspace_ids_safe_to_delete(
                referenced_by_deleted=referenced_by_deleted,
                index=index,
                surviving_run_ids=surviving,
                activity=activity,
            )
        )

    if purged:
        _LOG.info("purge_all_cli_runs: purged %d run(s): %s", len(purged), purged)
    return purged


def cleanup_old_cli_runs(*, keep_n: int = 5) -> list[str]:
    """Delete old unpinned runs independently within each retention bucket."""
    try:
        root = run_layout.cli_runs_root()
    except Exception:
        _LOG.warning("cleanup_old_cli_runs: could not resolve cli_runs_root", exc_info=True)
        return []

    all_dirs = iter_all_cli_run_dirs(root)
    index, uncertain = collect_workspace_reference_index(all_dirs)
    activity = None
    if not uncertain and index is not None:
        activity = assess_run_activity(
            [path.name for path in all_dirs],
            required_run_ids=set(index),
        )
        if activity is None:
            uncertain = True

    deleted: list[str] = []
    deleted_refs: set[str] = set()
    surviving = {path.name for path in all_dirs}
    for _bucket_id, bucket_root, legacy_flat in iter_retention_buckets(root):
        candidates = list_run_dirs_in_bucket(bucket_root, legacy_flat=legacy_flat)
        candidates.sort(key=_run_sort_key)
        unpinned = [d for d in candidates if not _is_pinned(d)]
        to_delete = unpinned[: max(0, len(unpinned) - keep_n)]
        for run_path in to_delete:
            run_id = run_path.name
            if not is_safe_run_dir_in_bucket(run_path, bucket_root):
                _LOG.warning("cleanup: skipping unsafe path %s", run_path)
                continue
            if _delete_run_dir(run_path):
                deleted.append(run_id)
                surviving.discard(run_id)
                if index is not None:
                    deleted_refs.update(index.get(run_id, frozenset()))

    if not uncertain and index is not None and activity is not None:
        delete_transcript_edit_workspaces(
            workspace_ids_safe_to_delete(
                referenced_by_deleted=deleted_refs,
                index=index,
                surviving_run_ids=surviving,
                activity=activity,
            )
        )

    if deleted:
        _LOG.info("cleanup_old_cli_runs: deleted %d run(s): %s", len(deleted), deleted)
    return deleted


def _run_sort_key(d: Path) -> float:
    ret = d / "retention.json"
    if ret.exists():
        try:
            data = json.loads(ret.read_text(encoding="utf-8"))
            return float(data.get("created_at_epoch_seconds") or 0.0)
        except Exception:
            pass
    try:
        return d.stat().st_mtime
    except Exception:
        return 0.0


def _is_pinned(d: Path) -> bool:
    ret = d / "retention.json"
    if not ret.exists():
        return False
    try:
        data = json.loads(ret.read_text(encoding="utf-8"))
        return bool(data.get("pinned"))
    except Exception:
        return False


def _delete_run_dir(d: Path) -> bool:
    if d.name == BY_LOOP_KIND_DIRNAME:
        return False
    try:
        shutil.rmtree(d)
        return True
    except Exception:
        _LOG.warning("cleanup: failed to delete %s", d, exc_info=True)
        return False


# Backward-compatible helpers for existing tests
def _is_safe_run_dir(d: Path, root: Path) -> bool:
    return is_safe_run_dir_in_bucket(d, root)
