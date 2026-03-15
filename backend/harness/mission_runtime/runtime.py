from __future__ import annotations

from time import time
from typing import Any, Callable

from .contracts import (
    MissionLedger,
    MissionRuntime as MissionRuntimeContract,
    MissionRuntimeCycleResult,
    MissionRuntimeRequest,
    MissionStatusSummary,
    MissionTraceSegment,
    ModeRecommendation,
    ModeTransition,
    ModeTransitionRecommendation,
    ModeCycleContext,
    TerminalRecommendation,
    build_mission_ledger_view,
)
from .capabilities.transition import evaluate_mode_transition
from .observability import build_mission_observation_from_runtime
from .registry import ModePolicyLookupError, ModePolicyRegistry


class MissionRuntimeError(RuntimeError):
    """Raised when mission runtime shell invariants are violated."""


class MissionRuntime(MissionRuntimeContract):
    """Phase A mission runtime shell (contract-aligned, family-agnostic)."""

    def __init__(
        self,
        *,
        policy_registry: ModePolicyRegistry,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self._policy_registry = policy_registry
        self._now_fn = now_fn or time

    def start_mission(self, *, request: MissionRuntimeRequest) -> MissionLedger:
        self._policy_registry.require(request.initial_mode)
        started_at = self._now_fn()
        return MissionLedger(
            mission_id=request.mission_id,
            mission_objective=request.objective,
            request_id=request.request_id,
            active_mode=request.initial_mode,
            mode_history=[request.initial_mode],
            created_at_epoch_seconds=started_at,
            updated_at_epoch_seconds=started_at,
        )

    def run_cycle(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedger | None = None,
    ) -> MissionRuntimeCycleResult:
        active_ledger = ledger or self.start_mission(request=request)
        if active_ledger.mission_id != request.mission_id:
            raise MissionRuntimeError("mission_id_mismatch")

        active_mode = active_ledger.active_mode
        policy = self._policy_registry.require(active_mode)
        policy_ledger_view = build_mission_ledger_view(active_ledger)
        context = policy.build_context(request=request, ledger=policy_ledger_view)
        context = _execute_mode_context(context)
        interpretation = policy.interpret(
            request=request,
            ledger=policy_ledger_view,
            context=context,
        )
        recommendation = policy.recommend(
            request=request,
            ledger=policy_ledger_view,
            context=context,
            interpretation=interpretation,
        )

        transition = self._apply_transition_if_recommended(
            ledger=active_ledger,
            recommendation=recommendation,
        )
        self._apply_recommendation_summaries(ledger=active_ledger, recommendation=recommendation)
        self._apply_terminal_handoff(ledger=active_ledger, terminal=recommendation.terminal, transition=transition)
        self._refresh_timestamps(ledger=active_ledger)
        trace_segment = MissionTraceSegment(
            segment_index=active_ledger.cycle_index,
            mode=active_mode,
            summary=interpretation.summary,
            timestamp_epoch_seconds=active_ledger.updated_at_epoch_seconds,
        )
        return MissionRuntimeCycleResult(
            mission_id=active_ledger.mission_id,
            active_mode=active_ledger.active_mode,
            ledger=active_ledger,
            interpretation=interpretation,
            recommendation=recommendation,
            transition=transition,
            terminal_handoff=recommendation.terminal,
            trace_segment=trace_segment,
        )

    def validate_transition(
        self,
        *,
        ledger: MissionLedger,
        recommendation: ModeTransitionRecommendation,
    ) -> ModeTransition:
        return evaluate_mode_transition(
            ledger=ledger,
            recommendation=recommendation,
            mode_exists=lambda mode_name: self._policy_registry.resolve(mode_name) is not None,
            now_epoch_seconds=self._now_fn(),
        )

    def _apply_transition_if_recommended(
        self,
        *,
        ledger: MissionLedger,
        recommendation: ModeRecommendation,
    ) -> ModeTransition | None:
        if recommendation.transition is None:
            return None
        transition = self.validate_transition(
            ledger=ledger,
            recommendation=recommendation.transition,
        )
        ledger.transition_history.append(transition)
        if transition.status == "applied":
            ledger.active_mode = transition.next_mode
            if not ledger.mode_history or ledger.mode_history[-1] != transition.next_mode:
                ledger.mode_history.append(transition.next_mode)
            ledger.high_signal_artifact_refs = _merge_refs(
                existing=ledger.high_signal_artifact_refs,
                incoming=transition.handed_forward_artifact_refs,
            )
        return transition

    def _apply_recommendation_summaries(
        self,
        *,
        ledger: MissionLedger,
        recommendation: ModeRecommendation,
    ) -> None:
        ledger.high_signal_artifact_refs = _merge_refs(
            existing=ledger.high_signal_artifact_refs,
            incoming=recommendation.high_signal_artifact_refs,
        )
        if recommendation.blocker_posture is not None:
            ledger.blocker_posture_summary = recommendation.blocker_posture
        if recommendation.verification_posture is not None:
            ledger.verification_posture_summary = recommendation.verification_posture
        if recommendation.resumability is not None:
            ledger.resumability_summary = recommendation.resumability

    def _apply_terminal_handoff(
        self,
        *,
        ledger: MissionLedger,
        terminal: TerminalRecommendation | None,
        transition: ModeTransition | None = None,
    ) -> None:
        if terminal is None:
            return
        if transition is not None and transition.status == "applied":
            ledger.mission_status = MissionStatusSummary(
                terminal=False,
                terminal_class=None,
                reason_code=terminal.reason_code,
            )
            return
        ledger.mission_status = MissionStatusSummary(
            terminal=terminal.terminal,
            terminal_class=terminal.terminal_class,
            reason_code=terminal.reason_code,
        )

    def _refresh_timestamps(self, *, ledger: MissionLedger) -> None:
        ledger.cycle_index += 1
        ledger.updated_at_epoch_seconds = self._now_fn()


def _merge_refs(*, existing: list[str], incoming: list[str]) -> list[str]:
    merged: list[str] = []
    for value in [*existing, *incoming]:
        ref = value.strip()
        if not ref or ref in merged:
            continue
        merged.append(ref)
    return merged


def _execute_mode_context(context: ModeCycleContext) -> ModeCycleContext:
    if context.execution_adapter is not None and context.execution_result is None:
        context.execution_result = context.execution_adapter()
    return context


def build_mission_observability_payload(
    *,
    request: MissionRuntimeRequest,
    ledger: MissionLedger,
    cycle_results: list[MissionRuntimeCycleResult],
) -> dict[str, Any]:
    """Build bounded mission-runtime observability payload for tracing/run-state/review."""
    return build_mission_observation_from_runtime(
        request=request,
        ledger=ledger,
        cycle_results=cycle_results,
    ).to_payload()
