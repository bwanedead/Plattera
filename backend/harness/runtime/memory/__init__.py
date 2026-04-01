"""Shared harness memory: continuity, observability telemetry, and loop-local state.

Mission meaning and pack-specific interpretation live in ``mission_state`` and
outside the harness; this package holds generic per-run carriage only, not a
parallel work ontology.
"""

from .continuity import OrchestrationContinuity
from .loop_state import LoopMemoryState
from .telemetry import PromptContactTelemetry

__all__ = [
    "LoopMemoryState",
    "OrchestrationContinuity",
    "PromptContactTelemetry",
]
