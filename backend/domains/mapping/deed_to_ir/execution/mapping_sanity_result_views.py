"""Sanity-review validation, composition, and incremental envelope fitting."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .result_view_common import bound_text, ensure_payload_marker_fits, try_build_view, view_budget_omission

MECHANICAL_SANITY_KEYS = frozenset(
    {
        "feature_metrics",
        "course_leg_tables",
        "endpoint_displacement_candidates",
        "recommended_source_evidence_refs",
        "review_questions",
    }
)

SANITY_PROSE_BOUND_KEYS = (
    "conclusion",
    "status",
    "summary",
    "conclusion_omitted",
    "conclusion_chars",
    "status_omitted",
    "status_chars",
    "summary_omitted",
    "summary_chars",
)

COLLECTION_OMISSION_KEYS = {
    "endpoint_displacement_candidates": "endpoint_displacement_candidates_omitted_count",
    "review_questions": "review_questions_omitted_count",
    "recommended_source_evidence_refs": "recommended_source_evidence_refs_omitted_count",
    "course_leg_tables": "course_leg_tables_omitted_count",
    "feature_metrics": "feature_metrics_omitted_count",
}

COURSES_OMITTED_COUNT_KEY = "courses_omitted_count"


def is_mapping_shaped_sanity(raw: Any) -> bool:
    if not isinstance(raw, Mapping):
        return False
    allowed = MECHANICAL_SANITY_KEYS | {"conclusion", "status", "summary"}
    return any(key in raw for key in allowed)


def compose_sanity_review(
    compact_review: Mapping[str, Any],
    raw_review: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return compact sanity collections and separately bounded optional prose."""
    compact_sanity = compact_review.get("sanity_review")
    if not isinstance(compact_sanity, Mapping):
        return None, {}

    collections = dict(compact_sanity)
    for key in SANITY_PROSE_BOUND_KEYS:
        collections.pop(key, None)

    prose: dict[str, Any] = {}
    raw_sanity = raw_review.get("sanity_review") if isinstance(raw_review, Mapping) else None
    for key in ("conclusion", "status"):
        value = raw_sanity.get(key) if isinstance(raw_sanity, Mapping) else None
        if isinstance(value, str) and value.strip():
            bound = bound_text(value, field=key)
            if bound:
                prose.update(bound)
    summary_source = None
    if isinstance(raw_sanity, Mapping) and isinstance(raw_sanity.get("summary"), str):
        summary_source = raw_sanity.get("summary")
    bound = bound_text(summary_source, field="summary")
    if bound:
        prose.update(bound)

    return collections, prose


