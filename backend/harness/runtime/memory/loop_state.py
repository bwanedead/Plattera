from __future__ import annotations

from dataclasses import dataclass, field

from .continuity import OrchestrationContinuity
from .telemetry import PromptContactTelemetry
from ..hitl.transport import HitlTransportPosture


@dataclass
class LoopMemoryState:
    """Per-run aggregate on ``OrchestratorContext``.

    Composes generic continuity (``harness.runtime.memory``), prompt-contact telemetry,
    HITL transport posture, and the current loop index. Use the nested fields
    for clear boundaries; mission understanding in ``continuity`` references
    ``mission_state`` types but is loop-local hydration, not a substitute for
    the mission-state subsystem.
    """

    continuity: OrchestrationContinuity = field(default_factory=OrchestrationContinuity)
    telemetry: PromptContactTelemetry = field(default_factory=PromptContactTelemetry)
    hitl: HitlTransportPosture = field(default_factory=HitlTransportPosture)
    iterations: int = 0
