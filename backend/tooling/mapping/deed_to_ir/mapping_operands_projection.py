"""Mechanical mapping-operands projection from upstream resolution snapshots."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

MAX_MAPPING_OPERANDS = 64
MAX_OPERAND_TITLE_CHARS = 160
MAX_OPERAND_DETERMINED_VALUE_CHARS = 320
MAX_OPERAND_CANDIDATE_VALUES = 8
MAX_OPERAND_CANDIDATE_VALUE_CHARS = 120
MAX_OPERAND_EVIDENCE_REFS = 8

_PARCEL_ID_FROM_ITEM = re.compile(r"^parcel_(\d+)(?:_|$)")
_CALL_OPERAND_ID = re.compile(
    r"^p(?P<parcel_num>\d+)_call(?P<call_index>\d+)_(?P<value_kind>bearing|distance)$",
    re.IGNORECASE,
)


def build_mapping_operands(
    snapshot: Mapping[str, Any],
    *,
    resolution_state_ref: str | None = None,
) -> dict[str, Any]:
    """Project a compact operand table for IR authoring (copy-only, no inference)."""
    items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
    operands: list[dict[str, Any]] = []
    omitted = 0
    field_truncation: dict[str, int] = {}

    for item in items:
        if not isinstance(item, Mapping):
            continue
        item_id = str(item.get("item_id") or "").strip()
        covered = item.get("covered_units")
        if isinstance(covered, list) and covered:
            for unit in covered:
                if not isinstance(unit, Mapping):
                    continue
                row, row_truncation = _project_atom_operand(unit, parent_item_id=item_id)
                if row is None:
                    continue
                if len(operands) >= MAX_MAPPING_OPERANDS:
                    omitted += 1
                    continue
                operands.append(row)
                _merge_truncation(field_truncation, row_truncation)
            continue

        if not _is_item_level_operand(item):
            continue
        row, row_truncation = _project_item_operand(item)
        if row is None:
            continue
        if len(operands) >= MAX_MAPPING_OPERANDS:
            omitted += 1
            continue
        operands.append(row)
        _merge_truncation(field_truncation, row_truncation)

    payload: dict[str, Any] = {
        "projection_mode": "mapping_operands",
        "resolution_state_ref": resolution_state_ref,
        "operands": operands,
        "totals": {
            "emitted": len(operands),
            "available": len(operands) + omitted,
        },
    }
    truncation: dict[str, int] = {}
    if omitted:
        truncation["operands_omitted"] = omitted
    truncation.update(field_truncation)
    if truncation:
        payload["truncation"] = truncation
    return payload


def build_operand_groups(operands: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Mechanically group call bearing/distance rows when operand ids encode call numbers."""
    pending: dict[tuple[str, int], dict[str, Any]] = {}
    blocker_groups: list[dict[str, Any]] = []

    for row in operands:
        if not isinstance(row, Mapping):
            continue
        if row.get("operand_role") == "scope_blocker":
            operand_id = str(row.get("operand_id") or "").strip()
            if not operand_id:
                continue
            blocker_groups.append(
                {
                    "group_id": f"{operand_id}_scope",
                    "parcel_id": row.get("parcel_id"),
                    "group_kind": "scope_blocker",
                    "rows": [
                        {
                            "operand_id": operand_id,
                            "title": row.get("title"),
                            "status": row.get("status"),
                            "determined_value": row.get("determined_value"),
                        }
                    ],
                }
            )
            continue

        operand_id = str(row.get("operand_id") or "").strip()
        match = _CALL_OPERAND_ID.match(operand_id)
        if match is None:
            continue
        parcel_id = f"parcel_{match.group('parcel_num')}"
        call_index = int(match.group("call_index"))
        key = (parcel_id, call_index)
        slot = pending.setdefault(
            key,
            {"call_index": call_index, "parcel_id": parcel_id},
        )
        value_kind = match.group("value_kind").lower()
        if value_kind == "bearing":
            slot["bearing_operand_id"] = operand_id
            slot["bearing_raw"] = row.get("determined_value")
        else:
            slot["distance_operand_id"] = operand_id
            slot["distance_raw"] = row.get("determined_value")

    by_parcel: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (parcel_id, call_index) in sorted(pending.keys(), key=lambda item: (item[0], item[1])):
        slot = pending[(parcel_id, call_index)]
        row: dict[str, Any] = {"call_index": call_index}
        if "bearing_operand_id" in slot:
            row["bearing_operand_id"] = slot["bearing_operand_id"]
            row["bearing_raw"] = slot.get("bearing_raw")
        if "distance_operand_id" in slot:
            row["distance_operand_id"] = slot["distance_operand_id"]
            row["distance_raw"] = slot.get("distance_raw")
        if len(row) > 1:
            by_parcel[parcel_id].append(row)

    groups: list[dict[str, Any]] = []
    for parcel_id in sorted(by_parcel):
        rows = by_parcel[parcel_id]
        if not rows:
            continue
        groups.append(
            {
                "group_id": f"{parcel_id}_calls",
                "parcel_id": parcel_id,
                "group_kind": "course_call_candidates",
                "rows": rows,
            }
        )
    groups.extend(blocker_groups)
    return groups


