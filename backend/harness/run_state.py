from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agents.transcript_edit.state_projection import derive_waiting_feedback_projection

from .mission_runtime.observability import parse_mission_observation_payload
from .terminal_taxonomy import (
    TerminalClass,
    classify_controller_terminal,
    classify_transcript_edit_terminal,
)

RUN_STATE_VERSION = "run_state.v1"
LoopFamily = Literal["controller_kernel", "transcript_edit", "mission_runtime"]


class RequestSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str | None = Field(default=None, max_length=240)
    mode: str | None = Field(default=None, max_length=64)
    trigger: str | None = Field(default=None, max_length=64)
    dossier_id: str | None = Field(default=None, max_length=128)


class LatestRefsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    has_refs: bool
    total_count: int = Field(ge=0)
    ref_keys: list[str] = Field(default_factory=list, max_length=16)


class BlockerSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    open_count: int | None = Field(default=None, ge=0)
    active_blocker_id: str | None = Field(default=None, max_length=128)
    waiting_human: bool
    answered_unintegrated_count: int | None = Field(default=None, ge=0)
    source: Literal["registry", "derived", "sparse"]


class VerificationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = Field(default=None, max_length=64)
    last_verification_kind: str | None = Field(default=None, max_length=64)
    mapping_ready: bool | None = None


class WaitingSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    waiting: bool
    waiting_kind: str | None = Field(default=None, max_length=64)
    resumable: bool
    owner_kind: str | None = Field(default=None, max_length=64)


class NormalizedTerminalSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terminal: bool
    terminal_class: TerminalClass | None = None
    reason_code: str | None = Field(default=None, max_length=256)


class ContinuitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iteration: int | None = Field(default=None, ge=0)
    last_phase: str | None = Field(default=None, max_length=128)
    last_reason_code: str | None = Field(default=None, max_length=256)
    has_recent_activity: bool


class MissionModeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_mode: str | None = Field(default=None, max_length=64)
    mode_history: list[str] = Field(default_factory=list, max_length=32)
    latest_transition_reason: str | None = Field(default=None, max_length=256)
    resume_context_summary: dict[str, Any] = Field(default_factory=dict)


class SharedRunStateEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=128)
    session_id: str | None = Field(default=None, max_length=256)
    request_id: str | None = Field(default=None, max_length=256)
    loop_family: LoopFamily
    request_summary: RequestSummary
    latest_refs_summary: LatestRefsSummary
    blocker_summary: BlockerSummary
    verification_summary: VerificationSummary
    waiting_summary: WaitingSummary
    terminal_summary: NormalizedTerminalSummary
    continuity_summary: ContinuitySummary
    mission_mode_summary: MissionModeSummary = Field(default_factory=MissionModeSummary)
    envelope_version: str = Field(min_length=1, max_length=64)


