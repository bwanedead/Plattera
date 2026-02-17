"""Tests for Agent Kernel v0 request/result models and enums."""

from pathlib import Path
import sys

from pydantic import BaseModel

# Ensure repo root is importable when pytest is invoked from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.models import (
    ActionType,
    KernelBudgets,
    KernelGoal,
    KernelRequest,
    KernelResult,
    KernelState,
    StopReason,
    TerminalOutcome,
    TerminalOutcomeKind,
)


def test_kernel_request_round_trip_includes_global_placement_flag():
    """KernelRequest should round-trip with required goal.requires_global_placement."""
    request = KernelRequest(
        request_id="req-001",
        goal=KernelGoal(
            requires_global_placement=True,
            render_required=True,
            objective="Compile and judge deed graph deterministically.",
        ),
        budgets=KernelBudgets(
            max_steps=12,
            max_wall_time_seconds=120,
            max_retrieval_calls=5,
            max_semantic_calls=3,
            max_patch_calls=2,
        ),
        initial_ir_ref="artifacts/ir/ir-001.json",
        initial_graph_json={"metadata": {"source": "inline"}, "nodes": [{"id": "n1"}]},
    )

    payload = request.model_dump_json()
    rehydrated = KernelRequest.model_validate_json(payload)

    assert rehydrated.request_id == "req-001"
    assert rehydrated.goal.requires_global_placement is True
    assert rehydrated.goal.render_required is True
    assert rehydrated.goal.objective.startswith("Compile and judge")
    assert rehydrated.budgets.max_steps == 12
    assert rehydrated.initial_ir_ref == "artifacts/ir/ir-001.json"
    assert rehydrated.initial_graph_json is not None
    assert rehydrated.initial_graph_json["metadata"]["source"] == "inline"


def test_kernel_result_round_trip_serializes_terminal_outcome_and_state():
    """KernelResult should round-trip deterministic terminal fields."""
    result = KernelResult(
        request_id="req-001",
        final_state=KernelState.DONE,
        terminal=TerminalOutcome(
            terminal_outcome=TerminalOutcomeKind.SUCCESS,
            stop_reason=StopReason.COMPLETED,
            success=True,
            reason_code="done",
        ),
        steps_executed=7,
        run_artifact_ref="artifacts/runs/run-001.json",
    )

    payload = result.model_dump_json()
    rehydrated = KernelResult.model_validate_json(payload)

    assert rehydrated.request_id == "req-001"
    assert rehydrated.final_state == KernelState.DONE
    assert rehydrated.terminal.terminal_outcome == TerminalOutcomeKind.SUCCESS
    assert rehydrated.terminal.stop_reason == StopReason.COMPLETED
    assert rehydrated.terminal.success is True
    assert rehydrated.steps_executed == 7
    assert rehydrated.run_artifact_ref == "artifacts/runs/run-001.json"


def test_action_type_round_trip_includes_set_graph_requirements():
    """ActionType enum should include and round-trip SET_GRAPH_REQUIREMENTS."""

    class ActionEnvelope(BaseModel):
        action: ActionType

    envelope = ActionEnvelope(action=ActionType.SET_GRAPH_REQUIREMENTS)
    payload = envelope.model_dump_json()
    rehydrated = ActionEnvelope.model_validate_json(payload)

    assert rehydrated.action == ActionType.SET_GRAPH_REQUIREMENTS


def test_stop_reason_round_trip_supports_new_diagnostic_members():
    class StopEnvelope(BaseModel):
        reason: StopReason

    expected = (
        StopReason.NEEDS_USER_CHOICE,
        StopReason.NEEDS_UPLOAD,
        StopReason.NEEDS_CAPABILITY,
        StopReason.WORKER_UNAVAILABLE,
        StopReason.VALIDATION_FAILED,
        StopReason.INTERNAL_ERROR,
    )

    for reason in expected:
        payload = StopEnvelope(reason=reason).model_dump_json()
        rehydrated = StopEnvelope.model_validate_json(payload)
        assert rehydrated.reason == reason
