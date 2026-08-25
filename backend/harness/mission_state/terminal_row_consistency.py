"""Pure consistency checks for resolved-like resolution rows with live-work posture.

Mechanical only: does not clear fields, reopen rows, or judge semantic correctness.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import ResolutionCoveredUnit, ResolutionItem, ResolutionState

# Shared closed-like vocabulary (also used by state_patch_shape_repair advisory).
CLOSED_LIKE_STATUSES = frozenset({"closed", "earned", "resolved", "complete"})

REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK = "resolution_terminal_row_has_live_work"
MAX_TERMINAL_ROW_CONFLICTS = 32
_EARNED_DETERMINATION = "earned"
_LIVE_WORK_FIELD_ORDER = ("next_needed_step", "requires_hitl", "no_further_progress")


@dataclass(frozen=True)
class TerminalRowConflict:
    coordinate: str
    fields: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "coordinate": self.coordinate,
            "fields": list(self.fields),
        }


@dataclass(frozen=True)
class TerminalRowConsistencyResult:
    reason_code: str
    conflicts: tuple[TerminalRowConflict, ...]
    conflicts_omitted_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "conflicts": [row.as_dict() for row in self.conflicts],
            "conflicts_omitted_count": int(self.conflicts_omitted_count),
        }


def _normalized_token(value: Any) -> str | None:
    if type(value) is not str:
        return None
    text = value.strip().lower()
    return text if text else None


def is_resolved_like(*, status: Any = None, determination: Any = None) -> bool:
    """True when status is closed-like or determination is earned (actual strings only)."""
    status_token = _normalized_token(status)
    if status_token is not None and status_token in CLOSED_LIKE_STATUSES:
        return True
    determination_token = _normalized_token(determination)
    return determination_token == _EARNED_DETERMINATION


def live_work_fields_present(row: Any) -> tuple[str, ...]:
    """Return whole live-work field names still set on a resolved-like row."""
    if isinstance(row, (ResolutionItem, ResolutionCoveredUnit)):
        data = {
            "next_needed_step": row.next_needed_step,
            "requires_hitl": row.requires_hitl,
            "no_further_progress": row.no_further_progress,
        }
    elif isinstance(row, Mapping):
        data = row
    else:
        return ()

    found: list[str] = []
    next_step = data.get("next_needed_step")
    if type(next_step) is str and next_step.strip():
        found.append("next_needed_step")
    if data.get("requires_hitl") is True:
        found.append("requires_hitl")
    if data.get("no_further_progress") is True:
        found.append("no_further_progress")
    return tuple(name for name in _LIVE_WORK_FIELD_ORDER if name in found)


def item_coordinate(item_id: str) -> str:
    return f"resolution.items[{item_id}]"


def covered_unit_coordinate(item_id: str, unit_id: str) -> str:
    return f"resolution.items[{item_id}].covered_units[{unit_id}]"


def evaluate_addressed_terminal_row_consistency(
    *,
    resolution_state: ResolutionState,
    addressed_item_ids: Sequence[str],
    addressed_unit_ids_by_item: Mapping[str, Sequence[str]],
) -> TerminalRowConsistencyResult | None:
    """Evaluate only addressed coordinates against fully merged rows.

    Returns a bounded conflict result, or ``None`` when no contradiction exists.
    """
    by_id = {item.item_id: item for item in resolution_state.items}
    conflicts: list[TerminalRowConflict] = []
    omitted = 0
    seen_coords: set[str] = set()

    def _append(coordinate: str, fields: tuple[str, ...]) -> None:
        nonlocal omitted
        if not fields or coordinate in seen_coords:
            return
        seen_coords.add(coordinate)
        if len(conflicts) >= MAX_TERMINAL_ROW_CONFLICTS:
            omitted += 1
            return
        conflicts.append(TerminalRowConflict(coordinate=coordinate, fields=fields))

    for item_id in addressed_item_ids:
        if type(item_id) is not str or not item_id.strip():
            continue
        item = by_id.get(item_id)
        if item is None:
            continue
        if is_resolved_like(status=item.status, determination=item.determination):
            _append(item_coordinate(item_id), live_work_fields_present(item))

    for item_id, unit_ids in addressed_unit_ids_by_item.items():
        if type(item_id) is not str or not item_id.strip():
            continue
        item = by_id.get(item_id)
        if item is None:
            continue
        units_by_id = {unit.unit_id: unit for unit in item.covered_units}
        for unit_id in unit_ids:
            if type(unit_id) is not str or not unit_id.strip():
                continue
            unit = units_by_id.get(unit_id)
            if unit is None:
                continue
            if is_resolved_like(status=unit.status, determination=unit.determination):
                _append(
                    covered_unit_coordinate(item_id, unit_id),
                    live_work_fields_present(unit),
                )

    if not conflicts and omitted == 0:
        return None
    return TerminalRowConsistencyResult(
        reason_code=REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
        conflicts=tuple(conflicts),
        conflicts_omitted_count=omitted,
    )
