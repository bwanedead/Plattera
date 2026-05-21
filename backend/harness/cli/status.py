"""Lightweight run inspection: process, artifacts, optional HITL pending."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from harness.runtime.control import read_run_control_request
from harness.runtime.hitl.watch import hitl_pending_path
from harness.runtime.model_failure_classifier import resume_hint_for_reason_code

from ._process_util import is_pid_alive
from .run_state import read_state, run_dir

_OPERATOR_INTERRUPT_REASON_CODES = {"paused_by_operator", "stopped_by_operator"}


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
    result_payload = _read_result_payload(result_p) if result_p.is_file() else None

    pid = int(state.pid)
    alive: bool | None
    if pid <= 0:
        alive = None
    else:
        alive = is_pid_alive(pid)

    # Mechanical dead-run classification: if the process is not alive, surface
    # operator interruptions first; otherwise fall back to resume-checkpoint hints
    # for abruptly interrupted runs with no terminal artifacts.
    interrupted_classification: dict[str, Any] | None = None
    if alive is False:
        result_reason_code = str((result_payload or {}).get("reason_code") or "").strip()
        if result_reason_code in _OPERATOR_INTERRUPT_REASON_CODES:
            interrupted_classification = {
                "kind": result_reason_code,
                "resumable": bool((result_payload or {}).get("resumable", True)),
                "interrupted_at_iteration": (result_payload or {}).get("interrupted_at_iteration"),
                "control_request": (result_payload or {}).get("control_request"),
            }
        elif not result_p.is_file() and not done_p.is_file():
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

    # Mechanical pending-control surface: if a live process has an un-consumed
    # control.json, show the operator that a pause/stop is in flight.
    control_classification: dict[str, Any] | None = None
    if alive is True:
        pending = read_run_control_request(run_dir(run_id) / "control.json")
        if pending is not None:
            control_classification = {
                "command": pending.command,
                "request_id": pending.request_id,
                "status": "pending",
                "requested_at_epoch_seconds": pending.requested_at_epoch_seconds,
                "reason": pending.reason,
                "requested_by": pending.requested_by,
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
    if control_classification is not None:
        out["control"] = control_classification
    if result_payload is not None:
        if bool(result_payload.get("resumable")):
            out["resumable"] = True
        reason_code = str(result_payload.get("reason_code") or "").strip()
        if reason_code:
            out["reason_code"] = reason_code
        resume_hint = result_payload.get("resume_hint")
        if isinstance(resume_hint, str) and resume_hint.strip():
            out["resume_hint"] = resume_hint.strip()
        elif reason_code:
            guided = resume_hint_for_reason_code(reason_code)
            if guided:
                out["resume_hint"] = guided
    return out


def _read_result_payload(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def main() -> None:
    parser = argparse.ArgumentParser(prog="harness.cli.status", description="Inspect harness CLI run-state.")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    _print_json(status_run(run_id=args.run_id.strip()))


if __name__ == "__main__":
    main()
