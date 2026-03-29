"""Bounded run snapshot for prompt-facing harness observability.

This helper keeps the shared prompt/tracing surface small and mechanical:
run identity, transport posture, and a short artifact summary.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .kernel import OrchestratorContext

_MAX_REF_KEYS = 5


def build_run_progress_frame(
    context: "OrchestratorContext",
    *,
    run_link_id: str,
    mission_objective: str,
    domain: str,
    constitution_version: str,
) -> dict[str, Any]:
    """Assemble a generic prompt-facing run snapshot."""
    lm = context.loop_memory
    ref_keys = sorted(str(key) for key in (lm.latest_refs or {}).keys() if str(key).strip())

    return {
        "run_identity": {
            "run_link_id": run_link_id,
            "mission_objective": mission_objective,
            "domain": domain,
            "constitution_version": constitution_version,
        },
        "run_posture": {
            "iterations": lm.iterations,
            "hitl_state": lm.hitl_state,
            "pending_feedback_prompt_id": lm.pending_feedback_prompt_id,
            "llm_contact_count": lm.llm_contact_count,
            "prompt_event_count": lm.prompt_event_count,
            "last_prompt_event_id": lm.last_prompt_event_id,
            "last_prompt_event_surface": lm.last_prompt_event_surface,
            "active_item_id": lm.active_item_id,
        },
        "artifact_summary": {
            "latest_ref_count": len(ref_keys),
            "latest_ref_keys": ref_keys[:_MAX_REF_KEYS],
        },
    }
