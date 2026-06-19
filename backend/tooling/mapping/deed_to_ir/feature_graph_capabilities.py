"""Mechanical projection of feature-graph capability catalog (no recommendations)."""

from __future__ import annotations

from typing import Any

from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, FeatureEdge, OpExpr
from feature_graph.operations import OPERATION_REGISTRY


def describe_feature_graph_capabilities() -> dict[str, Any]:
    """Project registry/schema facts without recommending deed-specific usage."""
    return {
        "feature_graph_request_schema": {
            "graph_id": {"type": "string", "required": True},
            "nodes": {"type": "array", "items": "FeatureNode", "required": True},
            "edges": {"type": "array", "items": "FeatureEdge", "required": True},
            "metadata": {"type": "object", "required": False},
        },
        "feature_node_schema": {
            "id": {"type": "string", "required": True},
            "kind": {"type": "FeatureKind", "required": True},
            "label": {"type": "string", "required": False},
            "geometry": {"type": "object", "required": False, "exclusive_with": ["op_expr", "feature_ref"]},
            "op_expr": {"type": "OpExpr", "required": False, "exclusive_with": ["geometry", "feature_ref"]},
            "feature_ref": {"type": "FeatureRef", "required": False, "exclusive_with": ["geometry", "op_expr"]},
            "metadata": {"type": "object", "required": False},
            "provenance": {"type": "ProvenanceAttachment", "required": False},
        },
        "feature_edge_schema": {
            "source_id": {"type": "string", "required": True},
            "target_id": {"type": "string", "required": True},
            "edge_type": {"type": "string", "required": True},
            "label": {"type": "string", "required": False},
            "metadata": {"type": "object", "required": False},
            "provenance": {"type": "ProvenanceAttachment", "required": False},
        },
        "op_expr_schema": {
            "op_name": {"type": "string", "required": True},
            "params": {"type": "object", "required": False},
            "operands": {"type": "array", "required": False},
        },
        "provenance_attachment_schema": {
            "citations": {"type": "array", "required": False},
            "source_entity_links": {
                "type": "array",
                "required": False,
                "item_shape": {
                    "entity_id": "string",
                    "entity_type": "string",
                    "source_ref": "string",
                    "relation": "string",
                },
            },
            "created_by": {"type": "string", "required": False},
            "created_at": {"type": "string", "required": False},
            "lineage": {"type": "array", "required": False},
        },
        "feature_kinds": [kind.value for kind in FeatureKind],
        "registered_operations": _project_operations(),
        "artifact_types": ["ir", "compile", "judge", "bundle"],
        "artifact_ref_prefixes": {
            "ir": "feature_graph:ir:",
            "compile": "feature_graph:compile:",
            "judge": "feature_graph:judge:",
            "bundle": "feature_graph:bundle:",
        },
        "schema_models": {
            "FeatureGraph": FeatureGraph.__name__,
            "FeatureNode": FeatureNode.__name__,
            "FeatureEdge": FeatureEdge.__name__,
            "OpExpr": OpExpr.__name__,
        },
    }


def _project_operations() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in sorted(OPERATION_REGISTRY):
        op = OPERATION_REGISTRY[name]
        rows.append(
            {
                "name": op.name,
                "category": op.category.value,
                "description": op.description,
                "required_parameters": op.get_required_parameters(),
                "optional_parameters": op.get_optional_parameters(),
                "parameters": [
                    {
                        "name": p.name,
                        "param_type": p.param_type,
                        "required": p.required,
                        "unit": p.unit,
                        "description": p.description,
                    }
                    for p in op.parameters
                ],
                "min_operands": op.min_operands,
                "max_operands": op.max_operands,
                "compiler_support": "supported" if op.supported else "unsupported",
            }
        )
    return rows
