"""Shared helper for the ``pause`` / ``stop`` CLI entrypoints.

Both commands share the same pre-write guards and JSON output shape; they
differ only in the ``command`` string written into ``control.json``. Keeping
this logic in one place prevents behavior drift between the two subcommands
and centralizes CLI refusal reason codes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._process_util import is_pid_alive
from .run_state import read_state, run_dir
from harness.runtime.control import CONTROL_FILENAME, write_run_control_request


def request_run_control(
    *,
    run_id: str,
    command: str,
    reason: str | None = None,
    requested_by: str = "cli",
) -> dict[str, Any]:
    """Validate guards and write a ``control.json`` for the given run.

    Mechanical only: does not signal the process, does not wait, does not
    interpret what ``command`` means beyond rejecting unknown values.
    """
    rid = str(run_id or "").strip()
    state = read_state(rid)
    if state is None:
        return {
            "event": "control_requested",
            "run_id": rid,
            "command": command,
            "status": "refused",
            "reason_code": "missing_state",
        }

    done_file = Path(state.paths.done_file)
    if done_file.is_file():
        return {
            "event": "control_requested",
            "run_id": rid,
            "command": command,
            "status": "refused",
            "reason_code": "run_has_done_sentinel",
        }

    pid = int(state.pid or 0)
    alive = bool(pid > 0 and is_pid_alive(pid))
    if not alive:
        result_file = Path(state.paths.result_file)
        checkpoint = run_dir(rid) / "kernel_resume.json"
        if result_file.is_file() or checkpoint.is_file():
            return {
                "event": "control_requested",
                "run_id": rid,
                "command": command,
                "status": "refused",
                "reason_code": "run_already_interrupted",
                "pid": pid,
                "result_file": str(result_file) if result_file.is_file() else None,
                "checkpoint_path": str(checkpoint) if checkpoint.is_file() else None,
            }
        return {
            "event": "control_requested",
            "run_id": rid,
            "command": command,
            "status": "refused",
            "reason_code": "run_not_alive_no_checkpoint",
            "pid": pid,
        }

    control_file = run_dir(rid) / CONTROL_FILENAME
    try:
        req = write_run_control_request(
            control_file,
            command=command,
            reason=reason,
            requested_by=requested_by,
        )
    except ValueError as exc:
        return {
            "event": "control_requested",
            "run_id": rid,
            "command": command,
            "status": "refused",
            "reason_code": str(exc),
        }

    return {
        "event": "control_requested",
        "run_id": rid,
        "command": req.command,
        "request_id": req.request_id,
        "control_file": str(control_file),
        "status": "requested",
        "pid": pid,
    }
