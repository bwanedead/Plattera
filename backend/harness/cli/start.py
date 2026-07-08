"""Start a harness run in a background process; persist run-state; print JSON metadata."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .run_id_allocator import RunIdAllocatorError, allocate_automatic_run_id
from .run_layout import RunLayoutError, normalize_run_id
from .run_state import new_run_state, read_state, write_state
from .watchdog_spawn import spawn_run_control_watchdog
from harness.runtime.run_control_sidecar import (
    summarize_run_control_sidecar,
    write_initial_run_control_sidecar,
)


def _backend_cwd() -> str:
    return str(Path(__file__).resolve().parents[2])


def _print_json(obj: dict[str, Any]) -> None:
    sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def _child_env(
    *,
    paths,
    run_id: str,
    loop_kind: str,
    model: str | None = None,
) -> dict[str, str]:
    base = os.environ.copy()
    base["HARNESS_CLI_RUN_ID"] = run_id
    base["HARNESS_CLI_DONE_FILE"] = paths.done_file
    base["HARNESS_CLI_RESULT_FILE"] = paths.result_file
    base["HARNESS_CLI_STDOUT_LOG"] = paths.stdout_log
    base["HARNESS_CLI_STDERR_LOG"] = paths.stderr_log
    base["HARNESS_CLI_LOOP_KIND"] = loop_kind
    if str(model or "").strip():
        base["HARNESS_CLI_MODEL"] = str(model).strip()
    return base


def _popen_flags() -> dict[str, Any]:
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return {"creationflags": flags}
    return {"start_new_session": True}


def build_stub_argv() -> list[str]:
    return [sys.executable, "-m", "harness.cli.stub_worker"]


def build_module_argv(module: str, module_args: list[str]) -> list[str]:
    return [sys.executable, "-m", module, *module_args]


def _resolve_run_id(*, explicit_run_id: str | None, loop_kind: str):
    text = str(explicit_run_id or "").strip()
    if text:
        return normalize_run_id(text), None
    try:
        allocated = allocate_automatic_run_id(run_collection=loop_kind)
    except (RunLayoutError, RunIdAllocatorError) as exc:
        raise RunLayoutError(getattr(exc, "code", "run_id_allocation_failed")) from exc
    return allocated.run_id, allocated.run_dir


def start_run(
    *,
    run_id: str,
    loop_kind: str,
    mode: str,
    spawn_argv: list[str],
    model: str | None = None,
    child_env_extra: dict[str, str] | None = None,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    model_str = str(model or "").strip()
    extra: dict[str, Any] = {}
    if model_str:
        extra["model"] = model_str
    state = new_run_state(
        run_id=run_id,
        pid=0,
        loop_kind=loop_kind,
        mode=mode,
        spawn_argv=list(spawn_argv),
        status="spawning",
        extra=extra or None,
        run_dir=run_dir,
    )
    paths = state.paths
    human_timeline_path = str((Path(paths.run_dir) / "audit" / "human" / "timeline.md").resolve())
    Path(paths.run_dir).mkdir(parents=True, exist_ok=True)
    run_control_file = write_initial_run_control_sidecar(paths.run_dir)

    env = _child_env(paths=paths, run_id=run_id, loop_kind=loop_kind, model=model)
    if child_env_extra:
        env.update(child_env_extra)

    stdout_f = open(paths.stdout_log, "ab", buffering=0)
    stderr_f = open(paths.stderr_log, "ab", buffering=0)
    try:
        popen_kw = _popen_flags()
        proc = subprocess.Popen(
            spawn_argv,
            cwd=_backend_cwd(),
            stdin=subprocess.DEVNULL,
            stdout=stdout_f,
            stderr=stderr_f,
            env=env,
            close_fds=os.name != "nt",
            **popen_kw,
        )
    except Exception as exc:
        stdout_f.close()
        stderr_f.close()
        state.status = f"spawn_failed:{exc}"
        state.pid = 0
        write_state(state)
        return {
            "run_id": run_id,
            "pid": None,
            "run_collection": state.run_collection,
            "run_dir": paths.run_dir,
            "human_timeline_path": human_timeline_path,
            "run_control_file": str(run_control_file.resolve()),
            "done_file": paths.done_file,
            "result_file": paths.result_file,
            "log_file": paths.stdout_log,
            "stdout_log": paths.stdout_log,
            "stderr_log": paths.stderr_log,
            "state_file": paths.state_file,
            "status": state.status,
            "mode": mode,
            "loop_kind": loop_kind,
            "model": str(model or "").strip() or None,
            "error": str(exc),
        }

    stdout_f.close()
    stderr_f.close()

    fresh = read_state(run_id)
    if fresh is not None:
        fresh.pid = int(proc.pid or 0)
        fresh.status = "started"
        write_state(fresh)
        state = fresh
    else:
        state.pid = int(proc.pid or 0)
        state.status = "started"
        write_state(state)

    spawn_run_control_watchdog(worker_pid=int(state.pid or 0), paths=paths, run_id=run_id)

    return {
        "run_id": run_id,
        "pid": state.pid,
        "run_collection": state.run_collection,
        "run_dir": paths.run_dir,
        "human_timeline_path": human_timeline_path,
        "run_control_file": str(run_control_file.resolve()),
        "run_control_state": summarize_run_control_sidecar(run_control_file),
        "done_file": paths.done_file,
        "result_file": paths.result_file,
        "log_file": paths.stdout_log,
        "stdout_log": paths.stdout_log,
        "stderr_log": paths.stderr_log,
        "state_file": paths.state_file,
        "status": state.status,
        "mode": mode,
        "loop_kind": loop_kind,
        "model": str(model or "").strip() or None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="harness.cli.start",
        description="Spawn a background harness run with durable run-state under harness artifacts.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Explicit run id (default: auto-allocated per loop-kind sequence).",
    )
    parser.add_argument(
        "--loop-kind",
        default="harness_cli",
        help="Feedback-store namespace for HITL inject/watch (default: harness_cli).",
    )
    parser.add_argument(
        "--mode",
        default=None,
        help="Opaque mode tag stored in state (default: stub or python module name).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Optional model override for the child run. "
            "Passed through via HARNESS_CLI_MODEL and used only if launch context omits model."
        ),
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument(
        "--stub",
        action="store_true",
        help="Run harness.cli.stub_worker (default when neither --stub nor --python-module is set).",
    )
    g.add_argument("--python-module", default=None, help="Run `python -m <module>` with optional --module-arg values.")
    parser.add_argument(
        "--module-arg",
        action="append",
        default=[],
        help="Extra argv segment after `-m module` (repeatable). Ignored without --python-module.",
    )
    args = parser.parse_args()

    loop_kind = str(args.loop_kind or "harness_cli").strip() or "harness_cli"
    try:
        run_id, preallocated_run_dir = _resolve_run_id(explicit_run_id=args.run_id, loop_kind=loop_kind)
    except RunLayoutError as exc:
        _print_json({"status": "error", "error": exc.code})
        sys.exit(2)

    use_stub = args.stub or not args.python_module
    if use_stub:
        spawn_argv = build_stub_argv()
        mode = args.mode or "stub"
    else:
        mod = str(args.python_module).strip()
        if not mod:
            _print_json({"status": "error", "error": "empty_python_module"})
            sys.exit(2)
        spawn_argv = build_module_argv(mod, list(args.module_arg or []))
        mode = args.mode or mod

    out = start_run(
        run_id=run_id,
        loop_kind=loop_kind,
        mode=mode,
        spawn_argv=spawn_argv,
        model=str(args.model or "").strip() or None,
        run_dir=preallocated_run_dir,
    )
    _print_json(out)
    if out.get("status", "").startswith("spawn_failed"):
        sys.exit(1)


if __name__ == "__main__":
    main()
