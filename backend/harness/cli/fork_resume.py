"""Fork a harness CLI run from a persisted per-turn checkpoint into a new child run.

Mechanical only: copies spawn argv, points the new worker at the selected checkpoint,
records fork lineage, and leaves the source run untouched.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from time import time
from typing import Any

from harness.runtime.run_control_sidecar import write_initial_run_control_sidecar
from .fork_continue_eligibility import continue_pre_allocate_refusal
from .fork_workspace import (
    DEFAULT_WORKSPACE_MODE,
    WORKSPACE_MODE_CONTINUE,
    WORKSPACE_MODES,
    parse_workspace_mode,
    prepare_continue_spawn_argv,
    prepare_isolated_spawn_argv,
)
from .workspace_claim import (
    acquire_continue_workspace_claim,
    refuse_continue_workspace_busy,
    release_continue_workspace_claim,
)
from .resume_paths import (
    RESUME_CHECKPOINT_FILENAME,
    resolve_existing_turn_checkpoint,
    turn_checkpoint_canonical_path,
)
from .run_id_allocator import RunIdAllocatorError, allocate_automatic_run_id
from .run_layout import RunLayoutError
from .run_state import new_run_state, read_state, run_dir, write_state
from .start import _backend_cwd, _child_env, _popen_flags
from .watchdog_spawn import spawn_run_control_watchdog
from harness.runtime.memory.resume_snapshot import parse_kernel_resume_snapshot
from harness.runtime.memory.resume_snapshot_storage import load_kernel_resume_snapshot_from_path


def fork_run_from_turn(
    *,
    run_id: str,
    from_turn: int,
    workspace_mode: str | None = None,
) -> dict[str, Any]:
    """Create a new child run that resumes from a selected per-turn checkpoint."""
    source_id = str(run_id or "").strip()
    turn = int(from_turn)
    if not source_id:
        return {"status": "refused", "reason_code": "run_id_required"}
    if turn < 1:
        return {"status": "refused", "run_id": source_id, "reason_code": "from_turn_invalid"}
    mode, mode_err = parse_workspace_mode(workspace_mode)
    if mode_err or mode is None:
        return {
            "status": "refused",
            "run_id": source_id,
            "reason_code": mode_err or "workspace_mode_invalid",
        }

    source_state = read_state(source_id)
    if source_state is None:
        return {"status": "refused", "run_id": source_id, "reason_code": "missing_state"}

    source_run_dir = run_dir(source_id)
    checkpoint = resolve_existing_turn_checkpoint(run_dir=source_run_dir, from_turn=turn)
    if checkpoint is None:
        expected = turn_checkpoint_canonical_path(run_dir=source_run_dir, from_turn=turn)
        latest = source_run_dir / RESUME_CHECKPOINT_FILENAME
        suggestion = None
        if latest.is_file():
            suggestion = f"python -m harness.cli.resume --run-id {source_id}"
        return {
            "status": "refused",
            "run_id": source_id,
            "reason_code": "turn_checkpoint_missing",
            "from_turn": turn,
            "expected_checkpoint_path": str(expected.resolve()),
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

    continued_workspace: str | None = None
    if mode == WORKSPACE_MODE_CONTINUE:
        gate = continue_pre_allocate_refusal(
            source_run_id=source_id,
            source_state=source_state,
            source_run_dir=source_run_dir,
            from_turn=turn,
        )
        if gate:
            return {"status": "refused", "run_id": source_id, "reason_code": gate}
        child_argv, continued_workspace, ws_err = prepare_continue_spawn_argv(
            spawn_argv=list(source_state.spawn_argv),
            source_run_id=source_id,
        )
        if ws_err or child_argv is None or continued_workspace is None:
            return {
                "status": "refused",
                "run_id": source_id,
                "reason_code": ws_err or "workspace_id_invalid",
            }
        busy = refuse_continue_workspace_busy(
            workspace_id=continued_workspace,
            source_run_id=source_id,
        )
        if busy:
            return {"status": "refused", "run_id": source_id, "reason_code": busy}
    else:
        child_argv = prepare_isolated_spawn_argv(list(source_state.spawn_argv))

    try:
        allocated = allocate_automatic_run_id(run_collection=source_state.run_collection)
    except (RunLayoutError, RunIdAllocatorError) as exc:
        return {
            "status": "refused",
            "run_id": source_id,
            "reason_code": getattr(exc, "code", "run_id_allocation_failed"),
        }

    child_id = allocated.run_id
    fork_lineage: dict[str, Any] = {
        "forked_from_run_id": source_id,
        "forked_from_turn": turn,
        "source_checkpoint_path": str(checkpoint.resolve()),
        "workspace_mode": mode,
    }
    if continued_workspace is not None:
        fork_lineage["source_workspace_id"] = continued_workspace
    model_env = source_state.extra.get("model") if isinstance(source_state.extra, dict) else None
    max_llm_calls = source_state.extra.get("max_llm_calls") if isinstance(source_state.extra, dict) else None
    if isinstance(source_state.extra, dict) and "max_llm_calls" in source_state.extra and (
        type(max_llm_calls) is not int or max_llm_calls < 0
    ):
        return {
            "status": "refused",
            "run_id": source_id,
            "reason_code": "logical_llm_call_budget_invalid",
        }
    child_state = new_run_state(
        run_id=child_id,
        pid=0,
        loop_kind=source_state.loop_kind,
        mode=source_state.mode,
        spawn_argv=child_argv,
        status="fork_started",
        extra={
            "fork_lineage": fork_lineage,
            **({"model": model_env} if model_env else {}),
            **({"max_llm_calls": max_llm_calls} if type(max_llm_calls) is int else {}),
        },
        run_dir=allocated.run_dir,
        run_collection=source_state.run_collection,
    )
    allocated.run_dir.mkdir(parents=True, exist_ok=True)
    write_initial_run_control_sidecar(allocated.run_dir)
    write_state(child_state)

    claimed = False
    if mode == WORKSPACE_MODE_CONTINUE and continued_workspace is not None:
        claim_err = acquire_continue_workspace_claim(
            workspace_id=continued_workspace,
            owner_run_id=child_id,
        )
        if claim_err:
            child_state.status = "fork_aborted"
            write_state(child_state)
            return {
                "status": "refused",
                "run_id": source_id,
                "reason_code": claim_err,
                "workspace_mode": mode,
            }
        claimed = True
        gate_again = continue_pre_allocate_refusal(
            source_run_id=source_id,
            source_state=source_state,
            source_run_dir=source_run_dir,
            from_turn=turn,
        )
        busy_again = refuse_continue_workspace_busy(
            workspace_id=continued_workspace,
            source_run_id=source_id,
            exclude_run_id=child_id,
        )
        if gate_again or busy_again:
            release_continue_workspace_claim(
                workspace_id=continued_workspace,
                owner_run_id=child_id,
            )
            child_state.status = "fork_aborted"
            write_state(child_state)
            return {
                "status": "refused",
                "run_id": source_id,
                "reason_code": gate_again or busy_again,
                "workspace_mode": mode,
            }

    env = _child_env(
        paths=child_state.paths,
        run_id=child_id,
        loop_kind=child_state.loop_kind,
        model=model_env if isinstance(model_env, str) else None,
        max_llm_calls=max_llm_calls if type(max_llm_calls) is int else None,
        forked_run=True,
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
    except Exception:
        stdout_f.close()
        stderr_f.close()
        if claimed and continued_workspace is not None:
            release_continue_workspace_claim(
                workspace_id=continued_workspace,
                owner_run_id=child_id,
            )
        child_state.status = "fork_spawn_failed"
        write_state(child_state)
        return {
            "status": "fork_spawn_failed",
            "run_id": child_id,
            "source_run_id": source_id,
            "reason_code": "spawn_failed",
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
        "workspace_mode": mode,
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
            "Completed turn to resume after (matches resume_checkpoints/turn_NNNN.json.gz; "
            "legacy turn_NNNN.json still readable; snapshot next_iteration must equal N+1)."
        ),
    )
    parser.add_argument(
        "--workspace-mode",
        choices=sorted(WORKSPACE_MODES),
        default=DEFAULT_WORKSPACE_MODE,
        help=(
            "isolated: new run_id and workspace_id (default). "
            "continue: new run_id, preserve source workspace_id; latest failed/exhausted checkpoint only."
        ),
    )
    args = parser.parse_args()
    _print_json(
        fork_run_from_turn(
            run_id=args.run_id.strip(),
            from_turn=int(args.from_turn),
            workspace_mode=args.workspace_mode,
        )
    )


if __name__ == "__main__":
    main()
