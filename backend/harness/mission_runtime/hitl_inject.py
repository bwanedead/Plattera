"""Inject HITL feedback into the feedback store for CLI agent-mode testing.

This is the CLI equivalent of the UI submitting feedback via the API endpoint.
Uses the same feedback_store mechanism the production system uses.

Usage:
  python -m harness.mission_runtime.hitl_inject \\
    --run-id mission-myrun-tx \\
    --prompt-id <prompt_id from hitl_watch output> \\
    --choice "75"
"""

from __future__ import annotations

import argparse
import json
import sys

from services.agent_viewer import feedback_store


def inject(
    *,
    run_id: str,
    prompt_id: str,
    choice: str,
    note: str | None = None,
) -> dict:
    entry = feedback_store.append_entry(
        loop_kind="transcript_edit",
        run_id=run_id,
        prompt_id=prompt_id,
        choice=choice,
        note=note,
    )
    return {"status": "injected", "run_id": run_id, "prompt_id": prompt_id, "choice": choice, "entry": entry}


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hitl-inject",
        description="Inject HITL feedback into the feedback store (same path as the UI).",
    )
    parser.add_argument("--run-id", required=True, help="The run_id used by the loop (request_id_prefix).")
    parser.add_argument("--prompt-id", required=True, help="The prompt_id from the hitl_watch output.")
    parser.add_argument("--choice", required=True, help="The feedback choice value (e.g. '75' or the full choice text).")
    parser.add_argument("--note", default=None, help="Optional note to include with the feedback.")
    args = parser.parse_args()

    result = inject(
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
