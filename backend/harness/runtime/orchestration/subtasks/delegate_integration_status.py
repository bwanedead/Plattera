"""Mechanical integration visibility for delegate ``subtask:*`` refs.

Exact-string scanning only — no semantic inference about whether an observation
should be trusted, closed, or treated as evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

STATUS_REFERENCED_IN_STATE = "referenced_in_state"
STATUS_REFERENCED_IN_REPAIR_BUNDLE = "referenced_in_repair_bundle"
STATUS_INTEGRATED_VIA_CONTEXT_REF = "integrated_via_context_ref"
STATUS_UNREFERENCED_RECENT = "unreferenced_recent"
STATUS_UNREFERENCED_STALE = "unreferenced_stale"

RECENT_TURN_AGE = 1

DELEGATE_INTEGRATION_REPAIR_NOTE = (
    "Delegate result refs are available. "
    "Hydrate or repair from these refs before re-running equivalent delegate work."
)


def compute_delegate_ref_integration_status(
    *,
    ref_id: str,
    record_turn_index: int,
    current_turn: int,
    mission_state: Mapping[str, Any] | None = None,
    resolution_state: Mapping[str, Any] | None = None,
    repair_bundle: Mapping[str, Any] | None = None,
) -> str:
    """Return mechanical integration status for one delegate result ref."""
    text = str(ref_id or "").strip()
    if not text:
        return STATUS_UNREFERENCED_STALE

    state_roots: list[Any] = []
    if isinstance(mission_state, Mapping):
        state_roots.append(mission_state)
    if isinstance(resolution_state, Mapping):
        state_roots.append(resolution_state)

    if any(_exact_ref_in_value(root, text) for root in state_roots):
        return STATUS_REFERENCED_IN_STATE

    if isinstance(repair_bundle, Mapping) and _exact_ref_in_value(repair_bundle, text):
        return STATUS_REFERENCED_IN_REPAIR_BUNDLE

    try:
        turn = int(record_turn_index)
    except (TypeError, ValueError):
        turn = 0
    age = max(0, int(current_turn) - turn) if turn else RECENT_TURN_AGE + 1
    if age <= RECENT_TURN_AGE:
        return STATUS_UNREFERENCED_RECENT
    return STATUS_UNREFERENCED_STALE


def compute_delegate_observation_integration_status(
    *,
    ref_id: str,
    context_refs: Sequence[str] | None = None,
    record_turn_index: int,
    current_turn: int,
    mission_state: Mapping[str, Any] | None = None,
    resolution_state: Mapping[str, Any] | None = None,
    repair_bundle: Mapping[str, Any] | None = None,
) -> str:
    """Return integration status for one delegate observation (ref + context refs)."""
    direct = compute_delegate_ref_integration_status(
        ref_id=ref_id,
        record_turn_index=record_turn_index,
        current_turn=current_turn,
        mission_state=mission_state,
        resolution_state=resolution_state,
        repair_bundle=repair_bundle,
    )
    if direct in (STATUS_REFERENCED_IN_STATE, STATUS_REFERENCED_IN_REPAIR_BUNDLE):
        return direct

    state_roots: list[Any] = []
    if isinstance(mission_state, Mapping):
        state_roots.append(mission_state)
    if isinstance(resolution_state, Mapping):
        state_roots.append(resolution_state)

    for ctx_ref in _normalized_context_refs(context_refs):
        if any(_exact_ref_in_value(root, ctx_ref) for root in state_roots):
            return STATUS_INTEGRATED_VIA_CONTEXT_REF
        if isinstance(repair_bundle, Mapping) and _exact_ref_in_value(repair_bundle, ctx_ref):
            return STATUS_REFERENCED_IN_REPAIR_BUNDLE

    return direct


def scan_delegate_results_integration(
    records: Sequence[Mapping[str, Any]] | None,
    *,
    current_turn: int,
    mission_state: Mapping[str, Any] | None = None,
    resolution_state: Mapping[str, Any] | None = None,
    repair_bundle: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Map ``ref_id`` → integration status for stored delegate result records."""
    out: dict[str, str] = {}
    if not records:
        return out
    for record in records:
        if not isinstance(record, Mapping):
            continue
        ref_id = str(record.get("ref_id") or "").strip()
        if not ref_id:
            continue
        try:
            record_turn = int(record.get("turn_index") or record.get("created_at_turn") or 0)
        except (TypeError, ValueError):
            record_turn = 0
        out[ref_id] = compute_delegate_observation_integration_status(
            ref_id=ref_id,
            context_refs=record.get("context_refs"),
            record_turn_index=record_turn,
            current_turn=int(current_turn),
            mission_state=mission_state,
            resolution_state=resolution_state,
            repair_bundle=repair_bundle,
        )
    return out


def should_show_delegate_integration_repair_note(
    *,
    repair_bundle: Mapping[str, Any] | None,
    integration_by_ref: Mapping[str, str],
) -> bool:
    """True when repair bundle exists and at least one delegate ref is unreferenced."""
    if not isinstance(repair_bundle, Mapping):
        return False
    fragments = repair_bundle.get("fragments")
    if not isinstance(fragments, list) or not fragments:
        return False
    unreferenced = {
        STATUS_UNREFERENCED_RECENT,
        STATUS_UNREFERENCED_STALE,
    }
    return any(status in unreferenced for status in integration_by_ref.values())


def _normalized_context_refs(context_refs: Sequence[str] | None) -> list[str]:
    out: list[str] = []
    for raw in context_refs or ():
        text = str(raw or "").strip()
        if not text or text in out:
            continue
        out.append(text)
    return out


def _exact_ref_in_value(value: Any, ref_id: str) -> bool:
    if isinstance(value, str):
        return value == ref_id
    if isinstance(value, Mapping):
        return any(_exact_ref_in_value(inner, ref_id) for inner in value.values())
    if isinstance(value, (list, tuple)):
        return any(_exact_ref_in_value(inner, ref_id) for inner in value)
    return False
