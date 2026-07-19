"""Draft patch-target whole-row fitting and omission accounting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Callable

from .result_view_common import ensure_payload_marker_fits, mapping_rows, try_build_view

MergeReviewFields = Callable[..., bool]
PayloadFits = Callable[[dict[str, Any]], bool]


def fit_draft_patch_targets(
    *,
    schema_id: str,
    payload: dict[str, Any],
    review: dict[str, Any],
    targets_raw: Any,
    continuity_key: str | None,
    merge_review_fields: MergeReviewFields,
    payload_fits: PayloadFits | None = None,
) -> None:
    if not isinstance(targets_raw, Sequence) or not targets_raw:
        return
    from tooling.mapping.deed_to_ir.draft_patch_targets import MAX_DRAFT_PATCH_TARGETS

    source_valid = sum(1 for item in targets_raw if isinstance(item, Mapping))
    rows, intake_omitted = mapping_rows(list(targets_raw), limit=MAX_DRAFT_PATCH_TARGETS)
    if not rows and intake_omitted <= 0:
        return

    kept: list[dict[str, Any]] = []
    for row in rows:
        trial_targets = kept + [dict(row)]
        if merge_review_fields(
            payload,
            review,
            {"draft_patch_targets": trial_targets},
            continuity_key=continuity_key,
        ):
            kept = trial_targets

    omitted = source_valid - len(kept)
    if omitted <= 0:
        return

    _set_patch_target_omitted_count(
        schema_id=schema_id,
        payload=payload,
        review=review,
        kept=kept,
        omitted=omitted,
        continuity_key=continuity_key,
        payload_fits=payload_fits,
    )


def peel_one_patch_target(
    *,
    payload: dict[str, Any],
    review: dict[str, Any],
) -> bool:
    targets = review.get("draft_patch_targets")
    if not isinstance(targets, list) or not targets:
        if review.pop("draft_patch_targets", None) is not None:
            payload["mapping_review"] = dict(review) if review else {}
            if not review:
                payload.pop("mapping_review", None)
            return True
        return False
    review["draft_patch_targets"] = targets[:-1]
    if not review["draft_patch_targets"]:
        review.pop("draft_patch_targets", None)
    payload["mapping_review"] = dict(review) if review else {}
    if not review:
        payload.pop("mapping_review", None)
    current = int(payload.get("draft_patch_targets_omitted_count") or 0)
    payload["draft_patch_targets_omitted_count"] = current + 1
    return True


def _set_patch_target_omitted_count(
    *,
    schema_id: str,
    payload: dict[str, Any],
    review: dict[str, Any],
    kept: list[dict[str, Any]],
    omitted: int,
    continuity_key: str | None,
    payload_fits: PayloadFits | None,
) -> None:
    if kept:
        review["draft_patch_targets"] = kept
        payload["mapping_review"] = dict(review)

    ensure_payload_marker_fits(
        payload,
        schema_id=schema_id,
        continuity_key=continuity_key,
        marker_key="draft_patch_targets_omitted_count",
        marker_value=omitted,
        peel=lambda: peel_one_patch_target(payload=payload, review=review),
    )
