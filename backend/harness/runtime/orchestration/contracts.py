from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ...execution.session import ExecutionSessionManager

from ...mission_state import MissionState, ResolutionState
from ...terminal_taxonomy import TerminalClass
from ..memory import LoopMemoryState


@dataclass(frozen=True)
class OrchestratorContext:
    session_manager: ExecutionSessionManager
    session_id: str
    loop_memory: LoopMemoryState
    request_id_prefix: str
    opaque_run_context: dict[str, Any] = field(default_factory=dict)


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

    @property
    def opaque_runtime_payload(self) -> dict[str, Any]:
        """Opaque loop-local state blob (same backing as ``runtime_state``; generic naming)."""
        return self.runtime_state


@runtime_checkable
class OrchestrationAdapter(Protocol):
    def initialize(self, context: OrchestratorContext) -> None: ...

    def sync(self, context: OrchestratorContext) -> SharedStateProjection: ...

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan: ...

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation: ...
