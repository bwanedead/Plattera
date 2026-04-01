"""Blocking watcher for CLI agent-mode HITL testing.

Polls for two signals:
- HITL prompt file: written by the running loop when human feedback is needed
- Done sentinel file: written by mission_flow_cli when the loop completes

Exits immediately when either signal arrives, printing a single JSON line:
  {"event": "hitl", "run_id": ..., "prompt_id": ..., "message": ..., "choices": [...]}
  {"event": "loop_done", "status": ..., "terminal": ...}
  {"event": "timeout", "timeout_seconds": ...}

Usage pattern for agent testing:
  # 1. Start loop in background
  python -m api.mission_flow_cli --mission-id myrun ... --done-file /tmp/done_myrun.json > /tmp/result_myrun.json &

  # 2. Watch (blocking) — exits when HITL arrives or loop finishes
  python -m harness.runtime.hitl.watch --run-id mission-myrun-tx --done-file /tmp/done_myrun.json

  # 3a. If event=hitl: inject feedback, then re-watch
  python -m harness.runtime.hitl.inject --loop-kind mission_flow_cli --run-id mission-myrun-tx --prompt-id <id> --choice "75"
  python -m harness.runtime.hitl.watch --run-id mission-myrun-tx --done-file /tmp/done_myrun.json

  # 3b. If event=loop_done: read /tmp/result_myrun.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from config.paths import dossiers_artifacts_root


def hitl_pending_path(run_id: str) -> Path:
    return dossiers_artifacts_root() / "hitl_prompts" / f"{run_id}_pending.json"


def _poll(
    *,
    run_id: str,
    done_file: Path | None,
    timeout_seconds: int,
    poll_interval: float = 2.0,
) -> dict:
    hitl_path = hitl_pending_path(run_id)
    deadline = time.time() + max(1, timeout_seconds)

    while time.time() < deadline:
        # Check for HITL prompt first — takes priority.
        if hitl_path.exists():
            try:
                payload = json.loads(hitl_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            try:
                hitl_path.unlink(missing_ok=True)
            except Exception:
                pass
            return {
                "event": "hitl",
                "run_id": run_id,
                "prompt_id": payload.get("prompt_id"),
                "message": payload.get("message"),
                "choices": payload.get("choices") or [],
                "context": payload.get("context") or {},
            }

        # Check for loop completion.
        if done_file is not None and done_file.exists():
            try:
                payload = json.loads(done_file.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            return {
                "event": "loop_done",
                "status": payload.get("status"),
                "terminal": payload.get("terminal"),
                "reason_code": payload.get("reason_code"),
            }

        time.sleep(poll_interval)

    return {"event": "timeout", "timeout_seconds": timeout_seconds}


def run_watch(
    *,
    run_id: str,
    done_file: str | None,
    timeout_seconds: int,
) -> dict:
    done_path = Path(done_file) if done_file else None
    return _poll(run_id=run_id, done_file=done_path, timeout_seconds=timeout_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hitl-watch",
        description="Block until a HITL prompt or loop-done sentinel appears for a given run.",
    )
    parser.add_argument("--run-id", required=True, help="The mission-flow request prefix (e.g. mission-myrun-tx).")
    parser.add_argument("--done-file", default=None, help="Path to the done-sentinel file written by mission_flow_cli.")
    parser.add_argument("--timeout", type=int, default=600, help="Max seconds to wait before giving up (default: 600).")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Poll interval in seconds (default: 2.0).")
    args = parser.parse_args()

    result = _poll(
        run_id=args.run_id,
        done_file=Path(args.done_file) if args.done_file else None,
        timeout_seconds=args.timeout,
        poll_interval=args.poll_interval,
    )
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
    print(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
