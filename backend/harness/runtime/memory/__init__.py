"""Shared harness memory: continuity and observability telemetry only.

Mission meaning and pack-specific interpretation live in ``mission_state`` and
outside the harness; this package holds generic per-run carriage only, not a
parallel work ontology.
"""

from .continuity import OrchestrationContinuity
from .telemetry import PromptContactTelemetry

__all__ = [
    "OrchestrationContinuity",
    "PromptContactTelemetry",
]
