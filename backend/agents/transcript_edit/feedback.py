from __future__ import annotations

from typing import Any

from .blocker_registry import mark_feedback_received
from .decision_ledger import mark_human_resolution_ticket_state
from .state_projection import sync_pending_feedback_cache_from_registry
from harness.orchestration_kernel.contracts import IntegrationResult, OrchestratorContext


def integrate_transcript_edit_feedback(
    pack: Any,
    context: OrchestratorContext,
    feedback_response: dict[str, Any],
) -> IntegrationResult:
    if not isinstance(feedback_response, dict):
        return IntegrationResult(integrated=False, integration_summary="invalid_feedback_response")

    decision_key = str(feedback_response.get("decision_key") or pack._state.pending_feedback_decision_key or "").strip().lower()
    prompt_id = str(feedback_response.get("prompt_id") or pack._state.pending_feedback_prompt_id or "").strip() or None
    feedback_value = str(feedback_response.get("selected_value") or "").strip() or None
    feedback_note = str(feedback_response.get("note") or "").strip() or None

    if decision_key:
        pack._state.blocker_registry = mark_feedback_received(
            registry=pack._state.blocker_registry,
            decision_key=decision_key,
            prompt_id=prompt_id or "",
            feedback_value=feedback_value,
            feedback_note=feedback_note,
            reason="hook9_feedback_integration",
        )

    if prompt_id and decision_key:
        pack._state.decision_ledger = mark_human_resolution_ticket_state(
            ledger=pack._state.decision_ledger,
            ticket_id=prompt_id,
            decision_key=decision_key,
            lifecycle_state="integrated",
            relevance="active",
        )

    pack._state.latest_feedback = feedback_response
    pack._state.evidence_signal_counter += 1
    pack._state.used_human_feedback = True
    pack._state.pending_feedback_prompt_id = None
    pack._state.pending_feedback_decision_key = None
    sync_pending_feedback_cache_from_registry(state=pack._state)

    feedback_summary = str(feedback_response.get("summary") or "").strip()
    return IntegrationResult(integrated=True, integration_summary=feedback_summary or "feedback_integrated")
