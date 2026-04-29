"""Prompt-event summarization for run-summary inspection."""

from __future__ import annotations

from typing import Any

from .common import _as_dict, _as_int, _as_str, _event_kind
from .models import ClosureReadinessProjection, PromptObservabilitySummary

_ZERO_INT_FIELDS = (
    "prompt_event_count",
    "consecutive_no_dispatch_turns",
    "repeated_state_patch_reason_code_streak",
    "consecutive_same_active_item_turns",
    "new_resolution_items_since_last_complete_run_attempt",
    "repeated_complete_run_without_state_change_count",
    "same_ref_bundle_reread_no_gain_streak",
    "same_item_same_ref_bundle_stall_streak",
    "same_item_hydrate_churn_no_gain_streak",
    "covered_unit_count",
    "covered_units_with_candidates_count",
    "closed_candidate_units_missing_determined_value_count",
    "closed_value_units_missing_evidence_count",
    "earned_units_missing_verification_basis_count",
    "success_condition_count",
    "success_conditions_with_earned_determination_count",
    "success_conditions_with_verification_basis_count",
    "resolution_item_count",
    "sequenced_item_count",
    "sequenced_items_missing_scope_count",
    "sequenced_items_missing_index_count",
    "duplicate_sequence_positions_count",
    "sequence_scope_order_gaps_count",
    "atomic_item_count",
    "group_item_count",
    "group_items_without_subclaims_count",
    "items_with_evidence_count",
    "items_with_verification_basis_count",
    "items_blocking_count",
    "items_requires_hitl_count",
    "items_no_further_progress_count",
    "closed_items_count",
    "closed_items_without_earned_determination_count",
    "closed_items_without_basis_count",
    "closed_items_without_completion_criteria_count",
    "critical_closed_items_without_evidence_count",
    "critical_closed_items_without_verification_basis_count",
    "blocking_items_without_relations_count",
    "closure_dimension_count",
    "closure_dimensions_with_earned_determination_count",
    "closed_dimensions_without_earned_determination_count",
    "closed_dimensions_without_basis_count",
    "closed_items_with_open_dependencies_count",
    "explicit_non_blocking_without_notes_count",
)
_OPTIONAL_INT_FIELDS = ("turns_since_last_tool_execution", "turns_since_latest_refs_change", "turns_since_last_state_patch_applied", "turns_since_resolution_item_count_change")
_STR_FIELDS = ("last_prompt_event_id", "last_state_patch_outcome", "last_state_patch_reason_code", "work_universe_posture")
def _nonblank_strs(values: Any) -> list[str]:
    return [value for value in values if isinstance(value, str) and value.strip()] if isinstance(values, list) else []
def _prompt_observability_summary_from_payload(
    payload: dict[str, Any], *, default_surface: str | None = None
) -> PromptObservabilitySummary:
    summary = payload.get("prompt_observability_summary")
    if not isinstance(summary, dict):
        return PromptObservabilitySummary(last_prompt_event_surface=_as_str(default_surface))
    readiness = _as_dict(summary.get("closure_readiness_projection"))
    data = {key: (_as_int(summary.get(key)) or 0) for key in _ZERO_INT_FIELDS}
    data.update({key: _as_int(summary.get(key)) for key in _OPTIONAL_INT_FIELDS})
    data.update({key: _as_str(summary.get(key)) for key in _STR_FIELDS})
    data["last_prompt_event_surface"] = _as_str(summary.get("last_prompt_event_surface")) or _as_str(default_surface)
    data["closure_readiness_projection"] = ClosureReadinessProjection(
        complete_run_blockers=_nonblank_strs(readiness.get("complete_run_blockers")),
        publish_blockers=_nonblank_strs(readiness.get("publish_blockers")),
    )
    data["mechanical_flags"] = _nonblank_strs(summary.get("mechanical_flags"))
    return PromptObservabilitySummary(**data)


def _prompt_observability_summary_from_trace_events(events: list[dict[str, Any]]) -> PromptObservabilitySummary:
    prompt_events = [
        event
        for event in events
        if _as_str(event.get("phase")) == "prompt_event"
        or _event_kind(event) == "prompt_event"
        or (isinstance(event.get("payload"), dict) and isinstance(event["payload"].get("prompt_event"), dict))
    ]
    last_payload = _as_dict(prompt_events[-1].get("payload")) if prompt_events else {}
    metadata = _as_dict(_as_dict(last_payload.get("prompt_event")).get("metadata"))
    return PromptObservabilitySummary(prompt_event_count=len(prompt_events), last_prompt_event_id=_as_str(metadata.get("prompt_event_id")), last_prompt_event_surface=_as_str(metadata.get("surface")) or _as_str(last_payload.get("surface")))
