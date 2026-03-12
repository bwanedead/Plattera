from __future__ import annotations

from agents.transcript_edit.controller import _should_convert_timeout_to_waiting_feedback
from agents.transcript_edit.loop_state import TranscriptEditLoopState
from agents.transcript_edit.state_projection import (
    derive_waiting_feedback_projection,
    sync_pending_feedback_cache_from_registry,
)
from agents.transcript_edit.terminalization import build_run_result, terminal_summary


def test_waiting_projection_registry_first_over_compat_fields() -> None:
    projection = derive_waiting_feedback_projection(
        blocker_registry={
            "active_blocker_id": "blocker:range",
            "rows": [
                {
                    "blocker_id": "blocker:range",
                    "decision_key": "range",
                    "state": "waiting_feedback",
                    "linked_prompt_id": "hitl_range_registry",
                }
            ],
        },
        fallback_prompt_id="hitl_range_compat",
        fallback_decision_key="closure_or_pob",
    )
    assert projection["pending_feedback_prompt_id"] == "hitl_range_registry"
    assert projection["pending_feedback_decision_key"] == "range"
    assert projection["waiting_feedback"] is True
    assert projection["source"] == "blocker_registry"


def test_sync_pending_feedback_cache_clears_non_authoritative_pending_fields() -> None:
    state = TranscriptEditLoopState(
        blocker_registry={
            "rows": [
                {
                    "blocker_id": "blocker:range",
                    "decision_key": "range",
                    "state": "answered_unintegrated",
                    "linked_prompt_id": "hitl_range_1_wait",
                }
            ]
        },
        pending_feedback_prompt_id="hitl_range_1_wait",
        pending_feedback_decision_key="range",
        pending_feedback_prompt={"decision_key": "range"},
    )
    sync_pending_feedback_cache_from_registry(state=state)
    assert state.pending_feedback_prompt_id is None
    assert state.pending_feedback_decision_key is None
    assert state.pending_feedback_prompt is None


def test_timeout_waiting_conversion_uses_registry_authority() -> None:
    state = TranscriptEditLoopState(
        blocker_registry={
            "rows": [
                {
                    "blocker_id": "blocker:range",
                    "decision_key": "range",
                    "state": "answered_unintegrated",
                    "linked_prompt_id": "hitl_range_1_wait",
                }
            ]
        },
        pending_feedback_prompt_id="hitl_range_1_wait",
        pending_feedback_decision_key="range",
    )
    assert (
        _should_convert_timeout_to_waiting_feedback(
            reason="budget_wall_time_exceeded",
            state=state,
        )
        is False
    )


def test_sync_pending_feedback_cache_clears_prompt_context_on_owner_change() -> None:
    state = TranscriptEditLoopState(
        blocker_registry={
            "active_blocker_id": "blocker:range",
            "rows": [
                {
                    "blocker_id": "blocker:range",
                    "decision_key": "range",
                    "state": "waiting_feedback",
                    "linked_prompt_id": "hitl_range_registry",
                }
            ],
        },
        pending_feedback_prompt_id="hitl_range_compat",
        pending_feedback_decision_key="range",
        pending_feedback_prompt={"decision_key": "range", "line1": "compat prompt"},
    )
    sync_pending_feedback_cache_from_registry(state=state)
    assert state.pending_feedback_prompt_id == "hitl_range_registry"
    assert state.pending_feedback_decision_key == "range"
    assert state.pending_feedback_prompt is None


def test_terminal_summary_does_not_treat_compat_pending_field_as_authority() -> None:
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s1",
        iterations=2,
        status="needs_review",
        reason_code="tx_agent_closure_requirements_unresolved",
        latest_refs={},
        review_required=True,
        runtime_hitl_state={
            "pending_feedback_prompt_id": "hitl_range_compat",
            "pending_feedback_decision_key": "range",
            "blocker_registry": {
                "rows": [
                    {
                        "blocker_id": "blocker:range",
                        "decision_key": "range",
                        "state": "answered_unintegrated",
                        "linked_prompt_id": "hitl_range_registry",
                    }
                ],
                "counts": {"answered_unintegrated": 1, "waiting_feedback": 0},
            },
        },
    )
    summary = terminal_summary(
        progress_log=[],
        result=result,
        runtime_hitl_state=result.runtime_hitl_state,
    )
    assert summary["pending_feedback_prompt_ids"] == []
    assert summary["human_feedback_pending"] is False
