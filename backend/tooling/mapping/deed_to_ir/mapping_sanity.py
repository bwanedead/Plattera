"""Mapping sanity review packet: mechanical geometry facts and course leg tables."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from feature_graph.artifacts import CompileArtifact
from feature_graph.models import FeatureGraph, FeatureNode
from feature_graph.rendering.sanity_metrics import (
    build_endpoint_displacement_candidates,
    compute_feature_geometry_metrics,
)

MAX_FEATURE_METRICS = 16
MAX_COURSE_LEG_TABLES = 8
MAX_COURSE_ROWS = 24
MAX_EVIDENCE_REFS = 12
MAX_RECOMMENDED_EVIDENCE_REFS = 12

MAX_PROJECTED_FEATURE_METRICS = 4
MAX_PROJECTED_COURSE_LEG_TABLES = 2
MAX_PROJECTED_COURSE_ROWS = 6
MAX_PROJECTED_DISPLACEMENT_CANDIDATES = 4
MAX_PROJECTED_RECOMMENDED_EVIDENCE_REFS = 6
MAX_PROJECTED_REVIEW_QUESTIONS = 4

_COURSE_ROW_PROJECTION_KEYS = (
    "leg_index",
    "bearing",
    "distance",
    "bearing_raw",
    "distance_raw",
    "source_entity_ids",
    "source_entity_ids_reason",
    "evidence_refs",
    "evidence_refs_reason",
)

GENERIC_REVIEW_QUESTIONS = [
    "Does endpoint displacement matter for the authored geometry role?",
    "If this feature was expected to close, inspect contributing course operands before declaring an open limitation.",
    "Station chains, centerlines, routes, strips, and intentionally open alignments may not close.",
    "Large unexplained endpoint displacement is a source-sanity trigger, not automatically a deed defect.",
]

_CALL_ENTITY_PATTERN = re.compile(r"_call(\d+)_", re.IGNORECASE)

AMBIGUOUS_OPERAND_FAMILY_REASON = "ambiguous_operand_family"


def build_operand_evidence_index(resolution_state_snapshot: Mapping[str, Any] | None) -> dict[str, list[str]]:
    """Mechanically index evidence refs by upstream unit/entity id from resolution snapshot."""
    if not isinstance(resolution_state_snapshot, Mapping):
        return {}
    index: dict[str, list[str]] = {}
    items = resolution_state_snapshot.get("items")
    if not isinstance(items, list):
        return index
    for item in items:
        if not isinstance(item, Mapping):
            continue
        covered = item.get("covered_units")
        if not isinstance(covered, list):
            continue
        for unit in covered:
            if not isinstance(unit, Mapping):
                continue
            unit_id = str(unit.get("unit_id") or "").strip()
            if not unit_id:
                continue
            refs = unit.get("evidence_refs")
            if not isinstance(refs, list):
                continue
            collected = [str(ref).strip() for ref in refs if isinstance(ref, str) and str(ref).strip()]
            if collected:
                index[unit_id] = collected[:MAX_EVIDENCE_REFS]
    return index


def _call_family_prefix(entity_id: str) -> str | None:
    """Stable entity-family prefix through the matching call segment (e.g. ``p1_call2_``)."""
    match = _CALL_ENTITY_PATTERN.search(entity_id)
    if match is None:
        return None
    return entity_id[: match.end()]


def _entity_ids_for_leg(source_entity_ids: list[str], leg_index: int) -> list[str]:
    matched: list[str] = []
    for entity_id in source_entity_ids:
        match = _CALL_ENTITY_PATTERN.search(entity_id)
        if match is not None and int(match.group(1)) == leg_index:
            matched.append(entity_id)
            continue
        if entity_id.lower().endswith(f"call{leg_index}"):
            matched.append(entity_id)
    return matched


def _entity_ids_from_operand_index_for_leg(
    operand_evidence_index: dict[str, list[str]] | None,
    leg_index: int,
) -> list[str]:
    if not operand_evidence_index:
        return []
    matched: list[str] = []
    for unit_id in operand_evidence_index:
        match = _CALL_ENTITY_PATTERN.search(unit_id)
        if match is not None and int(match.group(1)) == leg_index:
            matched.append(unit_id)
    return matched


def _order_entity_ids(entity_ids: list[str]) -> list[str]:
    combined = list(dict.fromkeys(entity_ids))
    distance_ids = [entity_id for entity_id in combined if _entity_value_kind(entity_id) == "distance"]
    bearing_ids = [entity_id for entity_id in combined if _entity_value_kind(entity_id) == "bearing"]
    other_ids = [
        entity_id
        for entity_id in combined
        if entity_id not in distance_ids and entity_id not in bearing_ids
    ]
    return distance_ids + bearing_ids + other_ids


def _resolve_leg_entity_binding(
    *,
    source_entity_ids: list[str],
    operand_evidence_index: dict[str, list[str]] | None,
    leg_index: int,
) -> tuple[list[str], str | None]:
    """Resolve course-leg entity IDs with provenance-safe family binding."""
    linked = _entity_ids_for_leg(source_entity_ids, leg_index)
    if linked:
        families = {
            prefix
            for entity_id in linked
            if (prefix := _call_family_prefix(entity_id)) is not None
        }
        if not families:
            return _order_entity_ids(linked), None

        linked_set = set(linked)
        family_represented_kinds: dict[str, set[str]] = {}
        for entity_id in linked:
            prefix = _call_family_prefix(entity_id)
            if prefix is None:
                continue
            kind = _entity_value_kind(entity_id)
            if kind is not None:
                family_represented_kinds.setdefault(prefix, set()).add(kind)
        supplemented = list(linked)
        for entity_id in _entity_ids_from_operand_index_for_leg(operand_evidence_index, leg_index):
            if entity_id in linked_set:
                continue
            prefix = _call_family_prefix(entity_id)
            if prefix is None or prefix not in families:
                continue
            kind = _entity_value_kind(entity_id)
            if kind not in ("distance", "bearing"):
                continue
            if kind in family_represented_kinds.setdefault(prefix, set()):
                continue
            supplemented.append(entity_id)
            linked_set.add(entity_id)
            family_represented_kinds[prefix].add(kind)
        return _order_entity_ids(supplemented), None

    indexed_matches = _entity_ids_from_operand_index_for_leg(operand_evidence_index, leg_index)
    if not indexed_matches:
        return [], None

    by_family: dict[str, list[str]] = {}
    for entity_id in indexed_matches:
        prefix = _call_family_prefix(entity_id)
        family_key = prefix if prefix is not None else f"__solo__:{entity_id}"
        by_family.setdefault(family_key, []).append(entity_id)

    if len(by_family) != 1:
        return [], AMBIGUOUS_OPERAND_FAMILY_REASON

    sole_family = next(iter(by_family.values()))
    return _order_entity_ids(sole_family), None


def _entity_value_kind(entity_id: str) -> str | None:
    lower = entity_id.lower()
    if "distance" in lower:
        return "distance"
    if "bearing" in lower:
        return "bearing"
    return None


def ordered_entity_ids_for_leg(
    *,
    source_entity_ids: list[str],
    operand_evidence_index: dict[str, list[str]] | None,
    leg_index: int,
) -> list[str]:
    """Public helper: order source entity ids for a course leg (distance before bearing)."""
    entity_ids, _reason = _resolve_leg_entity_binding(
        source_entity_ids=source_entity_ids,
        operand_evidence_index=operand_evidence_index,
        leg_index=leg_index,
    )
    return entity_ids


def _ordered_evidence_refs_for_entities(
    entity_ids: list[str],
    operand_evidence_index: dict[str, list[str]] | None,
) -> list[str]:
    if not entity_ids or not operand_evidence_index:
        return []
    refs: list[str] = []
    seen: set[str] = set()
    for entity_id in entity_ids:
        for ref in operand_evidence_index.get(entity_id, []):
            if ref in seen:
                continue
            seen.add(ref)
            refs.append(ref)
            if len(refs) >= MAX_EVIDENCE_REFS:
                return refs
    return refs


def _source_entity_ids_from_node(node: FeatureNode) -> list[str]:
    provenance = node.provenance
    if provenance is None or not provenance.source_entity_links:
        return []
    return [link.entity_id for link in provenance.source_entity_links if link.entity_id.strip()]


def _evidence_refs_for_entities(
    entity_ids: list[str],
    operand_evidence_index: dict[str, list[str]] | None,
) -> list[str]:
    if not entity_ids or not operand_evidence_index:
        return []
    refs: list[str] = []
    seen: set[str] = set()
    for entity_id in entity_ids:
        for ref in operand_evidence_index.get(entity_id, []):
            if ref in seen:
                continue
            seen.add(ref)
            refs.append(ref)
            if len(refs) >= MAX_EVIDENCE_REFS:
                return refs
    return refs


def build_course_leg_table(
    *,
    node: FeatureNode,
    compiled_entry: Mapping[str, Any],
    operand_evidence_index: dict[str, list[str]] | None = None,
) -> dict[str, Any] | None:
    """Build a compact per-leg table for CourseTraverse-derived features."""
    op_expr = node.op_expr
    if op_expr is None or str(op_expr.op_name or "") != "CourseTraverse":
        return None

    courses = compiled_entry.get("courses")
    if not isinstance(courses, list) or not courses:
        params = op_expr.params if isinstance(op_expr.params, dict) else {}
        param_courses = params.get("courses")
        courses = param_courses if isinstance(param_courses, list) else None
    if not isinstance(courses, list) or not courses:
        return None

    all_entity_ids = _source_entity_ids_from_node(node)
    rows: list[dict[str, Any]] = []
    for index, raw_course in enumerate(courses[:MAX_COURSE_ROWS]):
        if not isinstance(raw_course, Mapping):
            continue
        leg_index = index + 1
        source_entity_ids, binding_reason = _resolve_leg_entity_binding(
            source_entity_ids=all_entity_ids,
            operand_evidence_index=operand_evidence_index,
            leg_index=leg_index,
        )
        if not source_entity_ids and all_entity_ids and len(courses) == 1:
            source_entity_ids = list(all_entity_ids)
            binding_reason = None
        evidence_refs = _ordered_evidence_refs_for_entities(source_entity_ids, operand_evidence_index)
        row: dict[str, Any] = {"leg_index": leg_index}
        bearing = raw_course.get("bearing")
        distance = raw_course.get("distance")
        if isinstance(bearing, (int, float)):
            row["bearing"] = float(bearing)
        if isinstance(distance, (int, float)):
            row["distance"] = float(distance)
        bearing_raw = raw_course.get("bearing_raw")
        distance_raw = raw_course.get("distance_raw")
        if isinstance(bearing_raw, str) and bearing_raw.strip():
            row["bearing_raw"] = bearing_raw.strip()
        if isinstance(distance_raw, str) and distance_raw.strip():
            row["distance_raw"] = distance_raw.strip()
        if source_entity_ids:
            row["source_entity_ids"] = source_entity_ids
        elif binding_reason:
            row["source_entity_ids_reason"] = binding_reason
        row["evidence_refs"] = evidence_refs
        if not evidence_refs:
            row["evidence_refs_reason"] = (
                binding_reason if binding_reason else "no_operand_evidence_indexed"
            )
        rows.append(row)

    if not rows:
        return None
    return {
        "feature_id": node.id,
        "operation": "CourseTraverse",
        "course_count": len(rows),
        "courses": rows,
    }


def build_mapping_sanity_review(
    *,
    graph: FeatureGraph,
    compile_artifact: CompileArtifact,
    operand_evidence_index: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Assemble mechanical mapping sanity facts for agent review."""
    compiled = compile_artifact.compiled_features or {}
    node_by_id = {node.id: node for node in graph.nodes}

    feature_metrics: list[dict[str, Any]] = []
    course_leg_tables: list[dict[str, Any]] = []

    for feature_id, entry in compiled.items():
        if not isinstance(entry, Mapping):
            continue
        if len(feature_metrics) < MAX_FEATURE_METRICS:
            feature_metrics.append(
                compute_feature_geometry_metrics(feature_id=str(feature_id), compiled_entry=entry)
            )
        node = node_by_id.get(str(feature_id))
        if node is None or len(course_leg_tables) >= MAX_COURSE_LEG_TABLES:
            continue
        leg_table = build_course_leg_table(
            node=node,
            compiled_entry=entry,
            operand_evidence_index=operand_evidence_index,
        )
        if leg_table is not None:
            course_leg_tables.append(leg_table)

    endpoint_displacement_candidates = build_endpoint_displacement_candidates(feature_metrics)
    recommended_source_evidence_refs = _collect_recommended_source_evidence_refs(course_leg_tables)

    return {
        "feature_metrics": feature_metrics,
        "course_leg_tables": course_leg_tables,
        "endpoint_displacement_candidates": endpoint_displacement_candidates,
        "recommended_source_evidence_refs": recommended_source_evidence_refs,
        "review_questions": list(GENERIC_REVIEW_QUESTIONS),
    }


