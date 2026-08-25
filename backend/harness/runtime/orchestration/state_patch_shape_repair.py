"""Mechanical container-shape repair for model-authored ``state_patch`` payloads.

Coerces obvious singleton scalars/mappings into list-shaped fields, normalizes
unambiguous keyed object maps to canonical arrays, and strips known host-derived
projection fields before Pydantic validation. Does not invent semantics.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import ValidationError

from ...mission_state import EvidenceLocator
from ...mission_state.terminal_row_consistency import CLOSED_LIKE_STATUSES

MAX_SHAPE_REPAIRS = 20
MAX_SHAPE_REPAIR_PATH_CHARS = 400
MAX_SHAPE_REPAIR_KIND_CHARS = 64

_STRING_LIST_FIELDS = frozenset(
    {
        "reopen_triggers",
        "evidence_refs",
        "candidate_values",
        "dependencies",
    }
)

# Host-derived / projection-only fields agents sometimes copy back into patches.
READ_ONLY_PATCH_FIELDS = frozenset(
    {
        "evidence_ref_count",
    }
)

_CLOSED_LIKE_STATUSES = CLOSED_LIKE_STATUSES


def repair_state_patch_container_shapes(
    state_patch: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Return a repaired patch copy and compact shape-repair audit rows."""
    repairs: list[dict[str, str]] = []
    repaired = _repair_patch_root(dict(state_patch), repairs=repairs)
    return repaired, repairs[:MAX_SHAPE_REPAIRS]


def _repair_patch_root(patch: dict[str, Any], *, repairs: list[dict[str, str]]) -> dict[str, Any]:
    out = dict(patch)
    if "resolution" in out and isinstance(out["resolution"], dict):
        out["resolution"] = _repair_resolution_branch(out["resolution"], path="state_patch.resolution", repairs=repairs)
    if "mission" in out and isinstance(out["mission"], dict):
        out["mission"] = _repair_mission_branch(out["mission"], path="state_patch.mission", repairs=repairs)
    return out


def _repair_resolution_branch(raw: dict[str, Any], *, path: str, repairs: list[dict[str, str]]) -> dict[str, Any]:
    out = dict(raw)
    if "items" in out:
        out["items"] = _normalize_object_list_field(
            out["items"],
            id_field="item_id",
            row_predicate=_looks_like_resolution_item,
            path=f"{path}.items",
            repairs=repairs,
        )
        if isinstance(out["items"], list):
            out["items"] = [
                _repair_resolution_item_row(row, path=f"{path}.items[{index}]", repairs=repairs)
                if isinstance(row, dict)
                else row
                for index, row in enumerate(out["items"])
            ]
    if "relations" in out:
        out["relations"] = _normalize_object_list_field(
            out["relations"],
            id_field="relation_id",
            row_predicate=_looks_like_resolution_relation,
            path=f"{path}.relations",
            repairs=repairs,
            allow_keyed_map=False,
        )
    return out


def _repair_mission_branch(raw: dict[str, Any], *, path: str, repairs: list[dict[str, str]]) -> dict[str, Any]:
    out = dict(raw)
    if "high_signal_artifact_refs" in out:
        coerced, repair_kind = _coerce_string_to_singleton_list(out["high_signal_artifact_refs"])
        if repair_kind:
            _record_repair(repairs, path=f"{path}.high_signal_artifact_refs", repair=repair_kind)
            out["high_signal_artifact_refs"] = coerced
    if "success_conditions" in out:
        out["success_conditions"] = _normalize_object_list_field(
            out["success_conditions"],
            id_field="condition_id",
            row_predicate=_looks_like_success_condition,
            path=f"{path}.success_conditions",
            repairs=repairs,
            allow_keyed_map=False,
        )
    if "closure_state" in out and isinstance(out["closure_state"], dict):
        closure = dict(out["closure_state"])
        if "dimensions" in closure:
            closure["dimensions"] = _normalize_object_list_field(
                closure["dimensions"],
                id_field="dimension_id",
                row_predicate=_looks_like_closure_dimension,
                path=f"{path}.closure_state.dimensions",
                repairs=repairs,
                allow_keyed_map=False,
            )
        out["closure_state"] = closure
    return out


