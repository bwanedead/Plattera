"""Spawn-argv helpers for fork-resume child runs."""

from __future__ import annotations

import json
from typing import Any

LAUNCH_CONTEXT_JSON_FLAG = "--launch-context-json"


def strip_launch_context_identity_for_fork(spawn_argv: list[str]) -> list[str]:
    """Return spawn argv with ``run_id``/``workspace_id`` removed from embedded launch context.

    Child runs receive identity via ``HARNESS_CLI_RUN_ID``; copying a source launch context
    that embeds the parent run id would fail ``merge_cli_launch_identity``.
    """
    argv = list(spawn_argv)
    for index, arg in enumerate(argv):
        if arg == LAUNCH_CONTEXT_JSON_FLAG and index + 1 < len(argv):
            argv[index + 1] = _strip_identity_from_launch_context_json(argv[index + 1])
            return argv
        prefix = f"{LAUNCH_CONTEXT_JSON_FLAG}="
        if arg.startswith(prefix):
            raw = arg[len(prefix) :]
            argv[index] = prefix + _strip_identity_from_launch_context_json(raw)
            return argv
    return argv


def _strip_identity_from_launch_context_json(raw_json: str) -> str:
    try:
        doc = json.loads(raw_json)
    except json.JSONDecodeError:
        return raw_json
    if not isinstance(doc, dict):
        return raw_json
    stripped: dict[str, Any] = dict(doc)
    stripped.pop("run_id", None)
    stripped.pop("workspace_id", None)
    return json.dumps(stripped, separators=(",", ":"))
