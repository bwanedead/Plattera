from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.run_state import (
    RUN_STATE_VERSION,
    build_controller_kernel_run_state,
    build_mission_runtime_run_state,
    build_transcript_edit_run_state,
)


def _tx_snapshot_waiting() -> dict:
    return {
        "run_id": "tx-run-1",
        "status": "waiting_feedback",
        "request": {"mode": "audit_then_repair", "trigger": "manual", "dossier_id": "d-1"},
        "snapshot": {
            "run_id": "tx-run-1",
            "status": "waiting_feedback",
            "reason_code": "tx_agent_closure_requirements_unresolved",
            "iterations": 3,
            "session_id": "tx-session-1",
            "decision_ledger": {
                "items": [
                    {
                        "key": "range",
                        "label": "Range",
                        "state": "disputed",
                        "blocking": True,
                        "operational_impact": "mapping_blocking",
                        "closure_requirement": {
                            "mapping_blocking": True,
                            "operational_impact": "mapping_blocking",
                            "required_information": "Confirm the correct range token.",
                            "resolution_options": ["Range 75 West", "Range 74 West"],
                        },
                    }
                ]
            },
            "latest_refs": {f"ref_{idx}": {"artifact_path": f"artifact://{idx}"} for idx in range(20)},
            "progress_log": [
                {
                    "timestamp_epoch_seconds": 100,
                    "phase": "audit_result",
                    "iteration": 2,
                    "detail": {
                        "decision_ledger": {"summary": {"unresolved_count": 1}},
                    },
                },
                {"timestamp_epoch_seconds": 101, "phase": "human_feedback_needed", "iteration": 3},
                {"timestamp_epoch_seconds": 102, "phase": "image_verify_result", "iteration": 3},
            ],
            "critical_events": [],
            "runtime_hitl_state": {
                "pending_feedback_prompt_id": "hitl_range_compat",
                "pending_feedback_decision_key": "range",
                "blocker_registry": {
                    "active_blocker_id": "blocker:range",
                    "counts": {"waiting_feedback": 1, "answered_unintegrated": 1, "total": 2},
                    "rows": [
                        {
                            "blocker_id": "blocker:range",
                            "decision_key": "range",
                            "state": "waiting_feedback",
                            "linked_prompt_id": "hitl_range_registry",
                        },
                        {
                            "blocker_id": "blocker:township",
                            "decision_key": "township",
                            "state": "answered_unintegrated",
                            "linked_prompt_id": "hitl_township_2",
                        },
                    ],
                },
            },
            "terminal_summary": {
                "terminal_classification": "blocked_waiting_feedback",
                "human_feedback_pending": True,
                "decision_ledger": {"summary": {"unresolved_count": 4}},
                "mapping_ready": False,
                "closure_state": "needs_human_feedback",
            },
        },
    }


