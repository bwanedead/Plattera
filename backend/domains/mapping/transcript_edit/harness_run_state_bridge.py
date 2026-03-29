from __future__ import annotations

from typing import Any

from harness.run_state_registry import register_run_state_builder

from .terminal_taxonomy import classify_transcript_edit_terminal


def build_transcript_edit_run_state(*, run_snapshot: dict[str, Any]):
    (
        RUN_STATE_VERSION,
        SharedRunStateEnvelope,
        RequestSummary,
        BlockerSummary,
        VerificationSummary,
        WaitingSummary,
        NormalizedTerminalSummary,
        ContinuitySummary,
        MissionModeSummary,
        _as_dict,
        _as_dict_list,
        _as_str,
        _as_int,
        _as_bool,
        _prompt_observability_summary_from_snapshot,
        _mission_state_from_components,
        _summarize_refs,
        _last_phase,
        new_resolution_state,
        _resolution_state_from_payload_dict,
    ) = _run_state_deps()

    run_entry, snapshot = _resolve_run_payload(run_snapshot)
    run_id = _first_non_empty(snapshot.get("run_id"), run_entry.get("run_id"), "unknown_tx_run") or "unknown_tx_run"
    session_id = _as_str(snapshot.get("session_id"))
    request_id = _first_non_empty(run_id, session_id)
    status = _as_str(snapshot.get("status")) or _as_str(run_entry.get("status"))
    reason_code = _as_str(snapshot.get("reason_code"))
    request = _as_dict(run_entry.get("request"))
    terminal = _as_dict(snapshot.get("terminal_summary"))
    runtime_hitl_state = _as_dict(snapshot.get("runtime_hitl_state"))
    runtime_summary = _transcript_edit_runtime_summary(
        runtime_hitl_state=runtime_hitl_state,
        _as_dict=_as_dict,
        _as_str=_as_str,
        _as_int=_as_int,
        _as_bool=_as_bool,
    )
    progress_log = _as_dict_list(snapshot.get("progress_log"))
    critical_events = _as_dict_list(snapshot.get("critical_events"))

    human_feedback_pending = bool(runtime_summary.get("waiting_feedback"))
    terminal_result = classify_transcript_edit_terminal(
        status=status,
        reason_code=reason_code,
        terminal_classification=_as_str(terminal.get("terminal_classification")),
        human_feedback_pending=human_feedback_pending,
    )

    latest_refs = _as_dict(snapshot.get("latest_refs"))
    open_count = _as_int(runtime_summary.get("open_blocker_count"))
    answered_unintegrated_count = _as_int(runtime_summary.get("answered_unintegrated_count"))

    unresolved_count = _as_int(runtime_summary.get("unresolved_closure_count"))
    if unresolved_count is None:
        unresolved_count = _ledger_unresolved_count(
            terminal_summary=terminal,
            progress_log=progress_log,
            critical_events=critical_events,
            _as_dict=_as_dict,
        )
    verification_status = (
        _as_str(terminal.get("closure_state"))
        or _as_str(runtime_summary.get("verification_status"))
        or _as_str(terminal.get("terminal_classification"))
    )
    if unresolved_count is not None:
        if unresolved_count <= 0:
            verification_status = verification_status or "closure_resolved"
        else:
            verification_status = verification_status or "closure_unresolved"

    resolution_state = _build_transcript_edit_resolution_state(
        runtime_hitl_state=runtime_hitl_state,
        updated_at_epoch_seconds=float(snapshot.get("updated_at_epoch_seconds") or 0.0),
        new_resolution_state=new_resolution_state,
        _resolution_state_from_payload_dict=_resolution_state_from_payload_dict,
    )

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
            active_blocker_id=_as_str(runtime_summary.get("active_blocker_id")),
            waiting_human=bool(runtime_summary.get("waiting_feedback")),
            answered_unintegrated_count=answered_unintegrated_count,
            source="derived",
        ),
        verification_summary=VerificationSummary(
            status=verification_status,
            last_verification_kind=(
                _as_str(runtime_summary.get("verification_kind"))
                or _tx_last_verification_kind(progress_log=progress_log, critical_events=critical_events, _as_str=_as_str)
            ),
            mapping_ready=_as_bool(terminal.get("mapping_ready")),
        ),
        waiting_summary=WaitingSummary(
            waiting=bool(runtime_summary.get("waiting_feedback")),
            waiting_kind="human_feedback" if bool(runtime_summary.get("waiting_feedback")) else None,
            resumable=bool(runtime_summary.get("waiting_feedback")),
            owner_kind=(
                "mission_runtime_summary"
                if bool(runtime_summary.get("waiting_feedback")) and bool(runtime_summary.get("summary_present"))
                else None
            ),
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
        mission_state=_mission_state_from_components(
            mission_id=run_id,
            session_id=session_id,
            request_id=request_id,
            loop_family="transcript_edit",
            objective="transcript_edit_agent",
            active_mode=_as_str(request.get("mode")),
            updated_at_epoch_seconds=float(snapshot.get("updated_at_epoch_seconds") or 0.0),
            latest_refs_summary=_summarize_refs(latest_refs).model_dump(),
            prompt_observability_summary=_prompt_observability_summary_from_snapshot(snapshot).model_dump(),
            blocker_summary={
                "open_count": open_count,
                "active_blocker_id": _as_str(runtime_summary.get("active_blocker_id")),
                "waiting_human": bool(runtime_summary.get("waiting_feedback")),
                "answered_unintegrated_count": answered_unintegrated_count,
                "source": "derived",
            },
            verification_summary={
                "status": verification_status,
                "last_verification_kind": (
                    _as_str(runtime_summary.get("verification_kind"))
                    or _tx_last_verification_kind(progress_log=progress_log, critical_events=critical_events, _as_str=_as_str)
                ),
                "mapping_ready": _as_bool(terminal.get("mapping_ready")),
            },
            waiting_summary={
                "waiting": bool(runtime_summary.get("waiting_feedback")),
                "waiting_kind": "human_feedback" if bool(runtime_summary.get("waiting_feedback")) else None,
                "resumable": bool(runtime_summary.get("waiting_feedback")),
                "owner_kind": (
                    "mission_runtime_summary"
                    if bool(runtime_summary.get("waiting_feedback")) and bool(runtime_summary.get("summary_present"))
                    else None
                ),
            },
            terminal_summary={
                "terminal": bool(status in {"completed", "failed", "needs_review", "waiting_feedback"}),
                "terminal_class": terminal_result.terminal_class,
                "reason_code": terminal_result.reason_code,
            },
            continuity_summary={
                "iteration": _as_int(snapshot.get("iterations")),
                "last_phase": _last_phase(progress_log=progress_log, critical_events=critical_events),
                "last_reason_code": reason_code,
                "has_recent_activity": bool(progress_log or critical_events),
            },
            resolution_state=resolution_state,
        ),
        mission_mode_summary=MissionModeSummary(active_mode=_as_str(request.get("mode"))),
        prompt_observability_summary=_prompt_observability_summary_from_snapshot(snapshot),
        envelope_version=RUN_STATE_VERSION,
    )


