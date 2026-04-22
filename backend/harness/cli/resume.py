"""Re-spawn a harness CLI run from its persisted ``kernel_resume.json`` checkpoint.

Mechanical only: validates refusal guards, then spawns the original ``spawn_argv`` with
``HARNESS_CLI_RESUME_FILE`` pointing at the checkpoint so the runner picks it up via the
existing resume-snapshot path seam. No semantic interpretation of checkpoint contents.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from ._process_util import is_pid_alive
from .run_state import read_state, run_dir, write_state
from .start import _child_env, _popen_flags, _backend_cwd
from harness.runtime.control import (
    CONTROL_FILENAME,
    consume_run_control_request,
)
from harness.runtime.memory.resume_snapshot import (
    load_kernel_resume_snapshot_from_path,
    parse_kernel_resume_snapshot,
)


RESUME_CHECKPOINT_FILENAME = "kernel_resume.json"
_RESULT_RESUMABLE_REASON_CODES = {
    "model_call_failed",
    "provider_connection_error",
    "provider_error",
    "rate_limit",
    "rate_limited",
    "connection_error",
    "connection_timeout",
    "timeout",
    "transient_failure",
    "paused_by_operator",
    "stopped_by_operator",
}


def _checkpoint_path(run_id: str) -> Path:
    return run_dir(run_id) / RESUME_CHECKPOINT_FILENAME


def _read_result_file(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"result_unreadable:{exc}"
    if not isinstance(raw, dict):
        return None, "result_not_object"
    return raw, None


def _normalize_result_token(value: Any) -> str:
    return str(value or "").strip().lower()


def _result_reason_code(result: Mapping[str, Any]) -> str | None:
    reason = _normalize_result_token(result.get("reason_code"))
    return reason or None


def _result_allows_resume(result: Mapping[str, Any]) -> bool:
    status = _normalize_result_token(result.get("status"))
    terminal_class = _normalize_result_token(result.get("terminal_class"))
    if status in {"completed", "complete", "succeeded", "success"}:
        return False
    if terminal_class in {"completed", "complete", "succeeded", "success"}:
        return False

    resumable = result.get("resumable")
    if isinstance(resumable, bool):
        return resumable

    reason_code = _result_reason_code(result)
    if reason_code == "complete_run":
        return False
    return reason_code in _RESULT_RESUMABLE_REASON_CODES


def classify_resumability(run_id: str) -> dict[str, Any]:
    """Return a mechanical classification of whether this run can be resumed.

    Keys:
      - ``resumability``: one of ``resumable``, ``failed_resumable``, ``no_checkpoint``,
        ``terminal_done``, ``terminal_result``, ``process_alive``, ``missing_state``,
        ``checkpoint_unreadable``, ``checkpoint_invalid``
      - ``reason_code``: human-usable short code (same vocabulary)
      - ``checkpoint_path``: path string if the checkpoint exists
      - ``resume_command``: shell hint if resumable
    """
    state = read_state(run_id)
    if state is None:
        return {
            "run_id": run_id,
            "resumability": "missing_state",
            "reason_code": "missing_state",
        }
    done_p = Path(state.paths.done_file)
    result_p = Path(state.paths.result_file)
    checkpoint = _checkpoint_path(run_id)
    pid_alive = is_pid_alive(int(state.pid)) if state.pid else False

    result_doc: dict[str, Any] | None = None
    result_reason_code: str | None = None
    if result_p.is_file():
        result_doc, result_err = _read_result_file(result_p)
        if result_doc is None and not done_p.is_file():
            return {
                "run_id": run_id,
                "resumability": "terminal_result",
                "reason_code": result_err or "run_has_result_file",
                "checkpoint_path": str(checkpoint) if checkpoint.is_file() else None,
            }
        if result_doc is not None:
            result_reason_code = _result_reason_code(result_doc)

    if done_p.is_file():
        if result_doc is not None and _result_allows_resume(result_doc):
            if pid_alive:
                return {
                    "run_id": run_id,
                    "resumability": "process_alive",
                    "reason_code": "run_still_running",
                    "pid": int(state.pid),
                    "checkpoint_path": str(checkpoint) if checkpoint.is_file() else None,
                }
        else:
            reason_code = result_reason_code or "run_has_done_sentinel"
            return {
                "run_id": run_id,
                "resumability": "terminal_done",
                "reason_code": reason_code,
                "checkpoint_path": str(checkpoint) if checkpoint.is_file() else None,
            }
    if pid_alive:
        return {
            "run_id": run_id,
            "resumability": "process_alive",
            "reason_code": "run_still_running",
            "pid": int(state.pid),
            "checkpoint_path": str(checkpoint) if checkpoint.is_file() else None,
        }
    if result_p.is_file():
        assert result_doc is not None or done_p.is_file()
        if result_doc is None:
            return {
                "run_id": run_id,
                "resumability": "terminal_result",
                "reason_code": result_err or "run_has_result_file",
                "checkpoint_path": str(checkpoint) if checkpoint.is_file() else None,
            }
        result_reason_code = _result_reason_code(result_doc)
        if not _result_allows_resume(result_doc):
            return {
                "run_id": run_id,
                "resumability": "terminal_result",
                "reason_code": result_reason_code or "run_has_result_file",
                "checkpoint_path": str(checkpoint) if checkpoint.is_file() else None,
            }
    if not checkpoint.is_file():
        return {
            "run_id": run_id,
            "resumability": "no_checkpoint",
            "reason_code": "no_checkpoint",
        }

    doc, load_err = load_kernel_resume_snapshot_from_path(checkpoint)
    if load_err or doc is None:
        return {
            "run_id": run_id,
            "resumability": "checkpoint_unreadable",
            "reason_code": load_err or "checkpoint_unreadable",
            "checkpoint_path": str(checkpoint),
        }
    _, _, parse_err = parse_kernel_resume_snapshot(doc)
    if parse_err:
        return {
            "run_id": run_id,
            "resumability": "checkpoint_invalid",
            "reason_code": parse_err,
            "checkpoint_path": str(checkpoint),
        }
    if result_doc is not None:
        return {
            "run_id": run_id,
            "resumability": "failed_resumable",
            "reason_code": result_reason_code or "failed_resumable",
            "checkpoint_path": str(checkpoint),
            "resume_command": f"python -m harness.cli.resume --run-id {run_id}",
        }
    return {
        "run_id": run_id,
        "resumability": "resumable",
        "reason_code": "ok",
        "checkpoint_path": str(checkpoint),
        "resume_command": f"python -m harness.cli.resume --run-id {run_id}",
    }


def resume_run(*, run_id: str) -> dict[str, Any]:
    """Validate guards and re-spawn the worker with ``HARNESS_CLI_RESUME_FILE`` injected."""
    cls = classify_resumability(run_id)
    if cls.get("resumability") not in {"resumable", "failed_resumable"}:
        return {
            "status": "refused",
            "run_id": run_id,
            "reason_code": cls.get("reason_code") or cls.get("resumability"),
            "classification": cls,
        }

    state = read_state(run_id)
    if state is None:
        return {"status": "refused", "run_id": run_id, "reason_code": "missing_state"}

    checkpoint = str(_checkpoint_path(run_id).resolve())
    # Consume any pending operator control request so the resumed run does not
    # immediately honor a stale pause/stop on its first safe boundary.
    consume_run_control_request(run_dir(run_id) / CONTROL_FILENAME)
    paths = state.paths
    model_env = state.extra.get("model") if isinstance(state.extra, dict) else None
    env = _child_env(paths=paths, run_id=run_id, loop_kind=state.loop_kind, model=model_env)
    env["HARNESS_CLI_RESUME_FILE"] = checkpoint

    stdout_f = open(paths.stdout_log, "ab", buffering=0)
    stderr_f = open(paths.stderr_log, "ab", buffering=0)
    try:
        popen_kw = _popen_flags()
        proc = subprocess.Popen(
            list(state.spawn_argv),
            cwd=_backend_cwd(),
            stdin=subprocess.DEVNULL,
            stdout=stdout_f,
            stderr=stderr_f,
            env=env,
            close_fds=sys.platform != "win32",
            **popen_kw,
        )
    except Exception as exc:
        stdout_f.close()
        stderr_f.close()
        state.status = f"resume_spawn_failed:{exc}"
        write_state(state)
        return {
            "status": "resume_spawn_failed",
            "run_id": run_id,
            "reason_code": "spawn_failed",
            "error": str(exc),
        }
    stdout_f.close()
    stderr_f.close()

    state.pid = int(proc.pid or 0)
    state.status = "resumed"
    # Record resume lineage mechanically.
    extra = dict(state.extra or {})
    resumes = list(extra.get("resume_events") or [])
    resumes.append({"checkpoint_path": checkpoint, "pid": state.pid})
    extra["resume_events"] = resumes
    state.extra = extra
    write_state(state)

    return {
        "status": "resumed",
        "run_id": run_id,
        "pid": state.pid,
        "checkpoint_path": checkpoint,
        "done_file": paths.done_file,
        "result_file": paths.result_file,
        "state_file": paths.state_file,
    }


def _print_json(obj: dict[str, Any]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="harness.cli.resume",
        description="Re-spawn a harness CLI run from its kernel_resume.json checkpoint.",
    )
    parser.add_argument("--run-id", required=True, help="Run id of the interrupted run.")
    parser.add_argument(
        "--classify-only",
        action="store_true",
        help="Report the resumability classification without re-spawning.",
    )
    args = parser.parse_args()

    run_id = args.run_id.strip()
    if args.classify_only:
        _print_json(classify_resumability(run_id))
        return

    out = resume_run(run_id=run_id)
    _print_json(out)
    if out.get("status") != "resumed":
        sys.exit(2)


if __name__ == "__main__":
    main()
