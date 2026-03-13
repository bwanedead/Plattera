from __future__ import annotations

import hashlib
from typing import Any

from ...mission_runtime.observability import (
    MissionTransitionObservation,
    parse_mission_observation_payload,
)
from ...terminal_taxonomy import TerminalClass
from ..builder import build_canonical_trace
from ..schema import CanonicalTraceRecord, RawTraceEvent, TerminalSnapshot

_SOURCE_KIND_MISSION = "mission_runtime"


def build_mission_runtime_trace(
    *,
    mission_runtime_payload: dict[str, Any],
    payload_ref: str | None = None,
    trace_id: str | None = None,
) -> CanonicalTraceRecord:
    observation = parse_mission_observation_payload(mission_runtime_payload)
    mission_id = observation.mission_id
    request_id = observation.request_id
    objective = observation.objective
    active_mode = observation.active_mode
    mode_history = list(observation.mode_history)
    transitions = list(observation.transition_history)
    cycles = list(observation.cycles)
    mission_status = dict(observation.mission_status)
    resumability = dict(observation.resumability_summary)
    created_at = observation.created_at_epoch_seconds
    updated_at = observation.updated_at_epoch_seconds or created_at

    trace_identifier = trace_id or _default_trace_id(
        mission_id=mission_id,
        payload_ref=payload_ref,
        cycle_count=len(cycles),
        transition_count=len(transitions),
    )
    raw_events: list[RawTraceEvent] = []
    warnings: list[str] = []
    missing_components: list[str] = []

    raw_events.append(
        RawTraceEvent(
            timestamp_epoch_seconds=created_at,
            event_kind="request_start",
            phase="mission_start",
            iteration_index=0,
            actor="harness",
            status="started",
            reason_code=None,
            refs_delta={},
            payload={
                "mission_id": mission_id,
                "objective": objective,
                "active_mode": active_mode,
                "mode_history_count": len(mode_history),
            },
            source_origin={
                "kind": _SOURCE_KIND_MISSION,
                "ref": _source_ref(payload_ref, mission_id),
                "local_id": "mission_start",
                "sequence_index": 0,
            },
        )
    )

    for idx, cycle in enumerate(cycles):
        cycle_idx = cycle.cycle_index or (idx + 1)
        executed_mode = cycle.executed_mode
        resulting_active_mode = cycle.resulting_active_mode or active_mode
        summary = cycle.summary
        event_ts = cycle.timestamp_epoch_seconds or (created_at + idx + 1)
        raw_events.append(
            RawTraceEvent(
                timestamp_epoch_seconds=event_ts,
                event_kind="mode_segment",
                phase=f"mode:{executed_mode or 'unknown'}",
                iteration_index=max(cycle_idx - 1, 0),
                actor="harness",
                status="completed",
                reason_code=None,
                refs_delta={},
                payload={
                    "cycle_index": cycle_idx,
                    "executed_mode": executed_mode,
                    "resulting_active_mode": resulting_active_mode,
                    "summary": summary,
                },
                source_origin={
                    "kind": _SOURCE_KIND_MISSION,
                    "ref": _source_ref(payload_ref, mission_id),
                    "local_id": f"cycle:{cycle_idx}",
                    "sequence_index": idx + 1,
                },
            )
        )
        transition = cycle.transition
        if transition:
            raw_events.append(
                RawTraceEvent(
                    timestamp_epoch_seconds=transition.timestamp_epoch_seconds or event_ts,
                    event_kind="mission_transition",
                    phase="mission_transition",
                    iteration_index=max(cycle_idx - 1, 0),
                    actor="harness",
                    status="completed",
                    reason_code=transition.reason,
                    refs_delta=_refs_delta_from_transition(transition),
                    payload={
                        "prior_mode": transition.prior_mode,
                        "next_mode": transition.next_mode,
                        "reason": transition.reason,
                        "status": transition.status,
                        "order_anchor": transition.order_anchor,
                        "expected_next_work": transition.expected_next_work,
                        "resume_note_for_prior_mode": transition.resume_note_for_prior_mode,
                    },
                    source_origin={
                        "kind": _SOURCE_KIND_MISSION,
                        "ref": _source_ref(payload_ref, mission_id),
                        "local_id": f"transition:{transition.order_anchor or cycle_idx}",
                        "sequence_index": 1000 + idx,
                    },
                )
            )

    terminal_class = _as_terminal_class(mission_status.get("terminal_class"))
    reason_code = _as_str(mission_status.get("reason_code"))
    terminal_payload = {
        "mission_terminal": bool(mission_status.get("terminal")),
        "active_mode": active_mode,
        "reason_code": reason_code,
    }
    raw_events.append(
        RawTraceEvent(
            timestamp_epoch_seconds=updated_at,
            event_kind="terminal_outcome",
            phase="terminal",
            iteration_index=max(len(cycles) - 1, 0),
            actor="harness",
            status="completed",
            reason_code=reason_code,
            refs_delta={},
            payload={k: v for k, v in terminal_payload.items() if v not in (None, "")},
            source_origin={
                "kind": _SOURCE_KIND_MISSION,
                "ref": _source_ref(payload_ref, mission_id),
                "local_id": "terminal",
                "sequence_index": 10000,
            },
        )
    )

    if not cycles:
        missing_components.append("mission_cycles")
        warnings.append("mission_cycles_missing")
    if not transitions and len(mode_history) > 1:
        warnings.append("mission_mode_history_without_transitions")
    if not mode_history:
        missing_components.append("mission_mode_history")
        warnings.append("mission_mode_history_missing")

    return build_canonical_trace(
        trace_id=trace_identifier,
        run_id=mission_id,
        session_id=None,
        request_id=request_id,
        loop_family="mission_runtime",
        request_metadata={
            "objective": objective,
            "request_id": request_id,
        },
        start_context_summary={
            "payload_ref": payload_ref,
            "high_signal_artifact_ref_count": len(observation.high_signal_artifact_refs),
            "resume_reason": _as_str(resumability.get("resume_reason")),
        },
        started_at_epoch_seconds=created_at,
        events=raw_events,
        terminal=TerminalSnapshot(
            terminal_class=terminal_class or "in_progress",
            terminal_reason_code=reason_code,
            success=True if terminal_class == "completed" else False if terminal_class in {"failed", "blocked", "exhausted"} else None,
            terminal_metadata={},
        ),
        mission_id=mission_id,
        executed_mode=cycles[-1].executed_mode if cycles else None,
        active_mode=active_mode,
        mode_history=mode_history,
        transition_events=[_transition_event_dict(item) for item in transitions],
        resume_context_summary={
            "resumable": bool(resumability.get("resumable")),
            "resume_reason": _as_str(resumability.get("resume_reason")),
            "resume_requirements": [
                item
                for item in resumability.get("resume_requirements", [])
                if isinstance(item, str) and item.strip()
            ][:24]
            if isinstance(resumability.get("resume_requirements"), list)
            else [],
        },
        completeness_status="partial" if missing_components else "complete",
        missing_components=missing_components,
        normalization_warnings=warnings,
    )


