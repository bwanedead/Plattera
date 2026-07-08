"""Spawn the emergency-stop watchdog alongside CLI worker processes."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .run_state import HarnessCliRunPaths


def _backend_cwd() -> str:
    return str(Path(__file__).resolve().parents[2])


def _popen_flags() -> dict[str, Any]:
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return {"creationflags": flags}
    return {"start_new_session": True}


def spawn_run_control_watchdog(*, worker_pid: int, paths: HarnessCliRunPaths, run_id: str) -> subprocess.Popen[Any] | None:
    """Start a sibling watchdog process for ``worker_pid`` (best effort)."""
    if worker_pid <= 0:
        return None
    env = os.environ.copy()
    env["HARNESS_CLI_RUN_ID"] = run_id
    env["HARNESS_CLI_WATCHDOG_WORKER_PID"] = str(worker_pid)
    env["HARNESS_CLI_DONE_FILE"] = paths.done_file
    env["HARNESS_CLI_RESULT_FILE"] = paths.result_file
    try:
        return subprocess.Popen(
            [sys.executable, "-m", "harness.runtime.run_control_watchdog"],
            cwd=_backend_cwd(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            close_fds=sys.platform != "win32",
            **_popen_flags(),
        )
    except Exception:
        return None
