"""Mechanical resolution-state projection for deed-to-IR (copy-only, no inference)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

MAX_STARTUP_SUMMARY_ITEMS = 12
MAX_INDEX_ITEMS = 64
MAX_INDEX_UNITS = 256
MAX_INDEX_RELATIONS = 64
MAX_SELECTED_ITEM_ROWS = 16
MAX_SELECTED_UNITS_TOTAL = 32
MAX_UNITS_PER_SELECTED_ITEM = 8

RESOLUTION_STATE_REF_PREFIX = "transcript_edit:resolution_state:"
RESOLUTION_STATE_REF_PATTERN = re.compile(
    r"^transcript_edit:resolution_state:[A-Za-z0-9._:-]+$"
)

_INDEX_ITEM_KEYS = (
    "item_id",
    "title",
    "kind",
    "structure_kind",
    "status",
)
_INDEX_UNIT_KEYS = (
    "unit_id",
    "title",
    "value_kind",
    "kind",
    "status",
    "determination",
    "determined_value",
)
_SELECTED_UNIT_EXTRA_KEYS = (
    "candidate_values",
    "evidence_refs",
    "evidence_locators",
    "verification_basis",
    "summary",
    "closure_summary",
    "parent_item_id",
    "parent_item_title",
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
    for key in ("schema_version", "updated_at_epoch_seconds", "active_item_id"):
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


def build_resolution_state_index(
    snapshot: Mapping[str, Any],
    *,
    resolution_state_ref: str | None = None,
) -> dict[str, Any]:
    """Compact index projection for unfiltered resolution-state hydration."""
    items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
    relations = snapshot.get("relations") if isinstance(snapshot.get("relations"), list) else []
    index_items: list[dict[str, Any]] = []
    units_emitted = 0
    units_omitted = 0
    for item in items[:MAX_INDEX_ITEMS]:
        if not isinstance(item, Mapping):
            continue
        row = _compact_item_index_row(item)
        units = item.get("covered_units")
        unit_rows: list[dict[str, Any]] = []
        if isinstance(units, list):
            for unit in units:
                if units_emitted >= MAX_INDEX_UNITS:
                    units_omitted += 1
                    continue
                if not isinstance(unit, Mapping):
                    continue
                unit_rows.append(_compact_unit_index_row(unit))
                units_emitted += 1
        if unit_rows:
            row["units"] = unit_rows
        index_items.append(row)
    relation_rows = [_compact_relation_row(rel) for rel in relations[:MAX_INDEX_RELATIONS]]
    relation_rows = [row for row in relation_rows if row]
    payload: dict[str, Any] = {
        "projection_mode": "index",
        "resolution_state_ref": resolution_state_ref,
        "totals": resolution_state_counts(snapshot),
        "items": index_items,
        "relations": relation_rows,
    }
    if "schema_version" in snapshot:
        payload["schema_version"] = snapshot.get("schema_version")
    if "active_item_id" in snapshot:
        payload["active_item_id"] = snapshot.get("active_item_id")
    truncation: dict[str, int] = {}
    if len(items) > MAX_INDEX_ITEMS:
        truncation["items_omitted"] = len(items) - MAX_INDEX_ITEMS
    if len(relations) > MAX_INDEX_RELATIONS:
        truncation["relations_omitted"] = len(relations) - MAX_INDEX_RELATIONS
    if units_omitted:
        truncation["units_omitted"] = units_omitted
    if truncation:
        payload["truncation"] = truncation
    return payload


def build_resolution_state_selected_rows(
    snapshot: Mapping[str, Any],
    unit_ids: Sequence[str],
    *,
    resolution_state_ref: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], dict[str, int]]:
    """Return selected row projections, not-found ids, and named truncation totals."""
    wanted = [str(uid).strip() for uid in unit_ids if str(uid).strip()]
    wanted_set = set(wanted)
    found: set[str] = set()
    rows: list[dict[str, Any]] = []
    units_emitted = 0
    items_emitted = 0
    units_omitted = 0
    items_omitted = 0
    items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        item_id = str(item.get("item_id") or "").strip()
        if item_id and item_id in wanted_set:
            if items_emitted >= MAX_SELECTED_ITEM_ROWS:
                items_omitted += 1
                continue
            remaining_units = max(0, MAX_SELECTED_UNITS_TOTAL - units_emitted)
            row, row_units = _compact_selected_item_row(item, max_units=remaining_units)
            if row_units <= 0 and item.get("covered_units"):
                items_omitted += 1
                continue
            rows.append(row)
            found.add(item_id)
            items_emitted += 1
            units_emitted += row_units
            if row_units < _count_item_units(item):
                units_omitted += _count_item_units(item) - row_units
            continue
        units = item.get("covered_units")
        if not isinstance(units, list):
            continue
        matched_units: list[dict[str, Any]] = []
        for unit in units:
            if not isinstance(unit, Mapping):
                continue
            unit_id = str(unit.get("unit_id") or "").strip()
            if not unit_id or unit_id not in wanted_set:
                continue
            if items_emitted >= MAX_SELECTED_ITEM_ROWS and not matched_units:
                units_omitted += 1
                continue
            if units_emitted >= MAX_SELECTED_UNITS_TOTAL:
                units_omitted += 1
                continue
            if len(matched_units) >= MAX_UNITS_PER_SELECTED_ITEM:
                units_omitted += 1
                continue
            row = _compact_selected_unit_row(
                unit,
                parent_item_id=item_id,
                parent_item_title=item.get("title"),
            )
            matched_units.append(row)
            found.add(unit_id)
            units_emitted += 1
        if matched_units:
            rows.append(
                {
                    "item_id": item_id,
                    "title": item.get("title"),
                    "kind": item.get("kind"),
                    "structure_kind": item.get("structure_kind"),
                    "status": item.get("status"),
                    "units": matched_units,
                }
            )
            items_emitted += 1
    not_found = sorted(wanted_set - found)
    truncation: dict[str, int] = {}
    if units_omitted:
        truncation["units_omitted"] = units_omitted
    if items_omitted:
        truncation["items_omitted"] = items_omitted
    return rows, not_found, truncation


def resolution_state_startup_summary(snapshot: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Bounded item summary for startup prompt — ids/status only, not full graph."""
    if not isinstance(snapshot, Mapping):
        return []
    index = build_resolution_state_index(snapshot)
    summary: list[dict[str, Any]] = []
    for item in index.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        row: dict[str, Any] = {}
        for key in ("item_id", "title", "kind", "structure_kind", "status"):
            if key in item and item.get(key) is not None:
                row[key] = item.get(key)
        units = item.get("units")
        if isinstance(units, list):
            row["covered_unit_count"] = len(units)
        if row:
            summary.append(row)
        if len(summary) >= MAX_STARTUP_SUMMARY_ITEMS:
            break
    return summary


