from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from ..mission_state import MissionState, ResolutionState
from ..terminal_taxonomy import TerminalClass

HitlState = Literal["no_prompt", "waiting", "answered_unintegrated", "consumed"]


@dataclass(frozen=True)
class OrchestratorContext:
    session_manager: Any
    session_id: str
    loop_memory: Any
    request_id_prefix: str
    dossier_id: str | None = None
    rationale_strip_snapshot: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class SharedStateProjection:
    mission_state: MissionState
    resolution_state: ResolutionState
    latest_refs: dict[str, Any] = field(default_factory=dict)
    active_item_id: str | None = None


@dataclass(frozen=True)
class ActionPlan:
    action_type: str | None = None
    action_inputs: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    skip_execution: bool = False
    wait_for_human: bool = False
    complete_run: bool = False
    rationale: str | None = None


@dataclass(frozen=True)
class ProgressMetrics:
    previous_state_signature: str | None = None
    current_state_signature: str | None = None
    previous_open_item_count: int | None = None
    current_open_item_count: int | None = None
    pending_refresh: bool = False
    pending_human_input: bool = False
    new_artifact_signal: bool = False
    refresh_baseline_state_signature: str | None = None
    refresh_baseline_open_item_count: int | None = None


@dataclass(frozen=True)
class ProgressDelta:
    made_progress: bool
    reason_code: str
    reset_refresh: bool = False


@dataclass(frozen=True)
class TerminalEvaluation:
    terminal_class: TerminalClass
    reason_code: str


@dataclass(frozen=True)
class KernelLoopResult:
    terminal_class: TerminalClass
    reason_code: str
    iterations: int
    session_id: str
    run_artifact_ref: str | None
    latest_refs: dict[str, Any] = field(default_factory=dict)
    runtime_state: dict[str, Any] = field(default_factory=dict)
    trace_events: list[dict[str, Any]] = field(default_factory=list)


@runtime_checkable
class OrchestrationPack(Protocol):
    def initialize(self, context: OrchestratorContext) -> None: ...

    def sync(self, context: OrchestratorContext) -> SharedStateProjection: ...

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan: ...

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation: ...
