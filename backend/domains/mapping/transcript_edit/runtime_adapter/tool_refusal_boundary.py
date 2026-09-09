"""Canonical agent-correctable refusal classification for transcript-edit tools.

Domain-owned boundary: reclassifies only explicit allowlisted reason codes per
action. Does not author semantic repair, select refs, or change harness policy.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

_RETRYABLE_REASON_CODES_BY_ACTION: dict[str, frozenset[str]] = {
    "hydrate_artifact_refs": frozenset(
        {
            "ref_ids_required",
            "ref_ids_invalid_type",
            "ref_id_invalid_type",
            "ref_ids_empty",
            "max_refs_invalid",
        }
    ),
    "transform_artifact": frozenset(
        {
            "ref_id_required",
            "unsupported_sub_action",
            "params_invalid",
            "dossier_ref_required",
            "dossier_ref_invalid",
            "dossier_ref_kind_not_runtime_resolvable",
            "dossier_ref_run_not_in_topology",
        }
    ),
    "save_workspace_artifact": frozenset(
        {
            "invalid_request",
            "managed_provenance_requires_apply_transcript_edits",
            "dossier_target_required",
            "dossier_target_lineage_mismatch",
            "dossier_base_revision_invalid",
            "dossier_base_revision_not_found",
            "dossier_ref_required",
            "dossier_ref_invalid",
            "dossier_ref_kind_not_runtime_resolvable",
            "dossier_ref_run_not_in_topology",
        }
    ),
    "copy_forward_save_workspace_artifact": frozenset(
        {
            "base_ref_required",
            "copy_forward_paths_required",
            "set_paths_required",
            "invalid_request",
            "invalid_base_ref",
            "too_many_paths",
            "invalid_path_syntax",
            "overlapping_paths",
            "base_ref_not_found",
            "missing_copy_paths",
            "managed_provenance_requires_apply_transcript_edits",
            "dossier_base_revision_required",
            "dossier_base_revision_invalid",
            "dossier_base_revision_not_found",
            "dossier_target_lineage_mismatch",
            "dossier_ref_required",
            "dossier_ref_invalid",
            "dossier_ref_kind_not_runtime_resolvable",
            "dossier_ref_run_not_in_topology",
        }
    ),
    "apply_transcript_edits": frozenset(
        {
            "invalid_request",
            "unknown_request_fields",
            "unknown_decision_fields",
            "unknown_edit_fields",
            "request_too_large",
            "base_revision_ref_required",
            "aggregate_base_revision_ref_rejected",
            "invalid_base_revision_ref",
            "decisions_required",
            "too_many_decisions",
            "duplicate_decision_id",
            "decision_id_required",
            "decision_id_too_long",
            "invalid_determination",
            "verification_basis_required",
            "verification_basis_too_long",
            "earned_requires_evidence_refs",
            "uncertainty_reasons_required",
            "provisional_requires_uncertainty_reasons",
            "earned_requires_empty_uncertainty_reasons",
            "invalid_uncertainty_reason",
            "duplicate_uncertainty_reason",
            "too_many_uncertainty_reasons",
            "too_many_persisted_decisions",
            "invalid_string_list",
            "invalid_string_list_item",
            "string_list_too_long",
            "edits_required",
            "too_many_edits",
            "invalid_edit",
            "invalid_edit_lane",
            "expected_text_required",
            "replacement_text_required",
            "edit_text_too_long",
            "invalid_context_text",
            "context_text_too_long",
            "edit_target_not_found",
            "edit_target_ambiguous",
            "overlapping_edit_ranges",
            "overlaps_other_decision_span",
            "transcript_lane_missing",
            "transcript_lane_not_string",
            "stale_base_revision",
            "working_head_missing",
            "managed_provenance_requires_apply_transcript_edits",
            "dossier_base_revision_required",
            "dossier_base_revision_invalid",
            "dossier_base_revision_not_found",
            "dossier_ref_required",
            "dossier_ref_invalid",
            "dossier_ref_kind_not_runtime_resolvable",
            "dossier_ref_run_not_in_topology",
            "invalid_evidence_ref",
        }
    ),
    "publish_workspace_artifact": frozenset(
        {
            "source_revision_ref_required",
            "invalid_source_revision_ref",
            "source_revision_not_found",
            "source_revision_refs_required",
            "invalid_publish_request",
            "invalid_selection_collection",
            "invalid_selection_entry",
            "duplicate_selected_ref",
            "segment_selection_conflict",
            "incomplete_segment_coverage",
            "unexpected_segment_selection",
            "ref_not_exact_working_revision",
            "ref_outside_topology",
            "malformed_revision_document",
            "transcript_lane_invalid",
            "invalid_evidence_ref",
            "unsafe_revision_content",
            "dossier_publication_in_progress",
            "dossier_publication_revision_write_failed",
            "dossier_publication_pointer_write_failed",
        }
    ),
}


def retryable_reason_codes_for_action(action_id: str) -> frozenset[str]:
    """Return the allowlisted retryable reason codes for one action (testing aid)."""
    return _RETRYABLE_REASON_CODES_BY_ACTION.get(str(action_id or "").strip(), frozenset())


def _nonblank_string(value: Any) -> str | None:
    if type(value) is not str:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def apply_tool_refusal_boundary(action_id: str, result: Any) -> Any:
    """Reclassify allowlisted agent-correctable refusals; leave all else unchanged."""
    if not isinstance(result, Mapping):
        return result

    normalized_action_id = _nonblank_string(action_id)
    if normalized_action_id is None:
        return dict(result)

    if result.get("executed") is True:
        return dict(result)

    if result.get("executed") is not False:
        return dict(result)

    refusal = result.get("refusal")
    if not isinstance(refusal, Mapping):
        return dict(result)

    reason_code = _nonblank_string(refusal.get("reason_code"))
    if reason_code is None:
        return dict(result)

    allowlist = _RETRYABLE_REASON_CODES_BY_ACTION.get(normalized_action_id)
    if allowlist is None or reason_code not in allowlist:
        return dict(result)

    if (
        refusal.get("retryable") is True
        and refusal.get("blocked_by_invariant") is False
        and refusal.get("blocked_by_budget") is False
    ):
        return dict(result)

    out = dict(result)
    out["refusal"] = {
        **dict(refusal),
        "retryable": True,
        "blocked_by_invariant": False,
        "blocked_by_budget": False,
    }
    return out


def wrap_handler_with_refusal_boundary(
    handler: Callable[[Any], Any],
    *,
    action_id: str,
) -> Callable[[Any], Any]:
    """Apply ``apply_tool_refusal_boundary`` to every handler return value."""

    def wrapped(request: Any) -> Any:
        raw = handler(request)
        return apply_tool_refusal_boundary(action_id, raw)

    return wrapped
