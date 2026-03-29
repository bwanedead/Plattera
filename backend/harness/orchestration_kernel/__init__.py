"""Generic orchestration kernel surface.

This package exposes the shared loop runner, the minimal runtime result types,
and the mechanical progress helpers used by harness-level observability.
"""

from .contracts import ActionPlan
from .kernel import (
    KernelLoopResult,
    LoopMemoryState,
    OrchestratorContext,
    SharedStateProjection,
    TerminalEvaluation,
    run_orchestration_kernel_loop,
)
from .progress import ProgressDelta, ProgressMetrics, evaluate_progress

__all__ = [
    "ActionPlan",
    "KernelLoopResult",
    "LoopMemoryState",
    "OrchestratorContext",
    "ProgressDelta",
    "ProgressMetrics",
    "SharedStateProjection",
    "TerminalEvaluation",
    "evaluate_progress",
    "run_orchestration_kernel_loop",
]
