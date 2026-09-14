"""Reference-aware transcript-edit workspace cleanup (control-plane only)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from harness.cli import run_layout
from harness.cli.run_layout import is_safe_run_dir_in_bucket
from harness.cli.run_quiescence import (
    REASON_RUN_ACTIVITY_UNKNOWN,
    REASON_RUN_NOT_QUIESCENT,
    assess_run_quiescence,
)
from harness.cli.workspace_refs import discover_run_workspace_ids

_RECOGNIZED_ACTIVITY_REASONS = frozenset(
    {REASON_RUN_NOT_QUIESCENT, REASON_RUN_ACTIVITY_UNKNOWN}
)

_LOG = logging.getLogger(__name__)


def iter_all_cli_run_dirs(root: Path) -> list[Path]:
    found: list[Path] = []
    for _bucket_id, bucket_root, legacy_flat in run_layout.iter_retention_buckets(root):
        found.extend(run_layout.list_run_dirs_in_bucket(bucket_root, legacy_flat=legacy_flat))
    return found


def collect_workspace_reference_index(
    run_dirs: list[Path],
) -> tuple[dict[str, frozenset[str]] | None, bool]:
    """Map run_id → workspace ids. ``uncertain=True`` means skip workspace deletes."""
    index: dict[str, frozenset[str]] = {}
    for run_dir in run_dirs:
        refs, err = discover_run_workspace_ids(run_id=run_dir.name, run_dir=run_dir)
        if err or refs is None:
            return None, True
        index[run_dir.name] = refs
    return index, False


def assess_run_activity(
    run_ids: list[str],
    *,
    required_run_ids: set[str] | None = None,
) -> dict[str, str | None] | None:
    """Return per-run activity, or None when assessment is uncertain.

    Exactly ``None`` is quiescent. Only recognized nonblank quiescence reasons
    count as non-quiescent. Any other return type/value or exception fails closed.
    """
    activity: dict[str, str | None] = {}
    for run_id in run_ids:
        try:
            quiet = assess_run_quiescence(run_id)
        except Exception:
            return None
        classified = _classify_activity(quiet)
        if classified is False:
            return None
        activity[run_id] = classified
    required = required_run_ids if required_run_ids is not None else set(run_ids)
    if any(run_id not in activity for run_id in required):
        return None
    return activity


def _classify_activity(quiet: object) -> str | None | bool:
    """Return None (quiescent), a recognized reason, or False when uncertain."""
    if quiet is None:
        return None
    if type(quiet) is str and quiet in _RECOGNIZED_ACTIVITY_REASONS:
        return quiet
    return False


def workspace_ids_safe_to_delete(
    *,
    referenced_by_deleted: set[str],
    index: dict[str, frozenset[str]],
    surviving_run_ids: set[str],
    activity: dict[str, str | None],
) -> set[str]:
    """Workspaces with no surviving ref and no active/unknown ref."""
    deletable: set[str] = set()
    for workspace_id in referenced_by_deleted:
        if any(workspace_id in index.get(run_id, frozenset()) for run_id in surviving_run_ids):
            continue
        referenced_by = [
            run_id for run_id, refs in index.items() if workspace_id in refs
        ]
        if any(_activity_blocks_delete(run_id, activity) for run_id in referenced_by):
            continue
        deletable.add(workspace_id)
    return deletable


def _activity_blocks_delete(run_id: str, activity: dict[str, str | None]) -> bool:
    if run_id not in activity:
        return True
    value = activity[run_id]
    if value is None:
        return False
    if type(value) is str and value in _RECOGNIZED_ACTIVITY_REASONS:
        return True
    return True


def delete_transcript_edit_workspaces(workspace_ids: set[str]) -> None:
    for workspace_id in sorted(workspace_ids):
        _cleanup_leaf_workspaces(workspace_id)
        _cleanup_dossier_workspaces(workspace_id)


def _cleanup_leaf_workspaces(workspace_id: str) -> None:
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
                workspace_dir = tx_dir / workspace_id
                if workspace_dir.is_dir() and is_safe_run_dir_in_bucket(workspace_dir, tx_dir):
                    try:
                        shutil.rmtree(workspace_dir)
                        _LOG.info("cleanup: removed transcript_edit workspace %s", workspace_dir)
                    except Exception:
                        _LOG.warning("cleanup: failed to remove %s", workspace_dir, exc_info=True)
    except Exception:
        _LOG.warning("cleanup: transcript_edit workspace scan failed", exc_info=True)


def _cleanup_dossier_workspaces(workspace_id: str) -> None:
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
            workspace_dir = dossier_dir / workspace_id
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
