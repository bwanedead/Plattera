from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from agent_kernel.models import StopReason, TerminalOutcome, TerminalOutcomeKind
from agents.controller.controller_runtime import ControllerRunResult
from agents.transcript_edit.contracts import TranscriptEditAgentRunResult
from harness.mission_runtime.contracts import MissionRuntimeRequest
from harness.mission_runtime.modes.deed_to_ir import DEED_TO_IR_MODE_NAME, DeedToIRModePolicy
from harness.mission_runtime.modes.transcript_edit import TRANSCRIPT_EDIT_MODE_NAME, TranscriptEditModePolicy
from harness.mission_runtime.registry import ModePolicyRegistry
from harness.mission_runtime.runtime import MissionRuntime, build_mission_observability_payload
from harness.review.reporting import build_run_review_summary
from harness.run_state import build_mission_runtime_run_state
from harness.tracing.adapters.mission_runtime import build_mission_runtime_trace


def _request() -> MissionRuntimeRequest:
    return MissionRuntimeRequest(
        mission_id="mission-observe-1",
        objective="phase-f-observability",
        initial_mode=DEED_TO_IR_MODE_NAME,
        request_id="request-observe-1",
        metadata={
            "phase_e_enable_linear_transitions": True,
            "deed_to_ir_transition_to_transcript_edit": True,
            "transcript_edit_transition_to_deed_to_ir": True,
        },
    )


def _deed_result() -> ControllerRunResult:
    return ControllerRunResult(
        terminal=TerminalOutcome(
            terminal_outcome=TerminalOutcomeKind.SUCCESS,
            stop_reason=StopReason.COMPLETED,
            success=True,
            reason_code="deed_compile_ready",
        ),
        last_dashboard={"latest_refs": {"compile_ref": {"artifact_path": "artifact://deed/compile/1"}}},
        transcript_artifact_ref="artifact://deed/transcript/1",
        session_id="request-observe-1::deed-run-1",
        run_artifact_ref="artifact://deed/run/1",
        iterations=2,
    )


def _tx_result() -> TranscriptEditAgentRunResult:
    return TranscriptEditAgentRunResult(
        run_artifact_ref="artifact://tx/run/1",
        session_id="request-observe-1::tx-run-1",
        iterations=2,
        status="completed",
        reason_code="tx_agent_clean_complete",
        latest_refs={"tx_edited_transcript_ref": {"artifact_path": "artifact://tx/edited/1"}},
        review_required=False,
        runtime_hitl_state={
            "mission_runtime_summary": {
                "waiting_feedback": False,
                "pending_feedback_prompt_id": None,
                "open_blocker_count": 0,
                "unresolved_closure_count": 0,
                "closure_blocking": False,
                "verification_status": "closure_clear",
                "verification_kind": "transcript_edit_closure_ledger",
                "terminal_classification": "mapping_ready",
            }
        },
    )


def test_multi_mode_mission_observability_is_one_continuous_story() -> None:
    def _deed_runner(_request: MissionRuntimeRequest, _ledger: Any) -> ControllerRunResult:
        return _deed_result()

    def _tx_runner(_request: MissionRuntimeRequest, _ledger: Any) -> TranscriptEditAgentRunResult:
        return _tx_result()

    runtime = MissionRuntime(
        policy_registry=ModePolicyRegistry(
            [
                DeedToIRModePolicy(runner=_deed_runner),
                TranscriptEditModePolicy(runner=_tx_runner),
            ]
        ),
        now_fn=lambda: 100.0,
    )
    request = _request()
    cycle1 = runtime.run_cycle(request=request)
    cycle2 = runtime.run_cycle(request=request, ledger=cycle1.ledger)

    payload = build_mission_observability_payload(
        request=request,
        ledger=cycle2.ledger,
        cycle_results=[cycle1, cycle2],
    )
    mission_payload = payload["mission_runtime"]
    trace = build_mission_runtime_trace(mission_runtime_payload=mission_payload)
    run_state = build_mission_runtime_run_state(mission_runtime_payload=mission_payload)
    review = build_run_review_summary(trace=trace, run_state=run_state)

    assert trace.loop_family == "mission_runtime"
    assert trace.mission_id == "mission-observe-1"
    assert trace.mode_history == [DEED_TO_IR_MODE_NAME, TRANSCRIPT_EDIT_MODE_NAME, DEED_TO_IR_MODE_NAME]
    assert len(trace.transition_events) == 2
    assert any(event.event_kind == "mission_transition" for event in trace.events)

    mode_segments = [event for event in trace.events if event.event_kind == "mode_segment"]
    assert mode_segments[0].payload["executed_mode"] == DEED_TO_IR_MODE_NAME
    assert mode_segments[0].payload["resulting_active_mode"] == TRANSCRIPT_EDIT_MODE_NAME
    assert mode_segments[1].payload["executed_mode"] == TRANSCRIPT_EDIT_MODE_NAME
    assert mode_segments[1].payload["resulting_active_mode"] == DEED_TO_IR_MODE_NAME

    assert run_state.mission_mode_summary.active_mode == DEED_TO_IR_MODE_NAME
    assert run_state.mission_mode_summary.latest_transition_reason == "transcript_edit_review_ready_for_deed_resume"
    assert run_state.mission_mode_summary.mode_history == [DEED_TO_IR_MODE_NAME, TRANSCRIPT_EDIT_MODE_NAME, DEED_TO_IR_MODE_NAME]

    assert review.active_mode == DEED_TO_IR_MODE_NAME
    assert review.mode_history == [DEED_TO_IR_MODE_NAME, TRANSCRIPT_EDIT_MODE_NAME, DEED_TO_IR_MODE_NAME]
    assert review.transition_count == 2
    assert review.transition_reasons == [
        "deed_to_ir_output_requires_transcript_edit_review",
        "transcript_edit_review_ready_for_deed_resume",
    ]


def test_single_mode_observability_degrades_gracefully_without_transitions() -> None:
    payload = {
        "mission_runtime": {
            "mission_id": "mission-observe-single-1",
            "objective": "single mode mission",
            "request_id": "request-observe-single-1",
            "active_mode": DEED_TO_IR_MODE_NAME,
            "mode_history": [DEED_TO_IR_MODE_NAME],
            "transition_history": [],
            "high_signal_artifact_refs": [],
            "resumability_summary": {"resumable": False},
            "mission_status": {"terminal": False, "terminal_class": "in_progress", "reason_code": None},
            "blocker_posture_summary": {"waiting_human": False, "open_blocker_count": 0},
            "verification_posture_summary": {"status": "in_progress", "last_verification_kind": None},
            "created_at_epoch_seconds": 100,
            "updated_at_epoch_seconds": 101,
            "cycle_index": 1,
            "cycles": [
                {
                    "cycle_index": 1,
                    "executed_mode": DEED_TO_IR_MODE_NAME,
                    "resulting_active_mode": DEED_TO_IR_MODE_NAME,
                    "summary": "deed cycle in progress",
                    "timestamp_epoch_seconds": 101,
                    "transition": None,
                }
            ],
        }
    }
    mission_payload = payload["mission_runtime"]
    trace = build_mission_runtime_trace(mission_runtime_payload=mission_payload)
    run_state = build_mission_runtime_run_state(mission_runtime_payload=mission_payload)
    review = build_run_review_summary(trace=trace, run_state=run_state)

    assert trace.transition_events == []
    assert review.transition_count == 0
    assert review.mode_history == [DEED_TO_IR_MODE_NAME]
