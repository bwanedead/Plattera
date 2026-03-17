"""Run progress frame — bounded situational-awareness snapshot for the active run.

Assembled in hook 4 (build_focus_packet) from OrchestratorContext.loop_memory and
injected into the domain packet so every LLM call surface has a consistent view of
run identity, kernel posture, and work summary without exposing raw loop-memory verbosity.

Shape:
    run_identity  — static framing (run_link_id, mission_objective, domain, surface,
                    constitution_version)
    run_posture   — kernel-owned counters / flags that signal how the run is going
    work_summary  — top blocking items (shallow, max 5) + closure posture summary
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .contracts import OrchestratorContext

_MAX_BLOCKING_ITEMS = 5

# Shallow keys retained from each blocking item — enough for the LLM to reason
# about what is blocked without duplicating the full blocker payload.
_BLOCKER_SHALLOW_KEYS = (
    "decision_key",
    "focus_key",
    "blocker_type",
    "severity",
    "reason_code",
    "summary",
)


def build_run_progress_frame(
    context: "OrchestratorContext",
    *,
    run_link_id: str,
    mission_objective: str,
    domain: str,
    surface: str,
    constitution_version: str,
) -> dict[str, Any]:
    """Assemble a bounded run-progress snapshot from OrchestratorContext.loop_memory.

    Args:
        context: kernel orchestrator context (read-only access to loop_memory).
        run_link_id: canonical mission-level linkage string (= request_id_prefix).
        mission_objective: human-readable mission purpose string.
        domain: domain identifier string (e.g. "transcript_edit", "deed_to_ir").
        surface: LLM call surface identifier for this packet.
        constitution_version: identity constitution version tag.

    Returns:
        A dict suitable for direct injection into a domain packet under the key
        ``run_progress_frame``.
    """
    lm = context.loop_memory
    blocking_items = list(lm.blocker_surface or [])[:_MAX_BLOCKING_ITEMS]
    shallow_blockers = [_shallow_blocker(b) for b in blocking_items if isinstance(b, dict)]

    return {
        "run_identity": {
            "run_link_id": run_link_id,
            "mission_objective": mission_objective,
            "domain": domain,
            "surface": surface,
            "constitution_version": constitution_version,
        },
        "run_posture": {
            "hitl_state": lm.hitl_state,
            "no_progress_streak": lm.no_progress_streak,
            "focus_stagnation_streak": lm.focus_stagnation_streak,
            "invalid_plan_strikes": lm.invalid_plan_strikes,
            "pending_refresh": lm.pending_refresh,
        },
        "work_summary": {
            "blocking_items_top": shallow_blockers,
            "closure_posture_summary": dict(lm.closure_posture_summary or {}),
        },
    }


def _shallow_blocker(item: dict[str, Any]) -> dict[str, Any]:
    return {k: item[k] for k in _BLOCKER_SHALLOW_KEYS if k in item}
