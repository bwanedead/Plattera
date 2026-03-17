from __future__ import annotations

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
from harness.mission_runtime.contracts import MissionRuntimeRequest
from harness.mission_runtime.modes.deed_to_ir import (
    DEED_TO_IR_MODE_NAME,
    DeedToIRModePolicy,
    adapt_controller_run_result,
    build_deed_to_ir_mode_policy_from_controller_inputs,
)
from harness.mission_runtime.registry import ModePolicyRegistry
from harness.mission_runtime.runtime import MissionRuntime


def _make_request() -> MissionRuntimeRequest:
    return MissionRuntimeRequest(
        mission_id="mission-deed-1",
        objective="deed-to-ir integration smoke",
        initial_mode=DEED_TO_IR_MODE_NAME,
        request_id="request-deed-1",
    )


def _controller_result(
    *,
    terminal_outcome: TerminalOutcomeKind = TerminalOutcomeKind.SUCCESS,
    stop_reason: StopReason = StopReason.COMPLETED,
    success: bool = True,
    reason_code: str | None = "done_verified",
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
    )


def test_deed_to_ir_mode_policy_registers_and_runs_through_mission_runtime() -> None:
    run_calls = {"count": 0}

    def _runner(_request: MissionRuntimeRequest, _ledger: Any) -> ControllerRunResult:
        run_calls["count"] += 1
        return _controller_result()

    policy = DeedToIRModePolicy(runner=_runner)
    runtime = MissionRuntime(policy_registry=ModePolicyRegistry([policy]), now_fn=lambda: 100.0)

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
    policy = build_deed_to_ir_mode_policy_from_controller_inputs(
        session_manager=object(),  # type: ignore[arg-type]
        llm_client=object(),  # type: ignore[arg-type]
        start_request=start_req,
        model="gpt-5-mini",
        max_iterations=9,
    )
    runtime = MissionRuntime(policy_registry=ModePolicyRegistry([policy]), now_fn=lambda: 100.0)

    result = runtime.run_cycle(request=_make_request())

    assert observed.get("model") == "gpt-5-mini"
    assert observed.get("max_iterations") == 9
    assert observed.get("start_request") is start_req
    assert result.terminal_handoff is not None
    assert result.terminal_handoff.terminal is True


def test_deed_to_ir_phase_b_keeps_cycle_linear_without_transition_or_tx_state() -> None:
    policy = DeedToIRModePolicy(runner=lambda _request, _ledger: _controller_result())
    runtime = MissionRuntime(policy_registry=ModePolicyRegistry([policy]), now_fn=lambda: 100.0)

    result = runtime.run_cycle(request=_make_request())

    assert result.transition is None
    assert result.ledger.active_mode == DEED_TO_IR_MODE_NAME
    assert all("transcript_edit" not in mode for mode in result.ledger.mode_history)
    assert "mode" in result.interpretation.details
    assert result.interpretation.details["mode"] == DEED_TO_IR_MODE_NAME