def _project_atom_operand(
    unit: Mapping[str, Any],
    *,
    parent_item_id: str,
) -> tuple[dict[str, Any] | None, dict[str, int]]:
    unit_id = str(unit.get("unit_id") or "").strip()
    if not unit_id or not _unit_is_mapping_operand(unit):
        return None, {}
    row, truncation = _bound_operand_fields(
        {
            "operand_id": unit_id,
            "parent_item_id": parent_item_id,
            "parcel_id": _infer_parcel_id(unit_id=unit_id, parent_item_id=parent_item_id),
            "title": unit.get("title"),
            "value_kind": unit.get("value_kind") or unit.get("kind"),
            "determined_value": unit.get("determined_value"),
            "candidate_values": unit.get("candidate_values"),
            "status": unit.get("status"),
            "determination": unit.get("determination"),
            "evidence_refs": unit.get("evidence_refs"),
            "evidence_locator_count": _evidence_locator_count(unit),
        }
    )
    return _compact_row(row), truncation


def _project_item_operand(item: Mapping[str, Any]) -> tuple[dict[str, Any] | None, dict[str, int]]:
    item_id = str(item.get("item_id") or "").strip()
    if not item_id:
        return None, {}
    row, truncation = _bound_operand_fields(
        {
            "operand_id": item_id,
            "parent_item_id": item_id,
            "parcel_id": _infer_parcel_id(unit_id=item_id, parent_item_id=item_id),
            "title": item.get("title"),
            "value_kind": item.get("value_kind") or item.get("kind"),
            "status": item.get("status"),
            "determination": item.get("determination"),
            "determined_value": item.get("determined_value") or item.get("summary"),
            "candidate_values": item.get("candidate_values"),
            "evidence_refs": item.get("evidence_refs"),
            "evidence_locator_count": _evidence_locator_count(item),
        }
    )
    if _is_scope_blocker_item(item):
        row["operand_role"] = "scope_blocker"
    return _compact_row(row), truncation


