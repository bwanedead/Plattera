"""Payload adaptation and builders for ``SharedRunSummaryEnvelope`` (inspection read model)."""

from __future__ import annotations

from typing import Any

from ..mission_state import (
    MissionState,
    ResolutionState,
    new_mission_state,
    new_resolution_state,
)
from ..run_summary_registry import register_run_summary_builder, require_run_summary_builder
from ..runtime.mission.observability import parse_mission_observation_payload
from ..terminal_taxonomy import TerminalClass
from .models import (
    RUN_SUMMARY_ENVELOPE_VERSION,
    BlockerSummary,
    ContinuitySummary,
    LatestRefsSummary,
    MissionModeSummary,
    NormalizedTerminalSummary,
    PromptObservabilitySummary,
    RequestSummary,
    SharedRunSummaryEnvelope,
    VerificationSummary,
    WaitingSummary,
)


def build_registered_run_summary(*, loop_family: str, payload: dict[str, Any]) -> SharedRunSummaryEnvelope:
    builder = require_run_summary_builder(loop_family)
    return builder(payload)


def build_orchestration_kernel_run_summary(*, orchestration_kernel_payload: dict[str, Any]) -> SharedRunSummaryEnvelope:
    payload = _orchestration_kernel_payload(orchestration_kernel_payload)
    trace_events = _as_dict_list(payload.get("trace_events"))
    run_artifact = _as_dict(payload.get("run_artifact")) or payload
    run_header = _run_header_from_trace_events(trace_events)
    latest_refs_summary = _latest_refs_summary_from_trace_events(trace_events=trace_events, run_artifact=run_artifact)
    terminal_summary = _terminal_summary_from_trace_events(trace_events=trace_events, run_artifact=run_artifact)
    blocker_summary = _blocker_summary_from_orchestration_payload(
        payload=payload,
        terminal_summary=terminal_summary,
    )
    verification_summary = _verification_summary_from_orchestration_payload(
        payload=payload,
        trace_events=trace_events,
    )
    waiting_summary = _waiting_summary_from_blocker_summary(
        blocker_summary=blocker_summary,
        terminal_summary=terminal_summary,
    )
    continuity_summary = ContinuitySummary(
        iteration=_iteration_count_from_trace_events(trace_events=trace_events, run_artifact=run_artifact),
        last_phase=_last_phase_from_trace_events(trace_events=trace_events),
        last_reason_code=terminal_summary.reason_code or _last_reason_code_from_trace_events(trace_events=trace_events),
        has_recent_activity=bool(trace_events),
    )
    active_mode = _first_non_empty(
        _as_str(run_artifact.get("active_mode")),
        _as_str(run_artifact.get("mode")),
        _as_str(run_header.get("active_mode")),
        _as_str(run_header.get("mode")),
    )
    mode_history = _as_str_list(run_artifact.get("mode_history")) or _as_str_list(run_header.get("mode_history"))
    prompt_observability_summary = _prompt_observability_summary_from_trace_events(trace_events)
    if prompt_observability_summary.prompt_event_count == 0:
        prompt_observability_summary = _prompt_observability_summary_from_payload(
            payload,
            default_surface=active_mode,
        )
    request_summary = RequestSummary(
        objective=_first_non_empty(
            _as_str(run_artifact.get("objective")),
            _as_str(run_artifact.get("mission_objective")),
            _as_str(run_header.get("objective")),
        ),
        mode=_first_non_empty(active_mode, _as_str(run_header.get("mode"))),
        trigger=_first_non_empty(_as_str(run_artifact.get("trigger")), _as_str(run_header.get("trigger"))),
    )
    mission_state = _mission_state_from_components(
        mission_id=_first_non_empty(
            _as_str(run_artifact.get("run_id")),
            _extract_run_id_from_session(_as_str(run_artifact.get("session_id"))),
            _extract_run_id_from_session(_as_str(payload.get("session_id"))),
            "unknown_run",
        )
        or "unknown_run",
        session_id=_first_non_empty(_as_str(run_artifact.get("session_id")), _as_str(payload.get("session_id"))),
        request_id=_first_non_empty(_as_str(run_artifact.get("request_id")), _as_str(run_header.get("request_id"))),
        loop_family="orchestration_kernel",
        objective=request_summary.objective,
        active_mode=active_mode,
        updated_at_epoch_seconds=float(
            _as_int(run_artifact.get("created_at_epoch_seconds"))
            or _as_int(run_artifact.get("updated_at_epoch_seconds"))
            or 0
        ),
        latest_refs_summary=latest_refs_summary.model_dump(),
        high_signal_artifact_refs=latest_refs_summary.ref_keys,
        opaque_payload=_opaque_payload_from_orchestration_payload(payload),
        blocker_summary=blocker_summary.model_dump(),
        verification_summary=verification_summary.model_dump(),
        waiting_summary=waiting_summary.model_dump(),
        terminal_summary=terminal_summary.model_dump(),
        continuity_summary=continuity_summary.model_dump(),
        mission_mode_summary={
            "active_mode": active_mode,
            "mode_history": mode_history,
            "latest_transition_reason": _as_str(run_artifact.get("latest_transition_reason")),
            "resume_context_summary": _resume_context_summary_from_payload(payload),
        },
        prompt_observability_summary=prompt_observability_summary.model_dump(),
        resolution_state=_orchestration_kernel_resolution_state_from_payload(payload),
    )
    return SharedRunSummaryEnvelope(
        run_id=mission_state.mission_id,
        session_id=_first_non_empty(_as_str(run_artifact.get("session_id")), _as_str(payload.get("session_id"))),
        request_id=_first_non_empty(_as_str(run_artifact.get("request_id")), _as_str(run_header.get("request_id"))),
        loop_family="orchestration_kernel",
        request_summary=request_summary,
        latest_refs_summary=latest_refs_summary,
        blocker_summary=blocker_summary,
        verification_summary=verification_summary,
        waiting_summary=waiting_summary,
        terminal_summary=terminal_summary,
        continuity_summary=continuity_summary,
        mission_state=mission_state,
        mission_mode_summary=MissionModeSummary(
            active_mode=active_mode,
            mode_history=mode_history,
            latest_transition_reason=_as_str(run_artifact.get("latest_transition_reason")),
            resume_context_summary=_resume_context_summary_from_payload(payload),
        ),
        prompt_observability_summary=prompt_observability_summary,
        envelope_version=RUN_SUMMARY_ENVELOPE_VERSION,
    )


