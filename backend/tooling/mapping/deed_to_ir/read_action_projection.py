"""Compact mechanical summaries for deed-to-IR read actions (batch/timeline/carry-forward)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .mapping_operands_projection import compact_mapping_operands_for_projection

MAX_CAPABILITY_OPERATIONS_IN_SUMMARY = 12
MAX_FEATURE_KINDS_IN_SUMMARY = 8


def compact_hydrate_deed_to_ir_input_summary(
    outputs: Mapping[str, Any] | None,
    *,
    action_inputs: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(outputs, Mapping):
        return None
    sections: list[str] = []
    if isinstance(action_inputs, Mapping):
        raw_sections = action_inputs.get("sections")
        if isinstance(raw_sections, list):
            sections = [str(item) for item in raw_sections if str(item).strip()]
    if not sections:
        raw = outputs.get("sections")
        if isinstance(raw, list):
            sections = [str(item) for item in raw if str(item).strip()]

    operands = compact_mapping_operands_for_projection(outputs)
    if operands is None and "mapping_operands" not in sections:
        if not sections:
            return None
        return {
            "lane": "hydrate_deed_to_ir_input",
            "requested_sections": sections,
            "hydrated_section_count": outputs.get("hydrated_section_count"),
        }

    summary: dict[str, Any] = {
        "lane": "mapping_operands" if operands else "hydrate_deed_to_ir_input",
        "requested_sections": sections or None,
        "hydrated_section_count": outputs.get("hydrated_section_count"),
    }
    if operands:
        if operands.get("operand_suite_ref"):
            summary["operand_suite_ref"] = operands["operand_suite_ref"]
        groups = operands.get("operand_groups")
        if isinstance(groups, list):
            summary["operand_group_count"] = len(groups)
            summary["operand_groups"] = groups
        operand_rows = operands.get("operands")
        if isinstance(operand_rows, list):
            summary["operand_row_count"] = len(operand_rows)
        totals = operands.get("totals")
        if isinstance(totals, Mapping) and totals:
            summary["totals"] = dict(totals)
        truncation = operands.get("truncation")
        if isinstance(truncation, Mapping) and truncation:
            summary["truncation"] = dict(truncation)
    inherited = outputs.get("inherited_handoff_conditions")
    if isinstance(inherited, Mapping):
        mode = inherited.get("projection_mode")
        if mode == "deferred_for_operand_lane":
            summary["inherited_handoff_conditions"] = "deferred_for_operand_lane"
    return {key: value for key, value in summary.items() if value is not None}


def compact_feature_graph_capabilities_summary(
    outputs: Mapping[str, Any] | None,
    *,
    action_inputs: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(outputs, Mapping):
        return None
    capability_keys = (
        "starter_contract",
        "registered_operations",
        "feature_graph_request_schema",
        "examples",
        "canonical_feature_graph_json_schema",
        "provenance_schemas",
        "operation_contract",
    )
    if not any(key in outputs for key in capability_keys):
        if not isinstance(action_inputs, Mapping) or not action_inputs.get("sections"):
            return None
    sections: list[str] = []
    operation_names: list[str] = []
    if isinstance(action_inputs, Mapping):
        raw_sections = action_inputs.get("sections")
        if isinstance(raw_sections, list):
            sections = [str(item) for item in raw_sections if str(item).strip()]
        raw_ops = action_inputs.get("operation_names")
        if isinstance(raw_ops, list):
            operation_names = [str(item) for item in raw_ops if str(item).strip()]
    if not sections and isinstance(outputs.get("sections"), list):
        sections = [str(item) for item in outputs["sections"] if str(item).strip()]

    summary: dict[str, Any] = {
        "lane": "feature_graph_capabilities",
    }
    if sections:
        summary["requested_sections"] = sections
    if operation_names:
        summary["requested_operation_names"] = operation_names

    starter = outputs.get("starter_contract")
    if isinstance(starter, Mapping):
        contract: dict[str, Any] = {}
        first_draft = starter.get("first_draft_authoring_card")
        if isinstance(first_draft, Mapping):
            contract["first_draft_authoring_card"] = first_draft
        feature_kinds = starter.get("feature_kinds")
        if isinstance(feature_kinds, list) and feature_kinds:
            contract["feature_kinds"] = feature_kinds[:MAX_FEATURE_KINDS_IN_SUMMARY]
        note = starter.get("feature_kind_vs_operation_contract")
        if isinstance(note, Mapping):
            annotation_note = note.get("annotation_note")
            if isinstance(annotation_note, str) and annotation_note.strip():
                contract["annotation_note"] = annotation_note.strip()[:240]
        provenance_fields = starter.get("provenance_link_required_fields")
        if isinstance(provenance_fields, list) and provenance_fields:
            contract["provenance_link_required_fields"] = [
                str(item) for item in provenance_fields[:12]
            ]
        operations = starter.get("operations")
        if isinstance(operations, list) and operations:
            compact_ops: list[dict[str, Any]] = []
            for row in operations[:MAX_CAPABILITY_OPERATIONS_IN_SUMMARY]:
                if not isinstance(row, Mapping):
                    continue
                compact_ops.append(
                    {
                        key: row[key]
                        for key in ("name", "category", "compiler_support", "compile_note")
                        if key in row and row[key] is not None
                    }
                )
            if compact_ops:
                contract["operations"] = compact_ops
        if contract:
            summary["starter_contract"] = contract

    first_draft = outputs.get("first_draft_authoring_card")
    if isinstance(first_draft, Mapping):
        summary["first_draft_authoring_card"] = first_draft
    elif isinstance(starter, Mapping):
        nested = starter.get("first_draft_authoring_card")
        if isinstance(nested, Mapping):
            summary["first_draft_authoring_card"] = nested
    if "first_draft_authoring_card" not in summary and (
        isinstance(starter, Mapping)
        or any(key in outputs for key in ("starter_contract", "registered_operations", "examples"))
    ):
        from .first_draft_authoring_card import build_first_draft_authoring_card

        summary["first_draft_authoring_card"] = build_first_draft_authoring_card()

    ignored = outputs.get("ignored_operation_names")
    if isinstance(ignored, list) and ignored:
        summary["ignored_operation_names"] = [
            dict(row) for row in ignored[:4] if isinstance(row, Mapping)
        ]

    return summary if len(summary) > 1 else None


def compact_read_action_summary(
    action_type: str,
    outputs: Mapping[str, Any] | None,
    *,
    action_inputs: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    if action_type == "hydrate_deed_to_ir_input":
        return compact_hydrate_deed_to_ir_input_summary(outputs, action_inputs=action_inputs)
    if action_type == "describe_feature_graph_capabilities":
        return compact_feature_graph_capabilities_summary(outputs, action_inputs=action_inputs)
    return None


def render_read_action_summary_timeline_lines(
    summary: Mapping[str, Any] | None,
    *,
    indent: str = "      ",
) -> list[str]:
    if not isinstance(summary, Mapping) or not summary:
        return []
    lines = [f"{indent}read_action_summary:"]
    lane = summary.get("lane")
    if lane:
        lines.append(f"{indent}  lane: {lane}")
    for key in (
        "requested_sections",
        "requested_operation_names",
        "operand_suite_ref",
        "operand_group_count",
        "operand_row_count",
        "hydrated_section_count",
        "inherited_handoff_conditions",
    ):
        if key in summary and summary.get(key) is not None:
            lines.append(f"{indent}  {key}: {summary.get(key)}")
    groups = summary.get("operand_groups")
    if isinstance(groups, list) and groups:
        lines.append(f"{indent}  operand_groups:")
        for group in groups[:4]:
            if not isinstance(group, Mapping):
                continue
            group_kind = group.get("group_kind")
            group_id = group.get("group_id")
            rows = group.get("rows")
            row_count = len(rows) if isinstance(rows, list) else 0
            label = group_id or group_kind or "group"
            detail = f"{label}"
            if group_kind:
                detail = f"{detail} ({group_kind}, rows={row_count})"
            lines.append(f"{indent}    - {detail}")
    starter = summary.get("starter_contract")
    if isinstance(starter, Mapping):
        ops = starter.get("operations")
        if isinstance(ops, list) and ops:
            names = [
                str(row.get("name"))
                for row in ops[:8]
                if isinstance(row, Mapping) and row.get("name")
            ]
            if names:
                lines.append(f"{indent}  operations: {', '.join(names)}")
        fields = starter.get("provenance_link_required_fields")
        if isinstance(fields, list) and fields:
            lines.append(f"{indent}  provenance_link_fields: {', '.join(str(f) for f in fields[:6])}")
    card = summary.get("first_draft_authoring_card")
    if isinstance(card, Mapping):
        ops = card.get("normal_deed_operation_names")
        if isinstance(ops, list) and ops:
            lines.append(f"{indent}  first_draft_operations: {', '.join(str(o) for o in ops[:8])}")
    truncation = summary.get("truncation")
    if isinstance(truncation, Mapping) and truncation:
        lines.append(f"{indent}  truncation: {truncation}")
    return lines
