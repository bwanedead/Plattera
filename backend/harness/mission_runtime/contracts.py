from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Literal, runtime_checkable

from ..terminal_taxonomy import TerminalClass

TransitionStatus = Literal["applied", "rejected"]


@dataclass(frozen=True)
class MissionResumabilitySummary:
    resumable: bool = False
    resume_reason: str | None = None
    resume_requirements: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MissionStatusSummary:
    terminal: bool = False
    terminal_class: TerminalClass | None = None
    reason_code: str | None = None


@dataclass(frozen=True)
class MissionBlockerPostureSummary:
    waiting_human: bool = False
    open_blocker_count: int | None = None


@dataclass(frozen=True)
class MissionVerificationPostureSummary:
    status: str | None = None
    last_verification_kind: str | None = None


@dataclass(frozen=True)
class ModeTransition:
    prior_mode: str
    next_mode: str
    reason: str
    handed_forward_artifact_refs: list[str] = field(default_factory=list)
    expected_next_work: str | None = None
    resume_note_for_prior_mode: str | None = None
    status: TransitionStatus = "rejected"
    status_reason: str | None = None
    order_anchor: int = 0
    timestamp_epoch_seconds: float = 0.0


@dataclass(frozen=True)
class ModeTransitionRecommendation:
    next_mode: str
    reason: str
    handed_forward_artifact_refs: list[str] = field(default_factory=list)
    expected_next_work: str | None = None
    resume_note_for_prior_mode: str | None = None


@dataclass(frozen=True)
class TerminalRecommendation:
    terminal: bool
    terminal_class: TerminalClass | None = None
    reason_code: str | None = None


@dataclass(frozen=True)
class ModeInterpretation:
    summary: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class ModeCycleContext:
    payload: Mapping[str, Any] = field(default_factory=dict)
    execution_adapter: Callable[[], Any] | None = None
    execution_result: Any | None = None
    run_envelope: "MissionModeRunEnvelope" | None = None


@dataclass(frozen=True)
class ModeRecommendation:
    next_step_hint: str | None = None
    transition: ModeTransitionRecommendation | None = None
    terminal: TerminalRecommendation | None = None
    high_signal_artifact_refs: list[str] = field(default_factory=list)
    blocker_posture: MissionBlockerPostureSummary | None = None
    verification_posture: MissionVerificationPostureSummary | None = None
    resumability: MissionResumabilitySummary | None = None


@dataclass(frozen=True)
class MissionModeRunEnvelope:
    """Generic mission-mode run summary consumed at the runtime seam."""

    summary: str
    high_signal_artifact_refs: tuple[str, ...] = field(default_factory=tuple)
    blocker_posture: MissionBlockerPostureSummary | None = None
    verification_posture: MissionVerificationPostureSummary | None = None
    resumability: MissionResumabilitySummary | None = None
    terminal: TerminalRecommendation | None = None
    transition: ModeTransitionRecommendation | None = None
    domain_payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MissionRuntimeRequest:
    mission_id: str
    objective: str
    initial_mode: str
    request_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class MissionLedger:
    mission_id: str
    mission_objective: str
    request_id: str | None
    active_mode: str
    mode_history: list[str] = field(default_factory=list)
    transition_history: list[ModeTransition] = field(default_factory=list)
    high_signal_artifact_refs: list[str] = field(default_factory=list)
    resumability_summary: MissionResumabilitySummary = field(default_factory=MissionResumabilitySummary)
    mission_status: MissionStatusSummary = field(default_factory=MissionStatusSummary)
    blocker_posture_summary: MissionBlockerPostureSummary = field(default_factory=MissionBlockerPostureSummary)
    verification_posture_summary: MissionVerificationPostureSummary = field(default_factory=MissionVerificationPostureSummary)
    created_at_epoch_seconds: float = 0.0
    updated_at_epoch_seconds: float = 0.0
    cycle_index: int = 0