def initial_omitted_counts(collections: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for collection_key, omitted_key in COLLECTION_OMISSION_KEYS.items():
        value = collections.get(omitted_key)
        if isinstance(value, int) and value > 0:
            counts[omitted_key] = value
    courses_omitted = collections.get(COURSES_OMITTED_COUNT_KEY)
    if isinstance(courses_omitted, int) and courses_omitted > 0:
        counts[COURSES_OMITTED_COUNT_KEY] = courses_omitted
    return counts


def fit_sanity_head(
    *,
    schema_id: str,
    payload: dict[str, Any],
    review: dict[str, Any],
    collections: Mapping[str, Any],
    continuity_key: str | None,
    protected_session: Mapping[str, Any] | None,
    protected_posture: Mapping[str, Any] | None,
) -> None:
    """Incrementally fit protected sanity head collections."""
    omitted_counts = initial_omitted_counts(collections)
    sanity: dict[str, Any] = dict(omitted_counts)

    def fits(candidate: Mapping[str, Any]) -> bool:
        return _protected_fits(
            schema_id=schema_id,
            payload=payload,
            review=review,
            sanity=dict(candidate),
            continuity_key=continuity_key,
            protected_session=protected_session,
            protected_posture=protected_posture,
        )

    _fit_displacement_candidates(
        sanity,
        collections.get("endpoint_displacement_candidates"),
        omitted_counts,
        fits=fits,
    )
    _fit_string_collection(
        sanity,
        key="review_questions",
        items=collections.get("review_questions"),
        omitted_counts=omitted_counts,
        fits=fits,
    )
    _fit_string_collection(
        sanity,
        key="recommended_source_evidence_refs",
        items=collections.get("recommended_source_evidence_refs"),
        omitted_counts=omitted_counts,
        fits=fits,
    )
    _fit_course_leg_tables(
        sanity,
        collections.get("course_leg_tables"),
        omitted_counts=omitted_counts,
        fits=fits,
    )

    if sanity and fits(sanity):
        review["sanity_review"] = sanity
        payload["mapping_review"] = dict(review)
    elif sanity:
        marker = view_budget_omission(fields=["sanity_review"])
        ensure_payload_marker_fits(
            payload,
            schema_id=schema_id,
            continuity_key=continuity_key,
            marker_key="sanity_review_omitted",
            marker_value=marker,
            peel=lambda: peel_one_sanity_variable_item(review=review, payload=payload),
        )


def fit_sanity_variable_detail(
    *,
    schema_id: str,
    payload: dict[str, Any],
    review: dict[str, Any],
    collections: Mapping[str, Any],
    prose: Mapping[str, Any],
    continuity_key: str | None,
    protected_session: Mapping[str, Any] | None,
    protected_posture: Mapping[str, Any] | None,
) -> None:
    """Add lower-priority sanity detail after protected head is committed."""
    sanity = review.get("sanity_review")
    if not isinstance(sanity, Mapping):
        return

    omitted_counts = initial_omitted_counts(collections)
    sanity = dict(sanity)

    def fits(candidate: Mapping[str, Any]) -> bool:
        return _protected_fits(
            schema_id=schema_id,
            payload=payload,
            review=review,
            sanity=dict(candidate),
            continuity_key=continuity_key,
            protected_session=protected_session,
            protected_posture=protected_posture,
        )

    _fit_metric_rows(
        sanity,
        collections.get("feature_metrics"),
        omitted_counts=omitted_counts,
        fits=fits,
    )
    if prose:
        trial = dict(sanity)
        trial.update(dict(prose))
        if fits(trial):
            sanity.update(prose)
        else:
            optional_fields = [key for key in prose if key in SANITY_PROSE_BOUND_KEYS]
            if optional_fields:
                marker = view_budget_omission(fields=optional_fields)
                review["sanity_review"] = sanity
                payload["mapping_review"] = dict(review)

                def _peel_for_prose_marker() -> bool:
                    if peel_one_sanity_variable_item(review=review, payload=payload):
                        nonlocal sanity
                        updated = review.get("sanity_review")
                        if isinstance(updated, Mapping):
                            sanity = dict(updated)
                        return True
                    return False

                ensure_payload_marker_fits(
                    payload,
                    schema_id=schema_id,
                    continuity_key=continuity_key,
                    marker_key="sanity_review_detail_omitted",
                    marker_value=marker,
                    peel=_peel_for_prose_marker,
                )

    review["sanity_review"] = sanity
    payload["mapping_review"] = dict(review)


def peel_one_sanity_variable_item(
    *,
    review: dict[str, Any],
    payload: dict[str, Any],
) -> bool:
    """Remove one lowest-priority sanity variable item; update omission counts."""
    sanity = review.get("sanity_review")
    if not isinstance(sanity, Mapping):
        return False

    for key in SANITY_PROSE_BOUND_KEYS:
        if key in sanity:
            updated = dict(sanity)
            updated.pop(key, None)
            review["sanity_review"] = updated
            payload["mapping_review"] = dict(review)
            marker = view_budget_omission(fields=[key])
            if "sanity_review_detail_omitted" in payload:
                return True
            payload["sanity_review_detail_omitted"] = marker
            return True

    metrics = sanity.get("feature_metrics")
    if isinstance(metrics, list) and metrics:
        updated = dict(sanity)
        updated_metrics = list(metrics[:-1])
        if updated_metrics:
            updated["feature_metrics"] = updated_metrics
        else:
            updated.pop("feature_metrics", None)
        _increment_omitted_count(updated, "feature_metrics_omitted_count", 1)
        review["sanity_review"] = updated
        payload["mapping_review"] = dict(review)
        return True

    tables = sanity.get("course_leg_tables")
    if isinstance(tables, list) and tables:
        updated = dict(sanity)
        last_table = dict(tables[-1])
        courses = last_table.get("courses")
        if isinstance(courses, list) and len(courses) > 1:
            last_table["courses"] = courses[:-1]
            updated["course_leg_tables"] = list(tables[:-1]) + [last_table]
            _increment_omitted_count(updated, COURSES_OMITTED_COUNT_KEY, 1)
        else:
            updated["course_leg_tables"] = list(tables[:-1])
            _increment_omitted_count(updated, "course_leg_tables_omitted_count", 1)
        review["sanity_review"] = updated
        payload["mapping_review"] = dict(review)
        return True

    return False


def _protected_fits(
    *,
    schema_id: str,
    payload: Mapping[str, Any],
    review: Mapping[str, Any],
    sanity: Mapping[str, Any],
    continuity_key: str | None,
    protected_session: Mapping[str, Any] | None,
    protected_posture: Mapping[str, Any] | None,
) -> bool:
    trial = dict(payload)
    if protected_session is not None:
        trial["active_finalization_session"] = dict(protected_session)
    mapping_review = dict(review)
    if protected_posture is not None and "correction_posture" not in mapping_review:
        mapping_review["correction_posture"] = dict(protected_posture)
    if sanity:
        mapping_review["sanity_review"] = dict(sanity)
    if mapping_review:
        trial["mapping_review"] = mapping_review
    view, _ = try_build_view(
        schema_id=schema_id,
        payload=trial,
        continuity_key=continuity_key,
    )
    return view is not None


def _fit_displacement_candidates(
    sanity: dict[str, Any],
    raw: Any,
    omitted_counts: dict[str, int],
    *,
    fits: Callable[[Mapping[str, Any]], bool],
) -> None:
    if not isinstance(raw, list):
        return
    kept: list[dict[str, Any]] = []
    source_valid = sum(1 for item in raw if isinstance(item, Mapping))
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        trial = kept + [dict(item)]
        candidate = dict(sanity)
        candidate["endpoint_displacement_candidates"] = trial
        _apply_omitted(candidate, omitted_counts, "endpoint_displacement_candidates_omitted_count", source_valid - len(trial))
        if fits(candidate):
            kept = trial
            sanity["endpoint_displacement_candidates"] = kept
            _apply_omitted(sanity, omitted_counts, "endpoint_displacement_candidates_omitted_count", source_valid - len(kept))
    if kept:
        sanity["endpoint_displacement_candidates"] = kept
    elif source_valid:
        _apply_omitted(sanity, omitted_counts, "endpoint_displacement_candidates_omitted_count", source_valid)


def _fit_string_collection(
    sanity: dict[str, Any],
    *,
    key: str,
    items: Any,
    omitted_counts: dict[str, int],
    fits: Callable[[Mapping[str, Any]], bool],
) -> None:
    if not isinstance(items, list):
        return
    kept: list[str] = []
    source_valid = sum(1 for item in items if isinstance(item, str) and item.strip())
    omitted_key = COLLECTION_OMISSION_KEYS[key]
    for item in items:
        if not isinstance(item, str) or not item.strip():
            continue
        trial = kept + [item.strip()]
        candidate = dict(sanity)
        candidate[key] = trial
        _apply_omitted(candidate, omitted_counts, omitted_key, source_valid - len(trial))
        if fits(candidate):
            kept = trial
            sanity[key] = kept
            _apply_omitted(sanity, omitted_counts, omitted_key, source_valid - len(kept))
    if kept:
        sanity[key] = kept
    elif source_valid:
        _apply_omitted(sanity, omitted_counts, omitted_key, source_valid)


def _fit_metric_rows(
    sanity: dict[str, Any],
    raw: Any,
    *,
    omitted_counts: dict[str, int],
    fits: Callable[[Mapping[str, Any]], bool],
) -> None:
    if not isinstance(raw, list):
        return
    kept: list[dict[str, Any]] = []
    source_valid = sum(
        1
        for item in raw
        if isinstance(item, Mapping) and not item.get("skipped")
    )
    for item in raw:
        if not isinstance(item, Mapping) or item.get("skipped"):
            continue
        trial = kept + [dict(item)]
        candidate = dict(sanity)
        candidate["feature_metrics"] = trial
        _apply_omitted(candidate, omitted_counts, "feature_metrics_omitted_count", source_valid - len(trial))
        if fits(candidate):
            kept = trial
            sanity["feature_metrics"] = kept
            _apply_omitted(sanity, omitted_counts, "feature_metrics_omitted_count", source_valid - len(kept))
    if kept:
        sanity["feature_metrics"] = kept
    elif source_valid:
        _apply_omitted(sanity, omitted_counts, "feature_metrics_omitted_count", source_valid)


def _fit_course_leg_tables(
    sanity: dict[str, Any],
    raw: Any,
    *,
    omitted_counts: dict[str, int],
    fits: Callable[[Mapping[str, Any]], bool],
) -> None:
    if not isinstance(raw, list):
        return
    compact_tables = [table for table in raw if isinstance(table, Mapping)]
    if not compact_tables:
        return

    tooling_table_omitted = int(omitted_counts.get("course_leg_tables_omitted_count") or 0)

    kept_tables: list[dict[str, Any]] = []
    for table in compact_tables:
        shell = {
            key: table.get(key)
            for key in ("feature_id", "course_count", "operation")
            if table.get(key) is not None
        }
        courses = table.get("courses")
        if not isinstance(courses, list):
            continue
        built_courses: list[dict[str, Any]] = []
        for course in courses:
            if not isinstance(course, Mapping):
                continue
            trial_courses = built_courses + [dict(course)]
            trial_table = {**shell, "courses": trial_courses}
            if (
                kept_tables
                and kept_tables[-1].get("feature_id") == shell.get("feature_id")
            ):
                trial_tables = kept_tables[:-1] + [trial_table]
            else:
                trial_tables = kept_tables + [trial_table]
            candidate = dict(sanity)
            candidate["course_leg_tables"] = trial_tables
            _apply_table_course_omitted(
                candidate,
                compact_tables=compact_tables,
                kept_tables=trial_tables,
                tooling_table_omitted=tooling_table_omitted,
            )
            if fits(candidate):
                built_courses = trial_courses
                kept_tables = trial_tables
                sanity["course_leg_tables"] = kept_tables
                _apply_table_course_omitted(
                    sanity,
                    compact_tables=compact_tables,
                    kept_tables=kept_tables,
                    tooling_table_omitted=tooling_table_omitted,
                )

    if not kept_tables and compact_tables:
        _apply_table_course_omitted(
            sanity,
            compact_tables=compact_tables,
            kept_tables=kept_tables,
            tooling_table_omitted=tooling_table_omitted,
        )


def _apply_table_course_omitted(
    sanity: dict[str, Any],
    *,
    compact_tables: list[Mapping[str, Any]],
    kept_tables: list[Mapping[str, Any]],
    tooling_table_omitted: int,
) -> None:
    compact_table_count = len(compact_tables)
    kept_table_count = len(kept_tables)
    pressure_table_omitted = max(0, compact_table_count - kept_table_count)
    total_table_omitted = tooling_table_omitted + pressure_table_omitted

    pressure_course_omitted = 0
    tooling_course_for_represented = 0
    for table in kept_tables:
        feature_id = table.get("feature_id")
        compact_match = next(
            (candidate for candidate in compact_tables if candidate.get("feature_id") == feature_id),
            None,
        )
        if compact_match is None:
            continue
        source_courses = int(compact_match.get("courses_source_count") or 0)
        if source_courses <= 0:
            source_courses = len(compact_match.get("courses") or [])
        compact_courses = len(compact_match.get("courses") or [])
        kept_courses = len(table.get("courses") or [])
        tooling_course_for_represented += max(0, source_courses - compact_courses)
        pressure_course_omitted += max(0, compact_courses - kept_courses)

    total_course_omitted = tooling_course_for_represented + pressure_course_omitted

    if total_table_omitted:
        sanity["course_leg_tables_omitted_count"] = total_table_omitted
    elif "course_leg_tables_omitted_count" in sanity:
        sanity.pop("course_leg_tables_omitted_count", None)

    if total_course_omitted:
        sanity[COURSES_OMITTED_COUNT_KEY] = total_course_omitted
    elif COURSES_OMITTED_COUNT_KEY in sanity:
        sanity.pop(COURSES_OMITTED_COUNT_KEY, None)


def _apply_omitted(
    sanity: dict[str, Any],
    omitted_counts: dict[str, int],
    omitted_key: str,
    pressure_omitted: int,
) -> None:
    tooling = int(omitted_counts.get(omitted_key) or 0)
    total = tooling + max(0, pressure_omitted)
    if total:
        sanity[omitted_key] = total
    elif omitted_key in sanity:
        sanity.pop(omitted_key, None)


def _increment_omitted_count(sanity: dict[str, Any], omitted_key: str, delta: int) -> None:
    current = int(sanity.get(omitted_key) or 0)
    sanity[omitted_key] = current + delta
