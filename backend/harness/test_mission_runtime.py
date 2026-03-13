from __future__ import annotations

from dataclasses import FrozenInstanceError
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.mission_runtime.contracts import (
    MissionBlockerPostureSummary,
    MissionLedgerView,
    MissionResumabilitySummary,
    MissionRuntimeRequest,
    MissionVerificationPostureSummary,
    ModeCycleContext,
    ModeInterpretation,
    ModeRecommendation,
    ModeTransitionRecommendation,
    TerminalRecommendation,
)
from harness.mission_runtime.registry import ModePolicyLookupError, ModePolicyRegistry
from harness.mission_runtime.runtime import MissionRuntime


class FakeModePolicy:
    def __init__(
        self,
        *,
        mode_name: str,
        interpretation_summary: str = "interpreted",
        recommendation: ModeRecommendation | None = None,
    ) -> None:
        self.mode_name = mode_name
        self._interpretation_summary = interpretation_summary
        self._recommendation = recommendation or ModeRecommendation(next_step_hint="continue")
        self.context_calls = 0
        self.interpret_calls = 0
        self.recommend_calls = 0

    def build_context(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
    ) -> ModeCycleContext:
        self.context_calls += 1
        return ModeCycleContext(
            payload={"mission_id": request.mission_id, "active_mode": ledger.active_mode}
        )

    def interpret(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
    ) -> ModeInterpretation:
        self.interpret_calls += 1
        return ModeInterpretation(summary=self._interpretation_summary, details=context.payload)

    def recommend(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
        interpretation: ModeInterpretation,
    ) -> ModeRecommendation:
        self.recommend_calls += 1
        return self._recommendation


def _request(initial_mode: str = "mode.alpha") -> MissionRuntimeRequest:
    return MissionRuntimeRequest(
        mission_id="mission-1",
        objective="phase-a-shell-smoke",
        initial_mode=initial_mode,
        request_id="request-1",
    )


def test_runtime_initializes_with_active_mode_and_bounded_ledger_shape() -> None:
    policy = FakeModePolicy(mode_name="mode.alpha")
    runtime = MissionRuntime(
        policy_registry=ModePolicyRegistry([policy]),
        now_fn=lambda: 100.0,
    )

    result = runtime.run_cycle(request=_request())

    assert result.active_mode == "mode.alpha"
    assert result.ledger.mode_history == ["mode.alpha"]
    assert result.ledger.mission_id == "mission-1"
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


def test_mode_policy_lookup_works_and_invokes_hooks() -> None:
    alpha = FakeModePolicy(mode_name="mode.alpha")
    beta = FakeModePolicy(mode_name="mode.beta")
    runtime = MissionRuntime(
        policy_registry=ModePolicyRegistry([alpha, beta]),
        now_fn=lambda: 100.0,
    )

    runtime.run_cycle(request=_request(initial_mode="mode.beta"))

    assert beta.context_calls == 1
    assert beta.interpret_calls == 1
    assert beta.recommend_calls == 1
    assert alpha.context_calls == 0


def test_missing_mode_policy_fails_clearly() -> None:
    runtime = MissionRuntime(
        policy_registry=ModePolicyRegistry(),
        now_fn=lambda: 100.0,
    )

    with pytest.raises(ModePolicyLookupError, match="mode_policy_not_registered:mode.missing"):
        runtime.run_cycle(request=_request(initial_mode="mode.missing"))


def test_transition_recommendation_is_validated_and_applied_structurally() -> None:
    alpha = FakeModePolicy(
        mode_name="mode.alpha",
        recommendation=ModeRecommendation(
            transition=ModeTransitionRecommendation(
                next_mode="mode.beta",
                reason="needs transcript repair",
                handed_forward_artifact_refs=["artifact://handoff/1"],
                expected_next_work="resolve mismatch spans",
                resume_note_for_prior_mode="return with repaired spans",
            ),
            high_signal_artifact_refs=["artifact://source/1"],
        ),
    )
    beta = FakeModePolicy(mode_name="mode.beta")
    runtime = MissionRuntime(
        policy_registry=ModePolicyRegistry([alpha, beta]),
        now_fn=lambda: 100.0,
    )

    result = runtime.run_cycle(request=_request(initial_mode="mode.alpha"))

    assert result.transition is not None
    assert result.transition.status == "applied"
    assert result.transition.prior_mode == "mode.alpha"
    assert result.transition.next_mode == "mode.beta"
    assert result.transition.reason == "needs transcript repair"
    assert result.transition.order_anchor == 1
    assert result.ledger.active_mode == "mode.beta"
    assert result.ledger.mode_history == ["mode.alpha", "mode.beta"]
    assert result.ledger.high_signal_artifact_refs == [
        "artifact://handoff/1",
        "artifact://source/1",
    ]


