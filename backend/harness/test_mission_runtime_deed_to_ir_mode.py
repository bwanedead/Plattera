from __future__ import annotations

from dataclasses import asdict
import sys
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from agent_kernel.models import (
    KernelBudgets,
    KernelGoal,
    KernelSessionStartRequest,
    StopReason,
    TerminalOutcome,
    TerminalOutcomeKind,
)
from agents.controller.controller_runtime import ControllerRunResult
from agents.deed_to_ir import build_deed_to_ir_domain_pack_bundle
from agents.deed_to_ir.handoff import build_deed_to_ir_handoff_posture
from harness.mission_runtime.contracts import MissionRuntimeRequest
from harness.mission_runtime.modes.deed_to_ir import (
    DEED_TO_IR_MODE_NAME,
    DeedToIRModeAdapter,
    adapt_controller_run_result,
    build_deed_to_ir_mode_adapter_from_controller_inputs,
)
from harness.mission_runtime.registry import MissionModeAdapterRegistry
from harness.mission_runtime.runtime import MissionRuntime


def _make_request(*, metadata: dict[str, Any] | None = None) -> MissionRuntimeRequest:
    return MissionRuntimeRequest(
        mission_id="mission-deed-1",
        objective="deed-to-ir integration smoke",
        initial_mode=DEED_TO_IR_MODE_NAME,
        request_id="request-deed-1",
        metadata=metadata or {},
    )


def _controller_result(
    *,
    terminal_outcome: TerminalOutcomeKind = TerminalOutcomeKind.SUCCESS,
    stop_reason: StopReason = StopReason.COMPLETED,
    success: bool = True,
    reason_code: str | None = "done_verified",
    handoff_posture: dict[str, Any] | None = None,
) -> ControllerRunResult:
    return ControllerRunResult(
        terminal=TerminalOutcome(
            terminal_outcome=terminal_outcome,
            stop_reason=stop_reason,
            success=success,
            reason_code=reason_code,
        ),
        last_dashboard={
            "latest_refs": {
                "bundle_ref": {"artifact_ref": "artifact://bundle/1"},
                "compile_ref": {"artifact_path": "artifact://compile/1"},
            }
        },
        transcript_artifact_ref="artifact://transcript/1",
        session_id="request-deed-1::run-1",
        run_artifact_ref="artifact://run/1",
        iterations=4,
        handoff_posture=handoff_posture,
    )


def test_deed_to_ir_mode_adapter_registers_and_runs_through_mission_runtime() -> None:
    run_calls = {"count": 0}

    def _runner(_request: MissionRuntimeRequest, _ledger: Any) -> ControllerRunResult:
        run_calls["count"] += 1
        return _controller_result()

    policy = DeedToIRModeAdapter(runner=_runner)
    runtime = MissionRuntime(adapter_registry=MissionModeAdapterRegistry([policy]), now_fn=lambda: 100.0)

    result = runtime.run_cycle(request=_make_request())

    assert run_calls["count"] == 1
    assert result.active_mode == DEED_TO_IR_MODE_NAME
    assert result.transition is None
    assert result.terminal_handoff is not None
    assert result.terminal_handoff.terminal_class == "completed"
    assert result.ledger.mission_status.reason_code == "done_verified"
    assert result.ledger.mode_history == [DEED_TO_IR_MODE_NAME]
    assert set(vars(result.ledger).keys()) == {
        "mission_id",
        "mission_objective",
        "request_id",
        "active_mode",
        "mode_history",
        "transition_history",
        "high_signal_artifact_refs",
        "resumability_summary",
        "mission_status",
        "blocker_posture_summary",
        "verification_posture_summary",
        "created_at_epoch_seconds",
        "updated_at_epoch_seconds",
        "cycle_index",
    }


def test_controller_terminal_mapping_is_preserved_at_adapter_seam() -> None:
    interpretation, recommendation = adapt_controller_run_result(
        _controller_result(
            terminal_outcome=TerminalOutcomeKind.NEEDS_USER_CHOICE,
            stop_reason=StopReason.NEEDS_USER_CHOICE,
            success=False,
            reason_code="requires_choice",
        )
    )

    assert interpretation.details["terminal_class"] == "waiting_human"
    assert recommendation.terminal is not None
    assert recommendation.terminal.terminal_class == "waiting_human"
    assert recommendation.terminal.reason_code == "requires_choice"
    assert recommendation.resumability is not None
    assert recommendation.resumability.resumable is True
    assert recommendation.high_signal_artifact_refs == [
        "artifact://run/1",
        "artifact://transcript/1",
        "artifact://bundle/1",
        "artifact://compile/1",
    ]


