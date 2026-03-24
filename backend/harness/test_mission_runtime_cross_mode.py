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
from harness.mission_runtime.modes.deed_to_ir import DEED_TO_IR_MODE_NAME, DeedToIRModeAdapter
from harness.mission_runtime.modes.transcript_edit import TRANSCRIPT_EDIT_MODE_NAME, TranscriptEditModeAdapter
from harness.mission_runtime.registry import MissionModeAdapterRegistry
from harness.mission_runtime.runtime import MissionRuntime


def _request() -> MissionRuntimeRequest:
    return MissionRuntimeRequest(
        mission_id="mission-cross-1",
        objective="phase-e-cross-mode-round-trip",
        initial_mode=DEED_TO_IR_MODE_NAME,
        request_id="request-cross-1",
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
        last_dashboard={
            "latest_refs": {
                "bundle_ref": {"artifact_ref": "artifact://deed/bundle/1"},
                "compile_ref": {"artifact_path": "artifact://deed/compile/1"},
            }
        },
        transcript_artifact_ref="artifact://deed/transcript/1",
        session_id="request-cross-1::deed-run-1",
        run_artifact_ref="artifact://deed/run/1",
        iterations=3,
    )


def _transcript_result() -> TranscriptEditAgentRunResult:
    return TranscriptEditAgentRunResult(
        run_artifact_ref="artifact://tx/run/1",
        session_id="request-cross-1::tx-run-1",
        iterations=2,
        status="completed",
        reason_code="tx_agent_clean_complete",
        latest_refs={
            "tx_source_transcript_ref": {"artifact_path": "artifact://tx/source/1"},
            "tx_edited_transcript_ref": {"artifact_path": "artifact://tx/edited/1"},
        },
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


def test_linear_round_trip_transitions_preserve_one_mission_continuity_chain() -> None:
    deed_calls = {"count": 0}
    transcript_calls = {"count": 0}

    def _deed_runner(_request: MissionRuntimeRequest, _ledger: Any) -> ControllerRunResult:
        deed_calls["count"] += 1
        return _deed_result()

    def _transcript_runner(_request: MissionRuntimeRequest, _ledger: Any) -> TranscriptEditAgentRunResult:
        transcript_calls["count"] += 1
        return _transcript_result()

    runtime = MissionRuntime(
        adapter_registry=MissionModeAdapterRegistry(
            [
                DeedToIRModeAdapter(runner=_deed_runner),
                TranscriptEditModeAdapter(runner=_transcript_runner),
            ]
        ),
        now_fn=lambda: 100.0,
    )

    request = _request()
    cycle1 = runtime.run_cycle(request=request)
    cycle2 = runtime.run_cycle(request=request, ledger=cycle1.ledger)

    assert deed_calls["count"] == 1
    assert transcript_calls["count"] == 1

    assert cycle1.mission_id == "mission-cross-1"
    assert cycle2.mission_id == "mission-cross-1"
    assert cycle2.ledger.mission_id == "mission-cross-1"

    assert cycle1.trace_segment is not None
    assert cycle1.trace_segment.mode == DEED_TO_IR_MODE_NAME
    assert cycle1.transition is not None
    assert cycle1.transition.status == "applied"
    assert cycle1.transition.prior_mode == DEED_TO_IR_MODE_NAME
    assert cycle1.transition.next_mode == TRANSCRIPT_EDIT_MODE_NAME
    assert cycle1.transition.reason == "deed_to_ir_output_requires_transcript_edit_review"
    assert cycle1.transition.expected_next_work is not None
    assert cycle1.transition.resume_note_for_prior_mode is not None
    assert len(cycle1.transition.handed_forward_artifact_refs) > 0
    assert cycle1.active_mode == TRANSCRIPT_EDIT_MODE_NAME

    assert cycle2.trace_segment is not None
    assert cycle2.trace_segment.mode == TRANSCRIPT_EDIT_MODE_NAME
    assert cycle2.transition is not None
    assert cycle2.transition.status == "applied"
    assert cycle2.transition.prior_mode == TRANSCRIPT_EDIT_MODE_NAME
    assert cycle2.transition.next_mode == DEED_TO_IR_MODE_NAME
    assert cycle2.transition.reason == "transcript_edit_review_ready_for_deed_resume"
    assert cycle2.transition.expected_next_work is not None
    assert cycle2.transition.resume_note_for_prior_mode is not None
    assert len(cycle2.transition.handed_forward_artifact_refs) > 0
    assert cycle2.active_mode == DEED_TO_IR_MODE_NAME

    assert cycle2.ledger.mode_history == [
        DEED_TO_IR_MODE_NAME,
        TRANSCRIPT_EDIT_MODE_NAME,
        DEED_TO_IR_MODE_NAME,
    ]
    assert len(cycle2.ledger.transition_history) == 2
    assert cycle2.ledger.transition_history[0].order_anchor == 1
    assert cycle2.ledger.transition_history[1].order_anchor == 2
    assert len(cycle2.ledger.high_signal_artifact_refs) > 0

    assert cycle2.ledger.cycle_index == 2
    assert "child_mission_id" not in vars(cycle2.ledger)
    assert "child_missions" not in vars(cycle2.ledger)