def _controller_payload_completed() -> tuple[dict, dict]:
    transcript = {
        "events": [
            {
                "event_type": "run_header",
                "payload": {
                    "request_id": "request-1",
                    "session_id": "request-1::run-1",
                    "dossier_id": "d-1",
                },
            },
            {
                "event_type": "kernel_step_result",
                "payload": {
                    "iteration": 1,
                    "action_type": "retrieve_evidence",
                    "latest_refs": {"retrieval_ref": "artifact://retrieval-1"},
                },
            },
            {
                "event_type": "kernel_step_result",
                "payload": {
                    "iteration": 2,
                    "action_type": "declare_done",
                    "latest_refs": {"bundle_ref": "artifact://bundle-1"},
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
        "run_id": "run-1",
        "request_id": "request-1",
        "session_id": "request-1::run-1",
        "steps": [{"step_id": "step-1"}, {"step_id": "step-2"}],
    }
    return transcript, run_artifact


def test_transcript_edit_builder_uses_registry_waiting_and_ledger_unresolved() -> None:
    envelope = build_transcript_edit_run_state(run_snapshot=_tx_snapshot_waiting())
    assert envelope.loop_family == "transcript_edit"
    assert envelope.blocker_summary.source == "registry"
    assert envelope.blocker_summary.active_blocker_id == "blocker:range"
    assert envelope.blocker_summary.waiting_human is True
    assert envelope.blocker_summary.answered_unintegrated_count == 1
    assert envelope.waiting_summary.waiting is True
    assert envelope.waiting_summary.resumable is True
    assert envelope.waiting_summary.owner_kind == "blocker_registry"
    assert envelope.verification_summary.status == "needs_human_feedback"
    assert envelope.mission_mode_summary.active_mode == "audit_then_repair"
    assert envelope.mission_state.loop_family == "transcript_edit"
    assert envelope.mission_state.resolution_state.active_item_id == "te:ledger:range"
    assert envelope.mission_state.resolution_state.items[0].item_id == "te:ledger:range"
    assert envelope.mission_state.resolution_state.items[0].kind == "transcript_edit.decision_item"
    assert envelope.latest_refs_summary.total_count == 20
    assert len(envelope.latest_refs_summary.ref_keys) == 16
    assert envelope.envelope_version == RUN_STATE_VERSION


def test_controller_builder_is_sparse_and_does_not_invent_blocker_authority() -> None:
    transcript, run_artifact = _controller_payload_completed()
    envelope = build_controller_kernel_run_state(
        controller_transcript=transcript,
        run_artifact=run_artifact,
    )
    assert envelope.loop_family == "controller_kernel"
    assert envelope.blocker_summary.source == "sparse"
    assert envelope.blocker_summary.open_count is None
    assert envelope.blocker_summary.active_blocker_id is None
    assert envelope.mission_state.loop_family == "controller_kernel"
    assert envelope.waiting_summary.waiting is False
    assert envelope.terminal_summary.terminal is True
    assert envelope.terminal_summary.terminal_class == "completed"
    assert envelope.terminal_summary.reason_code == "done_verified"


def test_controller_builder_waiting_human_terminal_maps_and_resumable() -> None:
    transcript, run_artifact = _controller_payload_completed()
    transcript["events"][-1]["payload"]["terminal"] = {
        "terminal_outcome": "NEEDS_USER_CHOICE",
        "stop_reason": "needs_user_choice",
        "success": None,
        "reason_code": "requires_choice",
    }
    envelope = build_controller_kernel_run_state(
        controller_transcript=transcript,
        run_artifact=run_artifact,
    )
    assert envelope.terminal_summary.terminal_class == "waiting_human"
    assert envelope.waiting_summary.waiting is True
    assert envelope.waiting_summary.resumable is True
    assert envelope.waiting_summary.waiting_kind == "human_feedback"


def test_transcript_edit_missing_optional_data_is_explicit() -> None:
    payload = {
        "run_id": "tx-run-minimal",
        "snapshot": {
            "run_id": "tx-run-minimal",
            "status": "needs_review",
            "reason_code": "tx_agent_closure_requirements_unresolved",
            "progress_log": [],
            "critical_events": [],
            "runtime_hitl_state": {},
            "terminal_summary": {},
            "latest_refs": {},
        },
    }
    envelope = build_transcript_edit_run_state(run_snapshot=payload)
    assert envelope.blocker_summary.source == "registry"
    assert envelope.blocker_summary.open_count == 0
    assert envelope.waiting_summary.waiting is False
    assert envelope.waiting_summary.owner_kind is None
    assert envelope.latest_refs_summary.has_refs is False


def test_transcript_edit_waiting_falls_back_to_compat_only_without_registry_rows() -> None:
    payload = {
        "run_id": "tx-run-compat-wait",
        "snapshot": {
            "run_id": "tx-run-compat-wait",
            "status": "waiting_feedback",
            "reason_code": "tx_agent_waiting_for_feedback",
            "progress_log": [],
            "critical_events": [],
            "runtime_hitl_state": {
                "pending_feedback_prompt_id": "hitl_range_compat",
                "pending_feedback_decision_key": "RANGE",
                "blocker_registry": {"rows": []},
            },
            "terminal_summary": {},
            "latest_refs": {},
        },
    }
    envelope = build_transcript_edit_run_state(run_snapshot=payload)
    assert envelope.waiting_summary.waiting is True
    assert envelope.waiting_summary.resumable is True
    assert envelope.waiting_summary.owner_kind is None
    assert envelope.blocker_summary.source == "derived"


def test_mission_runtime_builder_adds_mission_mode_awareness_without_ledger_mirroring() -> None:
    payload = {
        "mission_id": "mission-run-state-1",
        "objective": "cross-mode mission",
        "request_id": "request-run-state-1",
        "active_mode": "deed_to_ir",
        "mode_history": ["deed_to_ir", "transcript_edit", "deed_to_ir"],
        "transition_history": [
            {
                "prior_mode": "deed_to_ir",
                "next_mode": "transcript_edit",
                "reason": "handoff_to_review",
                "resume_note_for_prior_mode": "resume with repaired refs",
            }
        ],
        "high_signal_artifact_refs": ["artifact://handoff/1", "artifact://handoff/2"],
        "resumability_summary": {
            "resumable": True,
            "resume_reason": "waiting_handoff_completion",
            "resume_requirements": ["artifact://handoff/2"],
        },
        "mission_status": {"terminal": False, "terminal_class": "in_progress", "reason_code": None},
        "blocker_posture_summary": {"waiting_human": False, "open_blocker_count": 0},
        "verification_posture_summary": {"status": "closure_clear", "last_verification_kind": "tx_ledger"},
        "cycle_index": 2,
        "resolution_state": {
            "active_item_id": "item:mission-active",
            "items": [
                {
                    "item_id": "item:mission-active",
                    "title": "Active mission work item",
                    "kind": "work_item",
                    "status": "open",
                    "summary": "Keep iterating the current item",
                }
            ],
        },
        "cycles": [{"executed_mode": "transcript_edit"}],
    }
    envelope = build_mission_runtime_run_state(mission_runtime_payload=payload)
    assert envelope.loop_family == "mission_runtime"
    assert envelope.run_id == "mission-run-state-1"
    assert envelope.request_summary.mode == "deed_to_ir"
    assert envelope.mission_mode_summary.active_mode == "deed_to_ir"
    assert envelope.mission_mode_summary.mode_history == ["deed_to_ir", "transcript_edit", "deed_to_ir"]
    assert envelope.mission_mode_summary.latest_transition_reason == "handoff_to_review"
    assert envelope.mission_state.loop_family == "mission_runtime"
    assert envelope.mission_state.resolution_state.active_item_id == "item:mission-active"
    assert envelope.mission_state.resolution_state.items[0].title == "Active mission work item"
    assert envelope.mission_mode_summary.resume_context_summary["resumable"] is True
    assert envelope.mission_mode_summary.resume_context_summary["latest_transition_target_mode"] == "transcript_edit"
    assert "expected_next_work" not in envelope.mission_mode_summary.resume_context_summary
    assert envelope.latest_refs_summary.total_count == 2


def test_mission_runtime_builder_prefers_nested_mission_state_resolution_state() -> None:
    payload = {
        "mission_id": "mission-run-state-2",
        "objective": "nested mission state",
        "request_id": "request-run-state-2",
        "active_mode": "deed_to_ir",
        "mode_history": ["deed_to_ir"],
        "transition_history": [],
        "high_signal_artifact_refs": [],
        "resumability_summary": {"resumable": False},
        "mission_status": {"terminal": False, "terminal_class": "in_progress", "reason_code": None},
        "blocker_posture_summary": {"waiting_human": False, "open_blocker_count": 0},
        "verification_posture_summary": {"status": "closure_clear", "last_verification_kind": "tx_ledger"},
        "cycle_index": 1,
        "mission_state": {
            "schema_version": "mission_state.v1",
            "mission_id": "mission-run-state-2",
            "loop_family": "mission_runtime",
            "objective": "nested mission state",
            "active_mode": "deed_to_ir",
            "updated_at_epoch_seconds": 123.0,
            "resolution_state": {
                "schema_version": "resolution_state.v1",
                "active_item_id": "item:nested",
                "items": [
                    {
                        "item_id": "item:nested",
                        "title": "Nested active item",
                        "kind": "work_item",
                        "status": "open",
                        "summary": "Nested resolution state should win",
                    }
                ],
            },
        },
    }
    envelope = build_mission_runtime_run_state(mission_runtime_payload=payload)
    assert envelope.mission_state.loop_family == "mission_runtime"
    assert envelope.mission_state.resolution_state.active_item_id == "item:nested"
    assert envelope.mission_state.resolution_state.items[0].title == "Nested active item"