def build_transcript_edit_run_state(*, run_snapshot: dict[str, Any]) -> SharedRunStateEnvelope:
    run_entry, snapshot = _resolve_run_payload(run_snapshot)
    run_id = _first_non_empty(snapshot.get("run_id"), run_entry.get("run_id"), "unknown_tx_run") or "unknown_tx_run"
    session_id = _as_str(snapshot.get("session_id"))
    request_id = _first_non_empty(run_id, session_id)
    status = _as_str(snapshot.get("status")) or _as_str(run_entry.get("status"))
    reason_code = _as_str(snapshot.get("reason_code"))
    request = _as_dict(run_entry.get("request"))
    terminal = _as_dict(snapshot.get("terminal_summary"))
    runtime_hitl_state = _as_dict(snapshot.get("runtime_hitl_state"))
    blocker_registry = _as_dict(runtime_hitl_state.get("blocker_registry"))
    blocker_rows = _as_dict_list(blocker_registry.get("rows"))
    blocker_counts = _as_dict(blocker_registry.get("counts"))
    progress_log = _as_dict_list(snapshot.get("progress_log"))
    critical_events = _as_dict_list(snapshot.get("critical_events"))

    waiting_projection = derive_waiting_feedback_projection(
        blocker_registry=blocker_registry,
        fallback_prompt_id=_as_str(runtime_hitl_state.get("pending_feedback_prompt_id")),
        fallback_decision_key=_as_str(runtime_hitl_state.get("pending_feedback_decision_key")),
    )
    waiting_from_compat_fallback = (
        _as_str(waiting_projection.get("source")) == "compat_fallback"
        and bool(waiting_projection.get("waiting_feedback"))
    )
    human_feedback_pending = bool(terminal.get("human_feedback_pending")) or bool(waiting_projection.get("waiting_feedback"))
    terminal_result = classify_transcript_edit_terminal(
        status=status,
        reason_code=reason_code,
        terminal_classification=_as_str(terminal.get("terminal_classification")),
        human_feedback_pending=human_feedback_pending,
    )

    latest_refs = _as_dict(snapshot.get("latest_refs"))
    open_count = _registry_open_count(blocker_rows)
    answered_unintegrated_count = int(
        blocker_counts.get("answered_unintegrated")
        if isinstance(blocker_counts.get("answered_unintegrated"), int)
        else sum(1 for row in blocker_rows if _as_str(row.get("state")) == "answered_unintegrated")
    )

    unresolved_count = _ledger_unresolved_count(
        terminal_summary=terminal,
        progress_log=progress_log,
        critical_events=critical_events,
    )
    verification_status = _as_str(terminal.get("closure_state")) or _as_str(terminal.get("terminal_classification"))
    if unresolved_count is not None:
        if unresolved_count <= 0:
            verification_status = verification_status or "closure_resolved"
        else:
            verification_status = verification_status or "closure_unresolved"

    return SharedRunStateEnvelope(
        run_id=run_id,
        session_id=session_id,
        request_id=request_id,
        loop_family="transcript_edit",
        request_summary=RequestSummary(
            objective="transcript_edit_agent",
            mode=_as_str(request.get("mode")),
            trigger=_as_str(request.get("trigger")),
            dossier_id=_as_str(request.get("dossier_id")),
        ),
        latest_refs_summary=_summarize_refs(latest_refs),
        blocker_summary=BlockerSummary(
            open_count=open_count,
            active_blocker_id=_as_str(blocker_registry.get("active_blocker_id")),
            waiting_human=bool(waiting_projection.get("waiting_feedback")),
            answered_unintegrated_count=answered_unintegrated_count,
            source="derived" if waiting_from_compat_fallback else "registry",
        ),
        verification_summary=VerificationSummary(
            status=verification_status,
            last_verification_kind=_tx_last_verification_kind(progress_log=progress_log, critical_events=critical_events),
            mapping_ready=_as_bool(terminal.get("mapping_ready")),
        ),
        waiting_summary=WaitingSummary(
            waiting=bool(waiting_projection.get("waiting_feedback")),
            waiting_kind="human_feedback" if bool(waiting_projection.get("waiting_feedback")) else None,
            resumable=bool(waiting_projection.get("resumable")),
            owner_kind="blocker_registry" if bool(waiting_projection.get("waiting_feedback_owner")) else None,
        ),
        terminal_summary=NormalizedTerminalSummary(
            terminal=bool(status in {"completed", "failed", "needs_review", "waiting_feedback"}),
            terminal_class=terminal_result.terminal_class,
            reason_code=terminal_result.reason_code,
        ),
        continuity_summary=ContinuitySummary(
            iteration=_as_int(snapshot.get("iterations")),
            last_phase=_last_phase(progress_log=progress_log, critical_events=critical_events),
            last_reason_code=reason_code,
            has_recent_activity=bool(progress_log or critical_events),
        ),
        mission_mode_summary=MissionModeSummary(active_mode=_as_str(request.get("mode"))),
        envelope_version=RUN_STATE_VERSION,
    )


