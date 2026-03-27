from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.review.reporting import build_review_aggregate, build_run_review_summary
from harness.run_state import (
    build_controller_kernel_run_state,
    build_mission_runtime_run_state,
    build_transcript_edit_run_state,
)
from harness.tracing.adapters.controller_kernel import build_controller_kernel_trace
from harness.tracing.adapters.mission_runtime import build_mission_runtime_trace
from harness.tracing.adapters.transcript_edit import build_transcript_edit_trace


def _controller_inputs() -> tuple[dict, dict]:
    transcript = {
        "events": [
            {
                "event_type": "run_header",
                "detail": "controller_run_started",
                "timestamp_epoch_seconds": 10,
                "payload": {
                    "request_id": "request-review-1",
                    "session_id": "request-review-1::run-review-1",
                    "dossier_id": "d-1",
                },
            },
            {
                "event_type": "agent_proposed_step",
                "detail": "retrieve_evidence",
                "timestamp_epoch_seconds": 11,
                "payload": {"iteration": 1, "action_type": "retrieve_evidence"},
            },
            {
                "event_type": "kernel_step_result",
                "detail": "executed",
                "timestamp_epoch_seconds": 12,
                "payload": {"iteration": 1, "action_type": "retrieve_evidence"},
            },
            {
                "event_type": "kernel_step_result",
                "detail": "executed",
                "timestamp_epoch_seconds": 13,
                "payload": {
                    "iteration": 2,
                    "action_type": "declare_done",
                    "terminal": {
                        "terminal_outcome": "SUCCESS",
                        "stop_reason": "completed",
                        "success": True,
                        "reason_code": "done_verified",
                    },
                },
            },
        ]
    }
    run_artifact = {
        "run_id": "run-review-1",
        "request_id": "request-review-1",
        "session_id": "request-review-1::run-review-1",
        "created_at_epoch_seconds": 10,
        "steps": [],
    }
    return transcript, run_artifact


def _tx_run_snapshot() -> dict:
    return {
        "run_id": "tx-review-1",
        "status": "waiting_feedback",
        "request": {"mode": "audit_then_repair", "trigger": "manual", "dossier_id": "d-2"},
        "snapshot": {
            "run_id": "tx-review-1",
            "status": "waiting_feedback",
            "reason_code": "tx_agent_closure_requirements_unresolved",
            "iterations": 3,
            "session_id": "tx-review-session-1",
            "latest_refs": {"tx_source_transcript_ref": {"artifact_path": "artifact://source"}},
            "progress_log": [
                {"timestamp_epoch_seconds": 100, "iteration": 0, "phase": "starting", "message": "start"},
                {
                    "timestamp_epoch_seconds": 101,
                    "iteration": 1,
                    "phase": "audit_result",
                    "message": "audit",
                    "detail": {"decision_ledger": {"summary": {"unresolved_count": 2}}},
                },
                {
                    "timestamp_epoch_seconds": 102,
                    "iteration": 2,
                    "phase": "image_verify_result",
                    "message": "verify",
                },
                {
                    "timestamp_epoch_seconds": 103,
                    "iteration": 3,
                    "phase": "human_feedback_needed",
                    "event_type": "human_feedback_needed",
                    "prompt_id": "hitl_range_3",
                },
            ],
            "critical_events": [],
            "runtime_hitl_state": {
                "blocker_registry": {
                    "active_blocker_id": "blocker:range",
                    "counts": {"waiting_feedback": 1, "answered_unintegrated": 0, "total": 1},
                    "rows": [
                        {
                            "blocker_id": "blocker:range",
                            "decision_key": "range",
                            "state": "waiting_feedback",
                            "linked_prompt_id": "hitl_range_3",
                        }
                    ],
                    "history": [
                        {
                            "timestamp_epoch_seconds": 103,
                            "iteration": 3,
                            "active_blocker_id": "blocker:range",
                            "prior_state": "open",
                            "new_state": "waiting_feedback",
                            "action_attempted": "request_hitl",
                            "result": "waiting_feedback",
                            "reason": "prompt_issued",
                        }
                    ],
                },
                "hitl_lifecycle_log": [
                    {
                        "timestamp_epoch_seconds": 103,
                        "iteration": 3,
                        "phase": "human_feedback_needed",
                        "prompt_id": "hitl_range_3",
                        "ticket_id": "ticket-range-3",
                    }
                ],
            },
            "terminal_summary": {
                "terminal_classification": "blocked_waiting_feedback",
                "human_feedback_pending": True,
                "decision_ledger": {"summary": {"unresolved_count": 2}},
            },
        },
    }


