"""Public model surface for Agent Kernel v0.

**Canonical (preferred for new code):** ``KernelSessionManager``, session models, tools, state machine.

**Compatibility (explicit; do not extend as primary architecture):** legacy loop and policy helpers
remain available from their owning modules for older callers — see ``COMPATIBILITY.md``.
"""

# --- Actions & tools (shared deps for session + compatibility loop) ---
from .actions import (
    ActionExecutor,
    ActionExecutorDeps,
    ArtifactOpener,
    ArtifactBundler,
    ArtifactCompiler,
    ArtifactDraftProposer,
    ArtifactGeoreferencer,
    ArtifactHydrator,
    ArtifactJudge,
    ArtifactRenderer,
    ArtifactValidator,
    EvidenceRetriever,
    PatchProposer,
    StatusSummarizer,
    SpanIndexUpserter,
)
from .claimability import ClaimabilityPolicy
# --- Canonical: step-driven kernel session ---
from .session import KernelSessionManager, SessionPersistence
from .budgets import BudgetSnapshot, BudgetStatus, BudgetTracker
from .policies import KernelPolicy
from .models import (
    ActionType,
    KernelClaimabilityStatus,
    KernelDashboard,
    KernelBudgets,
    KernelFailureClassification,
    KernelGapSummary,
    KernelGoal,
    KernelLatestRefs,
    KernelNoProgressRisk,
    KernelRefusal,
    KernelRequest,
    KernelResult,
    KernelSessionStartRequest,
    KernelSessionStartResult,
    KernelState,
    KernelStepRequest,
    KernelStepResult,
    StepExecutionState,
    StopReason,
    TerminalOutcomeKind,
    TerminalOutcome,
)
from .no_progress import (
    GapSignal,
    NoProgressDetector,
    NoProgressStatus,
    build_iteration_fingerprint,
    compute_artifact_digests,
    compute_gap_signature,
)
from .run_artifact import ArtifactRef, RunArtifact, StepRecord, ValidationInline
from .state_machine import KernelEvent, TransitionError, advance_state, can_transition

__all__ = [
    "ActionType",
    "ActionExecutor",
    "ActionExecutorDeps",
    "ArtifactOpener",
    "ArtifactBundler",
    "ArtifactCompiler",
    "ArtifactDraftProposer",
    "ArtifactGeoreferencer",
    "ArtifactHydrator",
    "ArtifactJudge",
    "ArtifactRenderer",
    "ArtifactValidator",
    "SpanIndexUpserter",
    "ArtifactRef",
    "BudgetSnapshot",
    "BudgetStatus",
    "BudgetTracker",
    "EvidenceRetriever",
    "KernelSessionManager",
    "KernelPolicy",
    "ClaimabilityPolicy",
    "KernelBudgets",
    "KernelClaimabilityStatus",
    "KernelDashboard",
    "KernelFailureClassification",
    "KernelGapSummary",
    "KernelGoal",
    "KernelLatestRefs",
    "KernelNoProgressRisk",
    "KernelRefusal",
    "KernelRequest",
    "KernelResult",
    "KernelSessionStartRequest",
    "KernelSessionStartResult",
    "KernelState",
    "KernelStepRequest",
    "KernelStepResult",
    "GapSignal",
    "NoProgressDetector",
    "NoProgressStatus",
    "PatchProposer",
    "RunArtifact",
    "StopReason",
    "StatusSummarizer",
    "StepRecord",
    "StepExecutionState",
    "TerminalOutcome",
    "TerminalOutcomeKind",
    "ValidationInline",
    "SessionPersistence",
    "KernelEvent",
    "TransitionError",
    "advance_state",
    "can_transition",
    "build_iteration_fingerprint",
    "compute_artifact_digests",
    "compute_gap_signature",
]