def register_transcript_edit_run_state_builder() -> None:
    register_run_state_builder(
        loop_family="transcript_edit",
        builder=lambda payload: build_transcript_edit_run_state(run_snapshot=payload),
    )


def _build_transcript_edit_resolution_state(
    *,
    runtime_hitl_state: dict[str, Any],
    updated_at_epoch_seconds: float,
    new_resolution_state,
    _resolution_state_from_payload_dict,
):
    runtime_resolution_state = runtime_hitl_state.get("resolution_state")
    if isinstance(runtime_resolution_state, dict):
        return _resolution_state_from_payload_dict(runtime_resolution_state)
    return new_resolution_state(
        updated_at_epoch_seconds=updated_at_epoch_seconds,
        domain_payload={
            "source": "native_resolution_missing",
            "native_resolution_source_present": False,
        },
    )


def _transcript_edit_runtime_summary(
    *,
    runtime_hitl_state: dict[str, Any],
    _as_dict,
    _as_str,
    _as_int,
    _as_bool,
) -> dict[str, Any]:
    summary = _as_dict(runtime_hitl_state.get("mission_runtime_summary"))
    return {
        "summary_present": bool(summary),
        "waiting_feedback": bool(summary.get("waiting_feedback")),
        "active_blocker_id": _as_str(summary.get("active_blocker_id")),
        "open_blocker_count": _as_int(summary.get("open_blocker_count")),
        "answered_unintegrated_count": _as_int(summary.get("answered_unintegrated_count")),
        "unresolved_closure_count": _as_int(summary.get("unresolved_closure_count")),
        "closure_blocking": _as_bool(summary.get("closure_blocking")),
        "verification_status": _as_str(summary.get("verification_status")),
        "verification_kind": _as_str(summary.get("verification_kind")),
    }


