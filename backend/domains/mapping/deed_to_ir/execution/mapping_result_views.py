"""Deed-to-IR mapping-submission AgentResultView builder."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tooling.mapping.deed_to_ir.mapping_review import compact_mapping_review_for_projection

from .finalization_result_views import (
    build_finalization_session_result_view_summary,
    resolve_session_summary_for_envelope,
)
from .mapping_patch_target_result_views import fit_draft_patch_targets, peel_one_patch_target
from .mapping_sanity_result_views import (
    compose_sanity_review,
    fit_sanity_head,
    fit_sanity_variable_detail,
    is_mapping_shaped_sanity,
    peel_one_sanity_variable_item,
)
from .result_view_common import (
    copy_scalar_fields,
    try_build_view,
    view_budget_omission,
)

SCHEMA_SUBMIT_IR_FOR_MAPPING = "deed_to_ir.submit_ir_for_mapping.v2"

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

    Protected core (jointly reserved):
    1. Current mapping/IR lineage and core artifact identity
    2. Mechanical sanity head
    3. Compact correction posture
    4. Compact active finalization session core

    Variable detail (after protected core):
    5. Additional sanity detail and optional prose
    6. Draft patch targets, fitted as whole rows
    7. Remaining mapping-review detail
    8. Active handoff and descriptive metadata
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
    compact_review = compact_mapping_review_for_projection(raw_review) or {}
    review: dict[str, Any] = {}

    session_summary = build_finalization_session_result_view_summary(
        outputs.get("active_finalization_session")
        if isinstance(outputs.get("active_finalization_session"), Mapping)
        else None
    )
    session_core = _session_core_only(session_summary)
    posture = _correction_posture(compact_review)

    raw_sanity = raw_review.get("sanity_review") if isinstance(raw_review, Mapping) else None
    sanity_collections = None
    sanity_prose: dict[str, Any] = {}
    if raw_sanity is not None:
        if not is_mapping_shaped_sanity(raw_sanity):
            payload["sanity_review_omitted"] = {"reason": "invalid_shape"}
        else:
            sanity_collections, sanity_prose = compose_sanity_review(compact_review, raw_review)
            if sanity_collections is not None:
                fit_sanity_head(
                    schema_id=SCHEMA_SUBMIT_IR_FOR_MAPPING,
                    payload=payload,
                    review=review,
                    collections=sanity_collections,
                    continuity_key=continuity_key,
                    protected_session=session_core,
                    protected_posture=posture,
                )

    if posture is not None and not _merge_review_fields(
        payload, review, {"correction_posture": posture}, continuity_key=continuity_key
    ):
        payload["correction_posture_omitted"] = view_budget_omission(
            fields=["correction_posture"]
        )

    if session_summary is not None:

        def _session_fits(candidate: Mapping[str, Any]) -> bool:
            return _payload_fits(
                payload,
                review,
                continuity_key=continuity_key,
                session=dict(candidate),
            )

        resolved, markers = resolve_session_summary_for_envelope(
            session_summary, fits=_session_fits
        )
        payload.update(markers)
        if resolved is not None:
            payload["active_finalization_session"] = resolved

    if sanity_collections is not None:
        fit_sanity_variable_detail(
            schema_id=SCHEMA_SUBMIT_IR_FOR_MAPPING,
            payload=payload,
            review=review,
            collections=sanity_collections,
            prose=sanity_prose,
            continuity_key=continuity_key,
            protected_session=None,
            protected_posture=None,
        )

    targets_source = raw_review if isinstance(raw_review, Mapping) else compact_review
    fit_draft_patch_targets(
        schema_id=SCHEMA_SUBMIT_IR_FOR_MAPPING,
        payload=payload,
        review=review,
        targets_raw=targets_source.get("draft_patch_targets"),
        continuity_key=continuity_key,
        merge_review_fields=_merge_review_fields,
        payload_fits=lambda candidate: _payload_fits_raw(
            candidate, continuity_key=continuity_key
        ),
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

    return _finalize_mapping_view(payload, review, continuity_key=continuity_key)


def _finalize_mapping_view(
    payload: dict[str, Any],
    review: dict[str, Any],
    *,
    continuity_key: str | None,
):
    view, omission = try_build_view(
        schema_id=SCHEMA_SUBMIT_IR_FOR_MAPPING,
        payload=payload,
        continuity_key=continuity_key,
    )
    if view is not None:
        return view, omission

    peelers = (
        _peel_handoff,
        _peel_remaining_review_detail,
        peel_one_patch_target,
        peel_one_sanity_variable_item,
    )
    for peeler in peelers:
        while peeler(payload=payload, review=review):
            view, omission = try_build_view(
                schema_id=SCHEMA_SUBMIT_IR_FOR_MAPPING,
                payload=payload,
                continuity_key=continuity_key,
            )
            if view is not None:
                return view, omission

    return try_build_view(
        schema_id=SCHEMA_SUBMIT_IR_FOR_MAPPING,
        payload=payload,
        continuity_key=continuity_key,
    )


def _session_core_only(session_summary: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(session_summary, Mapping):
        return None
    core = dict(session_summary)
    core.pop("diagnostics", None)
    return core


def _payload_fits(
    payload: dict[str, Any],
    review: dict[str, Any],
    *,
    continuity_key: str | None,
    session: Mapping[str, Any] | None = None,
) -> bool:
    trial = dict(payload)
    if session is not None:
        trial["active_finalization_session"] = dict(session)
    if review:
        trial["mapping_review"] = dict(review)
    view, _ = try_build_view(
        schema_id=SCHEMA_SUBMIT_IR_FOR_MAPPING,
        payload=trial,
        continuity_key=continuity_key,
    )
    return view is not None


def _payload_fits_raw(payload: dict[str, Any], *, continuity_key: str | None) -> bool:
    view, _ = try_build_view(
        schema_id=SCHEMA_SUBMIT_IR_FOR_MAPPING,
        payload=payload,
        continuity_key=continuity_key,
    )
    return view is not None


def _peel_handoff(payload: dict[str, Any], review: dict[str, Any]) -> bool:
    if "active_handoff_context" not in payload:
        return False
    payload.pop("active_handoff_context", None)
    payload["active_handoff_context_omitted"] = view_budget_omission(
        fields=["active_handoff_context"]
    )
    return True


def _peel_remaining_review_detail(payload: dict[str, Any], review: dict[str, Any]) -> bool:
    skip = _REVIEW_SKIP_KEYS | {"mapping_artifact_ref", "source_ir_artifact_ref"}
    protected = {"sanity_review", "correction_posture", "draft_patch_targets"}
    removable = [
        key
        for key in review
        if key not in protected
        and key not in skip
        and not _is_omission_marker_key(key)
    ]
    if not removable:
        return False
    for key in removable:
        review.pop(key, None)
    payload["mapping_review"] = dict(review) if review else {}
    if not review:
        payload.pop("mapping_review", None)
    payload["mapping_review_detail_omitted"] = view_budget_omission(fields=removable)
    return True


def _is_omission_marker_key(key: str) -> bool:
    return key.endswith("_omitted") or key.endswith("_omitted_count")


def _correction_posture(compact_review: Mapping[str, Any]) -> dict[str, Any] | None:
    posture = compact_review.get("correction_posture")
    if isinstance(posture, Mapping) and posture:
        return dict(posture)
    return None


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
