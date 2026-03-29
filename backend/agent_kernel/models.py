"""Core request/result models and enums for Agent Kernel v0."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .harness_action_ids import ActionType  # re-exported for callers importing models


class StopReason(str, Enum):
    """Deterministic terminal reasons for kernel execution."""

    COMPLETED = "completed"
    BUDGET_EXCEEDED = "budget_exceeded"
    NO_PROGRESS = "no_progress"
    NEEDS_USER_CHOICE = "needs_user_choice"
    NEEDS_UPLOAD = "needs_upload"
    NEEDS_CAPABILITY = "needs_capability"
    WORKER_UNAVAILABLE = "worker_unavailable"
    VALIDATION_FAILED = "validation_failed"
    INTERNAL_ERROR = "internal_error"
    ERROR = "error"
    CANCELLED = "cancelled"


class KernelState(str, Enum):
    """Generic kernel lifecycle states."""

    INIT = "init"
    SOURCE_READY = "source_ready"
    ANALYZED = "analyzed"
    REVIEWED = "reviewed"
    PACKAGE_READY = "package_ready"
    REPAIRING = "repairing"
    PACKAGE_COMMITTED = "package_committed"
    DONE = "done"

    # Transitional aliases for older workflow-oriented call sites.
    HAVE_IR = SOURCE_READY
    HAVE_COMPILE = ANALYZED
    HAVE_JUDGE = REVIEWED
    READY_TO_MAP = PACKAGE_READY
    MAPPED = PACKAGE_COMMITTED


class KernelGoal(BaseModel):
    """Goal flags supplied by the owning pack; shared core treats them as transitional hints."""

    requires_global_placement: bool = Field(
        ...,
        description="Transitional pack-owned hint; shared core does not assign closure doctrine.",
    )
    render_required: bool = Field(
        default=False,
        description="Transitional pack-owned hint; rendering semantics are pack-defined.",
    )
    objective: str = Field(default="", description="Human-readable run objective.")


class KernelBudgets(BaseModel):
    """Execution limits enforced by the kernel loop."""

    max_steps: int = Field(..., ge=1)
    max_wall_time_seconds: int = Field(..., ge=1)
    max_retrieval_calls: int = Field(..., ge=0)
    max_semantic_calls: int = Field(..., ge=0)
    max_patch_calls: int = Field(..., ge=0)


class KernelRequest(BaseModel):
    """Input contract for deterministic kernel runs.

    The bootstrap fields are transitional compatibility inputs; product packs can shape them
    externally before handing them to the shared host.
    """

    request_id: str = Field(..., min_length=1)
    goal: KernelGoal
    budgets: KernelBudgets
    initial_ir_ref: Optional[str] = Field(
        default=None,
        description="Transitional bootstrap ref for a pre-existing IR artifact.",
    )
    initial_graph_json: Optional[dict[str, object]] = Field(
        default=None,
        description="Transitional inline bootstrap payload when no durable IR ref is available.",
    )


class TerminalOutcomeKind(str, Enum):
    """External-facing terminal outcome taxonomy."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    NEEDS_USER_CHOICE = "NEEDS_USER_CHOICE"
    NEEDS_UPLOAD = "NEEDS_UPLOAD"
    FAILED = "FAILED"


class TerminalOutcome(BaseModel):
    """Terminal execution metadata for a run."""

    terminal_outcome: TerminalOutcomeKind
    stop_reason: StopReason
    success: bool
    reason_code: Optional[str] = None


class KernelResult(BaseModel):
    """Deterministic result envelope emitted by kernel runs."""

    request_id: str = Field(..., min_length=1)
    final_state: KernelState
    terminal: TerminalOutcome
    steps_executed: int = Field(..., ge=0)
    run_artifact_ref: Optional[str] = Field(
        default=None,
        description="Durable reference to persisted run artifact.",
    )


class KernelRefusal(BaseModel):
    """Deterministic refusal contract for session start/step calls."""

    reason_code: str = Field(..., min_length=1)
    missing_inputs: list[str] = Field(default_factory=list)
    retryable: bool
    blocked_by_budget: bool = False
    blocked_by_invariant: bool = False


