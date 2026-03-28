from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, TYPE_CHECKING

from ..mission_state import MissionState, ResolutionState
from ..terminal_taxonomy import TerminalClass

if TYPE_CHECKING:
    from agent_kernel.session import KernelSessionManager
    from .loop_memory import LoopMemoryState

# HitlState is the shared HITL lifecycle state machine.
# Transitions are owned exclusively by the orchestration kernel.
# Domain packs must not write HitlState directly.
HitlState = str  # Literal: "no_prompt" | "waiting" | "answered_unintegrated" | "consumed"


@dataclass(frozen=True)
class SharedStateProjection:
    """Domain pack's hook 3 output.

    The shared kernel now projects native `mission_state` / `resolution_state` containers.
    `resolution_state.active_item_id` is the authored active-item signal for this iteration;
    the kernel may preserve prior continuity when the domain leaves that field empty.
    Domain packs must not derive this field from advisory ranking or deterministic next-work
    selection inside hook 3.

    `advisory_active_items` remains secondary packet/trace context only. It must not become
    kernel-authored focus truth and is never written back as canonical shared state.
    """

    mission_state: MissionState
    resolution_state: ResolutionState
    blocking_items_summary: list[dict[str, Any]] = field(default_factory=list)
    closure_summary: dict[str, Any] = field(default_factory=dict)
    advisory_active_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class FocusPacket:
    """Domain-assembled evidence and context for the active focus item.

    The kernel passes this opaque container from hook 4 to hook 5.
    Kernel does not inspect domain_packet contents.
    """

    focus_key: str
    domain_packet: dict[str, Any]


@dataclass(frozen=True)
class MoveDecision:
    """Domain pack's resolved move for the active focus item.

    move_type values (canonical):
    - "apply_edit_plan"        — apply a prepared edit plan
    - "gather_more_evidence"   — run an investigation step
    - "request_human_feedback" — issue a HITL prompt (triggers HitlState machine)
    - "mark_blocked"           — domain cannot resolve this item (increments kernel strike)
    - "mark_resolved_no_edit"  — item resolved without execution (skip phase 6)
    - "skip_no_action"         — no actionable move this iteration (skip phase 6)
    """

    move_type: str
    focus_key: str | None
    rationale: str | None
    domain_move_payload: dict[str, Any]


@dataclass(frozen=True)
class MoveExecutionPlan:
    """Compiled execution-ready plan from hook 6.

    The kernel dispatches this to KernelSessionManager.step().

    Flags:
    - hitl_intent_flag: kernel transitions HitlState to "waiting" and terminates
      with waiting_human; domain pack must not call this for new HITL if
      OrchestratorContext.loop_memory.hitl_state == "no_prompt"
    - declare_done_flag: kernel terminates immediately with "completed" terminal
    - skip_execution: kernel skips KernelSessionManager.step() for this iteration
      (used for mark_resolved_no_edit, mark_blocked, etc.)
    """

    from agent_kernel.models import ActionType  # type: ignore[attr-defined]

    action_type: Any  # ActionType
    action_inputs: dict[str, Any]
    idempotency_key: str
    hitl_intent_flag: bool = False
    declare_done_flag: bool = False
    skip_execution: bool = False


@dataclass(frozen=True)
class ProgressMetrics:
    """Domain-supplied generic progress inputs for the shared evaluator.

    The domain pack derives these from its own authoritative state and evidence posture.
    The shared evaluator uses only these generic fields; no domain-specific field names
    enter the evaluator.
    """

    previous_finding_signature: str | None
    current_finding_signature: str
    previous_blocking_signature: str | None
    current_blocking_signature: str
    previous_blocking_count: int | None
    current_blocking_count: int
    # Domain-derived arrival signal. Kernel uses this to increment evidence_signal_counter.
    # The counter itself is kernel-owned; domain supplies the bool each iteration.
    new_evidence_signal: bool
    pending_feedback_prompt_id: str | None
    # T2: post-apply refresh tracking (mapped from domain's apply-reaudit semantics)
    pending_refresh: bool
    refresh_baseline_blocking_count: int | None
    refresh_baseline_blocking_signature: str | None


@dataclass(frozen=True)
class ProgressDelta:
    """Shared progress evaluation output."""

    made_progress: bool
    reason_code: str
    # When True, kernel clears pending_refresh flag (T2 kernel-side trigger reset)
    reset_refresh: bool


@dataclass(frozen=True)
class ClosureEvaluation:
    """Domain pack's closure evaluation output.

    Constraint: domain_terminal_class must use one of the six shared TerminalClass values.
    If domain cannot proceed, use "blocked" with closure_reason_code "impossible_unsupported".
    domain_terminal_class must NOT be "waiting_human" unless OrchestratorContext.loop_memory
    .hitl_state != "no_prompt" — new HITL intent is expressed through hook 5/6 MoveDecision
    with move_type "request_human_feedback", not through hook 8.
    """

    domain_complete: bool
    domain_terminal_class: TerminalClass
    closure_reason_code: str
    open_items_summary: str


@dataclass(frozen=True)
class IntegrationResult:
    """Domain pack's feedback integration completion signal.

    The kernel advances HitlState from "answered_unintegrated" to "consumed"
    only on successful return (integrated=True). The domain pack must not write
    HitlState directly.
    """

    integrated: bool
    integration_summary: str | None = None


