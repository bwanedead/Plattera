"""Block until HITL, loop_done, or timeout using persisted run-state paths."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from harness.runtime.hitl.watch import run_watch

from .run_state import read_state


def _latest_resume_started_at_epoch_seconds(extra: dict[str, Any]) -> float | None:
    resume_events = extra.get("resume_events") if isinstance(extra, dict) else None
    if not isinstance(resume_events, list):
        return None
    for event in reversed(resume_events):
        if not isinstance(event, dict):
            continue
        raw = event.get("started_at_epoch_seconds")
        if raw is None:
            continue
        try:
            started_at = float(raw)
        except (TypeError, ValueError):
            continue
        if started_at > 0:
            return started_at
    return None


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
    done_not_before = _latest_resume_started_at_epoch_seconds(state.extra)
    return run_watch(
        run_id=run_id,
        done_file=done_file,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
        done_not_before_epoch_seconds=done_not_before,
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
