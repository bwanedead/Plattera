"""CLI: validation-first compression of legacy resume turn checkpoints.

Default is dry-run. Pass ``--apply`` to mutate the filesystem for one ``--run-id``.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .resume_checkpoint_compress import compress_run_legacy_checkpoints


def _print_json(obj: dict[str, Any]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="harness.cli.compress_resume_checkpoints",
        description=(
            "Plan or apply migration of resume_checkpoints/turn_NNNN.json to "
            "turn_NNNN.json.gz for one run. Default is dry-run; --apply mutates."
        ),
    )
    parser.add_argument("--run-id", required=True, help="Exact CLI run id to inspect or migrate.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform verified writes/deletions. Without this flag, report a plan only.",
    )
    args = parser.parse_args(argv)
    result = compress_run_legacy_checkpoints(run_id=args.run_id.strip(), apply=bool(args.apply))
    _print_json(result)


if __name__ == "__main__":
    main()
