"""Request a graceful operator pause of a running harness CLI loop.

Writes ``<run_dir>/control.json`` with ``command: "pause"``. The runner
observes this file only at safe loop boundaries (before ``choose_action``,
after ``choose_action``, before tool dispatch, after tool result + checkpoint,
before the next iteration). No process signaling; no tool cancellation; no
kill.

Exit status ``0`` on success (``status: requested``), ``2`` on any refusal.
Paired with ``harness.cli.resume`` to continue the paused run.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ._control_request import request_run_control


def pause_run(*, run_id: str, reason: str | None = None) -> dict[str, Any]:
    return request_run_control(run_id=run_id, command="pause", reason=reason)


def _print_json(obj: dict[str, Any]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="harness.cli.pause",
        description="Request a graceful operator pause of a live harness CLI run.",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--reason", default=None, help="Optional short operator reason.")
    args = parser.parse_args()

    out = pause_run(run_id=args.run_id.strip(), reason=args.reason)
    _print_json(out)
    if out.get("status") != "requested":
        sys.exit(2)


if __name__ == "__main__":
    main()
