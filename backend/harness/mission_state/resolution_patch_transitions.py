"""Agent-authored resolution lifecycle transitions for sparse state patches.

``transition`` is patch-grammar only. It expands into deterministic live-work
clears before merge preview and commit, then is stripped so it never persists
inside ``ResolutionState``.

Harness-owned and domain-agnostic: no transcript-edit / deed vocabulary.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import ResolutionItem, ResolutionState

TRANSITION_KIND_RESOLVE = "resolve"

_ITEM_CONSEQUENCE_FIELDS = frozenset(
    {
        "status",
        "next_needed_step",
        "requires_hitl",
        "no_further_progress",
        "blocking",
    }
)
_UNIT_CONSEQUENCE_FIELDS = frozenset(
    {
        "status",
        "next_needed_step",
        "requires_hitl",
        "no_further_progress",
    }
)

_RESOLVE_ITEM_EXPANSION: dict[str, Any] = {
    "status": "closed",
    "next_needed_step": None,
    "requires_hitl": False,
    "no_further_progress": False,
    "blocking": False,
}
_RESOLVE_UNIT_EXPANSION: dict[str, Any] = {
    "status": "closed",
    "next_needed_step": None,
    "requires_hitl": False,
    "no_further_progress": False,
}


class ResolutionPatchTransitionError(ValueError):
    """Invalid transition grammar or missing resolution coordinate."""

    def __init__(
        self,
        reason_code: str,
        message: str,
        *,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.detail = dict(detail or {})


def expand_resolution_patch_transitions(
    *,
    resolution_state: ResolutionState,
    state_patch: Mapping[str, Any],
) -> dict[str, Any]:
    """Expand ``transition: {kind: resolve}`` into mechanical live-work clears.

    Returns a patch dict safe for merge. When no transitions are present, returns
    a shallow copy of the input mapping (values shared). When transitions are
    present, returns a deep-copied resolution branch with ``transition`` removed
    and consequence fields injected.
    """
    patch = dict(state_patch)
    resolution = patch.get("resolution")
    if not isinstance(resolution, dict):
        return patch
    items = resolution.get("items")
    if not isinstance(items, list):
        return patch

    if not _patch_contains_transition(items):
        return patch

    by_id = {item.item_id: item for item in resolution_state.items}
    expanded_items: list[Any] = []
    for index, row in enumerate(items):
        if not isinstance(row, dict):
            expanded_items.append(row)
            continue
        expanded_items.append(
            _expand_item_row(
                row=dict(row),
                index=index,
                existing_by_id=by_id,
            )
        )

    resolution_out = dict(resolution)
    resolution_out["items"] = expanded_items
    out = dict(patch)
    out["resolution"] = resolution_out
    return out


def _patch_contains_transition(items: list[Any]) -> bool:
    for row in items:
        if not isinstance(row, dict):
            continue
        if "transition" in row:
            return True
        units = row.get("covered_units")
        if isinstance(units, list):
            for unit in units:
                if isinstance(unit, dict) and "transition" in unit:
                    return True
    return False


def _expand_item_row(
    *,
    row: dict[str, Any],
    index: int,
    existing_by_id: dict[str, ResolutionItem],
) -> dict[str, Any]:
    units = row.get("covered_units")
    has_unit_transition = isinstance(units, list) and any(
        isinstance(unit, dict) and "transition" in unit for unit in units
    )
    has_item_transition = "transition" in row
    if not has_item_transition and not has_unit_transition:
        return row

    item_id = _require_item_id(row, index=index)
    path = f"resolution.items[{item_id}]"
    existing = existing_by_id.get(item_id)

    if has_item_transition:
        if existing is None:
            raise ResolutionPatchTransitionError(
                "transition_target_missing",
                f"{path}: transition requires an already-existing resolution item.",
                detail={"failing_path": path, "item_id": item_id},
            )
        _assert_transition_object(row.get("transition"), path=f"{path}.transition")
        _assert_no_consequence_fields(
            row,
            forbidden=_ITEM_CONSEQUENCE_FIELDS,
            path=path,
        )
        row.pop("transition", None)
        row.update(_RESOLVE_ITEM_EXPANSION)

    if has_unit_transition:
        if existing is None:
            raise ResolutionPatchTransitionError(
                "transition_target_missing",
                f"{path}: covered-unit transition requires an already-existing parent item.",
                detail={"failing_path": path, "item_id": item_id},
            )
        existing_unit_ids: set[str] = set()
        for unit in existing.covered_units or []:
            uid = getattr(unit, "unit_id", None)
            if isinstance(uid, str) and uid:
                existing_unit_ids.add(uid)
        expanded_units: list[Any] = []
        for u_index, unit_row in enumerate(units):
            if not isinstance(unit_row, dict):
                expanded_units.append(unit_row)
                continue
            expanded_units.append(
                _expand_unit_row(
                    row=dict(unit_row),
                    index=u_index,
                    item_id=item_id,
                    existing_unit_ids=frozenset(existing_unit_ids),
                )
            )
        row["covered_units"] = expanded_units
    return row


def _expand_unit_row(
    *,
    row: dict[str, Any],
    index: int,
    item_id: str,
    existing_unit_ids: frozenset[str],
) -> dict[str, Any]:
    unit_id = _require_unit_id(row, item_id=item_id, index=index)
    path = f"resolution.items[{item_id}].covered_units[{unit_id}]"
    if "transition" not in row:
        return row
    if unit_id not in existing_unit_ids:
        raise ResolutionPatchTransitionError(
            "transition_target_missing",
            f"{path}: transition requires an already-existing covered unit.",
            detail={"failing_path": path, "item_id": item_id, "unit_id": unit_id},
        )
    _assert_transition_object(row.get("transition"), path=f"{path}.transition")
    _assert_no_consequence_fields(
        row,
        forbidden=_UNIT_CONSEQUENCE_FIELDS,
        path=path,
    )
    row.pop("transition", None)
    row.update(_RESOLVE_UNIT_EXPANSION)
    return row


def _require_item_id(row: Mapping[str, Any], *, index: int) -> str:
    raw = row.get("item_id")
    if type(raw) is not str or not raw.strip():
        raise ResolutionPatchTransitionError(
            "transition_item_id_required",
            f"resolution.items[{index}].item_id must be a nonblank string when transition is used.",
            detail={"failing_path": f"resolution.items[{index}].item_id"},
        )
    return raw.strip()


def _require_unit_id(row: Mapping[str, Any], *, item_id: str, index: int) -> str:
    raw = row.get("unit_id")
    if type(raw) is not str or not raw.strip():
        raise ResolutionPatchTransitionError(
            "transition_unit_id_required",
            (
                f"resolution.items[{item_id}].covered_units[{index}].unit_id must be a "
                "nonblank string when transition is used."
            ),
            detail={
                "failing_path": f"resolution.items[{item_id}].covered_units[{index}].unit_id"
            },
        )
    return raw.strip()


def _assert_transition_object(value: Any, *, path: str) -> None:
    if type(value) is not dict:
        raise ResolutionPatchTransitionError(
            "transition_invalid",
            f"{path} must be an object with exactly kind='resolve'.",
            detail={"failing_path": path},
        )
    unknown = sorted(set(value) - {"kind"})
    if unknown:
        raise ResolutionPatchTransitionError(
            "transition_unknown_fields",
            f"{path} unknown fields: {unknown}",
            detail={"failing_path": path, "unknown_fields": unknown},
        )
    kind = value.get("kind")
    if type(kind) is not str or kind != TRANSITION_KIND_RESOLVE:
        raise ResolutionPatchTransitionError(
            "transition_kind_unsupported",
            f"{path}.kind must be the exact string {TRANSITION_KIND_RESOLVE!r}.",
            detail={"failing_path": f"{path}.kind", "got": kind},
        )


def _assert_no_consequence_fields(
    row: Mapping[str, Any],
    *,
    forbidden: frozenset[str],
    path: str,
) -> None:
    present = sorted(k for k in forbidden if k in row)
    if present:
        raise ResolutionPatchTransitionError(
            "transition_consequence_fields_conflict",
            (
                f"{path}: when transition is present, do not also supply mechanical "
                f"consequence fields {present}; use transition alone for those clears."
            ),
            detail={"failing_path": path, "conflicting_fields": present},
        )

