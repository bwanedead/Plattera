"""Spawn-argv helpers for fork-resume child runs."""

from __future__ import annotations

import json
from typing import Any

LAUNCH_CONTEXT_JSON_FLAG = "--launch-context-json"
LAUNCH_CONTEXT_EQUALS_PREFIX = f"{LAUNCH_CONTEXT_JSON_FLAG}="

REASON_LAUNCH_CONTEXT_MALFORMED = "launch_context_malformed"
REASON_LAUNCH_CONTEXT_NOT_OBJECT = "launch_context_not_object"
REASON_LAUNCH_CONTEXT_DUPLICATE = "launch_context_duplicate"
REASON_LAUNCH_CONTEXT_DANGLING = "launch_context_dangling"
REASON_LAUNCH_CONTEXT_VALUE_INVALID = "launch_context_value_invalid"


def parse_embedded_launch_context(
    spawn_argv: list[str],
) -> tuple[dict[str, Any] | None, str | None]:
    """Return the embedded launch-context object, or a stable refuse code.

    Isolated fork remains first-match and lenient when the embedded JSON is
    malformed. Continue-mode callers must use
    ``parse_embedded_launch_context_strict``.
    """
    raw = _raw_launch_context_json(spawn_argv)
    if raw is None:
        return None, None
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        return None, REASON_LAUNCH_CONTEXT_MALFORMED
    if type(doc) is not dict:
        return None, REASON_LAUNCH_CONTEXT_NOT_OBJECT
    return doc, None


def parse_embedded_launch_context_strict(
    spawn_argv: list[str],
) -> tuple[dict[str, Any] | None, str | None]:
    """Require zero or exactly one well-formed launch-context occurrence."""
    raws, collect_err = collect_launch_context_raw(spawn_argv)
    if collect_err:
        return None, collect_err
    if not raws:
        return None, None
    try:
        doc = json.loads(raws[0])
    except json.JSONDecodeError:
        return None, REASON_LAUNCH_CONTEXT_MALFORMED
    if type(doc) is not dict:
        return None, REASON_LAUNCH_CONTEXT_NOT_OBJECT
    return doc, None


def collect_launch_context_raw(spawn_argv: list[str]) -> tuple[list[str] | None, str | None]:
    """Return every launch-context JSON payload, or a stable refuse code.

    Duplicate, dangling, mixed, or non-string occurrences are refused. Callers
    must not choose the first or last match.
    """
    argv = list(spawn_argv or [])
    found: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if type(arg) is not str:
            return None, REASON_LAUNCH_CONTEXT_VALUE_INVALID
        if arg == LAUNCH_CONTEXT_JSON_FLAG:
            if index + 1 >= len(argv):
                return None, REASON_LAUNCH_CONTEXT_DANGLING
            nxt = argv[index + 1]
            if type(nxt) is not str:
                return None, REASON_LAUNCH_CONTEXT_VALUE_INVALID
            if nxt.startswith("--"):
                return None, REASON_LAUNCH_CONTEXT_DANGLING
            found.append(nxt)
            index += 2
            continue
        if arg.startswith(LAUNCH_CONTEXT_EQUALS_PREFIX):
            found.append(arg[len(LAUNCH_CONTEXT_EQUALS_PREFIX) :])
            index += 1
            continue
        index += 1
    if len(found) > 1:
        return None, REASON_LAUNCH_CONTEXT_DUPLICATE
    return found, None


def _raw_launch_context_json(spawn_argv: list[str]) -> str | None:
    argv = list(spawn_argv or [])
    for index, arg in enumerate(argv):
        if type(arg) is not str:
            continue
        if arg == LAUNCH_CONTEXT_JSON_FLAG and index + 1 < len(argv):
            nxt = argv[index + 1]
            return nxt if type(nxt) is str else None
        if arg.startswith(LAUNCH_CONTEXT_EQUALS_PREFIX):
            return arg[len(LAUNCH_CONTEXT_EQUALS_PREFIX) :]
    return None


def replace_embedded_launch_context(spawn_argv: list[str], doc: dict[str, Any]) -> list[str]:
    """Write ``doc`` into the first existing launch-context flag, or append one."""
    encoded = json.dumps(doc, separators=(",", ":"), allow_nan=False)
    argv = list(spawn_argv)
    for index, arg in enumerate(argv):
        if type(arg) is not str:
            continue
        if arg == LAUNCH_CONTEXT_JSON_FLAG and index + 1 < len(argv):
            argv[index + 1] = encoded
            return argv
        if arg.startswith(LAUNCH_CONTEXT_EQUALS_PREFIX):
            argv[index] = LAUNCH_CONTEXT_EQUALS_PREFIX + encoded
            return argv
    argv.extend([LAUNCH_CONTEXT_JSON_FLAG, encoded])
    return argv


def replace_unique_embedded_launch_context(
    spawn_argv: list[str],
    doc: dict[str, Any],
) -> tuple[list[str] | None, str | None]:
    """Rewrite argv so exactly one canonical split launch-context flag remains."""
    raws, collect_err = collect_launch_context_raw(spawn_argv)
    if collect_err:
        return None, collect_err
    del raws
    encoded = json.dumps(doc, separators=(",", ":"), allow_nan=False)
    return _remove_launch_context_flags(list(spawn_argv)) + [
        LAUNCH_CONTEXT_JSON_FLAG,
        encoded,
    ], None


def _remove_launch_context_flags(argv: list[str]) -> list[str]:
    out: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if type(arg) is str and arg == LAUNCH_CONTEXT_JSON_FLAG:
            index += 2 if index + 1 < len(argv) else 1
            continue
        if type(arg) is str and arg.startswith(LAUNCH_CONTEXT_EQUALS_PREFIX):
            index += 1
            continue
        out.append(arg)
        index += 1
    return out


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
