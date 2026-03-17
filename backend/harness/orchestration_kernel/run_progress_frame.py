"""Run progress frame — bounded situational-awareness snapshot for the active run.

Assembled in hook 4 (build_focus_packet) from OrchestratorContext.loop_memory and
injected into the domain packet so every LLM call surface has a consistent view of
run identity, kernel posture, and work summary without exposing raw loop-memory verbosity.

Shape:
    run_identity  — static run framing (run_link_id, mission_objective, domain,
                    constitution_version).  NOTE: ``surface`` is intentionally absent;
                    call-surface identity is owned exclusively by the developer/header
                    message assembled by compose_identity_header().
    run_posture   — kernel-owned counters / flags that signal how the run is going
    work_summary  — top blocking items from loop_memory.blocker_surface (shallow, max 5)
                    + closure posture summary

``blocking_items_top`` is strictly blockers-only: drawn from loop_memory.blocker_surface
(domain pack writes this via WorkStateProjection.blocker_surface in hook 3).  Ranked
work items are intentionally excluded — they are ephemeral phase-4 inputs and not
appropriate for long-term carry-forward context.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .contracts import OrchestratorContext

_MAX_BLOCKING_ITEMS = 5

# Run-stage taxonomy (D3) — kept intentionally small; derived from real kernel signals.
#   initial_recon  — first iteration; orient just completed, no iteration history yet
#   closure_active — normal working state; making progress or on first try
#   waiting_human  — loop is paused on a HITL prompt
#   stagnating     — no-progress or focus-stagnation streak indicates the loop is spinning
#   near_terminal  — very few (0-1) blocking items remain; loop is close to done
_RUN_STAGE_WAITING_HUMAN = "waiting_human"
_RUN_STAGE_STAGNATING = "stagnating"
_RUN_STAGE_NEAR_TERMINAL = "near_terminal"
_RUN_STAGE_INITIAL_RECON = "initial_recon"
_RUN_STAGE_CLOSURE_ACTIVE = "closure_active"

_STAGNATION_STREAK_THRESHOLD = 3


def _derive_run_stage(
    hitl_state: str,
    iterations: int,
    no_progress_streak: int,
    focus_stagnation_streak: int,
    blocking_count: int,
) -> str:
    """Derive a run_stage label from current kernel signals.

    Priority order (highest first):
    1. waiting_human — HITL prompt is outstanding
    2. stagnating    — repeated no-progress or focus-stagnation
    3. near_terminal — 0 or 1 mapping-blocking items remain
    4. initial_recon — first iteration (orient just ran, no history)
    5. closure_active — default working state
    """
    if hitl_state == "waiting":
        return _RUN_STAGE_WAITING_HUMAN
    if no_progress_streak >= _STAGNATION_STREAK_THRESHOLD or focus_stagnation_streak >= _STAGNATION_STREAK_THRESHOLD:
        return _RUN_STAGE_STAGNATING
    if iterations > 1 and blocking_count <= 1:
        return _RUN_STAGE_NEAR_TERMINAL
    if iterations <= 1:
        return _RUN_STAGE_INITIAL_RECON
    return _RUN_STAGE_CLOSURE_ACTIVE


# v1 shallow blocker keys — exactly these four, nothing else.
# Keeps each entry to a handful of tokens so the LLM can scan all 5 at a glance.
#   focus_key   — which work item is blocked (join key to focus selection)
#   state       — domain blocker/work-item lifecycle state string
#                 (e.g. "open", "waiting_evidence", "resolved").
#                 This is the DOMAIN's blocker state, NOT kernel HITL state
#                 (which lives in loop_memory.hitl_state and is separate).
#   reason_code — machine-readable classification (e.g. "image_not_found")
#   priority    — numeric ordering hint emitted by domain pack (omitted if absent)
_BLOCKER_SHALLOW_KEYS_V1 = ("focus_key", "state", "reason_code", "priority")


def build_run_progress_frame(
    context: "OrchestratorContext",
    *,
    run_link_id: str,
    mission_objective: str,
    domain: str,
    constitution_version: str,
) -> dict[str, Any]:
    """Assemble a bounded run-progress snapshot from OrchestratorContext.loop_memory.

    Args:
        context: kernel orchestrator context (read-only access to loop_memory).
        run_link_id: canonical mission-level linkage string (= request_id_prefix).
        mission_objective: human-readable mission purpose string.
        domain: domain identifier string (e.g. "transcript_edit", "deed_to_ir").
        constitution_version: identity constitution version tag.

    Returns:
        A dict suitable for direct injection into a domain packet under the key
        ``run_progress_frame``.  ``surface`` is not included in ``run_identity``
        because the focus packet is shared across resolver/planner surfaces; active
        surface identity belongs in the per-call header assembled by
        compose_identity_header().
    """
    lm = context.loop_memory
    blocking_items = list(lm.blocker_surface or [])[:_MAX_BLOCKING_ITEMS]
    shallow_blockers = [_shallow_blocker(b) for b in blocking_items if isinstance(b, dict)]
    blocking_count = len(list(lm.blocker_surface or []))

    run_stage = _derive_run_stage(
        hitl_state=lm.hitl_state,
        iterations=lm.iterations,
        no_progress_streak=lm.no_progress_streak,
        focus_stagnation_streak=lm.focus_stagnation_streak,
        blocking_count=blocking_count,
    )

    return {
        "run_identity": {
            "run_link_id": run_link_id,
            "mission_objective": mission_objective,
            "domain": domain,
            "constitution_version": constitution_version,
        },
        "run_posture": {
            "run_stage": run_stage,
            "hitl_state": lm.hitl_state,
            "no_progress_streak": lm.no_progress_streak,
            "focus_stagnation_streak": lm.focus_stagnation_streak,
            "invalid_plan_strikes": lm.invalid_plan_strikes,
            "pending_refresh": lm.pending_refresh,
            "llm_contact_count": lm.llm_contact_count,
        },
        "work_summary": {
            "blocking_items_top": shallow_blockers,
            "closure_posture_summary": dict(lm.closure_posture_summary or {}),
        },
    }


def _shallow_blocker(item: dict[str, Any]) -> dict[str, Any]:
    """Return the v1 shallow view of a single blocker item (4 keys max, no nested payloads)."""
    return {k: item[k] for k in _BLOCKER_SHALLOW_KEYS_V1 if k in item}