def _compact_item_index_row(item: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key in _INDEX_ITEM_KEYS:
        if key in item and item.get(key) is not None:
            row[key] = item.get(key)
    return row


def _compact_unit_index_row(unit: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key in _INDEX_UNIT_KEYS:
        if key in unit and unit.get(key) is not None:
            row[key] = unit.get(key)
    if "value_kind" not in row and "kind" in row:
        row["value_kind"] = row.get("kind")
    return row


def _compact_selected_unit_row(
    unit: Mapping[str, Any],
    *,
    parent_item_id: str,
    parent_item_title: Any,
) -> dict[str, Any]:
    row = _compact_unit_index_row(unit)
    row["parent_item_id"] = parent_item_id
    if parent_item_title is not None:
        row["parent_item_title"] = parent_item_title
    for key in _SELECTED_UNIT_EXTRA_KEYS:
        if key in ("parent_item_id", "parent_item_title"):
            continue
        if key in unit and unit.get(key) is not None:
            row[key] = _copy_value(unit.get(key))
    return row


def _compact_selected_item_row(item: Mapping[str, Any], *, max_units: int | None = None) -> tuple[dict[str, Any], int]:
    row = _compact_item_index_row(item)
    for key in ("determination", "determined_value", "verification_basis", "evidence_refs", "summary"):
        if key in item and item.get(key) is not None:
            row[key] = _copy_value(item.get(key))
    units = item.get("covered_units")
    emitted = 0
    if isinstance(units, list) and units:
        cap = max_units if max_units is not None else MAX_UNITS_PER_SELECTED_ITEM
        cap = min(cap, MAX_UNITS_PER_SELECTED_ITEM)
        unit_rows: list[dict[str, Any]] = []
        for unit in units:
            if emitted >= cap:
                break
            if not isinstance(unit, Mapping):
                continue
            unit_rows.append(
                _compact_selected_unit_row(
                    unit,
                    parent_item_id=str(item.get("item_id") or ""),
                    parent_item_title=item.get("title"),
                )
            )
            emitted += 1
        if unit_rows:
            row["units"] = unit_rows
    return row, emitted


def _count_item_units(item: Mapping[str, Any]) -> int:
    units = item.get("covered_units")
    if not isinstance(units, list):
        return 0
    return sum(1 for unit in units if isinstance(unit, Mapping))


def _compact_relation_row(relation: Any) -> dict[str, Any]:
    if not isinstance(relation, Mapping):
        return {}
    row: dict[str, Any] = {}
    relation_type = relation.get("relation_type")
    if relation_type is not None:
        row["relation_type"] = relation_type
    source = relation.get("source_item_id")
    if source is None:
        source = relation.get("from_item_id")
    target = relation.get("target_item_id")
    if target is None:
        target = relation.get("to_item_id")
    if source is not None:
        row["source"] = source
    if target is not None:
        row["target"] = target
    return row


def _copy_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [_copy_value(item) for item in value]


def _copy_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(k): _copy_value(v)
            for k, v in value.items()
            if str(k) != "opaque_payload"
        }
    if isinstance(value, list):
        return [_copy_value(item) for item in value]
    return value
