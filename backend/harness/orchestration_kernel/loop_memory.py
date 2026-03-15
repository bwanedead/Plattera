from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import HitlState


@dataclass
class LoopMemoryState:
    """Kernel-owned loop state.

    Written only by the orchestration kernel. Domain packs read via OrchestratorContext
    but must not write kernel-owned fields directly.

    Kernel-owned fields (domain packs must not write):
    - active_focus_key, focus_stagnation_streak  (focus state)
    - hitl_state, pending_feedback_prompt_id, pending_feedback_response  (HITL state machine)
    - no_progress_streak, last_progress_reason, evidence_signal_counter  (progress memory)
    - invalid_plan_strikes  (loop brake)

    Domain packs may read any field for decision-making but must only surface
    updates via hook return values (WorkStateProjection, ProgressMetrics, etc.).
    """

    # --- Continuity memory ---
    iterations: int = 0
    latest_refs: dict[str, Any] = field(default_factory=dict)
    # T2: pending_refresh is set by kernel when ProgressDelta.reset_refresh fires.
    # Kernel-side trigger; domain pack must not write.
    pending_refresh: bool = False

    # --- Work-State memory (written atomically from WorkStateProjection) ---
    # Focus state is kernel-owned and NOT part of WorkStateProjection.
    work_item_collection: list[dict[str, Any]] = field(default_factory=list)
    blocker_surface: list[dict[str, Any]] = field(default_factory=list)
    closure_posture_summary: dict[str, Any] = field(default_factory=dict)

    # Focus state (kernel-owned; NOT projected by domain pack)
    active_focus_key: str | None = None
    focus_stagnation_streak: int = 0

    # --- Progress memory (kernel-owned) ---
    no_progress_streak: int = 0
    last_progress_reason: str = "initial"

    # --- Evidence memory (kernel-owned counter) ---
    # Domain supplies new_evidence_signal bool each iteration via hook 7.
    # Kernel increments this counter when the signal is True.
    evidence_signal_counter: int = 0

    # --- HITL state machine (kernel-owned) ---
    # Transitions: no_prompt → waiting → answered_unintegrated → consumed
    # Kernel is the sole actor that writes hitl_state.
    hitl_state: HitlState = "no_prompt"
    pending_feedback_prompt_id: str | None = None
    # Set by kernel when feedback poll detects arrival; cleared after hook 9.
    pending_feedback_response: dict[str, Any] | None = None

    # --- Loop brakes (kernel-owned) ---
    invalid_plan_strikes: int = 0

    # --- Last step refusal record (kernel-owned, readable by domain pack) ---
    # Set when a retryable step refusal is tolerated (not immediately fatal).
    # Cleared on the next successful step execution.
    # Domain packs may read this to surface rejection context to the LLM.
    last_step_refusal_record: dict[str, Any] | None = None
