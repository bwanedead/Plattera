"""Request a graceful operator stop of a running harness CLI loop.

Writes ``<run_dir>/control.json`` with ``command: "stop"``. The runner
observes this file only at safe loop boundaries and exits with terminal class
``stopped`` / reason ``stopped_by_operator``. The run remains resumable from
its ``kernel_resume.json`` checkpoint via ``harness.cli.resume``; this is a
graceful, intentional stop, not a kill.

Exit status ``0`` on success (``status: requested``), ``2`` on any refusal.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ._control_request import request_run_control


def stop_run(*, run_id: str, reason: str | None = None) -> dict[str, Any]:
    return request_run_control(run_id=run_id, command="stop", reason=reason)


def _print_json(obj: dict[str, Any]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="harness.cli.stop",
        description="Request a graceful operator stop of a live harness CLI run.",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--reason", default=None, help="Optional short operator reason.")
    args = parser.parse_args()

    out = stop_run(run_id=args.run_id.strip(), reason=args.reason)
    _print_json(out)
    if out.get("status") != "requested":
        sys.exit(2)


if __name__ == "__main__":
    main()
