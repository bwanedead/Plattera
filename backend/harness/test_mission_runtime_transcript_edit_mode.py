from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from agents.transcript_edit.contracts import TranscriptEditAgentRunRequest, TranscriptEditAgentRunResult
from harness.mission_runtime.contracts import MissionRuntimeRequest
from harness.mission_runtime.modes.transcript_edit import (
    TRANSCRIPT_EDIT_MODE_NAME,
    TranscriptEditModePolicy,
    build_transcript_edit_mode_policy_from_controller_inputs,
)
from harness.mission_runtime.registry import ModePolicyRegistry
from harness.mission_runtime.runtime import MissionRuntime


def _request() -> MissionRuntimeRequest:
    return MissionRuntimeRequest(
        mission_id="mission-transcript-1",
        objective="transcript-edit integration smoke",
        initial_mode=TRANSCRIPT_EDIT_MODE_NAME,
        request_id="request-transcript-1",
    )


def _result(
    *,
    status: str = "completed",
    reason_code: str = "tx_agent_clean_complete",
    mission_runtime_summary: dict[str, Any] | None = None,
    latest_refs: dict[str, Any] | None = None,
) -> TranscriptEditAgentRunResult:
    return TranscriptEditAgentRunResult(
        run_artifact_ref="artifact://tx/run/1",
        session_id="tx-session-1",
        iterations=2,
        status=status,
        reason_code=reason_code,
        latest_refs=latest_refs
        or {
            "tx_source_transcript_ref": {"artifact_path": "artifact://tx/source/1"},
            "tx_edited_transcript_ref": {"artifact_path": "artifact://tx/edited/1"},
        },
        review_required=status != "completed",
        runtime_hitl_state={
            "mission_runtime_summary": mission_runtime_summary
            or {
                "waiting_feedback": False,
                "pending_feedback_prompt_id": None,
                "open_blocker_count": 0,
                "unresolved_closure_count": 0,
                "closure_blocking": False,
                "verification_status": "closure_clear",
                "verification_kind": "transcript_edit_closure_ledger",
            },
            "pending_feedback_prompt_id": None,
            "pending_feedback_decision_key": None,
        },
    )


def test_transcript_edit_mode_policy_registers_and_runs_through_mission_runtime() -> None:
    calls = {"count": 0}

    def _runner(_request: MissionRuntimeRequest, _ledger: Any) -> TranscriptEditAgentRunResult:
        calls["count"] += 1
        return _result()

    runtime = MissionRuntime(
        policy_registry=ModePolicyRegistry([TranscriptEditModePolicy(runner=_runner)]),
        now_fn=lambda: 100.0,
    )
    result = runtime.run_cycle(request=_request())

    assert calls["count"] == 1
    assert result.transition is None
    assert result.active_mode == TRANSCRIPT_EDIT_MODE_NAME
    assert result.ledger.active_mode == TRANSCRIPT_EDIT_MODE_NAME
    assert result.ledger.mode_history == [TRANSCRIPT_EDIT_MODE_NAME]
    assert result.terminal_handoff is not None
    assert result.terminal_handoff.terminal_class == "completed"
    assert result.interpretation.details["mode"] == TRANSCRIPT_EDIT_MODE_NAME


def test_transcript_edit_closure_summary_is_ledger_backed() -> None:
    policy = TranscriptEditModePolicy(
        runner=lambda _request, _ledger: _result(
            status="needs_review",
            reason_code="tx_agent_closure_requirements_unresolved",
            mission_runtime_summary={
                "waiting_feedback": False,
                "pending_feedback_prompt_id": None,
                "open_blocker_count": 0,
                "unresolved_closure_count": 1,
                "closure_blocking": True,
                "verification_status": "closure_blocking",
                "verification_kind": "transcript_edit_closure_ledger",
            },
        )
    )
    runtime = MissionRuntime(policy_registry=ModePolicyRegistry([policy]), now_fn=lambda: 100.0)
    result = runtime.run_cycle(request=_request())

    assert result.recommendation.verification_posture is not None
    assert result.recommendation.verification_posture.status == "closure_blocking"
    assert result.recommendation.verification_posture.last_verification_kind == "transcript_edit_closure_ledger"
    assert result.recommendation.blocker_posture is not None
    assert result.recommendation.blocker_posture.waiting_human is False


def test_transcript_edit_waiting_summary_is_registry_backed() -> None:
    policy = TranscriptEditModePolicy(
        runner=lambda _request, _ledger: _result(
            status="needs_review",
            reason_code="tx_agent_waiting_feedback",
            mission_runtime_summary={
                "waiting_feedback": True,
                "pending_feedback_prompt_id": "prompt-123",
                "open_blocker_count": 1,
                "unresolved_closure_count": 0,
                "closure_blocking": False,
                "verification_status": "closure_clear",
                "verification_kind": "transcript_edit_closure_ledger",
            },
        )
    )
    runtime = MissionRuntime(policy_registry=ModePolicyRegistry([policy]), now_fn=lambda: 100.0)
    result = runtime.run_cycle(request=_request())

    assert result.terminal_handoff is not None
    assert result.terminal_handoff.terminal_class == "waiting_human"
    assert result.recommendation.blocker_posture is not None
    assert result.recommendation.blocker_posture.waiting_human is True
    assert result.recommendation.blocker_posture.open_blocker_count == 1
    assert result.recommendation.resumability is not None
    assert result.recommendation.resumability.resumable is True
    assert result.recommendation.resumability.resume_requirements == ["prompt-123"]


def test_transcript_edit_clear_ledger_verification_posture_does_not_echo_reason_code() -> None:
    policy = TranscriptEditModePolicy(
        runner=lambda _request, _ledger: _result(
            status="needs_review",
            reason_code="tx_agent_no_safe_plan_for_findings",
            mission_runtime_summary={
                "waiting_feedback": False,
                "pending_feedback_prompt_id": None,
                "open_blocker_count": 2,
                "unresolved_closure_count": 0,
                "closure_blocking": False,
                "verification_status": "closure_clear",
                "verification_kind": "transcript_edit_closure_ledger",
            },
        )
    )
    runtime = MissionRuntime(policy_registry=ModePolicyRegistry([policy]), now_fn=lambda: 100.0)
    result = runtime.run_cycle(request=_request())

    assert result.recommendation.verification_posture is not None
    assert result.recommendation.verification_posture.status == "closure_clear"
    assert result.recommendation.verification_posture.status != "tx_agent_no_safe_plan_for_findings"


def test_transcript_edit_builder_wraps_existing_controller_runner_signature() -> None:
    observed: dict[str, Any] = {}

    def _fake_controller_runner(**kwargs: Any) -> TranscriptEditAgentRunResult:
        observed.update(kwargs)
        return _result()

    policy = build_transcript_edit_mode_policy_from_controller_inputs(
        session_manager=object(),  # type: ignore[arg-type]
        transcript_request=TranscriptEditAgentRunRequest(
            source_transcript_ref="artifact://tx/source/1",
            mode="audit_then_repair_then_promote",
        ),
        request_id_prefix="tx-mission-prefix",
        controller_runner=_fake_controller_runner,
    )
    runtime = MissionRuntime(policy_registry=ModePolicyRegistry([policy]), now_fn=lambda: 100.0)
    cycle = runtime.run_cycle(request=_request())

    assert observed["request_id_prefix"] == "tx-mission-prefix"
    assert observed["request"].source_transcript_ref == "artifact://tx/source/1"
    assert cycle.terminal_handoff is not None
    assert cycle.terminal_handoff.terminal is True