def build_mission_flow_run_summary(*, mission_flow_payload: dict[str, Any]) -> SharedRunSummaryEnvelope:
    observation = parse_mission_observation_payload(mission_flow_payload)
    mission_id = observation.mission_id
    request_id = observation.request_id
    active_mode = observation.active_mode
    mode_history = list(observation.mode_history)
    transition_history = list(observation.transition_history)
    cycles = list(observation.cycles)
    mission_status = dict(observation.mission_status)
    resumability = dict(observation.resumability_summary)
    blocker_posture = dict(observation.blocker_posture_summary)
    verification_posture = dict(observation.verification_posture_summary)
    latest_transition = transition_history[-1] if transition_history else None
    transition_reason = latest_transition.reason if latest_transition else None
    terminal_class = _as_terminal_class(mission_status.get("terminal_class"))
    reason_code = _as_str(mission_status.get("reason_code"))
    high_signal_refs = list(observation.high_signal_artifact_refs)
    resolution_state = _mission_flow_resolution_state_from_payload(mission_flow_payload)

    return SharedRunSummaryEnvelope(
        run_id=mission_id,
        session_id=None,
        request_id=request_id,
        loop_family="mission_flow",
        request_summary=RequestSummary(
            objective=observation.objective,
            mode=active_mode,
            trigger=None,
        ),
        latest_refs_summary=LatestRefsSummary(
            has_refs=bool(high_signal_refs),
            total_count=len(high_signal_refs),
            ref_keys=high_signal_refs[:16],
        ),
        blocker_summary=BlockerSummary(
            open_count=_as_int(blocker_posture.get("open_blocker_count")),
            active_blocker_id=None,
            waiting_human=bool(blocker_posture.get("waiting_human")),
            answered_unintegrated_count=None,
            source="derived",
        ),
        verification_summary=VerificationSummary(
            status=_as_str(verification_posture.get("status")),
            last_verification_kind=_as_str(verification_posture.get("last_verification_kind")),
        ),
        waiting_summary=WaitingSummary(
            waiting=bool(blocker_posture.get("waiting_human")),
            waiting_kind="human_feedback" if bool(blocker_posture.get("waiting_human")) else None,
            resumable=bool(resumability.get("resumable")),
            owner_kind="mission_transition" if bool(blocker_posture.get("waiting_human")) else None,
        ),
        terminal_summary=NormalizedTerminalSummary(
            terminal=bool(mission_status.get("terminal")),
            terminal_class=terminal_class,
            reason_code=reason_code,
        ),
        continuity_summary=ContinuitySummary(
            iteration=observation.cycle_index or len(cycles),
            last_phase=f"mode:{cycles[-1].executed_mode}" if cycles and cycles[-1].executed_mode else None,
            last_reason_code=reason_code or transition_reason,
            has_recent_activity=bool(cycles or transition_history),
        ),
        mission_state=_mission_state_from_components(
            mission_id=mission_id,
            session_id=None,
            request_id=request_id,
            loop_family="mission_flow",
            objective=observation.objective,
            active_mode=active_mode,
            updated_at_epoch_seconds=float(observation.updated_at_epoch_seconds or 0.0),
            latest_refs_summary={
                "has_refs": bool(high_signal_refs),
                "total_count": len(high_signal_refs),
                "ref_keys": high_signal_refs[:16],
            },
            high_signal_artifact_refs=high_signal_refs,
            opaque_payload=dict(observation.opaque_adapter_payload),
            prompt_observability_summary=_prompt_observability_summary_from_payload(
                mission_flow_payload,
                default_surface=active_mode,
            ).model_dump(),
            blocker_summary={
                "open_count": _as_int(blocker_posture.get("open_blocker_count")),
                "active_blocker_id": None,
                "waiting_human": bool(blocker_posture.get("waiting_human")),
                "answered_unintegrated_count": None,
                "source": "derived",
            },
            verification_summary={
                "status": _as_str(verification_posture.get("status")),
                "last_verification_kind": _as_str(verification_posture.get("last_verification_kind")),
            },
            waiting_summary={
                "waiting": bool(blocker_posture.get("waiting_human")),
                "waiting_kind": "human_feedback" if bool(blocker_posture.get("waiting_human")) else None,
                "resumable": bool(resumability.get("resumable")),
                "owner_kind": "mission_transition" if bool(blocker_posture.get("waiting_human")) else None,
            },
            terminal_summary={
                "terminal": bool(mission_status.get("terminal")),
                "terminal_class": terminal_class,
                "reason_code": reason_code,
            },
            continuity_summary={
                "iteration": observation.cycle_index or len(cycles),
                "last_phase": f"mode:{cycles[-1].executed_mode}" if cycles and cycles[-1].executed_mode else None,
                "last_reason_code": reason_code or transition_reason,
                "has_recent_activity": bool(cycles or transition_history),
            },
            mission_mode_summary={
                "active_mode": active_mode,
                "mode_history": mode_history,
                "latest_transition_reason": transition_reason,
                "resume_context_summary": {
                    "resumable": bool(resumability.get("resumable")),
                    "resume_reason": _as_str(resumability.get("resume_reason")),
                    "resume_requirements": _as_str_list(resumability.get("resume_requirements")),
                    "latest_transition_target_mode": latest_transition.next_mode if latest_transition else None,
                    "resume_note_for_prior_mode": (
                        latest_transition.resume_note_for_prior_mode if latest_transition else None
                    ),
                },
            },
            resolution_state=resolution_state,
        ),
        mission_mode_summary=MissionModeSummary(
            active_mode=active_mode,
            mode_history=mode_history,
            latest_transition_reason=transition_reason,
            resume_context_summary={
                "resumable": bool(resumability.get("resumable")),
                "resume_reason": _as_str(resumability.get("resume_reason")),
                "resume_requirements": _as_str_list(resumability.get("resume_requirements")),
                "latest_transition_target_mode": latest_transition.next_mode if latest_transition else None,
                "resume_note_for_prior_mode": (
                    latest_transition.resume_note_for_prior_mode if latest_transition else None
                ),
            },
        ),
        prompt_observability_summary=_prompt_observability_summary_from_payload(mission_flow_payload, default_surface=active_mode),
        envelope_version=RUN_SUMMARY_ENVELOPE_VERSION,
    )


