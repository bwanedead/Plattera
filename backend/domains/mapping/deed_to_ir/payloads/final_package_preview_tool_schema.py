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
)


def build_prepare_deed_to_ir_final_package_request_json_shape() -> dict[str, Any]:
    """Return the agent-visible JSON Schema for prepare_deed_to_ir_final_package rows."""
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
        },
        "additionalProperties": False,
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
