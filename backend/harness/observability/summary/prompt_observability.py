"""Prompt-event summarization for run-summary inspection."""

from __future__ import annotations

from typing import Any

from .common import _as_dict, _as_int, _as_str, _event_kind
from .models import PromptObservabilitySummary


def _prompt_observability_summary_from_payload(
    payload: dict[str, Any],
    *,
    default_surface: str | None = None,
) -> PromptObservabilitySummary:
    summary = payload.get("prompt_observability_summary")
    if isinstance(summary, dict):
        return PromptObservabilitySummary(
            prompt_event_count=_as_int(summary.get("prompt_event_count")) or 0,
            last_prompt_event_id=_as_str(summary.get("last_prompt_event_id")),
            last_prompt_event_surface=_as_str(summary.get("last_prompt_event_surface")) or _as_str(default_surface),
            consecutive_no_dispatch_turns=_as_int(summary.get("consecutive_no_dispatch_turns")) or 0,
            turns_since_last_tool_execution=_as_int(summary.get("turns_since_last_tool_execution")),
            turns_since_latest_refs_change=_as_int(summary.get("turns_since_latest_refs_change")),
            last_state_patch_outcome=_as_str(summary.get("last_state_patch_outcome")),
            last_state_patch_reason_code=_as_str(summary.get("last_state_patch_reason_code")),
            success_condition_count=_as_int(summary.get("success_condition_count")) or 0,
            success_conditions_with_earned_determination_count=(
                _as_int(summary.get("success_conditions_with_earned_determination_count")) or 0
            ),
            success_conditions_with_verification_basis_count=(
                _as_int(summary.get("success_conditions_with_verification_basis_count")) or 0
            ),
            resolution_item_count=_as_int(summary.get("resolution_item_count")) or 0,
            items_with_evidence_count=_as_int(summary.get("items_with_evidence_count")) or 0,
            items_with_verification_basis_count=_as_int(summary.get("items_with_verification_basis_count")) or 0,
            closed_items_count=_as_int(summary.get("closed_items_count")) or 0,
            closed_items_without_earned_determination_count=(
                _as_int(summary.get("closed_items_without_earned_determination_count")) or 0
            ),
            closed_items_without_basis_count=_as_int(summary.get("closed_items_without_basis_count")) or 0,
            closed_items_without_completion_criteria_count=(
                _as_int(summary.get("closed_items_without_completion_criteria_count")) or 0
            ),
            closure_dimension_count=_as_int(summary.get("closure_dimension_count")) or 0,
            closure_dimensions_with_earned_determination_count=(
                _as_int(summary.get("closure_dimensions_with_earned_determination_count")) or 0
            ),
            closed_dimensions_without_earned_determination_count=(
                _as_int(summary.get("closed_dimensions_without_earned_determination_count")) or 0
            ),
            closed_dimensions_without_basis_count=(
                _as_int(summary.get("closed_dimensions_without_basis_count")) or 0
            ),
        )
    return PromptObservabilitySummary(last_prompt_event_surface=_as_str(default_surface))


def _prompt_observability_summary_from_trace_events(events: list[dict[str, Any]]) -> PromptObservabilitySummary:
    prompt_events = [
        event
        for event in events
        if _as_str(event.get("phase")) == "prompt_event"
        or _event_kind(event) == "prompt_event"
        or (
            isinstance(event.get("payload"), dict)
            and isinstance(event["payload"].get("prompt_event"), dict)
        )
    ]
    last_payload = _as_dict(prompt_events[-1].get("payload")) if prompt_events else {}
    last_prompt_event = _as_dict(last_payload.get("prompt_event"))
    metadata = _as_dict(last_prompt_event.get("metadata"))
    return PromptObservabilitySummary(
        prompt_event_count=len(prompt_events),
        last_prompt_event_id=_as_str(metadata.get("prompt_event_id")),
        last_prompt_event_surface=_as_str(metadata.get("surface")) or _as_str(last_payload.get("surface")),
    )
