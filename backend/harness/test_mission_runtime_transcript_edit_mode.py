from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from agents.transcript_edit.contracts import TranscriptEditAgentRunRequest, TranscriptEditAgentRunResult
from agents.transcript_edit.domain_pack import build_transcript_edit_domain_pack_bundle
from harness.mission_runtime.contracts import MissionRuntimeRequest
from harness.mission_runtime.modes.transcript_edit import (
    TRANSCRIPT_EDIT_MODE_NAME,
    TranscriptEditModeAdapter,
    build_transcript_edit_mode_adapter_from_controller_inputs,
)
from harness.mission_runtime.registry import MissionModeAdapterRegistry
from harness.mission_runtime.runtime import MissionRuntime


def _request(*, metadata: dict[str, Any] | None = None) -> MissionRuntimeRequest:
    return MissionRuntimeRequest(
        mission_id="mission-transcript-1",
        objective="transcript-edit integration smoke",
        initial_mode=TRANSCRIPT_EDIT_MODE_NAME,
        request_id="request-transcript-1",
        metadata=metadata or {},
    )


def _result(
    *,
    status: str = "completed",
    reason_code: str = "tx_agent_clean_complete",
    mission_runtime_summary: dict[str, Any] | None = None,
    latest_refs: dict[str, Any] | None = None,
    handoff_posture: dict[str, Any] | None = None,
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
        handoff_posture=handoff_posture,
    )


def test_transcript_edit_mode_adapter_registers_and_runs_through_mission_runtime() -> None:
    calls = {"count": 0}

    def _runner(_request: MissionRuntimeRequest, _ledger: Any) -> TranscriptEditAgentRunResult:
        calls["count"] += 1
        return _result(
            handoff_posture={
                "posture": "ready_for_downstream_domain",
                "target_domain_id": "deed_to_ir",
                "target_family_id": "mapping",
                "reason_code": "tx_agent_clean_complete",
                "summary": "Transcript-edit can hand off validated artifacts downstream.",
            }
        )

    runtime = MissionRuntime(
        adapter_registry=MissionModeAdapterRegistry([TranscriptEditModeAdapter(runner=_runner)]),
        now_fn=lambda: 100.0,
    )
    result = runtime.run_cycle(
        request=_request(
            metadata={
                "phase_e_enable_linear_transitions": True,
                "transcript_edit_transition_to_deed_to_ir": True,
            }
        )
    )

    assert calls["count"] == 1
    assert result.transition is not None
    assert result.transition.next_mode == "deed_to_ir"
    assert result.active_mode == TRANSCRIPT_EDIT_MODE_NAME
    assert result.ledger.active_mode == TRANSCRIPT_EDIT_MODE_NAME
    assert result.ledger.mode_history == [TRANSCRIPT_EDIT_MODE_NAME]
    assert result.terminal_handoff is not None
    assert result.terminal_handoff.terminal_class == "completed"
    assert result.interpretation.details["mode"] == TRANSCRIPT_EDIT_MODE_NAME
    assert result.mode_run_envelope is not None
    assert result.mode_run_envelope.domain_payload["status"] == "completed"
    assert result.mode_run_envelope.domain_payload["handoff_posture"]["posture"] == "ready_for_downstream_domain"
    assert result.mode_run_envelope.family_coordination is not None
    assert result.mode_run_envelope.family_coordination.posture == "ready_for_downstream_domain"
    assert result.mode_run_envelope.family_coordination.transition_recommendation is not None
    assert result.mode_run_envelope.family_coordination.transition_recommendation.next_mode == "deed_to_ir"


def test_transcript_edit_closure_summary_is_ledger_backed() -> None:
    policy = TranscriptEditModeAdapter(
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
    runtime = MissionRuntime(adapter_registry=MissionModeAdapterRegistry([policy]), now_fn=lambda: 100.0)
    result = runtime.run_cycle(request=_request())

    assert result.recommendation.verification_posture is not None
    assert result.recommendation.verification_posture.status == "closure_blocking"
    assert result.recommendation.verification_posture.last_verification_kind == "transcript_edit_closure_ledger"
    assert result.recommendation.blocker_posture is not None
    assert result.recommendation.blocker_posture.waiting_human is False


def test_transcript_edit_waiting_summary_is_registry_backed() -> None:
    policy = TranscriptEditModeAdapter(
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
    runtime = MissionRuntime(adapter_registry=MissionModeAdapterRegistry([policy]), now_fn=lambda: 100.0)
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
    policy = TranscriptEditModeAdapter(
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
    runtime = MissionRuntime(adapter_registry=MissionModeAdapterRegistry([policy]), now_fn=lambda: 100.0)
    result = runtime.run_cycle(request=_request())

    assert result.recommendation.verification_posture is not None
    assert result.recommendation.verification_posture.status == "closure_clear"
    assert result.recommendation.verification_posture.status != "tx_agent_no_safe_plan_for_findings"


def test_transcript_edit_builder_wraps_kernel_runner_signature(monkeypatch: Any) -> None:
    """Builder forwards request_id_prefix and transcript_request to the kernel runner."""
    import harness.mission_runtime.modes.transcript_edit as _tx_mode_mod

    observed: dict[str, Any] = {}

    def _fake_kernel_runner(**kwargs: Any) -> TranscriptEditAgentRunResult:
        observed.update(kwargs)
        return _result()

    monkeypatch.setattr(_tx_mode_mod, "run_orchestration_kernel_transcript_loop", _fake_kernel_runner)

    tx_request = TranscriptEditAgentRunRequest(
        source_transcript_ref="artifact://tx/source/1",
        mode="audit_then_repair_then_promote",
    )
    policy = build_transcript_edit_mode_adapter_from_controller_inputs(
        session_manager=object(),  # type: ignore[arg-type]
        transcript_request=tx_request,
        request_id_prefix="tx-mission-prefix",
    )
    runtime = MissionRuntime(adapter_registry=MissionModeAdapterRegistry([policy]), now_fn=lambda: 100.0)
    cycle = runtime.run_cycle(request=_request())

    assert observed.get("request_id_prefix") == "tx-mission-prefix"
    assert observed.get("request") is tx_request
    assert cycle.terminal_handoff is not None
    assert cycle.terminal_handoff.terminal is True


def test_transcript_edit_bundle_helper_binds_manifest_and_prompt_branch_reference() -> None:
    class _PackStub:
        def __init__(self) -> None:
            self.domain_pack_bundle = None
            self.domain_manifest = None

        def bind_domain_bundle(self, bundle: object) -> None:
            self.domain_pack_bundle = bundle
            self.domain_manifest = getattr(bundle, "manifest", None)

    stub = _PackStub()
    bundle = build_transcript_edit_domain_pack_bundle(stub)  # type: ignore[arg-type]

    assert stub.domain_pack_bundle is bundle
    assert bundle.manifest.domain_id == "transcript_edit"
    assert bundle.manifest.family_id == "mapping"
    assert bundle.prompt_branch_source_ref == "agents.transcript_edit.prompt_sources"