def _bound_operand_fields(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    truncation: dict[str, int] = {}
    title, title_truncated = _bound_text(row.get("title"), MAX_OPERAND_TITLE_CHARS)
    if title_truncated:
        truncation["title_chars_truncated"] = truncation.get("title_chars_truncated", 0) + 1
    row["title"] = title

    value_kind, value_kind_truncated = _bound_text(row.get("value_kind"), MAX_OPERAND_TITLE_CHARS)
    if value_kind_truncated:
        truncation["value_kind_chars_truncated"] = truncation.get("value_kind_chars_truncated", 0) + 1
    row["value_kind"] = value_kind

    determined_value, value_truncated = _bound_text(
        row.get("determined_value"),
        MAX_OPERAND_DETERMINED_VALUE_CHARS,
    )
    if value_truncated:
        truncation["determined_value_chars_truncated"] = (
            truncation.get("determined_value_chars_truncated", 0) + 1
        )
    row["determined_value"] = determined_value

    candidates, candidate_truncation = _bound_candidate_values(row.get("candidate_values"))
    row["candidate_values"] = candidates
    _merge_truncation(truncation, candidate_truncation)

    evidence_refs, evidence_truncation = _bound_evidence_refs(row.get("evidence_refs"))
    row["evidence_refs"] = evidence_refs
    _merge_truncation(truncation, evidence_truncation)

    return row, truncation


def _bound_candidate_values(value: Any) -> tuple[list[str], dict[str, int]]:
    truncation: dict[str, int] = {}
    if not isinstance(value, list):
        return [], truncation
    out: list[str] = []
    omitted = 0
    for item in value:
        if len(out) >= MAX_OPERAND_CANDIDATE_VALUES:
            omitted += 1
            continue
        if not isinstance(item, str) or not item.strip():
            continue
        bounded, truncated = _bound_text(item, MAX_OPERAND_CANDIDATE_VALUE_CHARS)
        if bounded is None:
            continue
        out.append(bounded)
        if truncated:
            truncation["candidate_value_chars_truncated"] = (
                truncation.get("candidate_value_chars_truncated", 0) + 1
            )
    if omitted:
        truncation["candidate_values_omitted"] = omitted
    return out, truncation


def _bound_evidence_refs(value: Any) -> tuple[list[str], dict[str, int]]:
    truncation: dict[str, int] = {}
    if not isinstance(value, list):
        return [], truncation
    out: list[str] = []
    omitted = 0
    for item in value:
        if len(out) >= MAX_OPERAND_EVIDENCE_REFS:
            omitted += 1
            continue
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    if omitted:
        truncation["evidence_refs_omitted"] = omitted
    return out, truncation


def _bound_text(value: Any, max_chars: int) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    text = str(value).strip()
    if not text:
        return None, False
    if len(text) <= max_chars:
        return text, False
    return text[: max_chars - 1].rstrip() + "…", True


def _merge_truncation(target: dict[str, int], source: Mapping[str, int]) -> None:
    for key, count in source.items():
        if count:
            target[key] = target.get(key, 0) + int(count)


def _unit_is_mapping_operand(unit: Mapping[str, Any]) -> bool:
    if unit.get("determined_value") in (None, ""):
        return False
    status = str(unit.get("status") or "").lower()
    determination = str(unit.get("determination") or "").lower()
    return status in {"closed", "determined", "earned"} or determination in {"earned", "verified"}


def _is_scope_blocker_item(item: Mapping[str, Any]) -> bool:
    if item.get("blocking") is True:
        return True
    if item.get("no_further_progress") is True:
        return True
    return str(item.get("status") or "").lower() == "blocked"


def _is_item_level_operand(item: Mapping[str, Any]) -> bool:
    if _is_scope_blocker_item(item):
        return True
    if item.get("determination") or item.get("determined_value"):
        return True
    kind = str(item.get("kind") or "").lower()
    return kind in {"open_question", "missing_source_scope"}


def _infer_parcel_id(*, unit_id: str, parent_item_id: str) -> str | None:
    for source in (parent_item_id, unit_id):
        if not source:
            continue
        match = _PARCEL_ID_FROM_ITEM.match(source)
        if match:
            return f"parcel_{match.group(1)}"
        if source.startswith("p1_"):
            return "parcel_1"
        if source.startswith("p2_"):
            return "parcel_2"
    return None


def _evidence_locator_count(row: Mapping[str, Any]) -> int:
    locators = row.get("evidence_locators")
    return len(locators) if isinstance(locators, list) else 0


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "", [])}