def build_controller_kernel_run_state(
    *,
    controller_transcript: dict[str, Any],
    run_artifact: dict[str, Any],
) -> SharedRunStateEnvelope:
    transcript_events = _as_dict_list(controller_transcript.get("events"))
    run_header = _controller_run_header(transcript_events)
    run_header_payload = _as_dict(run_header.get("payload"))
    latest_refs = _controller_latest_refs(transcript_events)
    terminal = _controller_terminal_from_transcript(transcript_events)

    run_id = _first_non_empty(
        run_artifact.get("run_id"),
        _extract_run_id_from_session(_as_str(run_artifact.get("session_id"))),
        _extract_run_id_from_session(_as_str(run_header_payload.get("session_id"))),
        "unknown_controller_run",
    ) or "unknown_controller_run"
    session_id = _first_non_empty(run_artifact.get("session_id"), run_header_payload.get("session_id"))
    request_id = _first_non_empty(run_artifact.get("request_id"), run_header_payload.get("request_id"), run_id)
    stop_reason = _as_str(terminal.get("stop_reason"))
    terminal_outcome = _as_str(terminal.get("terminal_outcome"))
    terminal_result = classify_controller_terminal(
        stop_reason=stop_reason,
        terminal_outcome=terminal_outcome,
        success=terminal.get("success"),
        reason_code=_as_str(terminal.get("reason_code")),
    )

    waiting = terminal_result.terminal_class in {"waiting_human", "waiting_evidence"}
    waiting_kind = (
        "human_feedback"
        if terminal_result.terminal_class == "waiting_human"
        else "evidence"
        if terminal_result.terminal_class == "waiting_evidence"
        else None
    )

    return SharedRunStateEnvelope(
        run_id=run_id,
        session_id=session_id,
        request_id=request_id,
        loop_family="controller_kernel",
        request_summary=RequestSummary(
            objective="controller_runtime_loop",
            mode=_as_str(run_header_payload.get("mode")),
            trigger=None,
            dossier_id=_as_str(run_header_payload.get("dossier_id")),
        ),
        latest_refs_summary=_summarize_refs(latest_refs),
        blocker_summary=BlockerSummary(
            open_count=None,
            active_blocker_id=None,
            waiting_human=terminal_result.terminal_class == "waiting_human",
            answered_unintegrated_count=None,
            source="sparse",
        ),
        verification_summary=VerificationSummary(
            status=stop_reason or _as_str(terminal.get("reason_code")),
            last_verification_kind=_controller_last_verification_kind(transcript_events),
            mapping_ready=True if terminal_result.terminal_class == "completed" else False if terminal_result.terminal_class in {"failed", "blocked"} else None,
        ),
        waiting_summary=WaitingSummary(
            waiting=waiting,
            waiting_kind=waiting_kind,
            resumable=waiting,
            owner_kind="terminal_refusal" if waiting else None,
        ),
        terminal_summary=NormalizedTerminalSummary(
            terminal=bool(terminal),
            terminal_class=terminal_result.terminal_class if terminal else None,
            reason_code=terminal_result.reason_code if terminal else None,
        ),
        continuity_summary=ContinuitySummary(
            iteration=_controller_iteration_count(transcript_events, run_artifact),
            last_phase=_controller_last_phase(transcript_events),
            last_reason_code=_as_str(terminal.get("reason_code")),
            has_recent_activity=bool(transcript_events),
        ),
        mission_mode_summary=MissionModeSummary(active_mode=_as_str(run_header_payload.get("mode"))),
        envelope_version=RUN_STATE_VERSION,
    )


