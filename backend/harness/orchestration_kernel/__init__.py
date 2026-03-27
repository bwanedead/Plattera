"""Orchestration kernel — shared loop law above execution kernel and domain packs.

This package implements the shared phase grammar and loop governance for all domain families.
The execution kernel (backend/agent_kernel/) handles action dispatch and budgets.
Domain packs (e.g. backend/agents/transcript_edit/domain_pack.py) supply domain content and policy.

Public surface:
- run_orchestration_kernel_loop — the phase grammar runner
- contracts — shared types (OrchestratorContext, DomainPack, SharedStateProjection, ...)
- loop_memory — LoopMemoryState (kernel-owned loop state)
- progress — evaluate_progress (shared progress evaluator)
"""

from .contracts import (
    ClosureEvaluation,
    DomainPack,
    FocusPacket,
    HitlState,
    IntegrationResult,
    KernelLoopResult,
    MoveDecision,
    MoveExecutionPlan,
    OrchestratorContext,
    ProgressDelta,
    ProgressMetrics,
    RefreshResult,
    SharedStateProjection,
)
from .kernel import run_orchestration_kernel_loop
from .loop_memory import LoopMemoryState
from .progress import evaluate_progress

__all__ = [
    "ClosureEvaluation",
    "DomainPack",
    "FocusPacket",
    "HitlState",
    "IntegrationResult",
    "KernelLoopResult",
    "LoopMemoryState",
    "MoveDecision",
    "MoveExecutionPlan",
    "OrchestratorContext",
    "ProgressDelta",
    "ProgressMetrics",
    "RefreshResult",
    "SharedStateProjection",
    "evaluate_progress",
    "run_orchestration_kernel_loop",
]
