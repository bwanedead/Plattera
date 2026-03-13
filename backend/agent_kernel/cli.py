"""Minimal CLI for deterministic Agent Kernel runs.

Compatibility posture:
- Low-level legacy/debug surface.
- Not the canonical mission-runtime development CLI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence, TextIO

from .kernel import run_kernel
from .models import KernelRequest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-kernel",
        description=(
            "Run the deterministic kernel from a JSON request file "
            "(low-level debug surface; not canonical unified mission CLI)."
        ),
    )
    parser.add_argument("request_file", help="Path to a JSON-encoded KernelRequest.")
    return parser


def run_cli(argv: Sequence[str] | None = None, stdout: TextIO | None = None) -> int:
    """Run the kernel from a JSON request file and emit a JSON KernelResult."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    request_path = Path(args.request_file)
    request = KernelRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    output = run_kernel(request)

    sink = stdout or sys.stdout
    sink.write(output.kernel_result.model_dump_json(indent=2))
    sink.write("\n")
    return 0


def main() -> None:
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
