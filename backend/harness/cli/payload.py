from __future__ import annotations

from typing import Any

from ..runtime.orchestration.mission_contracts import MissionFlowCycleResult, MissionFlowRequest
from ..runtime.orchestration.mission_orchestrator import build_mission_observability_payload


def build_mission_cli_payload(
    *,
    mission_request: MissionFlowRequest,
    record: Any,
    cycle_results: list[MissionFlowCycleResult],
) -> dict[str, Any]:
    observability_payload = build_mission_observability_payload(
        request=mission_request,
        record=record,
        cycle_results=cycle_results,
    )
    return {
        "cli_surface": "mission_flow_cli",
        "canonical_surface": True,
        "mission_flow": observability_payload.get("mission_flow"),
    }
