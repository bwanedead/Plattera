from __future__ import annotations

from dataclasses import FrozenInstanceError
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.runtime.mission.contracts import (
    MissionBlockerPostureSummary,
    MissionFlowRequest,
    MissionModeRunEnvelope,
    MissionRecordView,
    MissionResumabilitySummary,
    MissionVerificationPostureSummary,
    ModeCycleContext,
    ModeCycleOutcome,
    ModeInterpretation,
    ModeTransitionRecommendation,
    TerminalRecommendation,
)
from harness.runtime.mission.mission_coordinator import MissionCoordinator
from harness.runtime.mission.registry import MissionModeAdapterRegistry, ModeAdapterLookupError


class FakeModeAdapter:
    def __init__(
        self,
        *,
        mode_name: str,
        interpretation_summary: str = "interpreted",
        cycle_outcome: ModeCycleOutcome | None = None,
    ) -> None:
        self.mode_name = mode_name
        self._interpretation_summary = interpretation_summary
        self._recommendation = cycle_outcome or ModeCycleOutcome()
        self.context_calls = 0
        self.interpret_calls = 0
        self.recommend_calls = 0

    def build_context(
        self,
        *,
        request: MissionFlowRequest,
        record: MissionRecordView,
    ) -> ModeCycleContext:
        self.context_calls += 1
        return ModeCycleContext(
            payload={"mission_id": request.mission_id, "active_mode": record.active_mode}
        )

    def build_run_envelope(
        self,
        *,
        request: MissionFlowRequest,
        record: MissionRecordView,
        context: ModeCycleContext,
    ) -> MissionModeRunEnvelope:
        del request, record
        return MissionModeRunEnvelope(
            summary=self._interpretation_summary,
            high_signal_artifact_refs=tuple(self._recommendation.high_signal_artifact_refs),
            blocker_posture=self._recommendation.blocker_posture,
            verification_posture=self._recommendation.verification_posture,
            resumability=self._recommendation.resumability,
            terminal=self._recommendation.terminal,
            transition=self._recommendation.transition,
            opaque_payload=dict(context.payload),
        )

    def interpret(
        self,
        *,
        request: MissionFlowRequest,
        record: MissionRecordView,
        context: ModeCycleContext,
    ) -> ModeInterpretation:
        self.interpret_calls += 1
        return ModeInterpretation(summary=self._interpretation_summary, details=context.payload)

    def recommend(
        self,
        *,
        request: MissionFlowRequest,
        record: MissionRecordView,
        context: ModeCycleContext,
        interpretation: ModeInterpretation,
    ) -> ModeCycleOutcome:
        self.recommend_calls += 1
        return self._recommendation


def _request(initial_mode: str = "mode.alpha") -> MissionFlowRequest:
    return MissionFlowRequest(
        mission_id="mission-1",
        objective="generic-mission-flow-smoke",
        initial_mode=initial_mode,
        request_id="request-1",
    )