def _repair_resolution_item_row(row: dict[str, Any], *, path: str, repairs: list[dict[str, str]]) -> dict[str, Any]:
    out = _strip_read_only_fields(row, path=path, repairs=repairs)
    for field in _STRING_LIST_FIELDS:
        if field not in out:
            continue
        coerced, repair_kind = _coerce_string_to_singleton_list(out[field])
        if repair_kind:
            _record_repair(repairs, path=f"{path}.{field}", repair=repair_kind)
            out[field] = coerced
    if "evidence_locators" in out:
        out["evidence_locators"] = _coerce_evidence_locators(
            out["evidence_locators"], path=f"{path}.evidence_locators", repairs=repairs
        )
    if "history" in out:
        out["history"] = _normalize_object_list_field(
            out["history"],
            id_field="event_kind",
            row_predicate=_looks_like_history_entry,
            path=f"{path}.history",
            repairs=repairs,
            allow_keyed_map=False,
        )
    if "covered_units" in out:
        out["covered_units"] = _normalize_object_list_field(
            out["covered_units"],
            id_field="unit_id",
            row_predicate=_looks_like_covered_unit,
            path=f"{path}.covered_units",
            repairs=repairs,
        )
        if isinstance(out["covered_units"], list):
            out["covered_units"] = [
                _repair_covered_unit_row(unit, path=f"{path}.covered_units[{index}]", repairs=repairs)
                if isinstance(unit, dict)
                else unit
                for index, unit in enumerate(out["covered_units"])
            ]
    _maybe_record_stale_live_field_advisory(out, path=path, repairs=repairs)
    return out


def _repair_covered_unit_row(row: dict[str, Any], *, path: str, repairs: list[dict[str, str]]) -> dict[str, Any]:
    out = _strip_read_only_fields(row, path=path, repairs=repairs)
    for field in _STRING_LIST_FIELDS:
        if field not in out:
            continue
        coerced, repair_kind = _coerce_string_to_singleton_list(out[field])
        if repair_kind:
            _record_repair(repairs, path=f"{path}.{field}", repair=repair_kind)
            out[field] = coerced
    if "evidence_locators" in out:
        out["evidence_locators"] = _coerce_evidence_locators(
            out["evidence_locators"], path=f"{path}.evidence_locators", repairs=repairs
        )
    _maybe_record_stale_live_field_advisory(out, path=path, repairs=repairs)
    return out


def _normalize_object_list_field(
    value: Any,
    *,
    id_field: str,
    row_predicate: Callable[[Mapping[str, Any]], bool],
    path: str,
    repairs: list[dict[str, str]],
    allow_keyed_map: bool = True,
) -> Any:
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return value
    if row_predicate(value):
        _record_repair(repairs, path=path, repair="mapping_to_singleton_list")
        return [value]
    if not allow_keyed_map:
        _record_repair(repairs, path=path, repair="invalid_keyed_map_rejected")
        return value
    normalized, code = _try_keyed_map_to_array(
        value,
        id_field=id_field,
        path=path,
    )
    if code:
        _record_repair(repairs, path=path, repair=code)
    if code == "keyed_map_to_array":
        return normalized
    return value


