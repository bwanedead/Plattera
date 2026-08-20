"""Repair-lane-only salvage of root-owned prose nested inside ``state_patch``.

Moves already-authored values to the action-plan root when the placement is
unambiguous. Does not invent, rewrite, or choose between conflicting content.
The canonical action-plan parser remains the final authority and must not
accept nested prose as a supported input shape.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

RELOCATABLE_PROSE_FIELDS = (
    "rationale",
    "operator_progress_message",
    "continuity_journal_entry",
)

_MOVE_TRANSFORMATION_IDS = {
    "rationale": "move_state_patch_rationale_to_root",
    "operator_progress_message": "move_state_patch_operator_progress_message_to_root",
    "continuity_journal_entry": "move_state_patch_continuity_journal_entry_to_root",
}


@dataclass(frozen=True)
class ProsePlacementNormalization:
    payload: dict[str, Any]
    transformations: tuple[str, ...]


def normalize_misplaced_action_plan_prose(
    payload: Mapping[str, Any],
) -> ProsePlacementNormalization:
    """Return a copy with allowlisted nested prose relocated when unambiguous."""
    out = dict(payload)
    raw_patch = out.get("state_patch")
    if not isinstance(raw_patch, Mapping):
        return ProsePlacementNormalization(payload=out, transformations=())
    patch = dict(raw_patch)
    transformations: list[str] = []
    for field in RELOCATABLE_PROSE_FIELDS:
        if field not in patch:
            continue
        nested = patch[field]
        if not _has_canonical_field_type(field, nested):
            continue
        if field not in out:
            out[field] = nested
            del patch[field]
            transformations.append(_MOVE_TRANSFORMATION_IDS[field])
            continue
        if out[field] == nested:
            del patch[field]
            transformations.append(f"remove_equal_nested_{field}")
    out["state_patch"] = patch
    return ProsePlacementNormalization(payload=out, transformations=tuple(transformations))


def _has_canonical_field_type(field: str, value: Any) -> bool:
    if field == "rationale":
        return isinstance(value, str)
    if field == "operator_progress_message":
        return value is None or isinstance(value, str)
    if field == "continuity_journal_entry":
        return value is None or isinstance(value, dict)
    return False
