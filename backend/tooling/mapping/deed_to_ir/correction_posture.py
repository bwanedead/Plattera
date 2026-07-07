"""Mechanical correction-posture detection for deed-to-IR (facts only, no semantic authorship)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from feature_graph.artifacts import CompileArtifact
from feature_graph.models import FeatureGraph, FeatureNode

from .correction_contract_card import (
    CORRECTION_CONTRACT_REF,
    CORRECTION_REPAIR_HINT,
    build_correction_contract_card,
)
from .correction_lane_advisory import detect_correction_lane_advisory
from .mapping_operands_projection import build_mapping_operands
from .mapping_sanity import ordered_entity_ids_for_leg
from .operand_value_parsing import parse_bearing_operand, parse_distance_operand

MAX_CANDIDATE_DELTAS = 8
MAX_BASIS_REFS = 8
DISTANCE_TOLERANCE_FEET = 0.05
BEARING_TOLERANCE_DEGREES = 0.01

REASON_IR_DIFFERS = "ir_value_differs_from_inherited_operand"
REASON_AGENT_STATE = "agent_authored_state_indicates_correction_used"

_CALL_OPERAND_ID = re.compile(
    r"^p(?P<parcel_num>\d+)_call(?P<call_index>\d+)_(?P<value_kind>bearing|distance)$",
    re.IGNORECASE,
)

_UPSTREAM_CORRECTIONS_REQUIRED = "upstream_corrections_required"


def detect_correction_posture(
    *,
    resolution_state_snapshot: Mapping[str, Any] | None,
    ir_graph: FeatureGraph | None = None,
    compile_artifact: CompileArtifact | None = None,
    ir_artifact_ref: str | None = None,
    upstream_corrections: Sequence[Any] | None = None,
    scope_results: Sequence[Any] | None = None,
    external_dependencies: Sequence[Any] | None = None,
    closure_dimensions: Sequence[Any] | None = None,
    notes: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Detect mechanical correction posture without authoring correction rows or choosing truth."""
    inactive: dict[str, Any] = {
        "active": False,
        "reason_codes": [],
        "candidate_deltas": [],
        "contract_ref": CORRECTION_CONTRACT_REF,
    }
    if not isinstance(resolution_state_snapshot, Mapping):
        return inactive
    if ir_graph is None:
        return inactive

    inherited = _index_inherited_operands(resolution_state_snapshot)
    if not inherited:
        return inactive

    ir_values, leg_values = _index_ir_call_values(
        graph=ir_graph,
        compile_artifact=compile_artifact,
        ir_artifact_ref=ir_artifact_ref,
    )

    candidate_deltas = _compare_inherited_to_ir(
        inherited=inherited,
        ir_values=ir_values,
        leg_values=leg_values,
        ir_graph=ir_graph,
    )
    if not candidate_deltas:
        return inactive

    reason_codes = [REASON_IR_DIFFERS]
    if _agent_state_indicates_correction_used(
        upstream_corrections=upstream_corrections,
        scope_results=scope_results,
        external_dependencies=external_dependencies,
        closure_dimensions=closure_dimensions,
        notes=notes,
    ):
        reason_codes.append(REASON_AGENT_STATE)

    return {
        "active": True,
        "reason_codes": reason_codes,
        "candidate_deltas": candidate_deltas[:MAX_CANDIDATE_DELTAS],
        "contract_ref": CORRECTION_CONTRACT_REF,
    }


