from __future__ import annotations

from typing import Any

from .adapters.kernel_direct import build_kernel_direct_trace
from .adapters.payload import build_mission_flow_trace
from .registry import (
    TraceFamilyLookupError,
    iter_trace_families,
    register_trace_family,
    require_trace_family,
)
from .schema import CanonicalTraceRecord, LoopFamily

_MISSION_FLOW_SHAPE_KEYS = {"mission_id", "active_mode", "mode_history", "cycles"}
_ORCHESTRATION_KERNEL_KEYS = {"trace_events", "run_artifact"}


def build_kernel_direct_canonical_trace(
    *,
    trace_events: list[dict[str, Any]],
    run_artifact: dict[str, Any],
    run_artifact_ref: str | None = None,
    trace_id: str | None = None,
) -> CanonicalTraceRecord:
    """Build a CanonicalTraceRecord from live kernel trace events (no transcript required)."""
    return build_kernel_direct_trace(
        trace_events=trace_events,
        run_artifact=run_artifact,
        run_artifact_ref=run_artifact_ref,
        trace_id=trace_id,
    )


def build_mission_flow_canonical_trace(
    *,
    mission_flow_payload: dict[str, Any],
    payload_ref: str | None = None,
    trace_id: str | None = None,
) -> CanonicalTraceRecord:
    return build_mission_flow_trace(
        mission_flow_payload=mission_flow_payload,
        payload_ref=payload_ref,
        trace_id=trace_id,
    )


def build_canonical_trace_from_payload(
    *,
    payload: dict[str, Any],
    loop_family: LoopFamily | None = None,
    trace_id: str | None = None,
) -> CanonicalTraceRecord:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object dictionary")

    family = loop_family or _detect_loop_family(payload)
    if family not in {"mission_flow", "orchestration_kernel"}:
        try:
            registration = require_trace_family(family)
        except TraceFamilyLookupError as exc:
            raise ValueError(f"unsupported loop_family: {family}") from exc
        if registration.validator is not None:
            registration.validator(payload)
        return registration.builder(
            payload=payload,
            snapshot_ref=_optional_str(payload.get("snapshot_ref")),
            trace_id=trace_id,
        )

    if family == "orchestration_kernel":
        kernel_payload = _orchestration_kernel_payload(payload)
        return build_kernel_direct_canonical_trace(
            trace_events=_as_trace_event_list(kernel_payload.get("trace_events")),
            run_artifact=_orchestration_run_artifact(kernel_payload),
            run_artifact_ref=_optional_str(kernel_payload.get("run_artifact_ref"))
            or _optional_str(kernel_payload.get("snapshot_ref")),
            trace_id=trace_id,
        )

    mission_payload = _mission_flow_payload(payload)
    return build_mission_flow_canonical_trace(
        mission_flow_payload=mission_payload,
        payload_ref=_optional_str(payload.get("mission_flow_ref"))
        or _optional_str(payload.get("snapshot_ref")),
        trace_id=trace_id,
    )


def _detect_loop_family(payload: dict[str, Any]) -> LoopFamily:
    looks_mission_flow = _looks_like_mission_flow_payload(payload)
    looks_orchestration_kernel = _looks_like_orchestration_kernel_payload(payload)
    registered_hits = [
        registration.loop_family
        for registration in iter_trace_families()
        if registration.loop_family not in {"mission_flow", "orchestration_kernel"} and registration.detector(payload)
    ]

    shape_hits = int(looks_mission_flow) + int(looks_orchestration_kernel) + len(registered_hits)
    if shape_hits > 1:
        raise ValueError(
            "ambiguous canonical trace payload: matches multiple canonical payload shapes;"
            " pass loop_family explicitly"
        )
    if looks_mission_flow:
        return "mission_flow"
    if looks_orchestration_kernel:
        return "orchestration_kernel"
    if len(registered_hits) == 1:
        return registered_hits[0]  # type: ignore[return-value]
    raise ValueError(
        "unsupported canonical trace payload shape: expected a registered payload,"
        " orchestration-kernel payload under 'trace_events'/'run_artifact', or"
        " mission-flow payload under 'mission_flow'"
    )


def _looks_like_mission_flow_payload(payload: dict[str, Any]) -> bool:
    mission_payload = _mission_flow_payload(payload, default_none=True)
    if not isinstance(mission_payload, dict):
        return False
    return _MISSION_FLOW_SHAPE_KEYS.issubset(mission_payload.keys())


def _mission_flow_payload(payload: dict[str, Any], default_none: bool = False) -> dict[str, Any]:
    nested = payload.get("mission_flow")
    if isinstance(nested, dict):
        return nested
    if _MISSION_FLOW_SHAPE_KEYS.issubset(payload.keys()):
        return payload
    if default_none:
        return {}
    raise ValueError(
        "invalid mission_flow payload: expected 'mission_flow' object"
        " with {'mission_id','active_mode','mode_history','cycles'}"
    )


def _looks_like_orchestration_kernel_payload(payload: dict[str, Any]) -> bool:
    kernel_payload = _orchestration_kernel_payload(payload, default_none=True)
    if not isinstance(kernel_payload, dict):
        return False
    has_trace_events = isinstance(kernel_payload.get("trace_events"), list)
    has_run_artifact = isinstance(kernel_payload.get("run_artifact"), dict)
    return has_trace_events and has_run_artifact


def _orchestration_kernel_payload(payload: dict[str, Any], default_none: bool = False) -> dict[str, Any]:
    nested = payload.get("orchestration_kernel")
    if isinstance(nested, dict):
        return nested
    if _ORCHESTRATION_KERNEL_KEYS.issubset(payload.keys()):
        return payload
    if default_none:
        return {}
    raise ValueError(
        "invalid orchestration_kernel payload: expected 'orchestration_kernel' object with"
        " {'trace_events','run_artifact'}"
    )


def _orchestration_run_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    run_artifact = payload.get("run_artifact")
    return run_artifact if isinstance(run_artifact, dict) else {}


def _as_trace_event_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _optional_str(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    return None
