"""Orchestration-kernel payload adaptation for ``SharedRunSummaryEnvelope``."""

from __future__ import annotations

from typing import Any

from ...mission_state import ResolutionState
from ...terminal_taxonomy import TerminalClass
from .common import (
    _as_bool,
    _as_dict,
    _as_dict_list,
    _as_int,
    _as_str,
    _as_str_list,
    _as_terminal_class,
    _event_kind,
    _first_non_empty,
)
from .state_projection import (
    _mission_flow_resolution_state_from_payload,
    _mission_state_from_components,
    _resolution_state_from_payload_dict,
)
from .models import (
    RUN_SUMMARY_ENVELOPE_VERSION,
    BlockerSummary,
    ContinuitySummary,
    LatestRefsSummary,
    MissionModeSummary,
    NormalizedTerminalSummary,
    RequestSummary,
    SharedRunSummaryEnvelope,
    VerificationSummary,
    WaitingSummary,
)
from .prompt_observability import (
    _prompt_observability_summary_from_payload,
    _prompt_observability_summary_from_trace_events,
)


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
    payload_prompt_observability_summary = _prompt_observability_summary_from_payload(
        payload,
        default_surface=active_mode,
    )
    trace_prompt_observability_summary = _prompt_observability_summary_from_trace_events(trace_events)
    prompt_observability_summary = payload_prompt_observability_summary
    if trace_prompt_observability_summary.prompt_event_count > 0:
        prompt_observability_summary = payload_prompt_observability_summary.model_copy(
            update={
                "prompt_event_count": trace_prompt_observability_summary.prompt_event_count,
                "last_prompt_event_id": trace_prompt_observability_summary.last_prompt_event_id,
                "last_prompt_event_surface": trace_prompt_observability_summary.last_prompt_event_surface,
            }
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
            _run_id_from_trace_events(trace_events),
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


def _orchestration_kernel_payload(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("orchestration_kernel")
    if isinstance(nested, dict):
        return nested
    return payload


def _opaque_payload_from_orchestration_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(payload.get("opaque_payload"))


def _orchestration_kernel_resolution_state_from_payload(payload: dict[str, Any]) -> ResolutionState:
    resolution_payload = _as_dict(payload.get("resolution_state"))
    if resolution_payload:
        return _resolution_state_from_payload_dict(resolution_payload)
    return _mission_flow_resolution_state_from_payload(payload)


def _run_id_from_trace_events(events: list[dict[str, Any]]) -> str | None:
    """Extract run_id from the canonical request_start trace event payload."""
    for event in events:
        if _event_kind(event) in {"run_header", "request_start"}:
            payload = _as_dict(event.get("payload"))
            run_id = _as_str((payload or {}).get("run_id"))
            if run_id:
                return run_id
    return None


def _extract_run_id_from_session(session_id: str | None) -> str | None:
    value = (session_id or "").strip()
    if not value or "::" not in value:
        return None
    return value.rsplit("::", maxsplit=1)[-1] or None


def _summarize_refs(refs: dict[str, Any]) -> LatestRefsSummary:
    keys = sorted(str(key) for key in refs.keys() if str(key).strip())
    return LatestRefsSummary(has_refs=bool(keys), total_count=len(keys), ref_keys=keys[:16])


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


def _last_phase_from_trace_events(*, trace_events: list[dict[str, Any]]) -> str | None:
    for event in reversed(trace_events):
        phase = _as_str(event.get("phase"))
        if phase:
            return phase
        event_kind = _event_kind(event)
        if event_kind:
            return event_kind
    return None


def _last_reason_code_from_trace_events(*, trace_events: list[dict[str, Any]]) -> str | None:
    for event in reversed(trace_events):
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
