"""Submit HITL feedback using run-state loop_kind defaults."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from harness.runtime.hitl.inject import inject

from .run_state import read_state


def _print_json(obj: dict[str, Any]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def answer_run(
    *,
    run_id: str,
    prompt_id: str,
    choice: str,
    note: str | None,
    loop_kind: str | None,
) -> dict[str, Any]:
    lk = loop_kind
    if not lk:
        state = read_state(run_id)
        if state is None:
            return {"status": "error", "reason": "missing_run_state", "run_id": run_id}
        lk = state.loop_kind
    return inject(loop_kind=lk, run_id=run_id, prompt_id=prompt_id, choice=choice, note=note)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="harness.cli.answer",
        description="Append HITL feedback for a run (same store as Agent Viewer).",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--prompt-id", required=True)
    parser.add_argument("--choice", required=True)
    parser.add_argument("--note", default=None)
    parser.add_argument(
        "--loop-kind",
        default=None,
        help="Override feedback namespace (default: value from run-state).",
    )
    args = parser.parse_args()

    result = answer_run(
        run_id=args.run_id.strip(),
        prompt_id=str(args.prompt_id).strip(),
        choice=str(args.choice),
        note=args.note,
        loop_kind=(args.loop_kind.strip() if args.loop_kind else None),
    )
    _print_json(result)
    if result.get("status") == "error":
        sys.exit(2)


if __name__ == "__main__":
    main()
