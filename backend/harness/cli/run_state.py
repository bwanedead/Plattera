"""Durable run-state records for harness CLI operator flows.

Each ``start`` creates a directory under
``harness_cli_artifacts_root() / "cli_runs" / <run_id> /`` with deterministic
JSON metadata and sibling artifact paths (logs, done, result).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from time import time
from typing import Any

from config.paths import harness_cli_artifacts_root


def cli_runs_root() -> Path:
    root = harness_cli_artifacts_root() / "cli_runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_dir(run_id: str) -> Path:
    return cli_runs_root() / str(run_id).strip()


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
    mode: str
    paths: HarnessCliRunPaths
    spawn_argv: list[str]
    created_at_epoch_seconds: float
    status: str
    extra: dict[str, Any]

    def to_json_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["paths"] = asdict(self.paths)
        return d

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
        return cls(
            run_id=str(data.get("run_id", "")),
            pid=int(data.get("pid", 0)),
            loop_kind=str(data.get("loop_kind", "")),
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


def read_state(run_id: str) -> HarnessCliRunState | None:
    p = state_path(run_id)
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


def build_paths(run_id: str) -> HarnessCliRunPaths:
    rd = run_dir(run_id)
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
    paths = build_paths(run_id)
    return HarnessCliRunState(
        run_id=run_id,
        pid=pid,
        loop_kind=loop_kind,
        mode=mode,
        paths=paths,
        spawn_argv=list(spawn_argv),
        created_at_epoch_seconds=time(),
        status=status,
        extra=extra or {},
    )