@dataclass(frozen=True)
class MissionLedgerView:
    mission_id: str
    mission_objective: str
    request_id: str | None
    active_mode: str
    mode_history: tuple[str, ...]
    transition_history: tuple["ModeTransitionView", ...]
    high_signal_artifact_refs: tuple[str, ...]
    resumability_summary: "MissionResumabilitySummaryView"
    mission_status: MissionStatusSummary
    blocker_posture_summary: MissionBlockerPostureSummary
    verification_posture_summary: MissionVerificationPostureSummary
    created_at_epoch_seconds: float
    updated_at_epoch_seconds: float
    cycle_index: int


@dataclass(frozen=True)
class MissionResumabilitySummaryView:
    resumable: bool
    resume_reason: str | None
    resume_requirements: tuple[str, ...]


@dataclass(frozen=True)
class ModeTransitionView:
    prior_mode: str
    next_mode: str
    reason: str
    handed_forward_artifact_refs: tuple[str, ...]
    expected_next_work: str | None
    resume_note_for_prior_mode: str | None
    status: TransitionStatus
    status_reason: str | None
    order_anchor: int
    timestamp_epoch_seconds: float


def build_mission_ledger_view(ledger: MissionLedger) -> MissionLedgerView:
    return MissionLedgerView(
        mission_id=ledger.mission_id,
        mission_objective=ledger.mission_objective,
        request_id=ledger.request_id,
        active_mode=ledger.active_mode,
        mode_history=tuple(ledger.mode_history),
        transition_history=tuple(_build_transition_view(item) for item in ledger.transition_history),
        high_signal_artifact_refs=tuple(ledger.high_signal_artifact_refs),
        resumability_summary=MissionResumabilitySummaryView(
            resumable=ledger.resumability_summary.resumable,
            resume_reason=ledger.resumability_summary.resume_reason,
            resume_requirements=tuple(ledger.resumability_summary.resume_requirements),
        ),
        mission_status=ledger.mission_status,
        blocker_posture_summary=ledger.blocker_posture_summary,
        verification_posture_summary=ledger.verification_posture_summary,
        created_at_epoch_seconds=ledger.created_at_epoch_seconds,
        updated_at_epoch_seconds=ledger.updated_at_epoch_seconds,
        cycle_index=ledger.cycle_index,
    )


def _build_transition_view(item: ModeTransition) -> ModeTransitionView:
    return ModeTransitionView(
        prior_mode=item.prior_mode,
        next_mode=item.next_mode,
        reason=item.reason,
        handed_forward_artifact_refs=tuple(item.handed_forward_artifact_refs),
        expected_next_work=item.expected_next_work,
        resume_note_for_prior_mode=item.resume_note_for_prior_mode,
        status=item.status,
        status_reason=item.status_reason,
        order_anchor=item.order_anchor,
        timestamp_epoch_seconds=item.timestamp_epoch_seconds,
    )


@dataclass(frozen=True)
class MissionTraceSegment:
    segment_index: int
    mode: str
    summary: str
    timestamp_epoch_seconds: float


@dataclass(frozen=True)
class MissionRuntimeCycleResult:
    mission_id: str
    active_mode: str
    ledger: MissionLedger
    interpretation: ModeInterpretation
    recommendation: ModeRecommendation
    mode_run_envelope: MissionModeRunEnvelope | None = None
    transition: ModeTransition | None = None
    terminal_handoff: TerminalRecommendation | None = None
    trace_segment: MissionTraceSegment | None = None


@runtime_checkable
class MissionModeAdapter(Protocol):
    mode_name: str

    def build_context(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
    ) -> ModeCycleContext: ...

    def build_run_envelope(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
    ) -> MissionModeRunEnvelope: ...

    def interpret(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
    ) -> ModeInterpretation: ...

    def recommend(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
        interpretation: ModeInterpretation,
    ) -> ModeRecommendation: ...


@runtime_checkable
class MissionRuntime(Protocol):
    def start_mission(self, *, request: MissionRuntimeRequest) -> MissionLedger: ...

    def run_cycle(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedger | None = None,
    ) -> MissionRuntimeCycleResult: ...
