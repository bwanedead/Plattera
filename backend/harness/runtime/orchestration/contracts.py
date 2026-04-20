from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from ...execution.session import ExecutionSessionManager

from ...mission_state import MissionState, ResolutionState
from ...terminal_taxonomy import TerminalClass
from ..memory import LoopMemoryState

if TYPE_CHECKING:
    from .lifecycle import PromptEventObserver, RawLlmIoObserver


@dataclass(frozen=True)
class OrchestratorContext:
    session_manager: ExecutionSessionManager
    session_id: str
    loop_memory: LoopMemoryState
    request_id_prefix: str
    opaque_run_context: dict[str, Any] = field(default_factory=dict)
    prompt_event_observer: PromptEventObserver | None = None
    raw_llm_io_observer: RawLlmIoObserver | None = None


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
    # Transport-only dispatch dedupe key. External seam may omit it; host fills it before execution.
    idempotency_key: str = ""
    skip_execution: bool = False
    wait_for_human: bool = False
    complete_run: bool = False
    # Generic HITL transport payload (LLM-authored). Blocking is ``wait_for_human``, not fields inside this dict.
    hitl_request: dict[str, Any] | None = None
    # Mechanical acknowledgment: drop matching rows from ``answered_hitl_responses`` (LLM declares integration).
    hitl_consumed_prompt_ids: tuple[str, ...] = ()
    # Required on every LLM-authored choose-action turn: short decision note carrying
    # why-this-move and expected-gain. Enforced by ``action_plan_parser``; the parser
    # rejects plans whose rationale is missing or whitespace-only. Host-synthesized
    # plans (non-LLM paths) may omit it, hence the optional field type.
    rationale: str | None = None
    state_patch: dict[str, Any] | None = None
    # LLM-authored continuity (not work-state mutation). Optional: omission means no continuity delta this turn.
    # When present, must be a non-empty object. Use when the turn produced observations, decisions, open threads,
    # or next-step understanding worth carrying forward.
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
    # Optional long-form explanation for observers/audit. ``reason_code`` stays short and bounded.
    terminal_summary: str | None = None


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
    # Optional long-form explanation for the terminal outcome. Kept separate from the short code.
    terminal_summary: str | None = None

    @property
    def opaque_runtime_payload(self) -> dict[str, Any]:
        """Opaque loop-local state blob (same backing as ``runtime_state``; generic naming)."""
        return self.runtime_state


@runtime_checkable
class OrchestrationAdapter(Protocol):
    """Semantic orchestration contract only; mechanical lifecycle lives in ``lifecycle.py``."""

    def initialize(self, context: OrchestratorContext) -> None: ...

    def sync(self, context: OrchestratorContext) -> SharedStateProjection: ...

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan: ...

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation: ...
