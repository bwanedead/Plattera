from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.mission_runtime.capabilities.transition import evaluate_mode_transition
from harness.mission_runtime.contracts import (
    MissionLedger,
    MissionLedgerView,
    MissionRuntimeRequest,
    ModeCycleContext,
    ModeInterpretation,
    ModeRecommendation,
    ModeTransitionRecommendation,
)
from harness.mission_runtime.registry import ModePolicyRegistry
from harness.mission_runtime.runtime import MissionRuntime


def test_transition_capability_rejects_unknown_mode() -> None:
    ledger = MissionLedger(
        mission_id="m1",
        mission_objective="o1",
        request_id="r1",
        active_mode="mode.alpha",
        mode_history=["mode.alpha"],
    )
    transition = evaluate_mode_transition(
        ledger=ledger,
        recommendation=ModeTransitionRecommendation(next_mode="mode.unknown", reason="switch"),
        mode_exists=lambda _mode: False,
        now_epoch_seconds=100.0,
    )
    assert transition.status == "rejected"
    assert transition.status_reason == "next_mode_policy_not_registered"


def test_runtime_executes_typed_mode_context_before_policy_interpretation() -> None:
    class AdapterPolicy:
        mode_name = "mode.adapter"

        def build_context(
            self,
            *,
            request: MissionRuntimeRequest,
            ledger: MissionLedgerView,
        ) -> ModeCycleContext:
            return ModeCycleContext(
                payload={},
                execution_adapter=lambda: {"value": 7},
            )

        def interpret(
            self,
            *,
            request: MissionRuntimeRequest,
            ledger: MissionLedgerView,
            context: ModeCycleContext,
        ) -> ModeInterpretation:
            value = context.execution_result.get("value") if isinstance(context.execution_result, dict) else None
            return ModeInterpretation(summary=f"value:{value}")

        def recommend(
            self,
            *,
            request: MissionRuntimeRequest,
            ledger: MissionLedgerView,
            context: ModeCycleContext,
            interpretation: ModeInterpretation,
        ) -> ModeRecommendation:
            return ModeRecommendation(next_step_hint="continue")

    runtime = MissionRuntime(policy_registry=ModePolicyRegistry([AdapterPolicy()]), now_fn=lambda: 100.0)
    result = runtime.run_cycle(
        request=MissionRuntimeRequest(
            mission_id="m-adapter",
            objective="adapter-capability-test",
            initial_mode="mode.adapter",
        )
    )
    assert result.interpretation.summary == "value:7"
