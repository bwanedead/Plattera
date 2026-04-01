"""Inject HITL feedback into the feedback store for CLI agent-mode testing.

This is the CLI equivalent of the UI submitting feedback via the API endpoint.
Uses the same feedback_store mechanism the production system uses.

Usage:
  python -m harness.runtime.hitl.inject \\
    --loop-kind mission_flow_cli \\
    --run-id <run_id> \\
    --prompt-id <prompt_id from watch output> \\
    --choice "<feedback>"
"""

from __future__ import annotations

import argparse
import json
import sys

from services.agent_viewer import feedback_store


def inject(
    *,
    loop_kind: str,
    run_id: str,
    prompt_id: str,
    choice: str,
    note: str | None = None,
) -> dict:
    entry = feedback_store.append_entry(
        loop_kind=loop_kind,
        run_id=run_id,
        prompt_id=prompt_id,
        choice=choice,
        note=note,
    )
    return {
        "status": "injected",
        "loop_kind": loop_kind,
        "run_id": run_id,
        "prompt_id": prompt_id,
        "choice": choice,
        "entry": entry,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hitl-inject",
        description="Inject HITL feedback into the feedback store (same path as the UI).",
    )
    parser.add_argument(
        "--loop-kind",
        required=True,
        help="Feedback store loop namespace (for example mission_flow_cli).",
    )
    parser.add_argument("--run-id", required=True, help="The run_id used by the loop (request_id_prefix).")
    parser.add_argument("--prompt-id", required=True, help="The prompt_id from the HITL watch output.")
    parser.add_argument("--choice", required=True, help="The feedback choice value or full choice text.")
    parser.add_argument("--note", default=None, help="Optional note to include with the feedback.")
    args = parser.parse_args()

    result = inject(
        loop_kind=args.loop_kind,
        run_id=args.run_id,
        prompt_id=args.prompt_id,
        choice=args.choice,
        note=args.note,
    )
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
    print(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
