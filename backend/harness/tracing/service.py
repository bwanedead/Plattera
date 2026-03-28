from __future__ import annotations

from typing import Any

from .adapters.controller_kernel import build_controller_kernel_trace
from .adapters.kernel_direct import build_kernel_direct_trace
from .adapters.mission_runtime import build_mission_runtime_trace
from .registry import (
    TraceFamilyLookupError,
    iter_trace_families,
    register_trace_family,
    require_trace_family,
)
from .schema import CanonicalTraceRecord, LoopFamily

_CONTROLLER_DISPATCH_KEYS = {"controller_transcript", "run_artifact"}
_MISSION_RUNTIME_KEYS = {"mission_id", "active_mode", "mode_history", "cycles"}


def build_controller_kernel_canonical_trace(
    *,
    controller_transcript: dict[str, Any],
    run_artifact: dict[str, Any],
    transcript_ref: str | None = None,
    run_artifact_ref: str | None = None,
    trace_id: str | None = None,
) -> CanonicalTraceRecord:
    return build_controller_kernel_trace(
        controller_transcript=controller_transcript,
        run_artifact=run_artifact,
        transcript_ref=transcript_ref,
        run_artifact_ref=run_artifact_ref,
        trace_id=trace_id,
    )


def build_kernel_direct_canonical_trace(
    *,
    trace_events: list[dict[str, Any]],
    run_artifact: dict[str, Any],
    run_artifact_ref: str | None = None,
    trace_id: str | None = None,
) -> CanonicalTraceRecord:
    """Build a CanonicalTraceRecord from live kernel trace events (no transcript required).

    Phase 11 D3 — orchestration-kernel path canonical trace builder.
    """
    return build_kernel_direct_trace(
        trace_events=trace_events,
        run_artifact=run_artifact,
        run_artifact_ref=run_artifact_ref,
        trace_id=trace_id,
    )


def build_mission_runtime_canonical_trace(
    *,
    mission_runtime_payload: dict[str, Any],
    payload_ref: str | None = None,
    trace_id: str | None = None,
) -> CanonicalTraceRecord:
    return build_mission_runtime_trace(
        mission_runtime_payload=mission_runtime_payload,
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
    if family == "controller_kernel":
        controller_transcript = _dict_field(payload, key="controller_transcript")
        run_artifact = _dict_field(payload, key="run_artifact")
        return build_controller_kernel_canonical_trace(
            controller_transcript=controller_transcript,
            run_artifact=run_artifact,
            transcript_ref=_optional_str(payload.get("controller_transcript_ref")),
            run_artifact_ref=_optional_str(payload.get("run_artifact_ref")),
            trace_id=trace_id,
        )

    if family not in {"controller_kernel", "mission_runtime"}:
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
    if family == "mission_runtime":
        mission_payload = _mission_runtime_payload(payload)
        return build_mission_runtime_canonical_trace(
            mission_runtime_payload=mission_payload,
            payload_ref=_optional_str(payload.get("mission_runtime_ref")) or _optional_str(payload.get("snapshot_ref")),
            trace_id=trace_id,
        )

    raise ValueError(f"unsupported loop_family: {family}")


def _detect_loop_family(payload: dict[str, Any]) -> LoopFamily:
    looks_controller = _CONTROLLER_DISPATCH_KEYS.issubset(payload.keys())
    looks_mission_runtime = _looks_like_mission_runtime_payload(payload)
    registered_hits = [
        registration.loop_family
        for registration in iter_trace_families()
        if registration.loop_family not in {"controller_kernel", "mission_runtime"} and registration.detector(payload)
    ]

    shape_hits = int(looks_controller) + int(looks_mission_runtime) + len(registered_hits)
    if shape_hits > 1:
        raise ValueError(
            "ambiguous canonical trace payload: matches multiple canonical payload shapes;"
            " pass loop_family explicitly"
        )
    if looks_controller:
        return "controller_kernel"
    if looks_mission_runtime:
        return "mission_runtime"
    if len(registered_hits) == 1:
        return registered_hits[0]  # type: ignore[return-value]
    raise ValueError(
        "unsupported canonical trace payload shape: expected controller payload with"
        " {'controller_transcript','run_artifact'}, a registered domain trace payload,"
        " or mission-runtime payload under 'mission_runtime'"
    )


def _looks_like_mission_runtime_payload(payload: dict[str, Any]) -> bool:
    mission_payload = _mission_runtime_payload(payload, default_none=True)
    if not isinstance(mission_payload, dict):
        return False
    return _MISSION_RUNTIME_KEYS.issubset(mission_payload.keys())


def _mission_runtime_payload(payload: dict[str, Any], default_none: bool = False) -> dict[str, Any]:
    nested = payload.get("mission_runtime")
    if isinstance(nested, dict):
        return nested
    if _MISSION_RUNTIME_KEYS.issubset(payload.keys()):
        return payload
    if default_none:
        return {}
    raise ValueError(
        "invalid mission_runtime payload: expected 'mission_runtime' object with"
        " {'mission_id','active_mode','mode_history','cycles'}"
    )


def _dict_field(payload: dict[str, Any], *, key: str) -> dict[str, Any]:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    raise ValueError(f"missing required object field '{key}' for controller_kernel canonical trace build")


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


register_trace_family(
    loop_family="controller_kernel",
    builder=lambda **kwargs: build_controller_kernel_canonical_trace(
        controller_transcript=kwargs["payload"]["controller_transcript"],
        run_artifact=kwargs["payload"]["run_artifact"],
        transcript_ref=_optional_str(kwargs["payload"].get("controller_transcript_ref")),
        run_artifact_ref=_optional_str(kwargs["payload"].get("run_artifact_ref")),
        trace_id=kwargs.get("trace_id"),
    ),
    detector=lambda payload: _CONTROLLER_DISPATCH_KEYS.issubset(payload.keys()),
)
register_trace_family(
    loop_family="mission_runtime",
    builder=lambda **kwargs: build_mission_runtime_canonical_trace(
        mission_runtime_payload=_mission_runtime_payload(kwargs["payload"]),
        payload_ref=_optional_str(kwargs["payload"].get("mission_runtime_ref"))
        or _optional_str(kwargs["payload"].get("snapshot_ref")),
        trace_id=kwargs.get("trace_id"),
    ),
    detector=_looks_like_mission_runtime_payload,
)
