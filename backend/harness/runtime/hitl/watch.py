"""Blocking watcher for CLI agent-mode HITL testing.

Polls for two signals:
- HITL prompt file: written by the running loop when human feedback is needed
- Done sentinel file: written by the harness run when the current worker reaches
  a terminal artifact state (completed / failed / exhausted /
  waiting_human after timeout / paused / stopped). Paused and stopped remain
  resumable operator interruptions when a checkpoint is present.

Exits immediately when either signal arrives, printing a single JSON line:
  {"event": "hitl", "run_id": ..., "prompt_id": ..., "message": ..., "choices": [...]}
  {"event": "loop_done", "status": ..., "terminal": ...}
  {"event": "timeout", "timeout_seconds": ...}

Normal usage (harness-owned auto-resume):
  # 1. Start run in background (persists run-state + paths)
  python -m harness.cli.start --run-id myrun --loop-kind harness_cli

  # 2. Watch (blocking) — returns when HITL prompt or terminal state arrives
  python -m harness.cli.watch --run-id myrun

  # 3a. If event=hitl: answer — the background process detects the answer and
  #     resumes automatically; no manual restart needed
  python -m harness.cli.answer --run-id myrun --prompt-id <id> --choice "75"
  python -m harness.cli.watch --run-id myrun   # watch the resumed run

  # 3b. If event=loop_done: read result.json / stdout.log from printed paths

  Lower-level (explicit paths):
  python -m harness.runtime.hitl.watch --run-id <run_id> --done-file <path>
  python -m harness.runtime.hitl.inject --loop-kind <namespace> --run-id <run_id> ...
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


def write_hitl_operator_sidecar(
    *,
    run_id: str,
    latest_record: dict[str, Any],
    pending_snapshot: list[dict[str, Any]],
) -> None:
    """Persist latest HITL prompt + open queue for operator CLI (mechanical JSON only)."""
    path = hitl_pending_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": str(run_id),
        "latest": dict(latest_record),
        "pending_hitl_requests": list(pending_snapshot),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _poll(
    *,
    run_id: str,
    done_file: Path | None,
    timeout_seconds: int,
    poll_interval: float = 2.0,
    done_not_before_epoch_seconds: float | None = None,
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
            latest = payload.get("latest") if isinstance(payload.get("latest"), dict) else payload
            try:
                hitl_path.unlink(missing_ok=True)
            except Exception:
                pass
            return {
                "event": "hitl",
                "run_id": run_id,
                "prompt_id": latest.get("prompt_id"),
                "message": latest.get("message"),
                "choices": latest.get("choices") or [],
                "context": latest.get("context") or {},
                "pending_hitl_requests": payload.get("pending_hitl_requests")
                if isinstance(payload.get("pending_hitl_requests"), list)
                else [],
            }

        # Check for loop completion.
        if done_file is not None and done_file.exists():
            if done_not_before_epoch_seconds is not None:
                try:
                    if done_file.stat().st_mtime < done_not_before_epoch_seconds:
                        time.sleep(poll_interval)
                        continue
                except OSError:
                    pass
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
    poll_interval: float = 2.0,
    done_not_before_epoch_seconds: float | None = None,
) -> dict:
    done_path = Path(done_file) if done_file else None
    return _poll(
        run_id=run_id,
        done_file=done_path,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
        done_not_before_epoch_seconds=done_not_before_epoch_seconds,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hitl-watch",
        description="Block until a HITL prompt or loop-done sentinel appears for a given run.",
    )
    parser.add_argument("--run-id", required=True, help="The mission-flow request prefix (e.g. mission-myrun-tx).")
    parser.add_argument(
        "--done-file",
        default=None,
        help="Path to the done-sentinel JSON file (harness.cli.start stores this in run-state).",
    )
    parser.add_argument("--timeout", type=int, default=600, help="Max seconds to wait before giving up (default: 600).")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Poll interval in seconds (default: 2.0).")
    parser.add_argument(
        "--done-not-before-epoch-seconds",
        type=float,
        default=None,
        help="Ignore done sentinels whose filesystem mtime is older than this epoch timestamp.",
    )
    args = parser.parse_args()

    result = _poll(
        run_id=args.run_id,
        done_file=Path(args.done_file) if args.done_file else None,
        timeout_seconds=args.timeout,
        poll_interval=args.poll_interval,
        done_not_before_epoch_seconds=args.done_not_before_epoch_seconds,
    )
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
    print(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
