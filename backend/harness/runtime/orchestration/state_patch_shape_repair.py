"""Mechanical container-shape repair for model-authored ``state_patch`` payloads.

Coerces obvious singleton scalars/mappings into list-shaped fields before
Pydantic validation. Does not invent semantics or alter field meaning.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from ...mission_state import EvidenceLocator

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
        out["items"] = _coerce_object_list(
            out["items"],
            predicate=_looks_like_resolution_item,
            path=f"{path}.items",
            repair_kind="mapping_to_singleton_list",
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
        out["relations"] = _coerce_object_list(
            out["relations"],
            predicate=_looks_like_resolution_relation,
            path=f"{path}.relations",
            repair_kind="mapping_to_singleton_list",
            repairs=repairs,
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
        out["success_conditions"] = _coerce_object_list(
            out["success_conditions"],
            predicate=_looks_like_success_condition,
            path=f"{path}.success_conditions",
            repair_kind="mapping_to_singleton_list",
            repairs=repairs,
        )
    if "closure_state" in out and isinstance(out["closure_state"], dict):
        closure = dict(out["closure_state"])
        if "dimensions" in closure:
            closure["dimensions"] = _coerce_object_list(
                closure["dimensions"],
                predicate=_looks_like_closure_dimension,
                path=f"{path}.closure_state.dimensions",
                repair_kind="mapping_to_singleton_list",
                repairs=repairs,
            )
        out["closure_state"] = closure
    return out


def _repair_resolution_item_row(row: dict[str, Any], *, path: str, repairs: list[dict[str, str]]) -> dict[str, Any]:
    out = dict(row)
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
        out["history"] = _coerce_object_list(
            out["history"],
            predicate=_looks_like_history_entry,
            path=f"{path}.history",
            repair_kind="mapping_to_singleton_list",
            repairs=repairs,
        )
    if "covered_units" in out:
        out["covered_units"] = _coerce_object_list(
            out["covered_units"],
            predicate=_looks_like_covered_unit,
            path=f"{path}.covered_units",
            repair_kind="mapping_to_singleton_list",
            repairs=repairs,
        )
        if isinstance(out["covered_units"], list):
            out["covered_units"] = [
                _repair_covered_unit_row(unit, path=f"{path}.covered_units[{index}]", repairs=repairs)
                if isinstance(unit, dict)
                else unit
                for index, unit in enumerate(out["covered_units"])
            ]
    return out


def _repair_covered_unit_row(row: dict[str, Any], *, path: str, repairs: list[dict[str, str]]) -> dict[str, Any]:
    out = dict(row)
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
    return out


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


def _coerce_object_list(
    value: Any,
    *,
    predicate,
    path: str,
    repair_kind: str,
    repairs: list[dict[str, str]],
) -> Any:
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and predicate(value):
        _record_repair(repairs, path=path, repair=repair_kind)
        return [value]
    return value


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
    repairs.append(
        {
            "path": path[:MAX_SHAPE_REPAIR_PATH_CHARS],
            "repair": repair[:MAX_SHAPE_REPAIR_KIND_CHARS],
        }
    )