def _mission_runtime_payload() -> dict:
    return {
        "mission_id": "mission-review-1",
        "objective": "cross mode review",
        "request_id": "mission-request-review-1",
        "active_mode": "deed_to_ir",
        "mode_history": ["deed_to_ir", "transcript_edit", "deed_to_ir"],
        "transition_history": [
            {
                "prior_mode": "deed_to_ir",
                "next_mode": "transcript_edit",
                "reason": "handoff_to_review",
                "status": "applied",
                "order_anchor": 1,
                "timestamp_epoch_seconds": 101,
                "resume_note_for_prior_mode": "resume after reconciliation",
                "handed_forward_artifact_refs": ["artifact://handoff/1"],
            },
            {
                "prior_mode": "transcript_edit",
                "next_mode": "deed_to_ir",
                "reason": "review_complete",
                "status": "applied",
                "order_anchor": 2,
                "timestamp_epoch_seconds": 103,
                "handed_forward_artifact_refs": ["artifact://handoff/2"],
            },
        ],
        "cycles": [
            {
                "cycle_index": 1,
                "executed_mode": "deed_to_ir",
                "resulting_active_mode": "transcript_edit",
                "summary": "deed cycle",
                "timestamp_epoch_seconds": 100,
                "transition": {
                    "prior_mode": "deed_to_ir",
                    "next_mode": "transcript_edit",
                    "reason": "handoff_to_review",
                    "status": "applied",
                    "order_anchor": 1,
                    "timestamp_epoch_seconds": 101,
                    "handed_forward_artifact_refs": ["artifact://handoff/1"],
                },
            },
            {
                "cycle_index": 2,
                "executed_mode": "transcript_edit",
                "resulting_active_mode": "deed_to_ir",
                "summary": "review cycle",
                "timestamp_epoch_seconds": 102,
                "transition": {
                    "prior_mode": "transcript_edit",
                    "next_mode": "deed_to_ir",
                    "reason": "review_complete",
                    "status": "applied",
                    "order_anchor": 2,
                    "timestamp_epoch_seconds": 103,
                    "handed_forward_artifact_refs": ["artifact://handoff/2"],
                },
            },
        ],
        "mission_status": {"terminal": False, "terminal_class": "in_progress", "reason_code": None},
        "resumability_summary": {"resumable": True, "resume_reason": "ready_for_deed_resume"},
        "blocker_posture_summary": {"waiting_human": False, "open_blocker_count": 0},
        "verification_posture_summary": {"status": "closure_clear", "last_verification_kind": "tx_ledger"},
        "created_at_epoch_seconds": 100,
        "updated_at_epoch_seconds": 103,
        "cycle_index": 2,
        "high_signal_artifact_refs": ["artifact://handoff/1", "artifact://handoff/2"],
    }


def test_per_run_review_summary_controller_trace() -> None:
    transcript, run_artifact = _controller_inputs()
    trace = build_controller_kernel_trace(
        controller_transcript=transcript,
        run_artifact=run_artifact,
    )
    run_state = build_controller_kernel_run_state(
        controller_transcript=transcript,
        run_artifact=run_artifact,
    )
    summary = build_run_review_summary(trace=trace, run_state=run_state)
    assert summary.loop_family == "controller_kernel"
    assert summary.terminal_class == "completed"
    assert summary.reason_code == "done_verified"
    assert summary.event_count >= 4
    assert summary.verification_present is False
    assert "missing_verification_before_completion" in summary.review_flags
    assert summary.emitted_pattern_summary.startswith("dominant_kind=")


