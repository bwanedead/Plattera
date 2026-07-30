"""Fork a harness CLI run from a persisted per-turn checkpoint into a new child run.

Mechanical only: copies spawn argv, points the new worker at the selected checkpoint,
records fork lineage, and leaves the source run untouched.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from time import time
from typing import Any

from harness.runtime.run_control_sidecar import write_initial_run_control_sidecar
from .fork_spawn_argv import strip_launch_context_identity_for_fork
from .resume_paths import RESUME_CHECKPOINT_FILENAME, turn_checkpoint_path
from .run_id_allocator import RunIdAllocatorError, allocate_automatic_run_id
from .run_layout import RunLayoutError
from .run_state import new_run_state, read_state, run_dir, write_state
from .start import _backend_cwd, _child_env, _popen_flags
from .watchdog_spawn import spawn_run_control_watchdog
from harness.runtime.memory.resume_snapshot import (
    load_kernel_resume_snapshot_from_path,
    parse_kernel_resume_snapshot,
)


def fork_run_from_turn(*, run_id: str, from_turn: int) -> dict[str, Any]:
    """Create a new child run that resumes from a selected per-turn checkpoint."""
    source_id = str(run_id or "").strip()
    turn = int(from_turn)
    if not source_id:
        return {"status": "refused", "reason_code": "run_id_required"}
    if turn < 1:
        return {"status": "refused", "run_id": source_id, "reason_code": "from_turn_invalid"}

    source_state = read_state(source_id)
    if source_state is None:
        return {"status": "refused", "run_id": source_id, "reason_code": "missing_state"}

    source_run_dir = run_dir(source_id)
    checkpoint = turn_checkpoint_path(run_dir=source_run_dir, from_turn=turn)
    if not checkpoint.is_file():
        latest = source_run_dir / RESUME_CHECKPOINT_FILENAME
        suggestion = None
        if latest.is_file():
            suggestion = f"python -m harness.cli.resume --run-id {source_id}"
        return {
            "status": "refused",
            "run_id": source_id,
            "reason_code": "turn_checkpoint_missing",
            "from_turn": turn,
            "expected_checkpoint_path": str(checkpoint.resolve()),
            "resume_latest_command": suggestion,
        }

    doc, load_err = load_kernel_resume_snapshot_from_path(checkpoint)
    if load_err or doc is None:
        return {
            "status": "refused",
            "run_id": source_id,
            "reason_code": load_err or "checkpoint_unreadable",
            "from_turn": turn,
            "checkpoint_path": str(checkpoint.resolve()),
        }
    _, _, parse_err = parse_kernel_resume_snapshot(doc)
    if parse_err:
        return {
            "status": "refused",
            "run_id": source_id,
            "reason_code": parse_err,
            "from_turn": turn,
            "checkpoint_path": str(checkpoint.resolve()),
        }

    expected_next_iteration = turn + 1
    snapshot_next = doc.get("next_iteration")
    if snapshot_next != expected_next_iteration:
        return {
            "status": "refused",
            "run_id": source_id,
            "reason_code": "checkpoint_turn_mismatch",
            "from_turn": turn,
            "expected_next_iteration": expected_next_iteration,
            "checkpoint_next_iteration": snapshot_next,
            "checkpoint_path": str(checkpoint.resolve()),
        }

    try:
        allocated = allocate_automatic_run_id(run_collection=source_state.run_collection)
    except (RunLayoutError, RunIdAllocatorError) as exc:
        return {
            "status": "refused",
            "run_id": source_id,
            "reason_code": getattr(exc, "code", "run_id_allocation_failed"),
        }

    child_id = allocated.run_id
    fork_lineage = {
        "forked_from_run_id": source_id,
        "forked_from_turn": turn,
        "source_checkpoint_path": str(checkpoint.resolve()),
    }
    model_env = source_state.extra.get("model") if isinstance(source_state.extra, dict) else None
    child_state = new_run_state(
        run_id=child_id,
        pid=0,
        loop_kind=source_state.loop_kind,
        mode=source_state.mode,
        spawn_argv=strip_launch_context_identity_for_fork(list(source_state.spawn_argv)),
        status="fork_started",
        extra={
            "fork_lineage": fork_lineage,
            **({"model": model_env} if model_env else {}),
        },
        run_dir=allocated.run_dir,
        run_collection=source_state.run_collection,
    )
    allocated.run_dir.mkdir(parents=True, exist_ok=True)
    write_initial_run_control_sidecar(allocated.run_dir)
    write_state(child_state)

    env = _child_env(
        paths=child_state.paths,
        run_id=child_id,
        loop_kind=child_state.loop_kind,
        model=model_env if isinstance(model_env, str) else None,
    )
    env["HARNESS_CLI_RESUME_FILE"] = str(checkpoint.resolve())

    stdout_f = open(child_state.paths.stdout_log, "ab", buffering=0)
    stderr_f = open(child_state.paths.stderr_log, "ab", buffering=0)
    try:
        proc = subprocess.Popen(
            list(child_state.spawn_argv),
            cwd=_backend_cwd(),
            stdin=subprocess.DEVNULL,
            stdout=stdout_f,
            stderr=stderr_f,
            env=env,
            close_fds=sys.platform != "win32",
            **_popen_flags(),
        )
    except Exception as exc:
        stdout_f.close()
        stderr_f.close()
        child_state.status = f"fork_spawn_failed:{exc}"
        write_state(child_state)
        return {
            "status": "fork_spawn_failed",
            "run_id": child_id,
            "source_run_id": source_id,
            "reason_code": "spawn_failed",
            "error": str(exc),
            "fork_lineage": fork_lineage,
        }
    stdout_f.close()
    stderr_f.close()

    child_state.pid = int(proc.pid or 0)
    child_state.status = "forked"
    write_state(child_state)
    spawn_run_control_watchdog(worker_pid=child_state.pid, paths=child_state.paths, run_id=child_id)

    return {
        "status": "forked",
        "run_id": child_id,
        "pid": child_state.pid,
        "source_run_id": source_id,
        "from_turn": turn,
        "checkpoint_path": str(checkpoint.resolve()),
        "fork_lineage": fork_lineage,
        "run_collection": child_state.run_collection,
        "loop_kind": child_state.loop_kind,
        "human_timeline_path": str(allocated.human_timeline_path.resolve()),
        "done_file": child_state.paths.done_file,
        "result_file": child_state.paths.result_file,
        "state_file": child_state.paths.state_file,
        "started_at_epoch_seconds": time(),
    }


def _print_json(obj: dict[str, Any]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="harness.cli.fork_resume",
        description="Fork a harness CLI run from a per-turn checkpoint into a new child run.",
    )
    parser.add_argument("--run-id", required=True, help="Source run id to fork from.")
    parser.add_argument(
        "--from-turn",
        required=True,
        type=int,
        help=(
            "Completed turn to resume after (matches resume_checkpoints/turn_NNNN.json; "
            "snapshot next_iteration must equal N+1)."
        ),
    )
    args = parser.parse_args()
    _print_json(fork_run_from_turn(run_id=args.run_id.strip(), from_turn=int(args.from_turn)))


if __name__ == "__main__":
    main()