def _collect_recommended_source_evidence_refs(course_leg_tables: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for table in course_leg_tables:
        courses = table.get("courses")
        if not isinstance(courses, list):
            continue
        for course in courses:
            if not isinstance(course, Mapping):
                continue
            evidence = course.get("evidence_refs")
            if not isinstance(evidence, list):
                continue
            for ref in evidence:
                if not isinstance(ref, str) or not ref.strip():
                    continue
                text = ref.strip()
                if text in seen:
                    continue
                seen.add(text)
                refs.append(text)
                if len(refs) >= MAX_RECOMMENDED_EVIDENCE_REFS:
                    return refs
    return refs


def _compact_metric_rows(raw: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(raw, list):
        return [], 0
    valid: list[dict[str, Any]] = []
    for metric in raw:
        if not isinstance(metric, Mapping) or metric.get("skipped"):
            continue
        row = {
            "feature_id": metric.get("feature_id"),
            "endpoint_displacement": metric.get("endpoint_displacement"),
            "total_length": metric.get("total_length"),
            "vertex_count": metric.get("vertex_count"),
        }
        compact_row = {key: value for key, value in row.items() if value is not None}
        if compact_row:
            valid.append(compact_row)
    intake_omitted = max(0, len(valid) - MAX_PROJECTED_FEATURE_METRICS)
    return valid[:MAX_PROJECTED_FEATURE_METRICS], intake_omitted


def _compact_course_row(course: Mapping[str, Any]) -> dict[str, Any] | None:
    row = {
        key: course.get(key)
        for key in _COURSE_ROW_PROJECTION_KEYS
        if course.get(key) is not None
    }
    return row or None


def _compact_course_leg_tables(raw: Any) -> tuple[list[dict[str, Any]], int, int]:
    if not isinstance(raw, list):
        return [], 0, 0
    staged: list[tuple[dict[str, Any], int]] = []
    for table in raw:
        if not isinstance(table, Mapping):
            continue
        raw_courses = table.get("courses")
        valid_courses: list[dict[str, Any]] = []
        if isinstance(raw_courses, list):
            for course in raw_courses:
                if not isinstance(course, Mapping):
                    continue
                compact_course = _compact_course_row(course)
                if compact_course is not None:
                    valid_courses.append(compact_course)
        table_row = {
            "feature_id": table.get("feature_id"),
            "course_count": table.get("course_count"),
            "courses": valid_courses[:MAX_PROJECTED_COURSE_ROWS],
        }
        if valid_courses:
            table_row["courses_source_count"] = len(valid_courses)
        if table_row.get("feature_id") is not None or valid_courses:
            staged.append((table_row, len(valid_courses)))
    tables_omitted = max(0, len(staged) - MAX_PROJECTED_COURSE_LEG_TABLES)
    kept_staged = staged[:MAX_PROJECTED_COURSE_LEG_TABLES]
    kept_tables = [row for row, _ in kept_staged]
    courses_omitted = sum(
        max(0, source_count - len(row.get("courses") or []))
        for row, source_count in kept_staged
    )
    return kept_tables, tables_omitted, courses_omitted


_DISPLACEMENT_CANDIDATE_KEYS = (
    "feature_id",
    "endpoint_displacement",
    "geometry_type",
    "total_length",
)


def _compact_displacement_candidate(item: Mapping[str, Any]) -> dict[str, Any] | None:
    row = {
        key: item.get(key)
        for key in _DISPLACEMENT_CANDIDATE_KEYS
        if item.get(key) is not None
    }
    return row or None


def _compact_mapping_rows(
    raw: Any,
    *,
    limit: int,
    row_builder: Any,
) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(raw, list):
        return [], 0
    valid: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        row = row_builder(item)
        if row is not None:
            valid.append(row)
    intake_omitted = max(0, len(valid) - limit)
    return valid[:limit], intake_omitted


def _compact_string_list(raw: Any, *, limit: int) -> tuple[list[str], int]:
    if not isinstance(raw, list):
        return [], 0
    valid = [item.strip() for item in raw if isinstance(item, str) and item.strip()]
    intake_omitted = max(0, len(valid) - limit)
    return valid[:limit], intake_omitted


def compact_sanity_review_for_projection(sanity_review: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Bounded sanity lane for agent result-view projection."""
    if not isinstance(sanity_review, Mapping) or not sanity_review:
        return None
    compact: dict[str, Any] = {}

    metrics, metrics_omitted = _compact_metric_rows(sanity_review.get("feature_metrics"))
    if isinstance(sanity_review.get("feature_metrics"), list):
        compact["feature_metrics"] = metrics
        if metrics_omitted:
            compact["feature_metrics_omitted_count"] = metrics_omitted

    leg_tables, tables_omitted, courses_omitted = _compact_course_leg_tables(
        sanity_review.get("course_leg_tables")
    )
    if isinstance(sanity_review.get("course_leg_tables"), list):
        compact["course_leg_tables"] = leg_tables
        if tables_omitted:
            compact["course_leg_tables_omitted_count"] = tables_omitted
        if courses_omitted:
            compact["courses_omitted_count"] = courses_omitted

    candidates, candidates_omitted = _compact_mapping_rows(
        sanity_review.get("endpoint_displacement_candidates"),
        limit=MAX_PROJECTED_DISPLACEMENT_CANDIDATES,
        row_builder=_compact_displacement_candidate,
    )
    if isinstance(sanity_review.get("endpoint_displacement_candidates"), list):
        compact["endpoint_displacement_candidates"] = candidates
        if candidates_omitted:
            compact["endpoint_displacement_candidates_omitted_count"] = candidates_omitted

    evidence_refs, evidence_omitted = _compact_string_list(
        sanity_review.get("recommended_source_evidence_refs"),
        limit=MAX_PROJECTED_RECOMMENDED_EVIDENCE_REFS,
    )
    if isinstance(sanity_review.get("recommended_source_evidence_refs"), list):
        compact["recommended_source_evidence_refs"] = evidence_refs
        if evidence_omitted:
            compact["recommended_source_evidence_refs_omitted_count"] = evidence_omitted

    questions, questions_omitted = _compact_string_list(
        sanity_review.get("review_questions"),
        limit=MAX_PROJECTED_REVIEW_QUESTIONS,
    )
    if isinstance(sanity_review.get("review_questions"), list):
        compact["review_questions"] = questions
        if questions_omitted:
            compact["review_questions_omitted_count"] = questions_omitted

    return compact


def render_sanity_review_timeline_lines(
    sanity_review: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(sanity_review, Mapping) or not sanity_review:
        return []
    lines = [f"{indent}mapping_sanity:"]
    for metric in sanity_review.get("feature_metrics") or []:
        if not isinstance(metric, Mapping) or metric.get("skipped"):
            continue
        feature_id = metric.get("feature_id") or "feature"
        lines.append(
            "{indent}  {feature_id} endpoint_gap={gap} total_length={length} vertices={vertices}".format(
                indent=indent,
                feature_id=feature_id,
                gap=metric.get("endpoint_displacement"),
                length=metric.get("total_length"),
                vertices=metric.get("vertex_count"),
            )
        )
    for table in sanity_review.get("course_leg_tables") or []:
        if not isinstance(table, Mapping):
            continue
        for course in table.get("courses") or []:
            if not isinstance(course, Mapping):
                continue
            evidence = course.get("evidence_refs")
            evidence_text = ""
            if isinstance(evidence, list) and evidence:
                evidence_text = str(evidence[0])
            lines.append(
                "{indent}  leg {leg} distance={distance} bearing={bearing} evidence={evidence}".format(
                    indent=indent,
                    leg=course.get("leg_index"),
                    distance=course.get("distance"),
                    bearing=course.get("bearing"),
                    evidence=evidence_text,
                )
            )
    return lines


def attach_sanity_review_to_mapping_review(
    mapping_review: dict[str, Any],
    *,
    graph: FeatureGraph,
    compile_artifact: CompileArtifact,
    operand_evidence_index: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    mapping_review["sanity_review"] = build_mapping_sanity_review(
        graph=graph,
        compile_artifact=compile_artifact,
        operand_evidence_index=operand_evidence_index,
    )
    return mapping_review