def _transition_event_dict(item: MissionTransitionObservation) -> dict[str, Any]:
    return {
        "prior_mode": item.prior_mode,
        "next_mode": item.next_mode,
        "reason": item.reason,
        "status": item.status,
        "order_anchor": item.order_anchor,
        "timestamp_epoch_seconds": item.timestamp_epoch_seconds,
        "expected_next_work": item.expected_next_work,
        "resume_note_for_prior_mode": item.resume_note_for_prior_mode,
        "handed_forward_artifact_refs": list(item.handed_forward_artifact_refs)[:24],
    }


def _refs_delta_from_transition(transition: MissionTransitionObservation) -> dict[str, Any]:
    refs = list(transition.handed_forward_artifact_refs)
    return {f"handoff_ref_{idx}": ref for idx, ref in enumerate(refs)}


def _source_ref(payload_ref: str | None, mission_id: str) -> str:
    text = _as_str(payload_ref)
    return text if text else f"mission:{mission_id}"


def _default_trace_id(
    *,
    mission_id: str,
    payload_ref: str | None,
    cycle_count: int,
    transition_count: int,
) -> str:
    seed = "|".join([mission_id, payload_ref or "", str(cycle_count), str(transition_count)])
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    return f"trace:mission_runtime:{mission_id}:{digest}"


def _as_terminal_class(value: Any) -> TerminalClass | None:
    text = _as_str(value)
    if text in {"completed", "failed", "blocked", "waiting_human", "waiting_evidence", "exhausted", "in_progress"}:
        return text  # type: ignore[return-value]
    return None


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
