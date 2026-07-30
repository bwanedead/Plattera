"""Latest-N retention cleanup for harness CLI run directories.

Policy (per collection bucket):
- Keep the latest ``keep_n`` *unpinned* run directories in each bucket:
  - legacy flat runs directly under ``cli_runs/``
  - each ``cli_runs/by_loop_kind/<run_collection>/`` queue independently
- Pinned runs are never auto-deleted.
- Collection directories themselves are never deleted as runs.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from time import time
from typing import Any

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

    purged: list[str] = []
    for _bucket_id, bucket_root, legacy_flat in iter_retention_buckets(root):
        for run_path in list_run_dirs_in_bucket(bucket_root, legacy_flat=legacy_flat):
            if not is_safe_run_dir_in_bucket(run_path, bucket_root):
                _LOG.warning("purge_all_cli_runs: skipping unsafe path %s", run_path)
                continue
            run_id = run_path.name
            if _delete_run_dir(run_path):
                purged.append(run_id)
                _cleanup_transcript_edit_workspace(run_id)

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

    deleted: list[str] = []
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
                _cleanup_transcript_edit_workspace(run_id)

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


def _cleanup_transcript_edit_workspace(run_id: str) -> None:
    """Remove leaf and dossier TE workspace dirs whose name equals the retired run_id."""
    _cleanup_leaf_transcript_edit_workspaces(run_id)
    _cleanup_dossier_transcript_edit_workspaces(run_id)


def _cleanup_leaf_transcript_edit_workspaces(run_id: str) -> None:
    try:
        from config.paths import dossiers_transcript_edit_artifacts_root

        te_root = dossiers_transcript_edit_artifacts_root()
    except Exception:
        return
    if not te_root.exists():
        return
    try:
        for dossier_dir in te_root.iterdir():
            if not dossier_dir.is_dir():
                continue
            for tx_dir in dossier_dir.iterdir():
                if not tx_dir.is_dir():
                    continue
                workspace_dir = tx_dir / run_id
                if workspace_dir.is_dir() and is_safe_run_dir_in_bucket(workspace_dir, tx_dir):
                    try:
                        shutil.rmtree(workspace_dir)
                        _LOG.info("cleanup: removed transcript_edit workspace %s", workspace_dir)
                    except Exception:
                        _LOG.warning("cleanup: failed to remove %s", workspace_dir, exc_info=True)
    except Exception:
        _LOG.warning("cleanup: transcript_edit workspace scan failed", exc_info=True)


def _cleanup_dossier_transcript_edit_workspaces(run_id: str) -> None:
    try:
        from config.paths import dossiers_transcript_edit_dossier_artifacts_root

        dossier_root = dossiers_transcript_edit_dossier_artifacts_root()
    except Exception:
        return
    if not dossier_root.exists():
        return
    try:
        for dossier_dir in dossier_root.iterdir():
            if not dossier_dir.is_dir():
                continue
            workspace_dir = dossier_dir / run_id
            if workspace_dir.is_dir() and is_safe_run_dir_in_bucket(workspace_dir, dossier_dir):
                try:
                    shutil.rmtree(workspace_dir)
                    _LOG.info(
                        "cleanup: removed transcript_edit_dossier workspace %s",
                        workspace_dir,
                    )
                except Exception:
                    _LOG.warning("cleanup: failed to remove %s", workspace_dir, exc_info=True)
    except Exception:
        _LOG.warning("cleanup: transcript_edit_dossier workspace scan failed", exc_info=True)


# Backward-compatible helpers for existing tests
def _is_safe_run_dir(d: Path, root: Path) -> bool:
    return is_safe_run_dir_in_bucket(d, root)
