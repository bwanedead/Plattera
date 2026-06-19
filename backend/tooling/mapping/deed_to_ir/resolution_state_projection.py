"""Mechanical resolution-state projection for deed-to-IR (copy-only, no inference)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

MAX_STARTUP_SUMMARY_ITEMS = 12

RESOLUTION_STATE_REF_PREFIX = "transcript_edit:resolution_state:"
RESOLUTION_STATE_REF_PATTERN = re.compile(
    r"^transcript_edit:resolution_state:[A-Za-z0-9._:-]+$"
)


class ResolutionStateHandoffError(ValueError):
    """Raised when resolution-state ref/snapshot pairing or ref prefix is invalid."""


def validate_resolution_state_handoff(
    *,
    resolution_state_ref: str | None,
    resolution_state_snapshot: Mapping[str, Any] | None,
) -> None:
    """Require both ref and snapshot together, or both absent; enforce ref prefix."""
    has_ref = bool(resolution_state_ref and str(resolution_state_ref).strip())
    has_snapshot = resolution_state_snapshot is not None
    if has_ref != has_snapshot:
        raise ResolutionStateHandoffError("resolution_state_ref_and_snapshot_must_be_paired")
    if has_ref and not RESOLUTION_STATE_REF_PATTERN.fullmatch(str(resolution_state_ref).strip()):
        raise ResolutionStateHandoffError("resolution_state_ref_invalid_prefix")


def mechanical_resolution_state_snapshot(raw: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Copy resolution state fields mechanically; return None when input is absent."""
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        return None
    out: dict[str, Any] = {
        "items": _copy_list(raw.get("items")),
        "relations": _copy_list(raw.get("relations")),
    }
    for key in ("schema_version", "updated_at_epoch_seconds", "active_item_id", "opaque_payload"):
        if key in raw:
            out[key] = _copy_value(raw.get(key))
    return out


def resolution_state_counts(snapshot: Mapping[str, Any] | None) -> dict[str, int]:
    if not isinstance(snapshot, Mapping):
        return {"items": 0, "relations": 0, "covered_units": 0}
    items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
    relations = snapshot.get("relations") if isinstance(snapshot.get("relations"), list) else []
    covered = 0
    for item in items:
        if isinstance(item, Mapping):
            units = item.get("covered_units")
            if isinstance(units, list):
                covered += len(units)
    return {
        "items": len(items),
        "relations": len(relations),
        "covered_units": covered,
    }


def resolution_state_startup_summary(snapshot: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Bounded item summary for startup prompt — ids/status only, not full graph."""
    if not isinstance(snapshot, Mapping):
        return []
    items = snapshot.get("items")
    if not isinstance(items, list):
        return []
    summary: list[dict[str, Any]] = []
    for item in items[:MAX_STARTUP_SUMMARY_ITEMS]:
        if not isinstance(item, Mapping):
            continue
        row: dict[str, Any] = {}
        for key in (
            "item_id",
            "title",
            "kind",
            "status",
            "determination",
            "determined_value",
        ):
            if key in item and item.get(key) is not None:
                row[key] = item.get(key)
        units = item.get("covered_units")
        if isinstance(units, list):
            row["covered_unit_count"] = len(units)
        if row:
            summary.append(row)
    return summary


def _copy_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [_copy_value(item) for item in value]


def _copy_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _copy_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_copy_value(item) for item in value]
    return value