class KernelLatestRefs(BaseModel):
    """Latest artifact pointers for dashboard.

    ``artifact_refs`` is the canonical shared surface. Any legacy slot handling is transitional and
    owned by callers/adapters, not by the model itself.
    """

    artifact_refs: dict[str, dict[str, object]] = Field(
        default_factory=dict,
        description="Merged opaque pointers owned by the pack or compatibility adapters.",
    )


class KernelGapSummary(BaseModel):
    """Compact gap summary for shared kernel planning."""

    top_gap_kinds: list[str] = Field(default_factory=list)
    gap_counts_by_kind: dict[str, int] = Field(default_factory=dict)
    top_reason_codes: list[str] = Field(default_factory=list)


class KernelClaimabilityStatus(BaseModel):
    """Claimability gate status computed from deterministic artifacts/results."""

    claimable_ready: bool
    missing_claimability: list[str] = Field(default_factory=list)


class KernelFailureClassification(BaseModel):
    """Most recent deterministic failure classification."""

    stop_reason: Optional[StopReason] = None
    reason_code: Optional[str] = None


class KernelNoProgressRisk(BaseModel):
    """Non-terminal no-progress risk signal returned every step."""

    risk_score: float = Field(0.0, ge=0.0, le=1.0)
    basis: str = Field(default="", max_length=128)


class KernelDashboard(BaseModel):
    """Compact flight-instruments payload returned on every session call."""

    latest_refs: KernelLatestRefs
    gap_summary: KernelGapSummary
    claimability: KernelClaimabilityStatus
    semantic_ready: Optional[bool] = None
    budgets_remaining: dict[str, int]
    failure_classification: KernelFailureClassification
    no_progress_risk: KernelNoProgressRisk
    last_refusal: Optional[KernelRefusal] = None


class KernelSessionStartRequest(BaseModel):
    """Input contract for initializing a step-driven kernel session.

    Shared core keeps this generic; pack-specific shaping stays outside the shared contract.
    """

    session_id: Optional[str] = None
    request_id: str = Field(..., min_length=1)
    goal: KernelGoal
    budgets: KernelBudgets
    dossier_id: Optional[str] = Field(default=None, description="Transitional pack-shaped bootstrap field.")
    source_entry_ref: Optional[str] = Field(default=None, description="Transitional pack-shaped bootstrap field.")
    initial_ir_ref: Optional[str] = Field(default=None, description="Transitional bootstrap ref.")
    initial_graph_json: Optional[dict[str, object]] = Field(
        default=None,
        description="Transitional inline bootstrap payload.",
    )


class KernelSessionStartResult(BaseModel):
    """Session bootstrap result with initial dashboard/tool menu state."""

    session_id: Optional[str] = None
    run_id: Optional[str] = None
    run_artifact_ref: Optional[str] = None
    tool_menu: list[str] = Field(default_factory=list)
    dashboard: Optional[KernelDashboard] = None
    budgets_remaining: Optional[dict[str, int]] = None
    refusal: Optional[KernelRefusal] = None


class KernelStepRequest(BaseModel):
    """One-step action request chosen by the orchestration shell.

    ``action_type`` is an opaque action id. Built-in harness ids and provider-registered ids share
    this single field.
    """

    session_id: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)
    action_type: str = Field(
        ...,
        min_length=1,
        description="Harness-reserved action id or domain-registered id (opaque string).",
    )
    inputs: dict[str, object] = Field(default_factory=dict)
    semantic_ready: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=512)


class StepExecutionState(str, Enum):
    """Execution-state classification for one-step responses."""

    EXECUTED = "executed"
    REFUSED = "refused"
    DEDUPED = "deduped"


class KernelStepResult(BaseModel):
    """Result envelope for exactly one session step call."""

    session_id: str
    idempotency_key: str
    execution_state: StepExecutionState
    step_record: Optional[dict[str, object]] = None
    refusal: Optional[KernelRefusal] = None
    dashboard: KernelDashboard
    terminal: Optional[TerminalOutcome] = None
