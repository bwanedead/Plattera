"""Compact publish-tool request schemas derived from published-output Pydantic models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .published_output import (
    ALLOWED_CLOSURE_DIMENSION_IDS,
    ClosureDimensionRow,
    DeedToIrPublishedOutput,
    ExternalDependencyRow,
    MAX_REF_LENGTH,
    OutputNoteRow,
    ScopeResultRow,
)

_REF_ARRAY_FIELDS = frozenset(
    {
        "blocker_refs",
        "dependency_refs",
        "available_refs",
        "basis_refs",
    }
)


def build_publish_deed_to_ir_output_request_json_shape() -> dict[str, Any]:
    """Return the agent-visible JSON Schema for publish_deed_to_ir_output rows."""
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


def _list_property_schema(
    *,
    parent_model: type[BaseModel],
    field_name: str,
    item_model: type[BaseModel],
    property_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "type": "array",
        "maxItems": _list_max_items(parent_model, field_name),
        "items": compact_tool_item_schema(
            item_model,
            property_overrides=property_overrides,
        ),
    }


def compact_tool_item_schema(
    model: type[BaseModel],
    *,
    property_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw = model.model_json_schema()
    properties = raw.get("properties") if isinstance(raw.get("properties"), dict) else {}
    compact_properties: dict[str, Any] = {}
    for name, schema in properties.items():
        if not isinstance(schema, dict):
            continue
        compact = _compact_property_schema(name, schema)
        if name in _REF_ARRAY_FIELDS:
            compact = _with_ref_array_items(compact)
        if property_overrides and name in property_overrides:
            compact = {**compact, **property_overrides[name]}
        compact_properties[str(name)] = compact

    return {
        "type": "object",
        "required": list(raw.get("required") or []),
        "properties": compact_properties,
        "additionalProperties": False,
    }


def _compact_property_schema(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    if "anyOf" in schema:
        variants = [item for item in schema["anyOf"] if isinstance(item, dict)]
        non_null = [item for item in variants if item.get("type") != "null"]
        has_null = any(item.get("type") == "null" for item in variants)
        if len(non_null) == 1:
            compact.update(non_null[0])
            compact["type"] = ["string", "null"] if has_null else compact.get("type", "string")
        else:
            compact["anyOf"] = variants
    else:
        for key, value in schema.items():
            if key in {"title"}:
                continue
            compact[key] = value

    if name in _REF_ARRAY_FIELDS and compact.get("type") == "array":
        compact = _with_ref_array_items(compact)
    return compact


def _with_ref_array_items(schema: dict[str, Any]) -> dict[str, Any]:
    items = schema.get("items") if isinstance(schema.get("items"), dict) else {"type": "string"}
    schema = dict(schema)
    schema["items"] = {
        **items,
        "type": "string",
        "minLength": 1,
        "maxLength": MAX_REF_LENGTH,
    }
    return schema


def _list_max_items(model: type[BaseModel], field_name: str) -> int:
    field = model.model_fields[field_name]
    for constraint in field.metadata:
        max_length = getattr(constraint, "max_length", None)
        if isinstance(max_length, int):
            return max_length
    raise ValueError(f"list_max_items_missing:{model.__name__}.{field_name}")
