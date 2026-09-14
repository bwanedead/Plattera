"""Exclusive continuation-workspace claim (generic CLI control-plane)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from harness.cli import run_layout
from harness.cli.fork_workspace import WORKSPACE_MODE_CONTINUE
from harness.cli.run_layout import RunLayoutError, normalize_run_id
from harness.cli.run_quiescence import (
    REASON_RUN_ACTIVITY_UNKNOWN,
    REASON_RUN_NOT_QUIESCENT,
    assess_run_quiescence,
)
from harness.cli.workspace_refs import discover_run_workspace_ids

REASON_CONTINUE_WORKSPACE_IN_USE = "continue_workspace_in_use"

_CLAIM_DIRNAME = "workspace_claims"
_CLAIM_STATUS = "claimed"
_CLAIM_KEYS = frozenset({"workspace_id", "owner_run_id", "status"})
_RELEASED_STATUSES = frozenset({"fork_aborted", "fork_spawn_failed"})
_IN_FLIGHT_STATUSES = frozenset({"fork_started"})


def refuse_continue_workspace_busy(
    *,
    workspace_id: str,
    source_run_id: str,
    exclude_run_id: str | None = None,
) -> str | None:
    """Refuse when another continuation already owns ``workspace_id``."""
    try:
        ws = normalize_run_id(workspace_id)
    except RunLayoutError:
        return REASON_RUN_ACTIVITY_UNKNOWN
    claim_err = _existing_claim_refusal(
        workspace_id=ws,
        allowed_owner_ids={source_run_id, exclude_run_id} - {None},
    )
    if claim_err:
        return claim_err
    return _scan_continue_occupants(
        workspace_id=ws,
        skip_run_ids={source_run_id, exclude_run_id} - {None},
    )


def acquire_continue_workspace_claim(*, workspace_id: str, owner_run_id: str) -> str | None:
    """Atomically claim ``workspace_id`` for ``owner_run_id``."""
    try:
        ws = normalize_run_id(workspace_id)
        owner = normalize_run_id(owner_run_id)
    except RunLayoutError:
        return REASON_RUN_ACTIVITY_UNKNOWN
    path = _claim_path(ws)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return REASON_RUN_ACTIVITY_UNKNOWN
    payload = json.dumps(
        {"workspace_id": ws, "owner_run_id": owner, "status": "claimed"},
        separators=(",", ":"),
        allow_nan=False,
    )
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        steal_err = _release_stale_claim(path, workspace_id=ws, owner_run_id=owner)
        if steal_err:
            return steal_err
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return REASON_CONTINUE_WORKSPACE_IN_USE
        except OSError:
            return REASON_RUN_ACTIVITY_UNKNOWN
    except OSError:
        return REASON_RUN_ACTIVITY_UNKNOWN
    try:
        os.write(fd, payload.encode("utf-8"))
    except OSError:
        os.close(fd)
        _best_effort_unlink(path)
        return REASON_RUN_ACTIVITY_UNKNOWN
    os.close(fd)
    return None


def release_continue_workspace_claim(*, workspace_id: str, owner_run_id: str) -> None:
    """Drop a claim only when this owner still holds it."""
    try:
        ws = normalize_run_id(workspace_id)
        owner = normalize_run_id(owner_run_id)
    except RunLayoutError:
        return
    path = _claim_path(ws)
    if not path.is_file():
        return
    doc, err = _read_claim(path, workspace_id=ws)
    if err or doc is None:
        return
    if doc.get("owner_run_id") != owner:
        return
    _best_effort_unlink(path)


def _scan_continue_occupants(*, workspace_id: str, skip_run_ids: set[str]) -> str | None:
    try:
        run_dirs = _iter_cli_run_dirs()
    except Exception:
        return REASON_RUN_ACTIVITY_UNKNOWN
    for run_path in run_dirs:
        run_id = run_path.name
        if run_id in skip_run_ids:
            continue
        occupant = _continue_occupant_refusal(
            run_id=run_id,
            run_dir=run_path,
            workspace_id=workspace_id,
        )
        if occupant:
            return occupant
    return None


def _continue_occupant_refusal(
    *,
    run_id: str,
    run_dir: Path,
    workspace_id: str,
) -> str | None:
    doc, load_err = _load_state(run_dir)
    if load_err or doc is None:
        return REASON_RUN_ACTIVITY_UNKNOWN
    if not _is_continue_mode(doc):
        return None
    refs, ref_err = discover_run_workspace_ids(run_id=run_id, run_dir=run_dir)
    if ref_err or refs is None:
        return REASON_RUN_ACTIVITY_UNKNOWN
    if workspace_id not in refs:
        return None
    status = doc.get("status") if type(doc.get("status")) is str else ""
    if status in _RELEASED_STATUSES:
        return None
    if status in _IN_FLIGHT_STATUSES:
        return REASON_CONTINUE_WORKSPACE_IN_USE
    if _has_terminal_file(run_dir):
        quiet = assess_run_quiescence(run_id)
        if quiet == REASON_RUN_NOT_QUIESCENT:
            return REASON_CONTINUE_WORKSPACE_IN_USE
        if quiet:
            return quiet
        return None
    quiet = assess_run_quiescence(run_id)
    if quiet == REASON_RUN_NOT_QUIESCENT:
        return REASON_CONTINUE_WORKSPACE_IN_USE
    if quiet:
        return quiet
    return REASON_CONTINUE_WORKSPACE_IN_USE


def _existing_claim_refusal(*, workspace_id: str, allowed_owner_ids: set[str]) -> str | None:
    path = _claim_path(workspace_id)
    if not path.exists():
        return None
    if not path.is_file():
        return REASON_RUN_ACTIVITY_UNKNOWN
    doc, err = _read_claim(path, workspace_id=workspace_id)
    if err or doc is None:
        return REASON_RUN_ACTIVITY_UNKNOWN
    owner = doc.get("owner_run_id")
    if type(owner) is not str:
        return REASON_RUN_ACTIVITY_UNKNOWN
    if owner in allowed_owner_ids:
        return None
    return _owner_occupancy_refusal(owner_run_id=owner)


def _release_stale_claim(path: Path, *, workspace_id: str, owner_run_id: str) -> str | None:
    doc, err = _read_claim(path, workspace_id=workspace_id)
    if err or doc is None:
        return REASON_RUN_ACTIVITY_UNKNOWN
    owner = doc.get("owner_run_id")
    if type(owner) is not str:
        return REASON_RUN_ACTIVITY_UNKNOWN
    if owner == owner_run_id:
        _best_effort_unlink(path)
        return None
    occupy = _owner_occupancy_refusal(owner_run_id=owner)
    if occupy:
        return occupy
    _best_effort_unlink(path)
    return None


def _owner_occupancy_refusal(*, owner_run_id: str) -> str | None:
    quiet = assess_run_quiescence(owner_run_id)
    if quiet == REASON_RUN_NOT_QUIESCENT:
        return REASON_CONTINUE_WORKSPACE_IN_USE
    if quiet == REASON_RUN_ACTIVITY_UNKNOWN:
        try:
            resolved = run_layout.resolve_run_directory(owner_run_id)
        except RunLayoutError as exc:
            if exc.code == "run_id_not_found":
                return None
            return REASON_RUN_ACTIVITY_UNKNOWN
        except Exception:
            return REASON_RUN_ACTIVITY_UNKNOWN
        doc, load_err = _load_state(resolved.path)
        if load_err or doc is None:
            return REASON_RUN_ACTIVITY_UNKNOWN
        status = doc.get("status") if type(doc.get("status")) is str else ""
        if status in _RELEASED_STATUSES:
            return None
        if _has_terminal_file(resolved.path):
            return None
        return REASON_RUN_ACTIVITY_UNKNOWN
    try:
        resolved = run_layout.resolve_run_directory(owner_run_id)
    except RunLayoutError as exc:
        if exc.code == "run_id_not_found":
            return None
        return REASON_RUN_ACTIVITY_UNKNOWN
    except Exception:
        return REASON_RUN_ACTIVITY_UNKNOWN
    doc, load_err = _load_state(resolved.path)
    if load_err or doc is None:
        return REASON_RUN_ACTIVITY_UNKNOWN
    status = doc.get("status") if type(doc.get("status")) is str else ""
    if status in _RELEASED_STATUSES:
        return None
    if status in _IN_FLIGHT_STATUSES:
        return REASON_CONTINUE_WORKSPACE_IN_USE
    if _has_terminal_file(resolved.path):
        return None
    return REASON_CONTINUE_WORKSPACE_IN_USE


def _claim_path(workspace_id: str) -> Path:
    return run_layout.cli_runs_root() / _CLAIM_DIRNAME / f"{workspace_id}.json"


def _iter_cli_run_dirs() -> list[Path]:
    root = run_layout.cli_runs_root()
    found: list[Path] = []
    for _bucket_id, bucket_root, legacy_flat in run_layout.iter_retention_buckets(root):
        found.extend(run_layout.list_run_dirs_in_bucket(bucket_root, legacy_flat=legacy_flat))
    return found


def _is_continue_mode(doc: dict[str, Any]) -> bool:
    extra = doc.get("extra")
    if type(extra) is not dict:
        return False
    lineage = extra.get("fork_lineage")
    if type(lineage) is not dict:
        return False
    return lineage.get("workspace_mode") == WORKSPACE_MODE_CONTINUE


def _has_terminal_file(run_dir: Path) -> bool:
    return (run_dir / "result.json").is_file() or (run_dir / "done.json").is_file()


def _load_state(run_dir: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = Path(run_dir) / "state.json"
    if not path.is_file():
        return None, REASON_RUN_ACTIVITY_UNKNOWN
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None, REASON_RUN_ACTIVITY_UNKNOWN
    if type(raw) is not dict:
        return None, REASON_RUN_ACTIVITY_UNKNOWN
    return raw, None


def _read_claim(
    path: Path,
    *,
    workspace_id: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Load a claim only when it matches the exact canonical schema."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None, REASON_RUN_ACTIVITY_UNKNOWN
    if type(raw) is not dict:
        return None, REASON_RUN_ACTIVITY_UNKNOWN
    if set(raw) != _CLAIM_KEYS:
        return None, REASON_RUN_ACTIVITY_UNKNOWN
    stored_ws = _canonical_claim_id(raw.get("workspace_id"))
    owner = _canonical_claim_id(raw.get("owner_run_id"))
    requested = _canonical_claim_id(workspace_id)
    if stored_ws is None or owner is None or requested is None:
        return None, REASON_RUN_ACTIVITY_UNKNOWN
    if stored_ws != requested or path.stem != requested:
        return None, REASON_RUN_ACTIVITY_UNKNOWN
    if raw.get("status") != _CLAIM_STATUS:
        return None, REASON_RUN_ACTIVITY_UNKNOWN
    return raw, None


def _canonical_claim_id(raw: object) -> str | None:
    if type(raw) is not str:
        return None
    try:
        normalized = normalize_run_id(raw)
    except RunLayoutError:
        return None
    if normalized != raw:
        return None
    return normalized


def _best_effort_unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        return
