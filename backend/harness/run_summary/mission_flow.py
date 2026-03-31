"""Mission-flow payload adaptation for ``SharedRunSummaryEnvelope``."""

from __future__ import annotations

from typing import Any

from ..runtime.mission.observability import parse_mission_observation_payload
from .common import _as_int, _as_str, _as_str_list, _as_terminal_class
from .mission_state import (
    _mission_flow_resolution_state_from_payload,
    _mission_state_from_components,
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
from .prompt_observability import _prompt_observability_summary_from_payload


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
