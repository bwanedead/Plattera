"""Durable run-state records for harness CLI operator flows.

New runs are allocated under ``cli_runs/by_loop_kind/<run_collection>/<run_id>/``.
Legacy flat runs under ``cli_runs/<run_id>/`` remain discoverable.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from time import time
from typing import Any

from .run_layout import (
    RunLayoutError,
    allocate_run_directory,
    cli_runs_root,
    normalize_run_collection,
    resolve_run_directory,
)


def run_dir(run_id: str) -> Path:
    return resolve_run_directory(run_id).path


def state_path(run_id: str) -> Path:
    return run_dir(run_id) / "state.json"


@dataclass
class HarnessCliRunPaths:
    run_dir: str
    state_file: str
    done_file: str
    result_file: str
    stdout_log: str
    stderr_log: str


@dataclass
class HarnessCliRunState:
    run_id: str
    pid: int
    loop_kind: str
    run_collection: str
    mode: str
    paths: HarnessCliRunPaths
    spawn_argv: list[str]
    created_at_epoch_seconds: float
    status: str
    extra: dict[str, Any]

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> HarnessCliRunState:
        paths_raw = data.get("paths") or {}
        paths = HarnessCliRunPaths(
            run_dir=str(paths_raw.get("run_dir", "")),
            state_file=str(paths_raw.get("state_file", "")),
            done_file=str(paths_raw.get("done_file", "")),
            result_file=str(paths_raw.get("result_file", "")),
            stdout_log=str(paths_raw.get("stdout_log", "")),
            stderr_log=str(paths_raw.get("stderr_log", "")),
        )
        loop_kind = str(data.get("loop_kind", ""))
        # Migration accommodation for pre-collection state.json files.
        run_collection = str(data.get("run_collection") or loop_kind or "").strip()
        return cls(
            run_id=str(data.get("run_id", "")),
            pid=int(data.get("pid", 0)),
            loop_kind=loop_kind,
            run_collection=run_collection,
            mode=str(data.get("mode", "")),
            paths=paths,
            spawn_argv=list(data.get("spawn_argv") or []),
            created_at_epoch_seconds=float(data.get("created_at_epoch_seconds", 0.0)),
            status=str(data.get("status", "")),
            extra=dict(data.get("extra") or {}),
        )


def write_state(state: HarnessCliRunState) -> None:
    p = Path(state.paths.state_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state.to_json_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def run_layout_issue(run_id: str) -> str | None:
    """Return a layout reason code when ``run_id`` is unsafe, missing, or ambiguous."""
    try:
        resolve_run_directory(run_id)
        return None
    except RunLayoutError as exc:
        return exc.code


def read_state(run_id: str) -> HarnessCliRunState | None:
    try:
        resolved = resolve_run_directory(run_id)
    except RunLayoutError as exc:
        if exc.code in {"run_id_not_found", "run_id_ambiguous"}:
            return None
        raise
    p = resolved.path / "state.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return HarnessCliRunState.from_json_dict(data)
    except Exception:
        return None


def update_state_fields(run_id: str, **fields: Any) -> HarnessCliRunState | None:
    state = read_state(run_id)
    if state is None:
        return None
    for k, v in fields.items():
        if hasattr(state, k):
            setattr(state, k, v)
    write_state(state)
    return state


def merge_state_extra(run_id: str, extra_patch: dict[str, Any]) -> HarnessCliRunState | None:
    """Merge keys into ``state.extra`` without dropping concurrent child-process updates."""
    state = read_state(run_id)
    if state is None:
        return None
    merged = dict(state.extra or {})
    merged.update(dict(extra_patch))
    state.extra = merged
    write_state(state)
    return state


def build_paths(*, run_id: str, run_collection: str) -> HarnessCliRunPaths:
    rd = allocate_run_directory(run_id=run_id, run_collection=run_collection)
    return HarnessCliRunPaths(
        run_dir=str(rd.resolve()),
        state_file=str((rd / "state.json").resolve()),
        done_file=str((rd / "done.json").resolve()),
        result_file=str((rd / "result.json").resolve()),
        stdout_log=str((rd / "stdout.log").resolve()),
        stderr_log=str((rd / "stderr.log").resolve()),
    )


def new_run_state(
    *,
    run_id: str,
    pid: int,
    loop_kind: str,
    mode: str,
    spawn_argv: list[str],
    status: str = "started",
    extra: dict[str, Any] | None = None,
) -> HarnessCliRunState:
    run_collection = normalize_run_collection(loop_kind)
    paths = build_paths(run_id=run_id, run_collection=run_collection)
    return HarnessCliRunState(
        run_id=run_id,
        pid=pid,
        loop_kind=loop_kind,
        run_collection=run_collection,
        mode=mode,
        paths=paths,
        spawn_argv=list(spawn_argv),
        created_at_epoch_seconds=time(),
        status=status,
        extra=extra or {},
    )
