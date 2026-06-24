"""CLI launch-context identity merge (control-plane only)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any


def merge_cli_launch_identity(context: Mapping[str, Any] | None) -> tuple[dict[str, Any], str | None]:
    """Inject CLI run identity into launch context when hosted under harness.cli.start."""
    base = dict(context or {})
    cli_run_id = str(os.environ.get("HARNESS_CLI_RUN_ID", "") or "").strip()
    if not cli_run_id:
        return base, None
    explicit_run_id = str(base.get("run_id") or "").strip()
    if explicit_run_id and explicit_run_id != cli_run_id:
        return base, "launch_run_id_cli_mismatch"
    if not explicit_run_id:
        base["run_id"] = cli_run_id
    if not str(base.get("workspace_id") or "").strip():
        base["workspace_id"] = cli_run_id
    return base, None


def cli_run_id_from_env() -> str | None:
    text = str(os.environ.get("HARNESS_CLI_RUN_ID", "") or "").strip()
    return text or None
