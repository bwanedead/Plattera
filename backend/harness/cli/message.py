"""Inject a user-to-agent message into a running or resumable harness run.

Generic harness capability — works for any agent built on the harness, not
just transcript-edit.  The message is appended to the on-disk user-message
store; the next iteration of the orchestrator polls it, records it in the
durable ledger, and surfaces it to the agent on the next prompt.

Usage examples::

    python -m harness.cli.message --run-id <id> --text "The parcel1 tie bearing is wrong; correct N. 2°00'W. to N. 4°00'W."
    python -m harness.cli.message --run-id <id> --text "Pause scope X" --source tester
    python -m harness.cli.message --run-id <id> --text "..." --metadata '{"hint":"...","item_id":"i-1"}'

Loop kind defaults to the value recorded by ``harness.cli.start`` for this run.

Works while the run is alive AND after a failed/completed run if
``kernel_resume.json`` exists — the operator can inject context, then run
``harness.cli.resume`` to continue.  Watch/resume already archives stale
terminal files via existing behavior; this CLI does not touch them.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from harness.runtime.user_messages.store import append_entry as _append_user_message

from .run_state import read_state, run_layout_issue


def _print_json(obj: dict[str, Any]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def inject_user_message(
    *,
    run_id: str,
    text: str,
    source: str | None,
    loop_kind: str | None,
    metadata: dict[str, Any] | None,
    message_id: str | None = None,
) -> dict[str, Any]:
    """Append a user message to the per-run store and return the persisted row."""
    layout_issue = run_layout_issue(run_id)
    if layout_issue == "run_id_ambiguous":
        return {"status": "error", "reason": "run_id_ambiguous", "run_id": run_id}
    lk = loop_kind
    if not lk:
        state = read_state(run_id)
        if state is None:
            return {
                "status": "error",
                "reason": layout_issue or "missing_run_state",
                "run_id": run_id,
            }
        lk = state.loop_kind
    entry = _append_user_message(
        loop_kind=lk,
        run_id=run_id,
        text=text,
        source=source,
        message_id=message_id,
        metadata=metadata,
    )
    return {
        "status": "injected",
        "loop_kind": lk,
        "run_id": run_id,
        "entry": entry,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="harness.cli.message",
        description=(
            "Inject a user-to-agent message into a running or resumable harness run.  "
            "Generic — works for any agent built on the harness."
        ),
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--text", required=True,
        help="The exact user-authored text to deliver to the agent.",
    )
    parser.add_argument(
        "--source", default="cli",
        help="Origin tag for the message (e.g. cli, viewer, tester, api).  Default: cli.",
    )
    parser.add_argument(
        "--loop-kind", default=None,
        help="Override loop_kind namespace (default: value from run-state).",
    )
    parser.add_argument(
        "--metadata", default=None,
        help="Optional JSON object string with extra context.",
    )
    parser.add_argument(
        "--message-id", default=None,
        help="Optional explicit message_id (default: auto-generated user-msg-<uuid>).",
    )
    args = parser.parse_args()

    metadata_obj: dict[str, Any] | None = None
    if args.metadata is not None:
        try:
            parsed = json.loads(args.metadata)
        except json.JSONDecodeError:
            _print_json({"status": "error", "reason": "metadata_not_valid_json"})
            sys.exit(2)
        if not isinstance(parsed, dict):
            _print_json({"status": "error", "reason": "metadata_not_object"})
            sys.exit(2)
        metadata_obj = parsed

    result = inject_user_message(
        run_id=args.run_id.strip(),
        text=str(args.text),
        source=(args.source.strip() if args.source else None) or None,
        loop_kind=(args.loop_kind.strip() if args.loop_kind else None),
        metadata=metadata_obj,
        message_id=(args.message_id.strip() if args.message_id else None) or None,
    )
    _print_json(result)
    if result.get("status") == "error":
        sys.exit(2)


if __name__ == "__main__":
    main()
