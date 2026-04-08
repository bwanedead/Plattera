"""Latest-N retention cleanup for harness CLI run directories.

Policy:
- Keep the latest ``keep_n`` *unpinned* CLI run directories.
- Pinned runs (``retention.json`` with ``pinned: true``) are never auto-deleted.
- Optionally clean transcript-edit workspace directories linked by run_id.

All deletions are best-effort — failures are logged, not raised.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from time import time
from typing import Any

_LOG = logging.getLogger(__name__)

_CLEANUP_POLICY_VERSION = "v1"


def write_run_retention_json(run_id: str, *, pinned: bool = False) -> None:
    """Write ``retention.json`` inside the CLI run directory for ``run_id``."""
    try:
        from harness.cli.run_state import run_dir as cli_run_dir
        path = cli_run_dir(run_id) / "retention.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({
                "run_id": run_id,
                "pinned": pinned,
                "created_at_epoch_seconds": time(),
                "cleanup_policy_version": _CLEANUP_POLICY_VERSION,
            }, indent=2),
            encoding="utf-8",
        )
    except Exception:
        _LOG.warning("write_run_retention_json failed for run_id=%s", run_id, exc_info=True)


def purge_all_cli_runs() -> list[str]:
    """Delete every CLI run directory — blank-slate reset.

    Intended for one-time pre-testing resets and emergency cleanouts.
    Ignores pinned status: all runs are removed.
    Linked transcript-edit workspaces are cleaned up for each purged run_id.

    Returns list of purged run_ids.
    """
    try:
        from harness.cli.run_state import cli_runs_root
        root = cli_runs_root()
    except Exception:
        _LOG.warning("purge_all_cli_runs: could not resolve cli_runs_root", exc_info=True)
        return []

    if not root.exists():
        return []

    try:
        candidates = [d for d in root.iterdir() if d.is_dir()]
    except Exception:
        _LOG.warning("purge_all_cli_runs: failed to list run dirs", exc_info=True)
        return []

    purged: list[str] = []
    for d in candidates:
        run_id = d.name
        if not _is_safe_run_dir(d, root):
            _LOG.warning("purge_all_cli_runs: skipping unsafe path %s", d)
            continue
        if _delete_run_dir(d):
            purged.append(run_id)
            _cleanup_transcript_edit_workspace(run_id)

    if purged:
        _LOG.info("purge_all_cli_runs: purged %d run(s): %s", len(purged), purged)
    return purged


def cleanup_old_cli_runs(*, keep_n: int = 4) -> list[str]:
    """Delete old unpinned CLI run directories, keeping the latest ``keep_n`` unpinned.

    Returns list of deleted run_ids.
    """
    try:
        from harness.cli.run_state import cli_runs_root
        root = cli_runs_root()
    except Exception:
        _LOG.warning("cleanup_old_cli_runs: could not resolve cli_runs_root", exc_info=True)
        return []

    if not root.exists():
        return []

    try:
        candidates = [d for d in root.iterdir() if d.is_dir()]
    except Exception:
        _LOG.warning("cleanup_old_cli_runs: failed to list run dirs", exc_info=True)
        return []

    # Sort oldest first by directory mtime (fallback: created_at from retention.json)
    candidates.sort(key=lambda d: _run_sort_key(d))

    # Partition pinned / unpinned
    unpinned = [d for d in candidates if not _is_pinned(d)]

    to_delete = unpinned[: max(0, len(unpinned) - keep_n)]
    deleted: list[str] = []
    for d in to_delete:
        run_id = d.name
        if not _is_safe_run_dir(d, root):
            _LOG.warning("cleanup: skipping unsafe path %s", d)
            continue
        if _delete_run_dir(d):
            deleted.append(run_id)
            _cleanup_transcript_edit_workspace(run_id)

    if deleted:
        _LOG.info("cleanup_old_cli_runs: deleted %d run(s): %s", len(deleted), deleted)
    return deleted


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


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


def _is_safe_run_dir(d: Path, root: Path) -> bool:
    """Verify the candidate dir is a direct child of root (no path traversal)."""
    try:
        d.resolve().relative_to(root.resolve())
        return d.parent.resolve() == root.resolve()
    except Exception:
        return False


def _delete_run_dir(d: Path) -> bool:
    try:
        shutil.rmtree(d)
        return True
    except Exception:
        _LOG.warning("cleanup: failed to delete %s", d, exc_info=True)
        return False


def _cleanup_transcript_edit_workspace(run_id: str) -> None:
    """Remove transcript-edit workspace dirs that match this run_id, if any exist."""
    try:
        from config.paths import dossiers_transcript_edit_artifacts_root
        te_root = dossiers_transcript_edit_artifacts_root()
    except Exception:
        return
    if not te_root.exists():
        return
    # Layout: artifacts/transcript_edit/<scope_id>/<transcription_id>/<workspace_id>/
    # workspace_id matches run_id when launched from a harness run
    try:
        for dossier_dir in te_root.iterdir():
            if not dossier_dir.is_dir():
                continue
            for tx_dir in dossier_dir.iterdir():
                if not tx_dir.is_dir():
                    continue
                workspace_dir = tx_dir / run_id
                if workspace_dir.is_dir() and _is_safe_run_dir(workspace_dir, tx_dir):
                    try:
                        shutil.rmtree(workspace_dir)
                        _LOG.info("cleanup: removed transcript_edit workspace %s", workspace_dir)
                    except Exception:
                        _LOG.warning("cleanup: failed to remove %s", workspace_dir, exc_info=True)
    except Exception:
        _LOG.warning("cleanup: transcript_edit workspace scan failed", exc_info=True)
