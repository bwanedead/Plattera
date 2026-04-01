from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.runtime.orchestration.mode_transition import evaluate_mode_transition
from harness.runtime.orchestration.mission_contracts import (
    MissionFlowRequest,
    MissionModeRunEnvelope,
    MissionRecord,
    MissionRecordView,
    ModeCycleContext,
    ModeCycleOutcome,
    ModeInterpretation,
    ModeTransitionRecommendation,
)
from harness.runtime.orchestration.mission_orchestrator import MissionCoordinator
from harness.runtime.orchestration.mode_registry import MissionModeAdapterRegistry


def test_transition_capability_rejects_unknown_mode() -> None:
    record = MissionRecord(
        mission_id="m1",
        mission_objective="o1",
        request_id="r1",
        active_mode="mode.alpha",
        mode_history=["mode.alpha"],
    )
    transition = evaluate_mode_transition(
        record=record,
        recommendation=ModeTransitionRecommendation(next_mode="mode.unknown", reason="switch"),
        mode_exists=lambda _mode: False,
        now_epoch_seconds=100.0,
    )
    assert transition.status == "rejected"
    assert transition.status_reason == "next_mode_adapter_not_registered"


def test_coordinator_executes_typed_mode_context_before_policy_interpretation() -> None:
    class AdapterPolicy:
        mode_name = "mode.adapter"

        def build_context(
            self,
            *,
            request: MissionFlowRequest,
            record: MissionRecordView,
        ) -> ModeCycleContext:
            return ModeCycleContext(
                payload={},
                execution_adapter=lambda: {"value": 7},
            )

        def build_run_envelope(
            self,
            *,
            request: MissionFlowRequest,
            record: MissionRecordView,
            context: ModeCycleContext,
        ) -> MissionModeRunEnvelope:
            del request, record
            return MissionModeRunEnvelope(summary="value:7", opaque_payload={"value": 7})

        def interpret(
            self,
            *,
            request: MissionFlowRequest,
            record: MissionRecordView,
            context: ModeCycleContext,
        ) -> ModeInterpretation:
            value = context.execution_result.get("value") if isinstance(context.execution_result, dict) else None
            return ModeInterpretation(summary=f"value:{value}")

        def recommend(
            self,
            *,
            request: MissionFlowRequest,
            record: MissionRecordView,
            context: ModeCycleContext,
            interpretation: ModeInterpretation,
        ) -> ModeCycleOutcome:
            return ModeCycleOutcome()

    coordinator = MissionCoordinator(
        adapter_registry=MissionModeAdapterRegistry([AdapterPolicy()]), now_fn=lambda: 100.0
    )
    result = coordinator.run_cycle(
        request=MissionFlowRequest(
            mission_id="m-adapter",
            objective="adapter-capability-test",
            initial_mode="mode.adapter",
        )
    )
    assert result.mode_run_envelope is not None
    assert result.mode_run_envelope.summary == "value:7"
    assert result.interpretation.summary == "value:7"
