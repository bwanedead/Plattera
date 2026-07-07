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

GENERIC_REVIEW_QUESTIONS = [
    "Does endpoint displacement matter for the authored geometry role?",
    "If this feature was expected to close, inspect contributing course operands before declaring an open limitation.",
    "Station chains, centerlines, routes, strips, and intentionally open alignments may not close.",
    "Large unexplained endpoint displacement is a source-sanity trigger, not automatically a deed defect.",
]

_CALL_ENTITY_PATTERN = re.compile(r"_call(\d+)_", re.IGNORECASE)


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
    return _ordered_entity_ids_for_leg(
        source_entity_ids=source_entity_ids,
        operand_evidence_index=operand_evidence_index,
        leg_index=leg_index,
    )


def _ordered_entity_ids_for_leg(
    *,
    source_entity_ids: list[str],
    operand_evidence_index: dict[str, list[str]] | None,
    leg_index: int,
) -> list[str]:
    linked = _entity_ids_for_leg(source_entity_ids, leg_index)
    indexed = _entity_ids_from_operand_index_for_leg(operand_evidence_index, leg_index)
    combined = list(dict.fromkeys(linked + indexed))
    if not combined and source_entity_ids and leg_index == 1 and len(source_entity_ids) == len(linked):
        return linked
    distance_ids = [entity_id for entity_id in combined if _entity_value_kind(entity_id) == "distance"]
    bearing_ids = [entity_id for entity_id in combined if _entity_value_kind(entity_id) == "bearing"]
    other_ids = [entity_id for entity_id in combined if entity_id not in distance_ids and entity_id not in bearing_ids]
    return distance_ids + bearing_ids + other_ids


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
        source_entity_ids = _ordered_entity_ids_for_leg(
            source_entity_ids=all_entity_ids,
            operand_evidence_index=operand_evidence_index,
            leg_index=leg_index,
        )
        if not source_entity_ids and all_entity_ids and len(courses) == 1:
            source_entity_ids = list(all_entity_ids)
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
        row["evidence_refs"] = evidence_refs
        if not evidence_refs:
            row["evidence_refs_reason"] = "no_operand_evidence_indexed"
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


def compact_sanity_review_for_projection(sanity_review: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Bounded sanity lane for tool-result slices and prompt projection."""
    if not isinstance(sanity_review, Mapping) or not sanity_review:
        return None
    compact: dict[str, Any] = {}

    metrics: list[dict[str, Any]] = []
    for metric in (sanity_review.get("feature_metrics") or [])[:4]:
        if not isinstance(metric, Mapping) or metric.get("skipped"):
            continue
        row = {
            "feature_id": metric.get("feature_id"),
            "endpoint_displacement": metric.get("endpoint_displacement"),
            "total_length": metric.get("total_length"),
            "vertex_count": metric.get("vertex_count"),
        }
        metrics.append({key: value for key, value in row.items() if value is not None})
    if metrics:
        compact["feature_metrics"] = metrics

    leg_tables: list[dict[str, Any]] = []
    for table in (sanity_review.get("course_leg_tables") or [])[:2]:
        if not isinstance(table, Mapping):
            continue
        courses: list[dict[str, Any]] = []
        for course in (table.get("courses") or [])[:6]:
            if not isinstance(course, Mapping):
                continue
            courses.append(
                {
                    key: course.get(key)
                    for key in (
                        "leg_index",
                        "bearing",
                        "distance",
                        "bearing_raw",
                        "distance_raw",
                        "source_entity_ids",
                        "evidence_refs",
                    )
                    if course.get(key) is not None
                }
            )
        leg_tables.append(
            {
                "feature_id": table.get("feature_id"),
                "course_count": table.get("course_count"),
                "courses": courses,
            }
        )
    if leg_tables:
        compact["course_leg_tables"] = leg_tables

    candidates = sanity_review.get("endpoint_displacement_candidates")
    if isinstance(candidates, list) and candidates:
        compact["endpoint_displacement_candidates"] = list(candidates)[:4]

    evidence_refs = sanity_review.get("recommended_source_evidence_refs")
    if isinstance(evidence_refs, list) and evidence_refs:
        compact["recommended_source_evidence_refs"] = list(evidence_refs)[:6]

    questions = sanity_review.get("review_questions")
    if isinstance(questions, list) and questions:
        compact["review_questions"] = list(questions)[:4]

    return compact or None


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
