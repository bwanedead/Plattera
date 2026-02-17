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
