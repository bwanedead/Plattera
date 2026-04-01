"""Run-summary helpers for projecting derived mission/resolution state."""

from __future__ import annotations

from typing import Any

from ...mission_state import (
    MissionState,
    ResolutionState,
    new_mission_state,
    new_resolution_state,
)
from .common import _as_str, _as_dict


def _mission_state_from_components(
    *,
    mission_id: str,
    session_id: str | None,
    request_id: str | None,
    loop_family: str,
    objective: str | None,
    active_mode: str | None,
    updated_at_epoch_seconds: float,
    latest_refs_summary: dict[str, Any] | None = None,
    high_signal_artifact_refs: list[str] | None = None,
    opaque_payload: dict[str, Any] | None = None,
    blocker_summary: dict[str, Any] | None = None,
    verification_summary: dict[str, Any] | None = None,
    waiting_summary: dict[str, Any] | None = None,
    terminal_summary: dict[str, Any] | None = None,
    continuity_summary: dict[str, Any] | None = None,
    mission_mode_summary: dict[str, Any] | None = None,
    prompt_observability_summary: dict[str, Any] | None = None,
    resolution_state: ResolutionState | dict[str, Any] | None = None,
) -> MissionState:
    return new_mission_state(
        mission_id=mission_id,
        session_id=session_id,
        request_id=request_id,
        loop_family=loop_family,
        objective=objective,
        active_mode=active_mode,
        updated_at_epoch_seconds=updated_at_epoch_seconds,
        latest_refs_summary=latest_refs_summary,
        high_signal_artifact_refs=high_signal_artifact_refs,
        opaque_payload=opaque_payload or {},
        blocker_summary=blocker_summary,
        verification_summary=verification_summary,
        waiting_summary=waiting_summary,
        terminal_summary=terminal_summary,
        continuity_summary=continuity_summary,
        mission_mode_summary=mission_mode_summary,
        prompt_observability_summary=prompt_observability_summary,
        resolution_state=resolution_state,
    )


def _opaque_payload_from_resolution_dict(payload: dict[str, Any]) -> dict[str, Any] | None:
    base = _as_dict(payload.get("opaque_payload"))
    return base if base else None


def _resolution_state_from_payload_dict(payload: dict[str, Any]) -> ResolutionState:
    return new_resolution_state(
        items=payload.get("items") if isinstance(payload.get("items"), list) else [],
        active_item_id=_as_str(payload.get("active_item_id")),
        relations=payload.get("relations") if isinstance(payload.get("relations"), list) else None,
        updated_at_epoch_seconds=float(payload.get("updated_at_epoch_seconds") or 0.0),
        opaque_payload=_opaque_payload_from_resolution_dict(payload),
    )


def _mission_flow_resolution_state_from_payload(payload: dict[str, Any]) -> ResolutionState:
    mission_state_payload = payload.get("mission_state")
    if isinstance(mission_state_payload, dict):
        nested_resolution = mission_state_payload.get("resolution_state")
        if isinstance(nested_resolution, dict):
            return _resolution_state_from_payload_dict(nested_resolution)
    resolution_payload = payload.get("resolution_state")
    if isinstance(resolution_payload, dict):
        return _resolution_state_from_payload_dict(resolution_payload)
    resolution_items = payload.get("resolution_items")
    if isinstance(resolution_items, list):
        return new_resolution_state(
            items=resolution_items,
            active_item_id=_as_str(payload.get("active_item_id")),
            updated_at_epoch_seconds=float(payload.get("updated_at_epoch_seconds") or 0.0),
        )
    return new_resolution_state(active_item_id=_as_str(payload.get("active_item_id")))
