from __future__ import annotations

from typing import Any

from .adapters.controller_kernel import build_controller_kernel_trace
from .adapters.mission_runtime import build_mission_runtime_trace
from .adapters.transcript_edit import build_transcript_edit_trace
from .schema import CanonicalTraceRecord, LoopFamily

_CONTROLLER_DISPATCH_KEYS = {"controller_transcript", "run_artifact"}
_TRANSCRIPT_EDIT_SIGNAL_KEYS = {"snapshot", "progress_log", "critical_events", "terminal_summary"}
_TRANSCRIPT_EDIT_REQUIRED_ANY = {"run_id", "status", "progress_log", "critical_events", "terminal_summary"}
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


def build_transcript_edit_canonical_trace(
    *,
    run_snapshot: dict[str, Any],
    snapshot_ref: str | None = None,
    trace_id: str | None = None,
) -> CanonicalTraceRecord:
    return build_transcript_edit_trace(
        run_snapshot=run_snapshot,
        snapshot_ref=snapshot_ref,
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

    if family == "transcript_edit":
        _validate_transcript_edit_payload(payload)
        return build_transcript_edit_canonical_trace(
            run_snapshot=payload,
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
    looks_transcript_edit = _looks_like_transcript_edit_payload(payload)
    looks_mission_runtime = _looks_like_mission_runtime_payload(payload)

    shape_hits = int(looks_controller) + int(looks_transcript_edit) + int(looks_mission_runtime)
    if shape_hits > 1:
        raise ValueError(
            "ambiguous canonical trace payload: matches multiple canonical payload shapes;"
            " pass loop_family explicitly"
        )
    if looks_controller:
        return "controller_kernel"
    if looks_transcript_edit:
        return "transcript_edit"
    if looks_mission_runtime:
        return "mission_runtime"
    raise ValueError(
        "unsupported canonical trace payload shape: expected controller payload with"
        " {'controller_transcript','run_artifact'}, a transcript-edit run snapshot payload,"
        " or mission-runtime payload under 'mission_runtime'"
    )


def _looks_like_transcript_edit_payload(payload: dict[str, Any]) -> bool:
    if isinstance(payload.get("snapshot"), dict):
        snapshot = payload["snapshot"]
        return bool(_TRANSCRIPT_EDIT_REQUIRED_ANY.intersection(snapshot.keys()))
    return "run_id" in payload and bool(_TRANSCRIPT_EDIT_SIGNAL_KEYS.intersection(payload.keys()))


def _validate_transcript_edit_payload(payload: dict[str, Any]) -> None:
    if isinstance(payload.get("snapshot"), dict):
        snapshot = payload["snapshot"]
        if not _TRANSCRIPT_EDIT_REQUIRED_ANY.intersection(snapshot.keys()):
            raise ValueError(
                "invalid transcript_edit payload: 'snapshot' object is missing required transcript-edit signals"
            )
        return
    if "run_id" not in payload or not _TRANSCRIPT_EDIT_SIGNAL_KEYS.intersection(payload.keys()):
        raise ValueError(
            "invalid transcript_edit payload: expected run snapshot with 'run_id' and one of"
            " {'snapshot','progress_log','critical_events','terminal_summary'}"
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
