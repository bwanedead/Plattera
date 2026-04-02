"""Minimal child process for CLI tests and dry-run operator flows.

Reads file paths from environment (set by ``harness.cli.start``) and writes
optional sleep, result JSON, and done sentinel. No mission semantics.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def _env_path(name: str) -> str | None:
    v = os.environ.get(name)
    return v.strip() if isinstance(v, str) and v.strip() else None


def main() -> None:
    done_path = _env_path("HARNESS_CLI_DONE_FILE")
    result_path = _env_path("HARNESS_CLI_RESULT_FILE")
    sleep_s = float(os.environ.get("HARNESS_CLI_STUB_SLEEP_SECONDS") or "0")

    if sleep_s > 0:
        time.sleep(sleep_s)

    if result_path:
        payload = {
            "stub": True,
            "message": "harness.cli.stub_worker completed",
        }
        Path(result_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if done_path:
        done_payload = {
            "status": "ok",
            "terminal": "stub_complete",
            "reason_code": None,
        }
        Path(done_path).write_text(json.dumps(done_payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