def _ledger_unresolved_count(
    *,
    terminal_summary: dict[str, Any],
    progress_log: list[dict[str, Any]],
    critical_events: list[dict[str, Any]],
    _as_dict,
) -> int | None:
    terminal_ledger = _as_dict(terminal_summary.get("decision_ledger"))
    count = _ledger_unresolved_count_from_ledger(terminal_ledger, _as_dict=_as_dict)
    if count is not None:
        return count
    for event in reversed(progress_log):
        count = _ledger_unresolved_count_from_ledger(_ledger_from_event(event, _as_dict=_as_dict), _as_dict=_as_dict)
        if count is not None:
            return count
    for event in reversed(critical_events):
        count = _ledger_unresolved_count_from_ledger(_ledger_from_event(event, _as_dict=_as_dict), _as_dict=_as_dict)
        if count is not None:
            return count
    return None


def _ledger_unresolved_count_from_ledger(ledger: dict[str, Any], *, _as_dict) -> int | None:
    summary = _as_dict(ledger.get("summary"))
    value = summary.get("unresolved_count")
    return int(value) if isinstance(value, int) else None


def _ledger_from_event(event: dict[str, Any], *, _as_dict) -> dict[str, Any]:
    detail = _as_dict(event.get("detail"))
    return _as_dict(detail.get("decision_ledger"))


def _tx_last_verification_kind(*, progress_log: list[dict[str, Any]], critical_events: list[dict[str, Any]], _as_str) -> str | None:
    for event in reversed(progress_log + critical_events):
        phase = _as_str(event.get("phase")) or ""
        if "verify" in phase:
            return phase
    return None


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _resolve_run_payload(run_snapshot: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(run_snapshot.get("snapshot"), dict):
        return run_snapshot, run_snapshot["snapshot"]
    return {}, run_snapshot


def _run_state_deps():
    from harness.run_state import (
        RUN_STATE_VERSION,
        SharedRunStateEnvelope,
        RequestSummary,
        BlockerSummary,
        VerificationSummary,
        WaitingSummary,
        NormalizedTerminalSummary,
        ContinuitySummary,
        MissionModeSummary,
        _as_dict,
        _as_dict_list,
        _as_str,
        _as_int,
        _as_bool,
        _prompt_observability_summary_from_snapshot,
        _mission_state_from_components,
        _summarize_refs,
        _last_phase,
        new_resolution_state,
        _resolution_state_from_payload_dict,
    )

    return (
        RUN_STATE_VERSION,
        SharedRunStateEnvelope,
        RequestSummary,
        BlockerSummary,
        VerificationSummary,
        WaitingSummary,
        NormalizedTerminalSummary,
        ContinuitySummary,
        MissionModeSummary,
        _as_dict,
        _as_dict_list,
        _as_str,
        _as_int,
        _as_bool,
        _prompt_observability_summary_from_snapshot,
        _mission_state_from_components,
        _summarize_refs,
        _last_phase,
        new_resolution_state,
        _resolution_state_from_payload_dict,
    )


register_transcript_edit_run_state_builder()
