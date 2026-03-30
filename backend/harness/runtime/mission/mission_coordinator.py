from __future__ import annotations

from time import time
from typing import Any, Callable

from .capabilities.transition import evaluate_mode_transition
from .contracts import (
    MissionFlowCoordinator,
    MissionFlowCycleResult,
    MissionFlowRequest,
    MissionModeAdapter,
    MissionModeRunEnvelope,
    MissionRecord,
    MissionStatusSummary,
    MissionTraceSegment,
    ModeCycleContext,
    ModeCycleOutcome,
    ModeTransition,
    ModeTransitionRecommendation,
    TerminalRecommendation,
    build_mission_record_view,
)
from .observability import build_mission_observation_from_runtime
from .registry import MissionModeAdapterRegistry


class MissionFlowCoordinatorError(RuntimeError):
    """Raised when mission flow coordinator invariants are violated."""


class MissionCoordinator(MissionFlowCoordinator):
    """Generic mission-flow shell: mode adapters, transitions, coordination record."""

    def __init__(
        self,
        *,
        adapter_registry: MissionModeAdapterRegistry,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self._adapter_registry = adapter_registry
        self._now_fn = now_fn or time

    def start_mission(self, *, request: MissionFlowRequest) -> MissionRecord:
        self._adapter_registry.require(request.initial_mode)
        started_at = self._now_fn()
        return MissionRecord(
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
        request: MissionFlowRequest,
        record: MissionRecord | None = None,
    ) -> MissionFlowCycleResult:
        active_record = record or self.start_mission(request=request)
        if active_record.mission_id != request.mission_id:
            raise MissionFlowCoordinatorError("mission_id_mismatch")

        active_mode = active_record.active_mode
        adapter = self._adapter_registry.require(active_mode)
        record_view = build_mission_record_view(active_record)
        context = adapter.build_context(request=request, record=record_view)
        context = _execute_mode_context(context)
        run_envelope = _build_mode_run_envelope(
            adapter=adapter,
            request=request,
            record=record_view,
            context=context,
        )
        context.run_envelope = run_envelope
        interpretation = adapter.interpret(
            request=request,
            record=record_view,
            context=context,
        )
        cycle_outcome = adapter.recommend(
            request=request,
            record=record_view,
            context=context,
            interpretation=interpretation,
        )

        transition = self._apply_transition_if_recommended(
            record=active_record,
            cycle_outcome=cycle_outcome,
        )
        self._apply_cycle_outcome_summaries(record=active_record, cycle_outcome=cycle_outcome)
        self._apply_terminal_handoff(
            record=active_record,
            terminal=cycle_outcome.terminal,
            transition=transition,
        )
        self._refresh_timestamps(record=active_record)
        trace_segment = MissionTraceSegment(
            segment_index=active_record.cycle_index,
            mode=active_mode,
            summary=interpretation.summary,
            timestamp_epoch_seconds=active_record.updated_at_epoch_seconds,
        )
        return MissionFlowCycleResult(
            mission_id=active_record.mission_id,
            active_mode=active_record.active_mode,
            record=active_record,
            interpretation=interpretation,
            cycle_outcome=cycle_outcome,
            mode_run_envelope=run_envelope,
            transition=transition,
            terminal_handoff=cycle_outcome.terminal,
            trace_segment=trace_segment,
        )

    def validate_transition(
        self,
        *,
        record: MissionRecord,
        recommendation: ModeTransitionRecommendation,
    ) -> ModeTransition:
        return evaluate_mode_transition(
            record=record,
            recommendation=recommendation,
            mode_exists=lambda mode_name: self._adapter_registry.resolve(mode_name) is not None,
            now_epoch_seconds=self._now_fn(),
        )

    def _apply_transition_if_recommended(
        self,
        *,
        record: MissionRecord,
        cycle_outcome: ModeCycleOutcome,
    ) -> ModeTransition | None:
        if cycle_outcome.transition is None:
            return None
        transition = self.validate_transition(
            record=record,
            recommendation=cycle_outcome.transition,
        )
        record.transition_history.append(transition)
        if transition.status == "applied":
            record.active_mode = transition.next_mode
            if not record.mode_history or record.mode_history[-1] != transition.next_mode:
                record.mode_history.append(transition.next_mode)
            record.high_signal_artifact_refs = _merge_refs(
                existing=record.high_signal_artifact_refs,
                incoming=transition.handed_forward_artifact_refs,
            )
        return transition

    def _apply_cycle_outcome_summaries(
        self,
        *,
        record: MissionRecord,
        cycle_outcome: ModeCycleOutcome,
    ) -> None:
        record.high_signal_artifact_refs = _merge_refs(
            existing=record.high_signal_artifact_refs,
            incoming=cycle_outcome.high_signal_artifact_refs,
        )
        if cycle_outcome.blocker_posture is not None:
            record.blocker_posture_summary = cycle_outcome.blocker_posture
        if cycle_outcome.verification_posture is not None:
            record.verification_posture_summary = cycle_outcome.verification_posture
        if cycle_outcome.resumability is not None:
            record.resumability_summary = cycle_outcome.resumability

    def _apply_terminal_handoff(
        self,
        *,
        record: MissionRecord,
        terminal: TerminalRecommendation | None,
        transition: ModeTransition | None = None,
    ) -> None:
        if terminal is None:
            return
        if transition is not None and transition.status == "applied":
            record.mission_status = MissionStatusSummary(
                terminal=False,
                terminal_class=None,
                reason_code=terminal.reason_code,
            )
            return
        record.mission_status = MissionStatusSummary(
            terminal=terminal.terminal,
            terminal_class=terminal.terminal_class,
            reason_code=terminal.reason_code,
        )

    def _refresh_timestamps(self, *, record: MissionRecord) -> None:
        record.cycle_index += 1
        record.updated_at_epoch_seconds = self._now_fn()


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


def _build_mode_run_envelope(
    *,
    adapter: MissionModeAdapter,
    request: MissionFlowRequest,
    record: Any,
    context: ModeCycleContext,
) -> MissionModeRunEnvelope:
    envelope = adapter.build_run_envelope(request=request, record=record, context=context)
    if not isinstance(envelope, MissionModeRunEnvelope):
        raise MissionFlowCoordinatorError("mode_adapter_invalid_run_envelope")
    return envelope


def build_mission_observability_payload(
    *,
    request: MissionFlowRequest,
    record: MissionRecord,
    cycle_results: list[MissionFlowCycleResult],
) -> dict[str, Any]:
    """Build bounded mission-flow observability payload for tracing/run-state/review."""
    return build_mission_observation_from_runtime(
        request=request,
        record=record,
        cycle_results=cycle_results,
    ).to_payload()