def test_invalid_transition_is_rejected_without_mode_switch() -> None:
    alpha = FakeModePolicy(
        mode_name="mode.alpha",
        recommendation=ModeRecommendation(
            transition=ModeTransitionRecommendation(
                next_mode="mode.unknown",
                reason="handoff needed",
            ),
        ),
    )
    runtime = MissionRuntime(
        policy_registry=ModePolicyRegistry([alpha]),
        now_fn=lambda: 100.0,
    )

    result = runtime.run_cycle(request=_request(initial_mode="mode.alpha"))

    assert result.transition is not None
    assert result.transition.status == "rejected"
    assert result.transition.status_reason == "next_mode_policy_not_registered"
    assert result.ledger.active_mode == "mode.alpha"
    assert result.ledger.mode_history == ["mode.alpha"]


def test_runtime_carries_mission_identity_through_cycle() -> None:
    alpha = FakeModePolicy(
        mode_name="mode.alpha",
        recommendation=ModeRecommendation(
            next_step_hint="continue",
            blocker_posture=MissionBlockerPostureSummary(waiting_human=True, open_blocker_count=2),
            verification_posture=MissionVerificationPostureSummary(
                status="verification_pending",
                last_verification_kind="artifact_check",
            ),
            resumability=MissionResumabilitySummary(
                resumable=True,
                resume_reason="waiting_human",
                resume_requirements=["human_response"],
            ),
        ),
    )
    runtime = MissionRuntime(
        policy_registry=ModePolicyRegistry([alpha]),
        now_fn=lambda: 100.0,
    )

    started = runtime.start_mission(request=_request(initial_mode="mode.alpha"))
    result = runtime.run_cycle(request=_request(initial_mode="mode.alpha"), ledger=started)

    assert result.ledger.mission_id == "mission-1"
    assert result.ledger.request_id == "request-1"
    assert result.ledger.active_mode == "mode.alpha"
    assert result.ledger.cycle_index == 1
    assert result.ledger.blocker_posture_summary.waiting_human is True
    assert result.ledger.verification_posture_summary.status == "verification_pending"
    assert result.ledger.resumability_summary.resumable is True


def test_terminal_recommendation_routes_through_shell_handoff() -> None:
    alpha = FakeModePolicy(
        mode_name="mode.alpha",
        recommendation=ModeRecommendation(
            terminal=TerminalRecommendation(
                terminal=True,
                terminal_class="completed",
                reason_code="phase_a_shell_done",
            )
        ),
    )
    runtime = MissionRuntime(
        policy_registry=ModePolicyRegistry([alpha]),
        now_fn=lambda: 100.0,
    )

    result = runtime.run_cycle(request=_request(initial_mode="mode.alpha"))

    assert result.terminal_handoff is not None
    assert result.terminal_handoff.terminal is True
    assert result.terminal_handoff.terminal_class == "completed"
    assert result.ledger.mission_status.terminal is True
    assert result.ledger.mission_status.reason_code == "phase_a_shell_done"


def test_duplicate_mode_policy_registration_fails() -> None:
    registry = ModePolicyRegistry([FakeModePolicy(mode_name="mode.alpha")])
    with pytest.raises(ValueError, match="mode_policy_already_registered:mode.alpha"):
        registry.register(FakeModePolicy(mode_name="mode.alpha"))


def test_policy_cannot_mutate_runtime_owned_ledger_state() -> None:
    class MutatingPolicy(FakeModePolicy):
        def __init__(self) -> None:
            super().__init__(mode_name="mode.alpha")
            self.mutation_blocked = False
            self.nested_mutation_blocked = False

        def build_context(
            self,
            *,
            request: MissionRuntimeRequest,
            ledger: MissionLedgerView,
        ) -> ModeCycleContext:
            try:
                ledger.active_mode = "mode.hijack"
            except FrozenInstanceError:
                self.mutation_blocked = True
            try:
                ledger.resumability_summary.resume_requirements.append("unauthorized")
            except AttributeError:
                self.nested_mutation_blocked = True
            return ModeCycleContext(payload={"mission_id": request.mission_id})

    policy = MutatingPolicy()
    runtime = MissionRuntime(
        policy_registry=ModePolicyRegistry([policy]),
        now_fn=lambda: 100.0,
    )

    result = runtime.run_cycle(request=_request(initial_mode="mode.alpha"))

    assert policy.mutation_blocked is True
    assert policy.nested_mutation_blocked is True
    assert result.ledger.active_mode == "mode.alpha"
