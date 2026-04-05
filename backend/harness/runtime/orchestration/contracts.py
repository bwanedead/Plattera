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
    """Kernel action; optional ``state_patch`` is model-authored generic work-state (see ``state_patch_apply``)."""

    action_type: str | None = None
    action_inputs: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    skip_execution: bool = False
    wait_for_human: bool = False
    complete_run: bool = False
    # Generic HITL transport payload (LLM-authored). Blocking is ``wait_for_human``, not fields inside this dict.
    hitl_request: dict[str, Any] | None = None
    # Mechanical acknowledgment: drop matching rows from ``answered_hitl_responses`` (LLM declares integration).
    hitl_consumed_prompt_ids: tuple[str, ...] = ()
    rationale: str | None = None
    state_patch: dict[str, Any] | None = None
    # LLM-authored continuity (not work-state mutation). ``LlmTurnOrchestrationAdapter`` requires a non-empty object.
    continuity_journal_entry: dict[str, Any] | None = None
    operator_progress_message: str | None = None


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
    # Mechanical persistence blob for process restart (``kernel_resume.v1``); no semantic authoring.
    kernel_resume_snapshot: dict[str, Any] | None = None

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