def test_builder_wraps_kernel_runner_signature(monkeypatch: Any) -> None:
    """Builder forwards model/max_iterations/start_request to the kernel runner."""
    import harness.mission_runtime.modes.deed_to_ir as _deed_mode_mod

    observed: dict[str, Any] = {}

    def _fake_kernel_runner(**kwargs: Any) -> ControllerRunResult:
        observed.update(kwargs)
        return _controller_result()

    monkeypatch.setattr(_deed_mode_mod, "run_orchestration_kernel_deed_loop", _fake_kernel_runner)

    start_req = KernelSessionStartRequest(
        request_id="request-deed-1",
        goal=KernelGoal(
            requires_global_placement=True,
            render_required=False,
            objective="deed objective",
        ),
        budgets=KernelBudgets(
            max_steps=5,
            max_wall_time_seconds=30,
            max_retrieval_calls=5,
            max_semantic_calls=5,
            max_patch_calls=1,
        ),
        dossier_id="dossier-1",
    )
    policy = build_deed_to_ir_mode_adapter_from_controller_inputs(
        session_manager=object(),  # type: ignore[arg-type]
        llm_client=object(),  # type: ignore[arg-type]
        start_request=start_req,
        model="gpt-5-mini",
        max_iterations=9,
    )
    runtime = MissionRuntime(adapter_registry=MissionModeAdapterRegistry([policy]), now_fn=lambda: 100.0)

    result = runtime.run_cycle(request=_make_request())

    assert observed.get("model") == "gpt-5-mini"
    assert observed.get("max_iterations") == 9
    assert observed.get("start_request") is start_req
    assert result.terminal_handoff is not None
    assert result.terminal_handoff.terminal is True


def test_deed_to_ir_phase_b_keeps_cycle_linear_without_transition_or_tx_state() -> None:
    policy = DeedToIRModeAdapter(runner=lambda _request, _ledger: _controller_result())
    runtime = MissionRuntime(adapter_registry=MissionModeAdapterRegistry([policy]), now_fn=lambda: 100.0)

    result = runtime.run_cycle(request=_make_request())

    assert result.transition is None
    assert result.ledger.active_mode == DEED_TO_IR_MODE_NAME
    assert all("transcript_edit" not in mode for mode in result.ledger.mode_history)
    assert "mode" in result.interpretation.details
    assert result.interpretation.details["mode"] == DEED_TO_IR_MODE_NAME


def test_deed_to_ir_bundle_helper_binds_manifest_and_prompt_branch_reference() -> None:
    class _PackStub:
        def __init__(self) -> None:
            self.domain_pack_bundle = None
            self.domain_manifest = None

        def bind_domain_bundle(self, bundle: object) -> None:
            self.domain_pack_bundle = bundle
            self.domain_manifest = getattr(bundle, "manifest", None)

    stub = _PackStub()
    bundle = build_deed_to_ir_domain_pack_bundle(stub)  # type: ignore[arg-type]

    assert stub.domain_pack_bundle is bundle
    assert bundle.manifest.domain_id == "deed_to_ir"
    assert bundle.manifest.family_id == "mapping"
    assert bundle.prompt_branch_source_ref == "agents.deed_to_ir.prompt_sources"


def test_deed_to_ir_mode_projects_handoff_posture_without_collapsing_transition() -> None:
    posture = asdict(
        build_deed_to_ir_handoff_posture(
            failure_classification={"stop_reason": "completed", "reason_code": "done_verified"},
            claimability={"claimable_ready": True, "missing_claimability": []},
        )
    )
    request = _make_request(
        metadata={
            "phase_e_enable_linear_transitions": True,
            "deed_to_ir_transition_to_transcript_edit": True,
        }
    )
    runtime = MissionRuntime(
        adapter_registry=MissionModeAdapterRegistry(
            [
                DeedToIRModeAdapter(
                    runner=lambda _request, _ledger: _controller_result(handoff_posture=posture),
                )
            ]
        ),
        now_fn=lambda: 100.0,
    )

    result = runtime.run_cycle(request=request)

    assert result.mode_run_envelope.domain_payload["handoff_posture"]["posture"] == "ready_for_downstream_domain"
    assert result.mode_run_envelope.family_coordination is not None
    assert result.mode_run_envelope.family_coordination.posture == "ready_for_downstream_domain"
    assert result.mode_run_envelope.family_coordination.transition_recommendation is not None
    assert result.mode_run_envelope.transition is not None
    assert result.mode_run_envelope.transition.next_mode == "transcript_edit"
    assert result.mode_run_envelope.transition.reason == "deed_to_ir_output_requires_transcript_edit_review"
