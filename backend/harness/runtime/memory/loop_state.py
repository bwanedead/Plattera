from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .continuity import OrchestrationContinuity
from .telemetry import PromptContactTelemetry
from .turn_recovery import TurnRecoveryState
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
    # Mechanical side channel: image evidence dicts accumulated from tool results each iteration.
    # Read and cleared by LlmTurnOrchestrationAdapter.choose_action before each kernel LLM call.
    # NOT persisted in resume snapshots; the model re-hydrates if needed after a resume.
    pending_image_evidence: list[dict[str, Any]] = field(default_factory=list)
    # Host-owned contract feedback from the prior choose-action turn.
    # Set by LlmTurnOrchestrationAdapter after any parse failure or repair attempt.
    # Cleared to {} on a clean (no-repair) successful turn.
    # Included in the next turn's prompt envelope so the model can self-correct.
    contract_feedback: dict[str, Any] = field(default_factory=dict)
    # Mechanical recovery context for output-side model failures. This is not
    # semantic state; it only tells the next prompt why the prior model turn
    # produced no usable action plan and how many bounded retries remain.
    turn_recovery: TurnRecoveryState = field(default_factory=TurnRecoveryState)
