"""Start a harness run in a background process; persist run-state; print JSON metadata."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from .run_state import new_run_state, write_state


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


def start_run(
    *,
    run_id: str,
    loop_kind: str,
    mode: str,
    spawn_argv: list[str],
    model: str | None = None,
    child_env_extra: dict[str, str] | None = None,
) -> dict[str, Any]:
    state = new_run_state(
        run_id=run_id,
        pid=0,
        loop_kind=loop_kind,
        mode=mode,
        spawn_argv=list(spawn_argv),
        status="spawning",
    )
    paths = state.paths
    Path(paths.run_dir).mkdir(parents=True, exist_ok=True)

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

    state.pid = int(proc.pid or 0)
    state.status = "started"
    write_state(state)

    return {
        "run_id": run_id,
        "pid": state.pid,
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
    parser.add_argument("--run-id", default=None, help="Explicit run id (default: random hcli- prefix).")
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

    run_id = (args.run_id or "").strip() or f"hcli-{uuid.uuid4().hex[:12]}"
    loop_kind = str(args.loop_kind or "harness_cli").strip() or "harness_cli"

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
    )
    _print_json(out)
    if out.get("status", "").startswith("spawn_failed"):
        sys.exit(1)


if __name__ == "__main__":
    main()