def compact_correction_posture_for_projection(posture: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Bounded carry-forward lane for mapping review / tool slices."""
    if not isinstance(posture, Mapping) or not posture.get("active"):
        return None
    compact: dict[str, Any] = {
        "active": True,
        "reason_codes": list(posture.get("reason_codes") or []),
        "contract_ref": posture.get("contract_ref") or CORRECTION_CONTRACT_REF,
        "candidate_delta_count": len(posture.get("candidate_deltas") or []),
    }
    deltas = posture.get("candidate_deltas")
    if isinstance(deltas, list) and deltas:
        compact["candidate_deltas"] = [
            {
                "target_entity_id": row.get("target_entity_id"),
                "value_kind": row.get("value_kind"),
                "inherited_value": row.get("inherited_value"),
                "ir_value": row.get("ir_value"),
            }
            for row in deltas
            if isinstance(row, Mapping)
        ]
    return compact


def upstream_corrections_required_refusal(*, correction_posture: Mapping[str, Any]) -> dict[str, Any]:
    """Retryable prepare refusal when correction posture is active and corrections lane is empty."""
    card = build_correction_contract_card()
    return {
        "executed": False,
        "reason_codes": [_UPSTREAM_CORRECTIONS_REQUIRED],
        "refusal": {
            "reason_code": _UPSTREAM_CORRECTIONS_REQUIRED,
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "error": {
                "code": _UPSTREAM_CORRECTIONS_REQUIRED,
                "message": (
                    "Selected IR appears to differ from inherited operands; add agent-authored "
                    "upstream_corrections rows or revise the package if no correction was used."
                ),
            },
            "correction_posture": dict(correction_posture),
            "correction_contract_card": card,
            "repair_hint": CORRECTION_REPAIR_HINT,
        },
    }


def render_correction_posture_timeline_lines(
    posture: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(posture, Mapping) or not posture.get("active"):
        return []
    lines = [f"{indent}correction_posture:"]
    reasons = posture.get("reason_codes")
    if isinstance(reasons, list) and reasons:
        lines.append(f"{indent}  reasons: {', '.join(str(code) for code in reasons)}")
    deltas = posture.get("candidate_deltas")
    if isinstance(deltas, list):
        lines.append(f"{indent}  candidate_deltas: {len(deltas)}")
        for row in deltas[:4]:
            if not isinstance(row, Mapping):
                continue
            target = row.get("target_entity_id")
            value_kind = row.get("value_kind")
            inherited = row.get("inherited_value")
            ir_value = row.get("ir_value")
            lines.append(
                f"{indent}    - {target or ''} ({value_kind or ''}): "
                f"inherited={inherited or ''} ir={ir_value or ''}"
            )
    elif posture.get("candidate_delta_count") is not None:
        lines.append(f"{indent}  candidate_deltas: {posture.get('candidate_delta_count')}")
    contract_ref = posture.get("contract_ref")
    if isinstance(contract_ref, str) and contract_ref.strip():
        lines.append(f"{indent}  contract_ref: {contract_ref.strip()}")
    return lines


def render_upstream_corrections_required_timeline_lines(
    outputs: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(outputs, Mapping):
        return []
    error = outputs.get("error")
    if not isinstance(error, Mapping) or error.get("code") != _UPSTREAM_CORRECTIONS_REQUIRED:
        return []
    lines = [f"{indent}upstream_corrections_required:"]
    repair_hint = outputs.get("repair_hint")
    if isinstance(repair_hint, str) and repair_hint.strip():
        lines.append(f"{indent}  repair_hint: {repair_hint.strip()}")
    lines.extend(
        render_correction_posture_timeline_lines(outputs.get("correction_posture"), indent=indent)
    )
    from .correction_contract_card import render_correction_contract_card_timeline_lines

    lines.extend(
        render_correction_contract_card_timeline_lines(
            outputs.get("correction_contract_card"),
            indent=indent,
        )
    )
    return lines


def attach_correction_posture_to_mapping_review(
    mapping_review: dict[str, Any],
    *,
    resolution_state_snapshot: Mapping[str, Any] | None,
    ir_graph: FeatureGraph | None,
    compile_artifact: CompileArtifact | None,
    ir_artifact_ref: str | None,
) -> None:
    posture = detect_correction_posture(
        resolution_state_snapshot=resolution_state_snapshot,
        ir_graph=ir_graph,
        compile_artifact=compile_artifact,
        ir_artifact_ref=ir_artifact_ref,
    )
    compact = compact_correction_posture_for_projection(posture)
    if compact is not None:
        mapping_review["correction_posture"] = compact


def _agent_state_indicates_correction_used(
    *,
    upstream_corrections: Sequence[Any] | None,
    scope_results: Sequence[Any] | None,
    external_dependencies: Sequence[Any] | None,
    closure_dimensions: Sequence[Any] | None,
    notes: Sequence[Any] | None,
) -> bool:
    if isinstance(upstream_corrections, list) and upstream_corrections:
        return False
    advisory = detect_correction_lane_advisory(
        upstream_corrections=[],
        scope_results=list(scope_results) if scope_results else None,
        external_dependencies=list(external_dependencies) if external_dependencies else None,
        closure_dimensions=list(closure_dimensions) if closure_dimensions else None,
        notes=list(notes) if notes else None,
    )
    return advisory is not None


def _index_inherited_operands(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    operands_payload = build_mapping_operands(snapshot)
    operands = operands_payload.get("operands")
    if not isinstance(operands, list):
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for row in operands:
        if not isinstance(row, Mapping):
            continue
        operand_id = str(row.get("operand_id") or "").strip()
        if not operand_id:
            continue
        value_kind = str(row.get("value_kind") or "").lower()
        if value_kind not in {"distance", "bearing"}:
            continue
        entry: dict[str, Any] = {
            "operand_id": operand_id,
            "value_kind": value_kind,
            "determined_value": row.get("determined_value"),
            "basis_refs": _bounded_refs(row.get("evidence_refs")),
        }
        if value_kind == "distance":
            parsed = parse_distance_operand(row.get("determined_value"))
            if parsed.get("parse_status") != "parsed":
                continue
            entry["numeric_feet"] = parsed.get("distance_feet")
            entry["display_value"] = parsed.get("distance_raw") or row.get("determined_value")
        else:
            parsed = parse_bearing_operand(row.get("determined_value"))
            if parsed.get("parse_status") != "parsed":
                continue
            entry["numeric_degrees"] = parsed.get("bearing_degrees")
            entry["display_value"] = parsed.get("bearing_raw") or row.get("determined_value")
        indexed[operand_id] = entry
    return indexed


def _index_ir_call_values(
    *,
    graph: FeatureGraph,
    compile_artifact: CompileArtifact | None,
    ir_artifact_ref: str | None,
) -> tuple[dict[str, dict[str, Any]], dict[int, dict[str, dict[str, Any]]]]:
    compiled = compile_artifact.compiled_features if compile_artifact is not None else {}
    indexed: dict[str, dict[str, Any]] = {}
    leg_values: dict[int, dict[str, dict[str, Any]]] = {}
    ir_ref = str(ir_artifact_ref or "").strip()
    ir_basis = [ir_ref] if ir_ref else []

    for node in graph.nodes:
        op_expr = node.op_expr
        if op_expr is None or str(op_expr.op_name or "") != "CourseTraverse":
            continue
        courses = _courses_for_node(node=node, compiled_entry=compiled.get(node.id))
        if not courses:
            continue
        source_entity_ids = _source_entity_ids_from_node(node)
        operand_index = {entity_id: ir_basis for entity_id in source_entity_ids}
        for index, raw_course in enumerate(courses):
            if not isinstance(raw_course, Mapping):
                continue
            leg_index = index + 1
            leg_row = _parse_course_leg_values(raw_course, basis_refs=ir_basis)
            if leg_row:
                leg_values[leg_index] = leg_row
            leg_entity_ids = ordered_entity_ids_for_leg(
                source_entity_ids=source_entity_ids,
                operand_evidence_index=operand_index,
                leg_index=leg_index,
            )
            for entity_id in leg_entity_ids:
                value_kind = _entity_value_kind(entity_id)
                if value_kind and value_kind in leg_row:
                    indexed[entity_id] = dict(leg_row[value_kind])

    return indexed, leg_values


def _parse_course_leg_values(
    raw_course: Mapping[str, Any],
    *,
    basis_refs: list[str],
) -> dict[str, dict[str, Any]]:
    row: dict[str, dict[str, Any]] = {}
    distance = raw_course.get("distance")
    bearing = raw_course.get("bearing")
    distance_raw = raw_course.get("distance_raw")
    bearing_raw = raw_course.get("bearing_raw")
    if isinstance(distance, (int, float)):
        row["distance"] = {
            "value_kind": "distance",
            "numeric_feet": float(distance),
            "display_value": str(distance_raw).strip()
            if isinstance(distance_raw, str) and distance_raw.strip()
            else f"{float(distance):g} feet",
            "basis_refs": list(basis_refs),
        }
    if isinstance(bearing, (int, float)):
        row["bearing"] = {
            "value_kind": "bearing",
            "numeric_degrees": float(bearing),
            "display_value": str(bearing_raw).strip()
            if isinstance(bearing_raw, str) and bearing_raw.strip()
            else f"{float(bearing):g} degrees",
            "basis_refs": list(basis_refs),
        }
    return row


def _compare_inherited_to_ir(
    *,
    inherited: dict[str, dict[str, Any]],
    ir_values: dict[str, dict[str, Any]],
    leg_values: dict[int, dict[str, dict[str, Any]]],
    ir_graph: FeatureGraph,
) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    for operand_id, inherited_row in inherited.items():
        ir_row = ir_values.get(operand_id)
        if ir_row is None:
            match = _CALL_OPERAND_ID.match(operand_id)
            if match is not None:
                parcel_num = match.group("parcel_num")
                leg_index = int(match.group("call_index"))
                if _graph_supports_parcel_leg_fallback(ir_graph, parcel_num):
                    value_kind = inherited_row.get("value_kind")
                    leg_kinds = leg_values.get(leg_index, {})
                    if isinstance(value_kind, str) and value_kind in leg_kinds:
                        ir_row = leg_kinds[value_kind]
        if ir_row is None:
            continue
        value_kind = inherited_row.get("value_kind")
        if value_kind == "distance":
            inherited_num = inherited_row.get("numeric_feet")
            ir_num = ir_row.get("numeric_feet")
            if not isinstance(inherited_num, (int, float)) or not isinstance(ir_num, (int, float)):
                continue
            if abs(float(inherited_num) - float(ir_num)) <= DISTANCE_TOLERANCE_FEET:
                continue
        elif value_kind == "bearing":
            inherited_num = inherited_row.get("numeric_degrees")
            ir_num = ir_row.get("numeric_degrees")
            if not isinstance(inherited_num, (int, float)) or not isinstance(ir_num, (int, float)):
                continue
            if abs(float(inherited_num) - float(ir_num)) <= BEARING_TOLERANCE_DEGREES:
                continue
        else:
            continue
        basis_refs = _bounded_refs(inherited_row.get("basis_refs")) + _bounded_refs(ir_row.get("basis_refs"))
        seen: set[str] = set()
        merged_refs: list[str] = []
        for ref in basis_refs:
            if ref in seen:
                continue
            seen.add(ref)
            merged_refs.append(ref)
            if len(merged_refs) >= MAX_BASIS_REFS:
                break
        deltas.append(
            {
                "target_entity_id": operand_id,
                "value_kind": value_kind,
                "inherited_value": inherited_row.get("display_value") or inherited_row.get("determined_value"),
                "ir_value": ir_row.get("display_value"),
                "basis_refs": merged_refs,
            }
        )
    return deltas


def _graph_supports_parcel_leg_fallback(graph: FeatureGraph, parcel_num: str) -> bool:
    """Allow call-index leg fallback only when the graph has a matching parcel traverse."""
    parcel_token = f"parcel_{parcel_num}"
    traverse_nodes = [
        node
        for node in graph.nodes
        if node.op_expr is not None and str(node.op_expr.op_name or "") == "CourseTraverse"
    ]
    if not traverse_nodes:
        return False
    if len(traverse_nodes) == 1:
        node = traverse_nodes[0]
        node_id = node.id.lower()
        return parcel_token in node_id or (parcel_num == "1" and "parcel_" not in node_id)
    matching = [node for node in traverse_nodes if parcel_token in node.id.lower()]
    return len(matching) == 1


def _courses_for_node(
    *,
    node: FeatureNode,
    compiled_entry: Mapping[str, Any] | None,
) -> list[Any] | None:
    if isinstance(compiled_entry, Mapping):
        courses = compiled_entry.get("courses")
        if isinstance(courses, list) and courses:
            return courses
    op_expr = node.op_expr
    if op_expr is None:
        return None
    params = op_expr.params if isinstance(op_expr.params, dict) else {}
    param_courses = params.get("courses")
    return param_courses if isinstance(param_courses, list) else None


def _source_entity_ids_from_node(node: FeatureNode) -> list[str]:
    provenance = node.provenance
    if provenance is None:
        return []
    links = provenance.source_entity_links
    if not links:
        return []
    ids: list[str] = []
    for link in links:
        entity_id = str(getattr(link, "entity_id", "") or "").strip()
        if entity_id:
            ids.append(entity_id)
    return ids


def _entity_value_kind(entity_id: str) -> str | None:
    lower = entity_id.lower()
    if "distance" in lower:
        return "distance"
    if "bearing" in lower:
        return "bearing"
    return None


def _bounded_refs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    refs: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            refs.append(text)
        if len(refs) >= MAX_BASIS_REFS:
            break
    return refs