def test_per_run_review_summary_transcript_edit_trace() -> None:
    payload = _tx_run_snapshot()
    trace = build_transcript_edit_trace(run_snapshot=payload)
    run_state = build_transcript_edit_run_state(run_snapshot=payload)
    summary = build_run_review_summary(trace=trace, run_state=run_state)
    assert summary.loop_family == "transcript_edit"
    assert summary.terminal_class == "waiting_human"
    assert summary.waiting_human_present is True
    assert summary.verification_present is True
    assert summary.blocker_transition_present is True
    assert summary.recurring_action_shapes


def test_aggregate_review_over_mixed_runs() -> None:
    ctrl_transcript, ctrl_run_artifact = _controller_inputs()
    ctrl_summary = build_run_review_summary(
        trace=build_controller_kernel_trace(
            controller_transcript=ctrl_transcript,
            run_artifact=ctrl_run_artifact,
        ),
        run_state=build_controller_kernel_run_state(
            controller_transcript=ctrl_transcript,
            run_artifact=ctrl_run_artifact,
        ),
    )
    tx_payload = _tx_run_snapshot()
    tx_summary = build_run_review_summary(
        trace=build_transcript_edit_trace(run_snapshot=tx_payload),
        run_state=build_transcript_edit_run_state(run_snapshot=tx_payload),
    )
    aggregate = build_review_aggregate(summaries=[ctrl_summary, tx_summary])
    assert aggregate.run_count == 2
    assert aggregate.loop_family_distribution["controller_kernel"] == 1
    assert aggregate.loop_family_distribution["transcript_edit"] == 1
    assert aggregate.terminal_class_distribution["completed"] == 1
    assert aggregate.terminal_class_distribution["waiting_human"] == 1
    assert aggregate.waiting_human_rate == 0.5
    assert aggregate.verification_missing_on_completion_count == 1


def test_partial_trace_warnings_and_pattern_summary_are_stable() -> None:
    payload = _tx_run_snapshot()
    payload["snapshot"]["progress_log"] = payload["snapshot"]["progress_log"] * 12
    payload["snapshot"]["critical_events"] = [
        {"timestamp_epoch_seconds": 120 + idx, "phase": "human_feedback", "event_type": "human_feedback"}
        for idx in range(200)
    ]
    trace = build_transcript_edit_trace(run_snapshot=payload)
    summary = build_run_review_summary(trace=trace, run_state=build_transcript_edit_run_state(run_snapshot=payload))
    assert summary.partial_trace is True
    assert "partial_trace_needs_caution" in summary.review_flags
    assert "tx_progress_log_bounded" in summary.normalization_warnings
    assert "tx_critical_events_bounded" in summary.normalization_warnings
    assert "synthesized=" in summary.emitted_pattern_summary


def test_mission_runtime_review_summary_represents_multi_mode_story() -> None:
    payload = _mission_runtime_payload()
    trace = build_mission_runtime_trace(mission_runtime_payload=payload)
    run_state = build_mission_runtime_run_state(mission_runtime_payload=payload)
    summary = build_run_review_summary(trace=trace, run_state=run_state)
    assert summary.loop_family == "mission_runtime"
    assert summary.active_mode == "deed_to_ir"
    assert summary.mode_history == ["deed_to_ir", "transcript_edit", "deed_to_ir"]
    assert summary.transition_count == 2
    assert summary.transition_reasons == ["handoff_to_review", "review_complete"]
    assert any(row["mode"] == "deed_to_ir" for row in summary.mode_event_distribution)

    aggregate = build_review_aggregate(summaries=[summary])
    assert aggregate.multi_mode_run_count == 1
    assert aggregate.total_transition_count == 2
