"""Compact prepare/publish tool schemas for deed-to-IR final package preview."""

from __future__ import annotations

from typing import Any

from .published_output_tool_schema import (
    _list_property_schema,
    build_publish_deed_to_ir_output_request_json_shape,
)
from .published_output import (
    ALLOWED_CLOSURE_DIMENSION_IDS,
    ClosureDimensionRow,
    DeedToIrPublishedOutput,
    ExternalDependencyRow,
    OutputNoteRow,
    ScopeResultRow,
    UpstreamCorrectionRow,
)


def _correction_decision_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "target_entity_id",
            "posture",
            "resolution_used_by_ir",
            "recommended_action",
            "rationale",
        ],
        "properties": {
            "target_entity_id": {"type": "string", "minLength": 1},
            "posture": {
                "type": "string",
                "enum": ["suspected", "confirmed_from_source", "needs_hitl"],
            },
            "resolution_used_by_ir": {"type": "boolean"},
            "recommended_action": {
                "type": "string",
                "enum": [
                    "transcript_amendment",
                    "ir_only_note",
                    "dependency_block",
                    "hitl_review",
                ],
            },
            "rationale": {"type": "string", "minLength": 1},
            "correction_id": {"type": "string", "minLength": 1},
            "title": {"type": "string"},
            "target_entity_type": {"type": "string"},
            "upstream_value": {"type": "string"},
            "corrected_value": {"type": "string"},
            "basis_refs": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
        },
        "additionalProperties": False,
    }


def build_prepare_deed_to_ir_final_package_explicit_request_json_shape() -> dict[str, Any]:
    """Advanced/compatibility path: explicit mapping ref + full package rows."""
    return {
        "type": "object",
        "required": ["mapping_artifact_ref"],
        "properties": {
            "mapping_artifact_ref": {"type": "string", "minLength": 1},
            "expected_ir_artifact_ref": {"type": "string", "minLength": 1},
            "scope_results": _list_property_schema(
                parent_model=DeedToIrPublishedOutput,
                field_name="scope_results",
                item_model=ScopeResultRow,
            ),
            "external_dependencies": _list_property_schema(
                parent_model=DeedToIrPublishedOutput,
                field_name="external_dependencies",
                item_model=ExternalDependencyRow,
            ),
            "closure_dimensions": _list_property_schema(
                parent_model=DeedToIrPublishedOutput,
                field_name="closure_dimensions",
                item_model=ClosureDimensionRow,
                property_overrides={
                    "dimension_id": {
                        "enum": sorted(ALLOWED_CLOSURE_DIMENSION_IDS),
                    }
                },
            ),
            "notes": _list_property_schema(
                parent_model=DeedToIrPublishedOutput,
                field_name="notes",
                item_model=OutputNoteRow,
            ),
            "upstream_corrections": _list_property_schema(
                parent_model=DeedToIrPublishedOutput,
                field_name="upstream_corrections",
                item_model=UpstreamCorrectionRow,
            ),
        },
        "additionalProperties": False,
    }


def _disposition_item_schema(*, id_field: str, id_enum: list[str] | None = None) -> dict[str, Any]:
    id_schema: dict[str, Any] = {"type": "string", "minLength": 1}
    if id_enum is not None:
        id_schema["enum"] = id_enum
    return {
        "type": "object",
        "required": [id_field, "status"],
        "properties": {
            id_field: id_schema,
            "status": {"type": "string", "minLength": 1},
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "basis_refs": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
            "blocker_refs": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
            "dependency_refs": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
        },
        "additionalProperties": False,
    }


def _dependency_decision_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["candidate_id", "disposition"],
        "properties": {
            "candidate_id": {"type": "string", "minLength": 1},
            "disposition": {
                "type": "string",
                "enum": ["include", "not_applicable"],
            },
            "status": {"type": "string", "minLength": 1},
            "rationale": {"type": "string", "minLength": 1},
            "dependency_id": {"type": "string", "minLength": 1},
        },
        "additionalProperties": False,
    }


def build_prepare_deed_to_ir_final_package_intent_first_request_json_shape() -> dict[str, Any]:
    """Preferred minimal intent-first prepare request."""
    return {
        "type": "object",
        "required": ["use_current_mapping_lineage"],
        "properties": {
            "use_current_mapping_lineage": {"type": "boolean", "const": True},
            "reuse_agent_authored_finalization_state": {"type": "boolean"},
            "correction_decisions": {
                "type": "array",
                "items": _correction_decision_item_schema(),
            },
            "dependency_decisions": {
                "type": "array",
                "items": _dependency_decision_item_schema(),
            },
            "scope_dispositions": {
                "type": "array",
                "items": _disposition_item_schema(id_field="scope_id"),
            },
            "closure_dispositions": {
                "type": "array",
                "items": _disposition_item_schema(
                    id_field="dimension_id",
                    id_enum=sorted(ALLOWED_CLOSURE_DIMENSION_IDS),
                ),
            },
            "scope_results": _list_property_schema(
                parent_model=DeedToIrPublishedOutput,
                field_name="scope_results",
                item_model=ScopeResultRow,
            ),
            "external_dependencies": _list_property_schema(
                parent_model=DeedToIrPublishedOutput,
                field_name="external_dependencies",
                item_model=ExternalDependencyRow,
            ),
            "closure_dimensions": _list_property_schema(
                parent_model=DeedToIrPublishedOutput,
                field_name="closure_dimensions",
                item_model=ClosureDimensionRow,
                property_overrides={
                    "dimension_id": {
                        "enum": sorted(ALLOWED_CLOSURE_DIMENSION_IDS),
                    }
                },
            ),
            "notes": _list_property_schema(
                parent_model=DeedToIrPublishedOutput,
                field_name="notes",
                item_model=OutputNoteRow,
            ),
        },
        "additionalProperties": False,
    }


def build_prepare_deed_to_ir_final_package_request_json_shape() -> dict[str, Any]:
    """Return the agent-visible JSON Schema for prepare_deed_to_ir_final_package."""
    return {
        "oneOf": [
            build_prepare_deed_to_ir_final_package_intent_first_request_json_shape(),
            build_prepare_deed_to_ir_final_package_explicit_request_json_shape(),
        ]
    }


def build_publish_from_preview_request_json_shape() -> dict[str, Any]:
    """Preview-ref publish path: agent passes only the prepared preview revision."""
    return {
        "type": "object",
        "required": ["final_package_preview_ref"],
        "properties": {
            "final_package_preview_ref": {"type": "string", "minLength": 1},
        },
        "additionalProperties": False,
    }


def build_publish_deed_to_ir_output_request_json_shape_with_preview() -> dict[str, Any]:
    """Publish accepts either a preview ref (preferred) or direct mapping + rows."""
    return {
        "oneOf": [
            build_publish_from_preview_request_json_shape(),
            build_publish_deed_to_ir_output_request_json_shape(),
        ]
    }