@dataclass(frozen=True)
class RefreshResult:
    """Domain pack's hook 2 output."""

    latest_refs: dict[str, Any]
    execution_succeeded: bool
    refusal_reason: str | None = None


@dataclass(frozen=True)
class KernelLoopResult:
    """Result returned by run_orchestration_kernel_loop."""

    terminal_class: TerminalClass
    reason_code: str
    iterations: int
    session_id: str
    run_artifact_ref: str | None
    latest_refs: dict[str, Any]
    # Opaque domain-specific terminal context for mission-runtime adapters.
    # Carries any mode-owned waiting/closure state the generic shell must pass through.
    domain_runtime_state: dict[str, Any]
    # Phase 11 D1: serialised RawTraceEvent dicts emitted live by the kernel.
    # Populated by KernelTraceCollector; empty list when tracing is disabled.
    # The calling runtime layer builds a CanonicalTraceRecord from these and
    # persists the trace artifact (D2).
    trace_events: list[dict[str, Any]] = field(default_factory=list)


class OrchestratorContext:
    """Passed to domain pack hooks each phase.

    The kernel constructs and owns this object. loop_memory is mutated by the kernel
    between hook calls; domain packs read it but must not write kernel-owned fields.

    Kernel-owned fields in loop_memory (must not be written by domain pack):
    - active_item_id, focus_stagnation_streak
    - hitl_state, pending_feedback_prompt_id
    - no_progress_streak, evidence_signal_counter
    - invalid_plan_strikes
    """

    __slots__ = (
        "session_manager",
        "session_id",
        "loop_memory",
        "request_id_prefix",
        "dossier_id",
        # D3: populated by kernel from tracer.build_raw_events() before hook 4 each iteration.
        # Domain packs inject this into their focus packet for rationale carry-forward.
        "rationale_strip_snapshot",
    )

    def __init__(
        self,
        *,
        session_manager: Any,  # KernelSessionManager
        session_id: str,
        loop_memory: Any,  # LoopMemoryState
        request_id_prefix: str,
        dossier_id: str | None,
    ) -> None:
        self.session_manager = session_manager
        self.session_id = session_id
        self.loop_memory = loop_memory
        self.request_id_prefix = request_id_prefix
        self.dossier_id = dossier_id
        self.rationale_strip_snapshot: list[dict[str, Any]] = []


class DomainPack(Protocol):
    """Nine-hook protocol a domain pack must implement to plug into the orchestration kernel.

    The kernel provides rails and transport. The pack authors focus, context, move resolution,
    progress metrics, and closure rules. If hitl_state == "answered_unintegrated",
    integrate_feedback fires before refresh.
    """

    def orient(self, context: OrchestratorContext) -> None:
        """Run once at loop start (not on resume).

        Domain initializes its work-state from source material (baseline audit,
        ledger initialization, span seeds, etc.). Writes to context.loop_memory.domain_state
        or to the domain pack's own internal state.
        """
        ...

    def refresh(self, context: OrchestratorContext) -> RefreshResult:
        """Per-iteration re-observation pass.

        Runs the domain's audit/re-audit step and updates domain work-state.
        Returns updated latest_refs and execution status.
        """
        ...

    def project(self, context: OrchestratorContext) -> SharedStateProjection:
        """Project domain authority into native shared-state containers.

        Domain projects from its authoritative sources into canonical shared
        `mission_state` / `resolution_state` containers. `resolution_state.active_item_id`
        is the authored active-item signal when the domain wants to override continuity.
        `advisory_active_items` is secondary packet/trace context only.
        """
        ...

    def build_focus_packet(self, context: OrchestratorContext, focus_key: str) -> FocusPacket:
        """Assemble evidence and context for the current focus item.

        Domain assembles its evidence waterfall (span context, image verification,
        visual evidence, feedback payload) for the given focus_key.
        """
        ...

    def resolve_move(self, context: OrchestratorContext, focus_packet: FocusPacket) -> MoveDecision:
        """Determine the next move for the focused item.

        Domain calls its planner/resolver and returns the resolved move type
        with opaque domain_move_payload for hook 6 to compile.
        """
        ...

    def compile_move(self, context: OrchestratorContext, move_decision: MoveDecision) -> MoveExecutionPlan:
        """Compile the move decision into an execution-ready plan.

        Domain translates the move type and payload into a concrete ActionType
        + action_inputs + idempotency_key. Sets hitl_intent_flag=True for HITL moves.
        """
        ...

    def supply_progress_metrics(self, context: OrchestratorContext) -> ProgressMetrics:
        """Supply domain-specific progress metrics for the shared evaluator.

        Domain derives metrics from its authoritative state (signatures, counts, flags).
        The kernel increments evidence_signal_counter when new_evidence_signal is True;
        the counter is kernel-owned.
        """
        ...

    def supply_closure_rules(self, context: OrchestratorContext) -> ClosureEvaluation:
        """Evaluate domain closure conditions and map to shared terminal scaffold.

        Maps domain-specific closure conditions to the six shared TerminalClass values.
        """
        ...

    def integrate_feedback(
        self, context: OrchestratorContext, feedback_response: dict[str, Any]
    ) -> IntegrationResult:
        """Integrate a received human feedback response into domain work-state.

        Fires when OrchestratorContext.loop_memory.hitl_state == "answered_unintegrated".
        Domain integrates feedback into its authoritative state (e.g. ledger, registry).
        Returns IntegrationResult; kernel advances HitlState to "consumed" on success.
        Domain must not write HitlState directly.
        """
        ...
