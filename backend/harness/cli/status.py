"""Lightweight run inspection: process, artifacts, optional HITL pending."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from harness.runtime.hitl.watch import hitl_pending_path

from ._process_util import is_pid_alive
from .run_state import read_state


def _print_json(obj: dict[str, Any]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def status_run(*, run_id: str) -> dict[str, Any]:
    state = read_state(run_id)
    if state is None:
        return {
            "run_id": run_id,
            "state": "missing",
            "process_alive": None,
            "done_file_exists": False,
            "result_file_exists": False,
            "hitl_pending": False,
        }

    done_p = Path(state.paths.done_file)
    result_p = Path(state.paths.result_file)
    hitl_p = hitl_pending_path(run_id)

    pid = int(state.pid)
    alive: bool | None
    if pid <= 0:
        alive = None
    else:
        alive = is_pid_alive(pid)

    # Mechanical dead-run classification: if the process is not alive and there is
    # no done sentinel, surface whether a resume checkpoint exists so operators can
    # decide whether to invoke ``harness.cli.resume``.
    interrupted_classification: dict[str, Any] | None = None
    if alive is False and not done_p.is_file() and not result_p.is_file():
        from .resume import classify_resumability
        cls = classify_resumability(run_id)
        resumability = cls.get("resumability")
        if resumability == "resumable":
            interrupted_classification = {
                "kind": "interrupted_resumable",
                "checkpoint_path": cls.get("checkpoint_path"),
                "resume_command": cls.get("resume_command"),
            }
        else:
            interrupted_classification = {
                "kind": "interrupted_no_checkpoint",
                "reason_code": cls.get("reason_code") or resumability,
            }

    out: dict[str, Any] = {
        "run_id": run_id,
        "state": "ok",
        "status": state.status,
        "mode": state.mode,
        "loop_kind": state.loop_kind,
        "pid": pid,
        "process_alive": alive,
        "done_file_exists": done_p.is_file(),
        "result_file_exists": result_p.is_file(),
        "hitl_pending": hitl_p.is_file(),
        "paths": {
            "run_dir": state.paths.run_dir,
            "state_file": state.paths.state_file,
            "done_file": state.paths.done_file,
            "result_file": state.paths.result_file,
            "stdout_log": state.paths.stdout_log,
            "stderr_log": state.paths.stderr_log,
        },
    }
    if interrupted_classification is not None:
        out["interrupted"] = interrupted_classification
    return out


def main() -> None:
    parser = argparse.ArgumentParser(prog="harness.cli.status", description="Inspect harness CLI run-state.")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    _print_json(status_run(run_id=args.run_id.strip()))


if __name__ == "__main__":
    main()
