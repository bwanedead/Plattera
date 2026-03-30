from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...mission_state import MissionState, ResolutionState, new_mission_state, new_resolution_state


def _default_mission_state() -> MissionState:
    return new_mission_state(
        mission_id="unknown_mission",
        # Canonical loop_family for orchestration-kernel runs (wire + trace vocabulary).
        loop_family="orchestration_kernel",
        resolution_state=new_resolution_state(),
    )


@dataclass
class OrchestrationContinuity:
    """Hydrated mission understanding and refs carried iteration-to-iteration.

    Values are updated from each ``SharedStateProjection`` sync and step
    execution; this is continuity carriage for the orchestrator, not the
    authoritative mission-state store.
    """

    latest_refs: dict[str, Any] = field(default_factory=dict)
    mission_state: MissionState = field(default_factory=_default_mission_state)
    resolution_state: ResolutionState = field(default_factory=new_resolution_state)
    active_item_id: str | None = None
