"""Deed-to-IR mapping-submission AgentResultView builder."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tooling.mapping.deed_to_ir.mapping_review import compact_mapping_review_for_projection

from .finalization_result_views import (
    build_finalization_session_result_view_summary,
    resolve_session_summary_for_envelope,
)
from .result_view_common import bound_text, copy_scalar_fields, try_build_view, view_budget_omission

SCHEMA_SUBMIT_IR_FOR_MAPPING = "deed_to_ir.submit_ir_for_mapping.v1"

_MAPPING_IDENTITY_KEYS = (
    "mapping_artifact_ref",
    "compile_artifact_ref",
    "judge_artifact_ref",
    "geometry_ref",
    "clean_render_ref",
    "control_render_ref",
    "graph_id",
    "compiled_feature_count",
    "rendered_feature_count",
    "skipped_feature_count",
    "compile_gap_count",
    "judge_gap_count",
    "warning_count",
    "coordinate_space",
    "world_bbox",
)

_SANITY_DETAIL_KEYS = (
    "feature_metrics",
    "course_leg_tables",
    "endpoint_displacement_candidates",
    "recommended_source_evidence_refs",
    "review_questions",
)

_REVIEW_SKIP_KEYS = frozenset(
    {
        "sanity_review",
        "correction_posture",
        "draft_patch_targets",
        "active_handoff_context",
    }
)


def build_submit_ir_for_mapping_view(
    outputs: Mapping[str, Any],
    *,
    continuity_key: str | None,
):
    """Priority under envelope pressure (greedy keep; explicit omit on drop):

    1. Current mapping/IR lineage pair
    2. Bounded sanity conclusion/status
    3. Correction posture and draft patch targets
    4. Compact finalization-session summary
    5. Remaining review detail
    6. Active handoff and descriptive metadata
    """
    lineage_pair = _current_lineage_pair(outputs)
    payload = copy_scalar_fields(outputs, _MAPPING_IDENTITY_KEYS)
    if lineage_pair:
        payload["current_mapping_lineage"] = lineage_pair
        if lineage_pair.get("mapping_artifact_ref"):
            payload["mapping_artifact_ref"] = lineage_pair["mapping_artifact_ref"]
        if lineage_pair.get("source_ir_artifact_ref"):
            payload["ir_artifact_ref"] = lineage_pair["source_ir_artifact_ref"]

    view, omission = try_build_view(
        schema_id=SCHEMA_SUBMIT_IR_FOR_MAPPING,
        payload=payload,
        continuity_key=continuity_key,
    )
    if view is None:
        return None, omission

    raw_review = (
        outputs.get("mapping_review")
        if isinstance(outputs.get("mapping_review"), Mapping)
        else None
    )
    compact_review = compact_mapping_review_for_projection(raw_review)
    review: dict[str, Any] = {}

    sanity_core, sanity_detail = _split_sanity(compact_review, raw_review)
    if sanity_core:
        if not _set_review_field(
            payload, review, field="sanity_review", value=sanity_core, continuity_key=continuity_key
        ):
            # Keep bounded conclusion/status markers; drop summary-sized extras first.
            core_only = {
                key: sanity_core[key]
                for key in (
                    "conclusion",
                    "status",
                    "conclusion_omitted",
                    "conclusion_chars",
                    "status_omitted",
                    "status_chars",
                )
                if key in sanity_core
            }
            if core_only and _set_review_field(
                payload,
                review,
                field="sanity_review",
                value=core_only,
                continuity_key=continuity_key,
            ):
                dropped = [key for key in sanity_core if key not in core_only]
                if dropped:
                    payload["sanity_review_omitted"] = view_budget_omission(fields=dropped)
            else:
                payload["sanity_review_omitted"] = view_budget_omission(fields=["sanity_review"])

    repair = _repair_guidance(compact_review)
    if repair and not _merge_review_fields(
        payload, review, repair, continuity_key=continuity_key
    ):
        payload["mapping_repair_guidance_omitted"] = view_budget_omission(
            fields=list(repair.keys())
        )

    session = build_finalization_session_result_view_summary(
        outputs.get("active_finalization_session")
        if isinstance(outputs.get("active_finalization_session"), Mapping)
        else None
    )
    if session is not None:

        def _session_fits(candidate: Mapping[str, Any]) -> bool:
            trial = dict(payload)
            trial["active_finalization_session"] = dict(candidate)
            view, _ = try_build_view(
                schema_id=SCHEMA_SUBMIT_IR_FOR_MAPPING,
                payload=trial,
                continuity_key=continuity_key,
            )
            return view is not None

        resolved, markers = resolve_session_summary_for_envelope(
            session, fits=_session_fits
        )
        payload.update(markers)
        if resolved is not None:
            payload["active_finalization_session"] = resolved

    if sanity_detail and isinstance(review.get("sanity_review"), Mapping):
        enriched = dict(review["sanity_review"])
        enriched.update(sanity_detail)
        if not _set_review_field(
            payload,
            review,
            field="sanity_review",
            value=enriched,
            continuity_key=continuity_key,
        ):
            payload["sanity_review_detail_omitted"] = view_budget_omission(
                fields=list(sanity_detail.keys())
            )

    remaining = _remaining_review_fields(compact_review)
    if remaining and not _merge_review_fields(
        payload, review, remaining, continuity_key=continuity_key
    ):
        payload["mapping_review_detail_omitted"] = view_budget_omission(
            fields=list(remaining.keys())
        )

    handoff = outputs.get("active_handoff_context")
    if isinstance(handoff, Mapping) and handoff and not _set_payload_field(
        payload,
        key="active_handoff_context",
        value=dict(handoff),
        continuity_key=continuity_key,
    ):
        payload["active_handoff_context_omitted"] = view_budget_omission(
            fields=["active_handoff_context"]
        )

    return try_build_view(
        schema_id=SCHEMA_SUBMIT_IR_FOR_MAPPING,
        payload=payload,
        continuity_key=continuity_key,
    )


def _split_sanity(
    compact_review: Mapping[str, Any] | None,
    raw_review: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    compact_sanity = (
        compact_review.get("sanity_review") if isinstance(compact_review, Mapping) else None
    )
    raw_sanity = raw_review.get("sanity_review") if isinstance(raw_review, Mapping) else None
    source = compact_sanity if isinstance(compact_sanity, Mapping) else {}

    core: dict[str, Any] = {}
    for key in ("conclusion", "status"):
        value = None
        if isinstance(raw_sanity, Mapping):
            value = raw_sanity.get(key)
        if value in (None, "") and isinstance(source, Mapping):
            value = source.get(key)
        # Non-string values are omitted rather than coerced.
        if isinstance(value, str) and value.strip():
            bound = bound_text(value, field=key)
            if bound:
                core.update(bound)

    summary_source = None
    if isinstance(raw_sanity, Mapping) and isinstance(raw_sanity.get("summary"), str):
        summary_source = raw_sanity.get("summary")
    elif isinstance(source, Mapping) and isinstance(source.get("summary"), str):
        summary_source = source.get("summary")
    bound = bound_text(summary_source, field="summary")
    if bound:
        core.update(bound)

    detail: dict[str, Any] = {}
    if isinstance(source, Mapping):
        for key in _SANITY_DETAIL_KEYS:
            if key in source and source[key] is not None:
                detail[key] = source[key]
    return (core or None), detail


def _repair_guidance(compact_review: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(compact_review, Mapping):
        return {}
    out: dict[str, Any] = {}
    if compact_review.get("correction_posture") is not None:
        out["correction_posture"] = compact_review["correction_posture"]
    if compact_review.get("draft_patch_targets") is not None:
        out["draft_patch_targets"] = compact_review["draft_patch_targets"]
    return out


def _remaining_review_fields(compact_review: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(compact_review, Mapping):
        return {}
    return {
        key: value
        for key, value in compact_review.items()
        if key not in _REVIEW_SKIP_KEYS and value is not None
    }


def _set_payload_field(
    payload: dict[str, Any],
    *,
    key: str,
    value: Any,
    continuity_key: str | None,
) -> bool:
    trial = dict(payload)
    trial[key] = value
    view, _ = try_build_view(
        schema_id=SCHEMA_SUBMIT_IR_FOR_MAPPING,
        payload=trial,
        continuity_key=continuity_key,
    )
    if view is None:
        return False
    payload[key] = value
    return True


def _set_review_field(
    payload: dict[str, Any],
    review: dict[str, Any],
    *,
    field: str,
    value: Any,
    continuity_key: str | None,
) -> bool:
    trial_review = dict(review)
    trial_review[field] = value
    if not _set_payload_field(
        payload,
        key="mapping_review",
        value=trial_review,
        continuity_key=continuity_key,
    ):
        return False
    review.clear()
    review.update(trial_review)
    return True


def _merge_review_fields(
    payload: dict[str, Any],
    review: dict[str, Any],
    fields: Mapping[str, Any],
    *,
    continuity_key: str | None,
) -> bool:
    trial_review = dict(review)
    trial_review.update(dict(fields))
    if not _set_payload_field(
        payload,
        key="mapping_review",
        value=trial_review,
        continuity_key=continuity_key,
    ):
        return False
    review.clear()
    review.update(trial_review)
    return True


def _current_lineage_pair(outputs: Mapping[str, Any]) -> dict[str, Any] | None:
    lineage = outputs.get("current_mapping_lineage")
    if isinstance(lineage, Mapping):
        from tooling.mapping.deed_to_ir.mapping_lineage import (
            compact_current_mapping_lineage_for_projection,
        )

        compact = compact_current_mapping_lineage_for_projection(lineage)
        if compact is not None:
            return compact
    mapping_ref = outputs.get("mapping_artifact_ref")
    review = outputs.get("mapping_review")
    ir_ref = None
    top_ir = outputs.get("ir_artifact_ref")
    if isinstance(top_ir, str) and top_ir.strip():
        ir_ref = top_ir.strip()
    elif isinstance(review, Mapping):
        for key in ("source_ir_artifact_ref", "ir_artifact_ref"):
            candidate = review.get(key)
            if isinstance(candidate, str) and candidate.strip():
                ir_ref = candidate.strip()
                break
    if (
        isinstance(mapping_ref, str)
        and mapping_ref.strip()
        and isinstance(ir_ref, str)
        and ir_ref.strip()
    ):
        return {
            "mapping_artifact_ref": mapping_ref.strip(),
            "source_ir_artifact_ref": ir_ref.strip(),
            "lineage_current": True,
        }
    return None