def _prompt_observability_summary_from_payload(
    payload: dict[str, Any],
    *,
    default_surface: str | None = None,
) -> PromptObservabilitySummary:
    summary = payload.get("prompt_observability_summary")
    if isinstance(summary, dict):
        return PromptObservabilitySummary(
            prompt_event_count=_as_int(summary.get("prompt_event_count")) or 0,
            last_prompt_event_id=_as_str(summary.get("last_prompt_event_id")),
            last_prompt_event_surface=_as_str(summary.get("last_prompt_event_surface")) or _as_str(default_surface),
        )
    return PromptObservabilitySummary(last_prompt_event_surface=_as_str(default_surface))


def _prompt_observability_summary_from_trace_events(events: list[dict[str, Any]]) -> PromptObservabilitySummary:
    prompt_events = [
        event
        for event in events
        if _as_str(event.get("phase")) == "prompt_event"
        or _event_kind(event) == "prompt_event"
        or (
            isinstance(event.get("payload"), dict)
            and isinstance(event["payload"].get("prompt_event"), dict)
        )
    ]
    last_payload = _as_dict(prompt_events[-1].get("payload")) if prompt_events else {}
    last_prompt_event = _as_dict(last_payload.get("prompt_event"))
    metadata = _as_dict(last_prompt_event.get("metadata"))
    return PromptObservabilitySummary(
        prompt_event_count=len(prompt_events),
        last_prompt_event_id=_as_str(metadata.get("prompt_event_id")),
        last_prompt_event_surface=_as_str(metadata.get("surface")) or _as_str(last_payload.get("surface")),
    )


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


