"""Emergency-stop watchdog for CLI-hosted harness worker processes."""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from .run_control_sidecar import (
    EMERGENCY_STOP_TRIGGERED_FILENAME,
    emergency_stop_requested,
    run_control_path,
)

_LOG = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 0.25
RESUME_CHECKPOINT_FILENAME = "kernel_resume.json"


def write_emergency_stop_terminal_artifacts(
    *,
    run_dir: str | Path,
    done_file: str | Path,
    result_file: str | Path,
) -> dict[str, Any]:
    """Best-effort terminal artifacts before hard-terminating a worker."""
    run_path = Path(run_dir)
    done_path = Path(done_file)
    result_path = Path(result_file)
    resumable = (run_path / RESUME_CHECKPOINT_FILENAME).is_file()
    triggered_at = time.time()
    worker_pid = int(os.environ.get("HARNESS_CLI_WATCHDOG_WORKER_PID", "0") or 0)

    if done_path.is_file() and result_path.is_file():
        return {
            "reason_code": "emergency_stop_requested",
            "triggered_at_epoch_seconds": triggered_at,
            "worker_pid": worker_pid,
            "resumable": resumable,
            "terminal_write_skipped": True,
            "reason": "terminal_artifacts_already_present",
        }

    done_payload: dict[str, Any] = {
        "status": "stopped",
        "terminal_class": "stopped",
        "terminal": "stopped",
        "reason_code": "emergency_stop_requested",
        "resumable": resumable,
        "emergency_stop": True,
        "operator_interrupted": True,
    }
    result_payload: dict[str, Any] = {
        **done_payload,
        "terminal_summary": "Emergency stop requested via run_control.json",
    }
    triggered_payload: dict[str, Any] = {
        "reason_code": "emergency_stop_requested",
        "triggered_at_epoch_seconds": triggered_at,
        "worker_pid": worker_pid,
        "resumable": resumable,
    }

    _write_json(done_path, done_payload)
    _write_json(result_path, result_payload)
    _write_json(run_path / EMERGENCY_STOP_TRIGGERED_FILENAME, triggered_payload)
    _maybe_update_cli_run_state("stopped")
    return triggered_payload


def terminate_worker_process(pid: int) -> None:
    """Hard-terminate a worker process (best effort)."""
    if pid <= 0:
        return
    if sys.platform == "win32":
        import subprocess

        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        _LOG.warning("worker SIGTERM failed pid=%s", pid, exc_info=True)
    deadline = time.time() + 2.0
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        except OSError:
            break
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        _LOG.warning("worker SIGKILL failed pid=%s", pid, exc_info=True)


def run_watchdog_loop(
    *,
    run_dir: str | Path,
    worker_pid: int,
    done_file: str | Path,
    result_file: str | Path,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> int:
    """Poll ``run_control.json`` until emergency stop or worker exit."""
    sidecar = run_control_path(run_dir)
    interval = max(0.05, float(poll_interval_seconds))
    while True:
        if not _pid_alive(worker_pid):
            return 0
        if emergency_stop_requested(sidecar):
            if not (Path(done_file).is_file() and Path(result_file).is_file()):
                write_emergency_stop_terminal_artifacts(
                    run_dir=run_dir,
                    done_file=done_file,
                    result_file=result_file,
                )
            terminate_worker_process(worker_pid)
            return 0
        time.sleep(interval)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import subprocess

        proc = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in (proc.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return False


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _maybe_update_cli_run_state(status: str) -> None:
    cli_run_id = str(os.environ.get("HARNESS_CLI_RUN_ID", "") or "").strip()
    if not cli_run_id:
        return
    try:
        from harness.cli.run_state import update_state_fields

        update_state_fields(cli_run_id, status=str(status))
    except Exception:
        _LOG.warning("run-state update failed during emergency stop", exc_info=True)


def main() -> None:
    run_id = str(os.environ.get("HARNESS_CLI_RUN_ID", "") or "").strip()
    worker_pid_raw = str(os.environ.get("HARNESS_CLI_WATCHDOG_WORKER_PID", "") or "").strip()
    done_file = str(os.environ.get("HARNESS_CLI_DONE_FILE", "") or "").strip()
    result_file = str(os.environ.get("HARNESS_CLI_RESULT_FILE", "") or "").strip()
    if not run_id or not worker_pid_raw or not done_file or not result_file:
        _LOG.error("watchdog missing required env")
        sys.exit(2)
    try:
        worker_pid = int(worker_pid_raw)
    except ValueError:
        _LOG.error("watchdog invalid worker pid")
        sys.exit(2)
    try:
        from harness.cli.run_state import run_dir

        run_path = run_dir(run_id)
    except Exception:
        _LOG.error("watchdog could not resolve run_dir for %s", run_id, exc_info=True)
        sys.exit(2)
    exit_code = run_watchdog_loop(
        run_dir=run_path,
        worker_pid=worker_pid,
        done_file=done_file,
        result_file=result_file,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
