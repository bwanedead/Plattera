"""Generic workspace-identity discovery from persisted CLI run state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.cli.fork_spawn_argv import parse_embedded_launch_context_strict
from harness.cli.fork_workspace import resolve_continue_workspace_id
from harness.cli.run_layout import RunLayoutError, normalize_run_id

REASON_WORKSPACE_REFS_UNCERTAIN = "workspace_refs_uncertain"


def discover_run_workspace_ids(*, run_id: str, run_dir: Path) -> tuple[frozenset[str] | None, str | None]:
    """Return workspace IDs referenced by one run, or fail closed.

    Sources: launch-context ``workspace_id``, ``fork_lineage.source_workspace_id``,
    and the launch-identity default (the run id) when both are absent.
    """
    try:
        rid = normalize_run_id(run_id)
    except RunLayoutError:
        return None, REASON_WORKSPACE_REFS_UNCERTAIN
    doc, load_err = _load_state_object(Path(run_dir) / "state.json")
    if load_err or doc is None:
        return None, REASON_WORKSPACE_REFS_UNCERTAIN
    launch_ws, lineage_ws, extract_err = _explicit_workspace_ids(doc, source_run_id=rid)
    if extract_err:
        return None, extract_err
    if launch_ws is not None and lineage_ws is not None and launch_ws != lineage_ws:
        return None, REASON_WORKSPACE_REFS_UNCERTAIN
    if launch_ws is not None:
        return frozenset({launch_ws}), None
    if lineage_ws is not None:
        return frozenset({lineage_ws}), None
    return frozenset({rid}), None


def _explicit_workspace_ids(
    doc: dict[str, Any],
    *,
    source_run_id: str,
) -> tuple[str | None, str | None, str | None]:
    launch_ws: str | None = None
    if "spawn_argv" in doc:
        spawn_argv = doc.get("spawn_argv")
        if type(spawn_argv) is not list:
            return None, None, REASON_WORKSPACE_REFS_UNCERTAIN
        launch, parse_err = parse_embedded_launch_context_strict(list(spawn_argv))
        if parse_err:
            return None, None, REASON_WORKSPACE_REFS_UNCERTAIN
        if launch is not None and "workspace_id" in launch:
            launch_ws, ws_err = resolve_continue_workspace_id(
                launch=launch,
                source_run_id=source_run_id,
            )
            if ws_err or launch_ws is None:
                return None, None, REASON_WORKSPACE_REFS_UNCERTAIN
    extra = doc.get("extra")
    if extra is None:
        extra = {}
    if type(extra) is not dict:
        return None, None, REASON_WORKSPACE_REFS_UNCERTAIN
    lineage = extra.get("fork_lineage")
    lineage_ws: str | None = None
    if lineage is None:
        return launch_ws, None, None
    if type(lineage) is not dict:
        return None, None, REASON_WORKSPACE_REFS_UNCERTAIN
    if "source_workspace_id" not in lineage:
        return launch_ws, None, None
    raw = lineage.get("source_workspace_id")
    if type(raw) is not str:
        return None, None, REASON_WORKSPACE_REFS_UNCERTAIN
    lineage_ws, lineage_err = resolve_continue_workspace_id(
        launch={"workspace_id": raw},
        source_run_id=source_run_id,
    )
    if lineage_err or lineage_ws is None:
        return None, None, REASON_WORKSPACE_REFS_UNCERTAIN
    return launch_ws, lineage_ws, None


def _load_state_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, REASON_WORKSPACE_REFS_UNCERTAIN
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None, REASON_WORKSPACE_REFS_UNCERTAIN
    if type(raw) is not dict:
        return None, REASON_WORKSPACE_REFS_UNCERTAIN
    return raw, None
