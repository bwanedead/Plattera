"""Generic fork workspace-mode helpers (control-plane only)."""

from __future__ import annotations

from typing import Any

from harness.cli.fork_spawn_argv import (
    parse_embedded_launch_context_strict,
    replace_unique_embedded_launch_context,
    strip_launch_context_identity_for_fork,
)
from harness.cli.run_layout import RunLayoutError, normalize_run_id

WORKSPACE_MODE_ISOLATED = "isolated"
WORKSPACE_MODE_CONTINUE = "continue"
WORKSPACE_MODES = frozenset({WORKSPACE_MODE_ISOLATED, WORKSPACE_MODE_CONTINUE})
DEFAULT_WORKSPACE_MODE = WORKSPACE_MODE_ISOLATED

REASON_WORKSPACE_MODE_INVALID = "workspace_mode_invalid"
REASON_WORKSPACE_ID_INVALID = "workspace_id_invalid"
REASON_WORKSPACE_ID_UNSAFE = "workspace_id_unsafe"
REASON_LAUNCH_RUN_ID_SOURCE_MISMATCH = "launch_run_id_source_mismatch"


def parse_workspace_mode(raw: object) -> tuple[str | None, str | None]:
    """Return a closed-vocabulary mode, defaulting omitted/None to isolated."""
    if raw is None:
        return DEFAULT_WORKSPACE_MODE, None
    if type(raw) is not str or raw not in WORKSPACE_MODES:
        return None, REASON_WORKSPACE_MODE_INVALID
    return raw, None


def prepare_isolated_spawn_argv(spawn_argv: list[str]) -> list[str]:
    return strip_launch_context_identity_for_fork(list(spawn_argv))


def prepare_continue_spawn_argv(
    *,
    spawn_argv: list[str],
    source_run_id: str,
) -> tuple[list[str] | None, str | None, str | None]:
    """Return ``(argv, workspace_id, refuse_code)`` for a continuation child."""
    launch, parse_err = parse_embedded_launch_context_strict(spawn_argv)
    if parse_err:
        return None, None, parse_err
    if launch is not None:
        identity_err = _source_run_id_coherent(launch, source_run_id)
        if identity_err:
            return None, None, identity_err
    workspace_id, ws_err = resolve_continue_workspace_id(
        launch=launch,
        source_run_id=source_run_id,
    )
    if ws_err or workspace_id is None:
        return None, None, ws_err or REASON_WORKSPACE_ID_INVALID
    child_launch = dict(launch) if launch is not None else {}
    child_launch.pop("run_id", None)
    child_launch["workspace_id"] = workspace_id
    rewritten, replace_err = replace_unique_embedded_launch_context(list(spawn_argv), child_launch)
    if replace_err or rewritten is None:
        return None, None, replace_err or "launch_context_duplicate"
    return rewritten, workspace_id, None


def resolve_continue_workspace_id(
    *,
    launch: dict[str, Any] | None,
    source_run_id: str,
) -> tuple[str | None, str | None]:
    """Preserve an explicit source workspace, else the source run's launch identity."""
    if launch is None or "workspace_id" not in launch:
        return _safe_workspace_id(source_run_id)
    return _exact_workspace_id(launch.get("workspace_id"))


def _source_run_id_coherent(launch: dict[str, Any], source_run_id: str) -> str | None:
    if "run_id" not in launch:
        return None
    raw = launch.get("run_id")
    if type(raw) is not str or raw != source_run_id:
        return REASON_LAUNCH_RUN_ID_SOURCE_MISMATCH
    return None


def _exact_workspace_id(raw: object) -> tuple[str | None, str | None]:
    if type(raw) is not str:
        return None, REASON_WORKSPACE_ID_INVALID
    if not raw or raw.strip() != raw:
        return None, REASON_WORKSPACE_ID_INVALID
    return _safe_workspace_id(raw)


def _safe_workspace_id(raw: str) -> tuple[str | None, str | None]:
    try:
        return normalize_run_id(raw), None
    except RunLayoutError as exc:
        if exc.code == "run_id_empty":
            return None, REASON_WORKSPACE_ID_INVALID
        return None, REASON_WORKSPACE_ID_UNSAFE