def _resolution_state_from_payload_dict(payload: dict[str, Any]) -> ResolutionState:
    return new_resolution_state(
        items=payload.get("items") if isinstance(payload.get("items"), list) else [],
        active_item_id=_as_str(payload.get("active_item_id")),
        relations=payload.get("relations") if isinstance(payload.get("relations"), list) else None,
        updated_at_epoch_seconds=float(payload.get("updated_at_epoch_seconds") or 0.0),
        opaque_payload=_opaque_payload_from_resolution_dict(payload),
    )


def _summarize_refs(refs: dict[str, Any]) -> LatestRefsSummary:
    keys = sorted(str(key) for key in refs.keys() if str(key).strip())
    return LatestRefsSummary(has_refs=bool(keys), total_count=len(keys), ref_keys=keys[:16])


def _orchestration_kernel_payload(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("orchestration_kernel")
    if isinstance(nested, dict):
        return nested
    return payload


def _opaque_payload_from_resolution_dict(payload: dict[str, Any]) -> dict[str, Any] | None:
    base = _as_dict(payload.get("opaque_payload"))
    return base if base else None


def _opaque_payload_from_orchestration_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(payload.get("opaque_payload"))


def _run_header_from_trace_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in events:
        if _event_kind(event) in {"run_header", "request_start"}:
            payload = _as_dict(event.get("payload"))
            return payload or _as_dict(event)
    return {}


def _latest_refs_summary_from_trace_events(
    *,
    trace_events: list[dict[str, Any]],
    run_artifact: dict[str, Any],
) -> LatestRefsSummary:
    refs: dict[str, Any] = {}
    for event in reversed(trace_events):
        payload = _as_dict(event.get("payload"))
        refs = _as_dict(payload.get("latest_refs"))
        if refs:
            break
        refs = _as_dict(event.get("refs_delta"))
        if refs:
            break
    if not refs:
        refs = _as_dict(run_artifact.get("latest_refs"))
    return _summarize_refs(refs)


def _terminal_summary_from_trace_events(
    *,
    trace_events: list[dict[str, Any]],
    run_artifact: dict[str, Any],
) -> NormalizedTerminalSummary:
    terminal_payload: dict[str, Any] = {}
    for event in reversed(trace_events):
        if _event_kind(event) != "terminal_outcome":
            continue
        terminal_payload = _as_dict(event.get("payload"))
        if terminal_payload:
            break
    if not terminal_payload:
        terminal_payload = _as_dict(run_artifact.get("terminal"))
    terminal_class = _as_terminal_class(terminal_payload.get("terminal_class"))
    if terminal_class is None:
        terminal_class = _terminal_class_from_payload(terminal_payload)
    return NormalizedTerminalSummary(
        terminal=bool(terminal_payload),
        terminal_class=terminal_class,
        reason_code=_first_non_empty(_as_str(terminal_payload.get("reason_code")), _as_str(terminal_payload.get("stop_reason"))),
    )


def _terminal_class_from_payload(payload: dict[str, Any]) -> TerminalClass | None:
    terminal_outcome = _as_str(payload.get("terminal_outcome"))
    if terminal_outcome in {"SUCCESS", "completed"}:
        return "completed"
    if terminal_outcome in {"FAILED", "failed"}:
        return "failed"
    stop_reason = _as_str(payload.get("stop_reason"))
    if stop_reason == "needs_user_choice":
        return "waiting_human"
    if stop_reason == "needs_upload":
        return "waiting_evidence"
    if stop_reason in {"needs_capability", "worker_unavailable", "validation_failed", "blocked"}:
        return "blocked"
    if stop_reason in {"budget_exceeded", "no_progress"}:
        return "exhausted"
    if stop_reason in {"internal_error", "error", "cancelled"}:
        return "failed"
    return None


def _blocker_summary_from_orchestration_payload(
    *,
    payload: dict[str, Any],
    terminal_summary: NormalizedTerminalSummary,
) -> BlockerSummary:
    blocker_payload = _as_dict(payload.get("blocker_summary"))
    waiting_human = bool(_as_bool(blocker_payload.get("waiting_human")))
    waiting_human = waiting_human or terminal_summary.terminal_class in {"waiting_human", "waiting_evidence"}
    open_count = _as_int(blocker_payload.get("open_count"))
    if open_count is None:
        open_count = 1 if waiting_human else 0
    return BlockerSummary(
        open_count=open_count,
        active_blocker_id=_as_str(blocker_payload.get("active_blocker_id")),
        waiting_human=waiting_human,
        answered_unintegrated_count=_as_int(blocker_payload.get("answered_unintegrated_count")),
        source=_first_non_empty(_as_str(blocker_payload.get("source")), "derived") or "derived",
    )


def _verification_summary_from_orchestration_payload(
    *,
    payload: dict[str, Any],
    trace_events: list[dict[str, Any]],
) -> VerificationSummary:
    verification_payload = _as_dict(payload.get("verification_summary"))
    status = _as_str(verification_payload.get("status"))
    last_verification_kind = _as_str(verification_payload.get("last_verification_kind"))
    if last_verification_kind is None:
        last_verification_kind = _last_verification_kind_from_trace_events(trace_events)
    return VerificationSummary(
        status=status,
        last_verification_kind=last_verification_kind,
    )


def _waiting_summary_from_blocker_summary(
    *,
    blocker_summary: BlockerSummary,
    terminal_summary: NormalizedTerminalSummary,
) -> WaitingSummary:
    waiting_kind = "human_feedback" if blocker_summary.waiting_human else None
    if terminal_summary.terminal_class == "waiting_evidence":
        waiting_kind = "evidence"
    return WaitingSummary(
        waiting=blocker_summary.waiting_human or terminal_summary.terminal_class in {"waiting_human", "waiting_evidence"},
        waiting_kind=waiting_kind,
        resumable=bool(blocker_summary.waiting_human or terminal_summary.terminal_class in {"waiting_human", "waiting_evidence"}),
        owner_kind="mission_transition" if blocker_summary.waiting_human else None,
    )


def _iteration_count_from_trace_events(
    *,
    trace_events: list[dict[str, Any]],
    run_artifact: dict[str, Any],
) -> int | None:
    max_iteration = max((_as_int(_as_dict(event.get("payload")).get("iteration")) or 0 for event in trace_events), default=0)
    if max_iteration > 0:
        return max_iteration
    steps = run_artifact.get("steps")
    if isinstance(steps, list):
        return len(steps)
    return None


def _last_verification_kind_from_trace_events(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        payload = _as_dict(event.get("payload"))
        action_type = _as_str(payload.get("action_type")) or ""
        if action_type in {"validate", "declare_done"}:
            return action_type
    return None


def _last_phase_from_trace_events(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        phase = _as_str(event.get("phase"))
        if phase:
            return phase
        event_kind = _event_kind(event)
        if event_kind:
            return event_kind
    return None


def _last_reason_code_from_trace_events(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        reason_code = _as_str(event.get("reason_code"))
        if reason_code:
            return reason_code
        payload = _as_dict(event.get("payload"))
        reason_code = _as_str(payload.get("reason_code"))
        if reason_code:
            return reason_code
    return None


def _resume_context_summary_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    resume_context = _as_dict(payload.get("resume_context_summary"))
    if resume_context:
        return resume_context
    resumability = _as_dict(payload.get("resumability_summary"))
    if resumability:
        return {
            "resumable": bool(resumability.get("resumable")),
            "resume_reason": _as_str(resumability.get("resume_reason")),
            "resume_requirements": _as_str_list(resumability.get("resume_requirements")),
        }
    return {}


def _orchestration_kernel_resolution_state_from_payload(payload: dict[str, Any]) -> ResolutionState:
    resolution_payload = _as_dict(payload.get("resolution_state"))
    if resolution_payload:
        return _resolution_state_from_payload_dict(resolution_payload)
    return _mission_flow_resolution_state_from_payload(payload)


def _extract_run_id_from_session(session_id: str | None) -> str | None:
    value = (session_id or "").strip()
    if not value or "::" not in value:
        return None
    return value.rsplit("::", maxsplit=1)[-1] or None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _event_kind(event: dict[str, Any]) -> str | None:
    return _first_non_empty(_as_str(event.get("event_kind")), _as_str(event.get("event_type")))


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _as_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _as_str(item)
        if not text or text in out:
            continue
        out.append(text)
    return out


def _as_terminal_class(value: Any) -> TerminalClass | None:
    text = _as_str(value)
    if text in {"completed", "blocked", "waiting_human", "waiting_evidence", "exhausted", "failed"}:
        return text  # type: ignore[return-value]
    return None


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        text = _as_str(value)
        if text:
            return text
    return None


def _build_mission_flow_run_summary_from_payload(payload: dict[str, Any]) -> SharedRunSummaryEnvelope:
    mission_flow_payload: dict[str, Any] | None = None
    nested = payload.get("mission_flow")
    if isinstance(nested, dict):
        mission_flow_payload = nested
    if mission_flow_payload is None:
        mission_flow_payload = payload if isinstance(payload, dict) else {}
    if not isinstance(mission_flow_payload, dict):
        raise ValueError("invalid mission_flow payload for run-state build")
    return build_mission_flow_run_summary(mission_flow_payload=mission_flow_payload)


def _build_orchestration_kernel_run_summary_from_payload(payload: dict[str, Any]) -> SharedRunSummaryEnvelope:
    orchestration_kernel_payload = payload.get("orchestration_kernel")
    if not isinstance(orchestration_kernel_payload, dict):
        orchestration_kernel_payload = payload if isinstance(payload, dict) else {}
    if not isinstance(orchestration_kernel_payload, dict):
        raise ValueError("invalid orchestration_kernel payload for run-state build")
    return build_orchestration_kernel_run_summary(orchestration_kernel_payload=orchestration_kernel_payload)


register_run_summary_builder(
    loop_family="orchestration_kernel",
    builder=_build_orchestration_kernel_run_summary_from_payload,
)
register_run_summary_builder(
    loop_family="mission_flow",
    builder=_build_mission_flow_run_summary_from_payload,
)
