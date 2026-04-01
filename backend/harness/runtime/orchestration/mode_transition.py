from __future__ import annotations

from typing import Callable

from .mission_contracts import MissionRecord, ModeTransition, ModeTransitionRecommendation


def evaluate_mode_transition(
    *,
    record: MissionRecord,
    recommendation: ModeTransitionRecommendation,
    mode_exists: Callable[[str], bool],
    now_epoch_seconds: float,
) -> ModeTransition:
    prior_mode = record.active_mode
    next_mode = recommendation.next_mode.strip()
    reason = recommendation.reason.strip()
    status = "applied"
    status_reason = None
    if not next_mode:
        status = "rejected"
        status_reason = "next_mode_required"
    elif next_mode == prior_mode:
        status = "rejected"
        status_reason = "next_mode_matches_active_mode"
    elif not reason:
        status = "rejected"
        status_reason = "transition_reason_required"
    elif not mode_exists(next_mode):
        status = "rejected"
        status_reason = "next_mode_adapter_not_registered"
    return ModeTransition(
        prior_mode=prior_mode,
        next_mode=next_mode,
        reason=reason or "unspecified",
        handed_forward_artifact_refs=list(recommendation.handed_forward_artifact_refs),
        resume_note_for_prior_mode=recommendation.resume_note_for_prior_mode,
        status=status,
        status_reason=status_reason,
        order_anchor=len(record.transition_history) + 1,
        timestamp_epoch_seconds=now_epoch_seconds,
    )
