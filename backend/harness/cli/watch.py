"""Block until HITL, loop_done, or timeout using persisted run-state paths."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from harness.runtime.hitl.watch import run_watch

from .run_state import read_state


def _print_json(obj: dict[str, Any]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def watch_run(
    *,
    run_id: str,
    timeout_seconds: int,
    poll_interval: float,
) -> dict[str, Any]:
    state = read_state(run_id)
    if state is None:
        return {"event": "error", "reason": "missing_run_state", "run_id": run_id}
    done_file = state.paths.done_file or None
    return run_watch(
        run_id=run_id,
        done_file=done_file,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="harness.cli.watch",
        description="Block until HITL pending, done sentinel from run-state, or timeout.",
    )
    parser.add_argument("--run-id", required=True, help="Run id used with harness.cli.start.")
    parser.add_argument("--timeout", type=int, default=600, help="Seconds to wait (default: 600).")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Poll interval in seconds.")
    args = parser.parse_args()

    result = watch_run(
        run_id=args.run_id.strip(),
        timeout_seconds=max(1, int(args.timeout)),
        poll_interval=float(args.poll_interval),
    )
    _print_json(result)
    if result.get("event") == "error":
        sys.exit(2)


if __name__ == "__main__":
    main()