def _try_keyed_map_to_array(
    value: Mapping[str, Any],
    *,
    id_field: str,
    path: str,
) -> tuple[Any, str | None]:
    if not value:
        return value, None
    rows: list[dict[str, Any]] = []
    for key, inner in value.items():
        if not isinstance(key, str) or not key.strip():
            return value, "invalid_keyed_map_rejected"
        if not isinstance(inner, Mapping):
            return value, "invalid_keyed_map_rejected"
        key_text = key.strip()
        inner_id_raw = inner.get(id_field) if isinstance(inner, Mapping) else None
        inner_id = str(inner_id_raw).strip() if inner_id_raw is not None else ""
        if inner_id and inner_id != key_text:
            return value, "key_id_conflict_rejected"
        row = dict(inner)
        if not inner_id:
            row[id_field] = key_text
        rows.append(row)
    return rows, "keyed_map_to_array"


def _strip_read_only_fields(
    row: Mapping[str, Any],
    *,
    path: str,
    repairs: list[dict[str, str]],
) -> dict[str, Any]:
    out = dict(row)
    for field in READ_ONLY_PATCH_FIELDS:
        if field not in out:
            continue
        del out[field]
        _record_repair(repairs, path=f"{path}.{field}", repair="read_only_field_ignored")
    return out


def _maybe_record_stale_live_field_advisory(
    row: Mapping[str, Any],
    *,
    path: str,
    repairs: list[dict[str, str]],
) -> None:
    status = str(row.get("status") or "").strip().lower()
    if status not in _CLOSED_LIKE_STATUSES:
        return
    next_step = row.get("next_needed_step")
    if isinstance(next_step, str) and next_step.strip():
        _record_repair(repairs, path=f"{path}.next_needed_step", repair="stale_live_field_advisory")


def _coerce_string_to_singleton_list(value: Any) -> tuple[Any, str | None]:
    if isinstance(value, list):
        return value, None
    if isinstance(value, str):
        text = value.strip()
        if text:
            return [text], "string_to_singleton_list"
    return value, None


def _coerce_evidence_locators(
    value: Any,
    *,
    path: str,
    repairs: list[dict[str, str]],
) -> Any:
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return value
    try:
        EvidenceLocator.model_validate(value)
    except ValidationError:
        return value
    _record_repair(repairs, path=path, repair="mapping_to_singleton_list")
    return [value]


def _looks_like_resolution_item(row: Mapping[str, Any]) -> bool:
    item_id = row.get("item_id")
    return isinstance(item_id, str) and bool(item_id.strip())


def _looks_like_covered_unit(row: Mapping[str, Any]) -> bool:
    unit_id = row.get("unit_id")
    return isinstance(unit_id, str) and bool(unit_id.strip())


def _looks_like_resolution_relation(row: Mapping[str, Any]) -> bool:
    source = row.get("source_item_id")
    target = row.get("target_item_id")
    relation_type = row.get("relation_type")
    return (
        isinstance(source, str)
        and bool(source.strip())
        and isinstance(target, str)
        and bool(target.strip())
        and isinstance(relation_type, str)
        and bool(relation_type.strip())
    )


def _looks_like_success_condition(row: Mapping[str, Any]) -> bool:
    condition_id = row.get("condition_id")
    return isinstance(condition_id, str) and bool(condition_id.strip())


def _looks_like_closure_dimension(row: Mapping[str, Any]) -> bool:
    dimension_id = row.get("dimension_id")
    return isinstance(dimension_id, str) and bool(dimension_id.strip())


def _looks_like_history_entry(row: Mapping[str, Any]) -> bool:
    event_kind = row.get("event_kind")
    return isinstance(event_kind, str) and bool(event_kind.strip())


def _record_repair(repairs: list[dict[str, str]], *, path: str, repair: str) -> None:
    if len(repairs) >= MAX_SHAPE_REPAIRS:
        return
    entry: dict[str, str] = {
        "path": path[:MAX_SHAPE_REPAIR_PATH_CHARS],
        "repair": repair[:MAX_SHAPE_REPAIR_KIND_CHARS],
    }
    if repair == "keyed_map_to_array":
        entry["expected_shape"] = "array"
    if repair in ("key_id_conflict_rejected", "invalid_keyed_map_rejected"):
        entry["expected_shape"] = "array"
    repairs.append(entry)
