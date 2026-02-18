"""Core request/result models and enums for Agent Kernel v0."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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
    """Explicit kernel state machine states."""

    INIT = "init"
    HAVE_IR = "have_ir"
    HAVE_COMPILE = "have_compile"
    HAVE_JUDGE = "have_judge"
    REPAIRING = "repairing"
    READY_TO_MAP = "ready_to_map"
    MAPPED = "mapped"
    DONE = "done"


class ActionType(str, Enum):
    """Kernel actions, including deterministic and LLM-facing stubs."""

    SET_GRAPH_REQUIREMENTS = "set_graph_requirements"
    HYDRATE_DEED = "hydrate_deed"
    OPEN_ARTIFACT = "open_artifact"
    DRAFT_IR = "draft_ir"
    DECLARE_DONE = "declare_done"
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    COMPILE = "compile"
    JUDGE = "judge"
    BUNDLE = "bundle"
    GEOREFERENCE = "georeference"
    VALIDATE = "validate"
    PROPOSE_PATCH = "propose_patch"
    SUMMARIZE_STATUS = "summarize_status"


class KernelGoal(BaseModel):
    """Goal flags that drive deterministic routing behavior."""

    requires_global_placement: bool = Field(
        ...,
        description="Whether execution must surface global placement gaps deterministically.",
    )
    render_required: bool = Field(
        default=False,
        description="Whether final rendering is required to consider the run complete.",
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
    """Input contract for deterministic kernel runs."""

    request_id: str = Field(..., min_length=1)
    goal: KernelGoal
    budgets: KernelBudgets
    initial_ir_ref: Optional[str] = Field(
        default=None,
        description="Optional durable reference to a pre-existing IR artifact.",
    )
    initial_graph_json: Optional[dict[str, object]] = Field(
        default=None,
        description="Optional inline graph payload when no initial IR artifact ref is available.",
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
    """Compact latest artifact refs for dashboard instrumentation."""

    ir_ref: Optional[dict[str, object]] = None
    compile_ref: Optional[dict[str, object]] = None
    judge_ref: Optional[dict[str, object]] = None
    bundle_ref: Optional[dict[str, object]] = None
    georef_ref: Optional[dict[str, object]] = None
    validate_ref: Optional[dict[str, object]] = None
    retrieval_ref: Optional[dict[str, object]] = None


class KernelGapSummary(BaseModel):
    """Compact gap summary for controller-side planning."""

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
    """Input contract for initializing a step-driven kernel session."""

    session_id: Optional[str] = None
    request_id: str = Field(..., min_length=1)
    goal: KernelGoal
    budgets: KernelBudgets
    dossier_id: Optional[str] = None
    source_entry_ref: Optional[str] = None
    initial_ir_ref: Optional[str] = None
    initial_graph_json: Optional[dict[str, object]] = None
    policy_id: str = "feature_graph_deed_to_map_v0"


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
    """One-step action request chosen by a controller."""

    session_id: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)
    action_type: ActionType
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
