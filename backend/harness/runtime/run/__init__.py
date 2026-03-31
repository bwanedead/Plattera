"""Single-run loop mechanics (one bounded cycle / kernel turn).

Exposes the per-run orchestrator, loop memory aggregate, contracts, and
progress helpers used by harness-level observability. Multi-cycle mission
coordination lives in ``harness.runtime.mission``.
"""

from ..memory import OrchestrationContinuity, PromptContactTelemetry
from .contracts import (
    ActionPlan,
    KernelLoopResult,
    OrchestratorContext,
    OrchestrationPack,
    SharedStateProjection,
    TerminalEvaluation,
)
from .hitl_transport import HitlTransportPosture
from .loop_memory import LoopMemoryState
from .orchestrator import run_orchestration_kernel_loop
from .progress import ProgressDelta, ProgressMetrics, evaluate_progress

__all__ = [
    "ActionPlan",
    "HitlTransportPosture",
    "KernelLoopResult",
    "LoopMemoryState",
    "OrchestrationContinuity",
    "OrchestrationPack",
    "OrchestratorContext",
    "PromptContactTelemetry",
    "ProgressDelta",
    "ProgressMetrics",
    "SharedStateProjection",
    "TerminalEvaluation",
    "evaluate_progress",
    "run_orchestration_kernel_loop",
]
