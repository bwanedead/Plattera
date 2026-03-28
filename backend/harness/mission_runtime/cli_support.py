from __future__ import annotations

from typing import Any

from .contracts import MissionRuntimeCycleResult, MissionRuntimeRequest
from .runtime import build_mission_observability_payload

def build_mission_cli_payload(
    *,
    mission_request: MissionRuntimeRequest,
    ledger: Any,
    cycle_results: list[MissionRuntimeCycleResult],
) -> dict[str, Any]:
    observability_payload = build_mission_observability_payload(
        request=mission_request,
        ledger=ledger,
        cycle_results=cycle_results,
    )
    return {
        "cli_surface": "mission_runtime_cli",
        "canonical_surface": True,
        "mission_runtime": observability_payload.get("mission_runtime"),
    }


def persist_mission_trace_index(
    *,
    mission_request: MissionRuntimeRequest,
    ledger: Any,
    cycle_results: list[MissionRuntimeCycleResult],
) -> str | None:
    from .observability import build_mission_observation_from_runtime, build_mission_trace_index
    import json as _json
    try:
        observation = build_mission_observation_from_runtime(
            request=mission_request,
            ledger=ledger,
            cycle_results=cycle_results,
        )
        has_transitions = any(t.status == "applied" for t in observation.transition_history)
        if not has_transitions:
            return None
        trace_index = build_mission_trace_index(observation=observation)
        try:
            from config.paths import dossiers_artifacts_root
        except ModuleNotFoundError:
            from backend.config.paths import dossiers_artifacts_root  # type: ignore[no-redef]
        mission_id = str(getattr(mission_request, "mission_id", None) or "unknown").strip()
        dest = dossiers_artifacts_root() / "mission_traces" / f"mission_trace_{mission_id}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_json.dumps(trace_index, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(dest)
    except Exception:
        return None
