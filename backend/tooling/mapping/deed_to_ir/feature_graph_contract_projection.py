"""Compact mechanical projection of feature-graph model contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from feature_graph.models import FeatureEdge, FeatureGraph, FeatureNode, FeatureRef, OpExpr
from feature_graph.provenance import (
    Citation,
    EvidenceRef,
    ProvenanceAttachment,
    SourceEntityLink,
    TextSpan,
)


CORE_MODELS: tuple[type[BaseModel], ...] = (
    FeatureGraph,
    FeatureNode,
    FeatureEdge,
    FeatureRef,
    OpExpr,
)

PROVENANCE_MODELS: tuple[type[BaseModel], ...] = (
    ProvenanceAttachment,
    SourceEntityLink,
    Citation,
    TextSpan,
    EvidenceRef,
)


def build_core_schema_projection() -> dict[str, Any]:
    return {
        "models": _project_models(CORE_MODELS),
        "content_rules": {
            "feature_node_content": (
                "Provide at most one of geometry, op_expr, or feature_ref. Providing none is valid "
                "for a semantic or unresolved node."
            ),
            "op_expr_operands": "Each operand is a feature id string or a nested OpExpr object.",
            "graph_cycles": "Edges usually form a DAG, but cycles are valid for constraint systems.",
            "edge_references": (
                "source_id and target_id are exact node ids. Missing ids are deterministic judge gaps, "
                "not schema coercions."
            ),
        },
        "geometry_contract": {
            "shape": {"type": "GeoJSON-like geometry type", "coordinates": "coordinate arrays"},
            "runtime_behavior": "Direct geometry is preserved and passed through by the compiler.",
            "coordinate_posture": (
                "Coordinates may be local/schematic unless an explicit frame or placement is represented."
            ),
        },
        "edge_type_contract": {
            "type": "open string",
            "common_values": ["depends_on", "next_step", "anchored_to", "derived_from"],
            "note": "Common values are conventions, not a closed enum.",
        },
    }


def build_provenance_schema_projection() -> dict[str, Any]:
    return {
        "models": _project_models(PROVENANCE_MODELS),
        "rules": {
            "authorship": "The agent authors source_entity_links; deterministic code validates but does not infer them.",
            "resolution_link": {
                "entity_id": "Exact resolution item_id or covered-unit unit_id.",
                "entity_type": "Use resolution_item or resolution_unit as applicable.",
                "source_ref": "Exact transcript_edit:resolution_state:* handoff ref.",
                "relation": "Relationship label; derived_from is the default.",
            },
            "many_to_many": (
                "One IR entity may cite multiple upstream units and one upstream unit may support multiple IR entities."
            ),
        },
    }


def canonical_feature_graph_json_schema() -> dict[str, Any]:
    """Return the exact Pydantic validation schema on explicit request."""
    return FeatureGraph.model_json_schema()


def _project_models(models: tuple[type[BaseModel], ...]) -> dict[str, Any]:
    return {model.__name__: _compact_model_schema(model) for model in models}


def _compact_model_schema(model: type[BaseModel]) -> dict[str, Any]:
    raw = model.model_json_schema()
    root = _resolve_root_schema(raw)
    required = set(root.get("required") or [])
    properties = root.get("properties") if isinstance(root.get("properties"), dict) else {}
    fields: dict[str, Any] = {}
    for name, schema in properties.items():
        if not isinstance(schema, dict):
            continue
        row: dict[str, Any] = {
            "type": _schema_type_label(schema),
            "required": name in required,
        }
        for key in ("description", "default", "minLength", "maxLength"):
            if key in schema:
                row[_snake_case(key)] = schema[key]
        fields[str(name)] = row
    return {
        "description": _bound_description(root.get("description")),
        "fields": fields,
        "extra_fields": _extra_fields_posture(model),
    }


def _resolve_root_schema(raw: dict[str, Any]) -> dict[str, Any]:
    ref = raw.get("$ref")
    if not isinstance(ref, str):
        all_of = raw.get("allOf")
        if isinstance(all_of, list) and len(all_of) == 1 and isinstance(all_of[0], dict):
            ref = all_of[0].get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        return raw
    name = ref.rsplit("/", 1)[-1]
    definitions = raw.get("$defs") if isinstance(raw.get("$defs"), dict) else {}
    resolved = definitions.get(name)
    return resolved if isinstance(resolved, dict) else raw


def _schema_type_label(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return _ref_name(schema["$ref"])
    all_of = schema.get("allOf")
    if isinstance(all_of, list) and len(all_of) == 1 and isinstance(all_of[0], dict):
        return _schema_type_label(all_of[0])
    schema_type = schema.get("type")
    if schema_type == "array":
        items = schema.get("items") if isinstance(schema.get("items"), dict) else {}
        return f"array<{_schema_type_label(items)}>"
    if isinstance(schema_type, str):
        return schema_type
    variants = schema.get("anyOf")
    if isinstance(variants, list):
        labels = [_schema_type_label(v) for v in variants if isinstance(v, dict)]
        return " | ".join(dict.fromkeys(labels))
    return "any"


def _ref_name(value: Any) -> str:
    text = str(value or "")
    return text.rsplit("/", 1)[-1] if text else "object"


def _extra_fields_posture(model: type[BaseModel]) -> str:
    extra = model.model_config.get("extra")
    if extra == "forbid":
        return "forbidden"
    if extra == "allow":
        return "allowed"
    return "ignored"


def _snake_case(value: str) -> str:
    out: list[str] = []
    for char in value:
        if char.isupper():
            out.extend(("_", char.lower()))
        else:
            out.append(char)
    return "".join(out).lstrip("_")


def _bound_description(value: Any, limit: int = 320) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