def test_coordinator_initializes_with_active_mode_and_bounded_record_shape() -> None:
    policy = FakeModeAdapter(mode_name="mode.alpha")
    coordinator = MissionCoordinator(
        adapter_registry=MissionModeAdapterRegistry([policy]),
        now_fn=lambda: 100.0,
    )

    result = coordinator.run_cycle(request=_request())

    assert result.active_mode == "mode.alpha"
    assert result.record.mode_history == ["mode.alpha"]
    assert result.record.mission_id == "mission-1"
    assert result.mode_run_envelope is not None
    assert set(vars(result.record).keys()) == {
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


def test_mode_adapter_lookup_works_and_invokes_hooks() -> None:
    alpha = FakeModeAdapter(mode_name="mode.alpha")
    beta = FakeModeAdapter(mode_name="mode.beta")
    coordinator = MissionCoordinator(
        adapter_registry=MissionModeAdapterRegistry([alpha, beta]),
        now_fn=lambda: 100.0,
    )

    coordinator.run_cycle(request=_request(initial_mode="mode.beta"))

    assert beta.context_calls == 1
    assert beta.interpret_calls == 1
    assert beta.recommend_calls == 1
    assert alpha.context_calls == 0


def test_missing_mode_adapter_fails_clearly() -> None:
    coordinator = MissionCoordinator(
        adapter_registry=MissionModeAdapterRegistry(),
        now_fn=lambda: 100.0,
    )

    with pytest.raises(ModeAdapterLookupError, match="mode_adapter_not_registered:mode.missing"):
        coordinator.run_cycle(request=_request(initial_mode="mode.missing"))


def test_transition_recommendation_is_validated_and_applied_structurally() -> None:
    alpha = FakeModeAdapter(
        mode_name="mode.alpha",
        cycle_outcome=ModeCycleOutcome(
                transition=ModeTransitionRecommendation(
                    next_mode="mode.beta",
                    reason="needs downstream follow_up",
                    handed_forward_artifact_refs=["artifact://handoff/1"],
                    resume_note_for_prior_mode="return after follow_up completes",
                ),
            high_signal_artifact_refs=["artifact://source/1"],
        ),
    )
    beta = FakeModeAdapter(mode_name="mode.beta")
    coordinator = MissionCoordinator(
        adapter_registry=MissionModeAdapterRegistry([alpha, beta]),
        now_fn=lambda: 100.0,
    )

    result = coordinator.run_cycle(request=_request(initial_mode="mode.alpha"))

    assert result.transition is not None
    assert result.transition.status == "applied"
    assert result.transition.prior_mode == "mode.alpha"
    assert result.transition.next_mode == "mode.beta"
    assert result.transition.reason == "needs downstream follow_up"
    assert result.transition.order_anchor == 1
    assert result.record.active_mode == "mode.beta"
    assert result.record.mode_history == ["mode.alpha", "mode.beta"]
    assert result.record.high_signal_artifact_refs == [
        "artifact://handoff/1",
        "artifact://source/1",
    ]


def test_invalid_transition_is_rejected_without_mode_switch() -> None:
    alpha = FakeModeAdapter(
        mode_name="mode.alpha",
        cycle_outcome=ModeCycleOutcome(
            transition=ModeTransitionRecommendation(
                next_mode="mode.unknown",
                reason="handoff needed",
            ),
        ),
    )
    coordinator = MissionCoordinator(
        adapter_registry=MissionModeAdapterRegistry([alpha]),
        now_fn=lambda: 100.0,
    )

    result = coordinator.run_cycle(request=_request(initial_mode="mode.alpha"))

    assert result.transition is not None
    assert result.transition.status == "rejected"
    assert result.transition.status_reason == "next_mode_adapter_not_registered"
    assert result.record.active_mode == "mode.alpha"
    assert result.record.mode_history == ["mode.alpha"]


def test_coordinator_carries_mission_identity_through_cycle() -> None:
    alpha = FakeModeAdapter(
        mode_name="mode.alpha",
        cycle_outcome=ModeCycleOutcome(
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
    coordinator = MissionCoordinator(
        adapter_registry=MissionModeAdapterRegistry([alpha]),
        now_fn=lambda: 100.0,
    )

    started = coordinator.start_mission(request=_request(initial_mode="mode.alpha"))
    result = coordinator.run_cycle(request=_request(initial_mode="mode.alpha"), record=started)

    assert result.record.mission_id == "mission-1"
    assert result.record.request_id == "request-1"
    assert result.record.active_mode == "mode.alpha"
    assert result.record.cycle_index == 1
    assert result.record.blocker_posture_summary.waiting_human is True
    assert result.record.verification_posture_summary.status == "verification_pending"
    assert result.record.resumability_summary.resumable is True


def test_terminal_recommendation_routes_through_shell_handoff() -> None:
    alpha = FakeModeAdapter(
        mode_name="mode.alpha",
        cycle_outcome=ModeCycleOutcome(
            terminal=TerminalRecommendation(
                terminal=True,
                terminal_class="completed",
                reason_code="phase_a_shell_done",
            )
        ),
    )
    coordinator = MissionCoordinator(
        adapter_registry=MissionModeAdapterRegistry([alpha]),
        now_fn=lambda: 100.0,
    )

    result = coordinator.run_cycle(request=_request(initial_mode="mode.alpha"))

    assert result.terminal_handoff is not None
    assert result.terminal_handoff.terminal is True
    assert result.terminal_handoff.terminal_class == "completed"
    assert result.record.mission_status.terminal is True
    assert result.record.mission_status.reason_code == "phase_a_shell_done"


def test_duplicate_mode_adapter_registration_fails() -> None:
    registry = MissionModeAdapterRegistry([FakeModeAdapter(mode_name="mode.alpha")])
    with pytest.raises(ValueError, match="mode_adapter_already_registered:mode.alpha"):
        registry.register(FakeModeAdapter(mode_name="mode.alpha"))


def test_policy_cannot_mutate_coordinator_owned_record_state() -> None:
    class MutatingAdapter(FakeModeAdapter):
        def __init__(self) -> None:
            super().__init__(mode_name="mode.alpha")
            self.mutation_blocked = False
            self.nested_mutation_blocked = False

        def build_context(
            self,
            *,
            request: MissionFlowRequest,
            record: MissionRecordView,
        ) -> ModeCycleContext:
            try:
                record.active_mode = "mode.hijack"
            except FrozenInstanceError:
                self.mutation_blocked = True
            try:
                record.resumability_summary.resume_requirements.append("unauthorized")
            except AttributeError:
                self.nested_mutation_blocked = True
            return ModeCycleContext(payload={"mission_id": request.mission_id})

    policy = MutatingAdapter()
    coordinator = MissionCoordinator(
        adapter_registry=MissionModeAdapterRegistry([policy]),
        now_fn=lambda: 100.0,
    )

    result = coordinator.run_cycle(request=_request(initial_mode="mode.alpha"))

    assert policy.mutation_blocked is True
    assert policy.nested_mutation_blocked is True
    assert result.record.active_mode == "mode.alpha"
