"""Mechanical resolution-state snapshot loading from filesystem paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .resolution_state_projection import ResolutionStateHandoffError


def load_resolution_state_snapshot_from_path(path: str | Path) -> dict[str, Any]:
    text = str(path or "").strip()
    if not text:
        raise ResolutionStateHandoffError("resolution_state_snapshot_path_empty")
    target = Path(text)
    if not target.is_file():
        raise ResolutionStateHandoffError("resolution_state_snapshot_path_not_found")
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResolutionStateHandoffError("resolution_state_snapshot_path_unreadable") from exc
    if not isinstance(raw, dict):
        raise ResolutionStateHandoffError("resolution_state_snapshot_not_object")
    return raw


def resolve_resolution_state_snapshot(
    *,
    resolution_state_snapshot: dict[str, Any] | None,
    resolution_state_snapshot_path: str | None,
) -> dict[str, Any] | None:
    has_inline = resolution_state_snapshot is not None
    has_path = bool(str(resolution_state_snapshot_path or "").strip())
    if has_inline and has_path:
        raise ResolutionStateHandoffError("resolution_state_snapshot_path_and_inline_mutually_exclusive")
    if has_path:
        return load_resolution_state_snapshot_from_path(str(resolution_state_snapshot_path).strip())
    return resolution_state_snapshot