def build_mission_runtime_run_state(*, mission_runtime_payload: dict[str, Any]) -> SharedRunStateEnvelope:
    observation = parse_mission_observation_payload(mission_runtime_payload)
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

    return SharedRunStateEnvelope(
        run_id=mission_id,
        session_id=None,
        request_id=request_id,
        loop_family="mission_runtime",
        request_summary=RequestSummary(
            objective=observation.objective,
            mode=active_mode,
            trigger=None,
            dossier_id=None,
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
            mapping_ready=True
            if terminal_class == "completed"
            else False
            if terminal_class in {"failed", "blocked", "exhausted"}
            else None,
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
        mission_mode_summary=MissionModeSummary(
            active_mode=active_mode,
            mode_history=mode_history,
            latest_transition_reason=transition_reason,
            resume_context_summary={
                    "resumable": bool(resumability.get("resumable")),
                    "resume_reason": _as_str(resumability.get("resume_reason")),
                    "resume_requirements": _as_str_list(resumability.get("resume_requirements")),
                    "expected_next_work": latest_transition.expected_next_work if latest_transition else None,
                    "resume_note_for_prior_mode": (
                        latest_transition.resume_note_for_prior_mode if latest_transition else None
                    ),
                },
            ),
        envelope_version=RUN_STATE_VERSION,
    )


def _resolve_run_payload(run_snapshot: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(run_snapshot.get("snapshot"), dict):
        return run_snapshot, _as_dict(run_snapshot.get("snapshot"))
    return {}, run_snapshot


def _summarize_refs(refs: dict[str, Any]) -> LatestRefsSummary:
    keys = sorted(str(key) for key in refs.keys() if str(key).strip())
    return LatestRefsSummary(has_refs=bool(keys), total_count=len(keys), ref_keys=keys[:16])


def _registry_open_count(rows: list[dict[str, Any]]) -> int:
    closed = {"resolved", "integrated", "superseded", "stale"}
    return sum(1 for row in rows if _as_str(row.get("state")) not in closed)


def _ledger_unresolved_count(
    *,
    terminal_summary: dict[str, Any],
    progress_log: list[dict[str, Any]],
    critical_events: list[dict[str, Any]],
) -> int | None:
    terminal_ledger = _as_dict(terminal_summary.get("decision_ledger"))
    count = _ledger_unresolved_count_from_ledger(terminal_ledger)
    if count is not None:
        return count
    for event in reversed(progress_log):
        count = _ledger_unresolved_count_from_ledger(_ledger_from_event(event))
        if count is not None:
            return count
    for event in reversed(critical_events):
        count = _ledger_unresolved_count_from_ledger(_ledger_from_event(event))
        if count is not None:
            return count
    return None


def _ledger_unresolved_count_from_ledger(ledger: dict[str, Any]) -> int | None:
    summary = _as_dict(ledger.get("summary"))
    value = summary.get("unresolved_count")
    return int(value) if isinstance(value, int) else None


def _ledger_from_event(event: dict[str, Any]) -> dict[str, Any]:
    detail = _as_dict(event.get("detail"))
    return _as_dict(detail.get("decision_ledger"))


def _tx_last_verification_kind(*, progress_log: list[dict[str, Any]], critical_events: list[dict[str, Any]]) -> str | None:
    for event in reversed(progress_log + critical_events):
        phase = _as_str(event.get("phase")) or ""
        if "verify" in phase:
            return phase
    return None


def _last_phase(*, progress_log: list[dict[str, Any]], critical_events: list[dict[str, Any]]) -> str | None:
    merged = progress_log + critical_events
    for event in reversed(merged):
        phase = _as_str(event.get("phase"))
        if phase:
            return phase
    return None


def _controller_run_header(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in events:
        if _as_str(event.get("event_type")) == "run_header":
            return event
    return {}


def _controller_latest_refs(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        payload = _as_dict(event.get("payload"))
        refs = _as_dict(payload.get("latest_refs"))
        if refs:
            return refs
    return {}


def _controller_terminal_from_transcript(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        payload = _as_dict(event.get("payload"))
        terminal = _as_dict(payload.get("terminal"))
        if terminal:
            return terminal
    return {}


def _controller_iteration_count(events: list[dict[str, Any]], run_artifact: dict[str, Any]) -> int | None:
    max_iteration = max((_as_int(_as_dict(event.get("payload")).get("iteration")) or 0 for event in events), default=0)
    if max_iteration > 0:
        return max_iteration
    steps = run_artifact.get("steps")
    if isinstance(steps, list):
        return len(steps)
    return None


def _controller_last_verification_kind(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        payload = _as_dict(event.get("payload"))
        action_type = _as_str(payload.get("action_type")) or ""
        if action_type in {"validate", "declare_done"}:
            return action_type
    return None


def _controller_last_phase(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        event_type = _as_str(event.get("event_type"))
        if event_type:
            return event_type
    return None


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
