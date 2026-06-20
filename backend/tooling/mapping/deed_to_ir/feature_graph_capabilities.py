"""Mechanical feature-graph contract and vocabulary projection."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from feature_graph.artifact_refs import ARTIFACT_REF_PREFIXES
from feature_graph.models import FeatureGraph, FeatureKind
from feature_graph.operations import OPERATION_REGISTRY

from .feature_graph_contract_projection import (
    build_core_schema_projection,
    build_provenance_schema_projection,
    canonical_feature_graph_json_schema,
)
from .feature_graph_examples import (
    build_complete_supported_graph_example,
    build_direct_geometry_example,
    build_operation_example,
    build_reference_node_example,
)

DEFAULT_CAPABILITY_SECTIONS = (
    "core_schema",
    "provenance",
    "operations",
    "examples",
    "artifact_refs",
)
VALID_CAPABILITY_SECTIONS = frozenset((*DEFAULT_CAPABILITY_SECTIONS, "validation_schema"))


def describe_feature_graph_capabilities(
    *,
    sections: Sequence[str] | None = None,
    operation_names: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Project exact contract facts without recommending deed-specific choices."""
    selected_sections = _normalize_sections(sections)
    selected_operations = _select_operations(operation_names)
    result: dict[str, Any] = {"sections": selected_sections}

    if "core_schema" in selected_sections:
        core = build_core_schema_projection()
        result["feature_graph_request_schema"] = core["models"]["FeatureGraph"]
        result["model_schemas"] = core["models"]
        result["feature_kinds"] = [kind.value for kind in FeatureKind]
        result["content_rules"] = core["content_rules"]
        result["geometry_contract"] = core["geometry_contract"]
        result["edge_type_contract"] = core["edge_type_contract"]

    if "provenance" in selected_sections:
        provenance = build_provenance_schema_projection()
        result["provenance_schemas"] = provenance["models"]
        result["provenance_rules"] = provenance["rules"]

    if "operations" in selected_sections:
        result["registered_operations"] = [
            _project_operation(OPERATION_REGISTRY[name]) for name in selected_operations
        ]
        result["operation_contract"] = {
            "op_name": "Exact registered name when available; unregistered names remain representable.",
            "params": "Object governed by the selected operation's parameter contract.",
            "operands": "Exact feature ids or nested OpExpr objects.",
            "unsupported_behavior": (
                "Unsupported or unregistered operations may remain in IR, but deterministic mapping reports "
                "an explicit unsupported-operation gap instead of inventing geometry."
            ),
        }

    if "examples" in selected_sections:
        result["examples"] = {
            "warning": (
                "Contract-shape examples only. Never copy example values, geometry, ids, or scope into run IR "
                "unless the deed evidence independently supports them."
            ),
            "complete_supported_graph": build_complete_supported_graph_example(),
            "direct_geometry_node": build_direct_geometry_example(),
            "external_feature_reference_node": build_reference_node_example(),
            "operation_expressions": {
                name: build_operation_example(OPERATION_REGISTRY[name])
                for name in selected_operations
            },
        }

    if "artifact_refs" in selected_sections:
        result["artifact_types"] = list(ARTIFACT_REF_PREFIXES.keys())
        result["artifact_ref_prefixes"] = dict(ARTIFACT_REF_PREFIXES)

    if "validation_schema" in selected_sections:
        result["canonical_feature_graph_json_schema"] = canonical_feature_graph_json_schema()

    return result


def _normalize_sections(sections: Sequence[str] | None) -> list[str]:
    if sections is None:
        return list(DEFAULT_CAPABILITY_SECTIONS)
    selected = _unique_non_empty_strings(sections)
    if not selected:
        raise ValueError("feature_graph_capability_sections_required")
    unknown = sorted(set(selected) - VALID_CAPABILITY_SECTIONS)
    if unknown:
        raise ValueError("unknown_feature_graph_capability_sections")
    return selected


def _select_operations(operation_names: Sequence[str] | None) -> list[str]:
    if operation_names is None:
        return sorted(OPERATION_REGISTRY)
    selected = _unique_non_empty_strings(operation_names)
    if not selected:
        raise ValueError("feature_graph_operation_names_required")
    unknown = sorted(set(selected) - set(OPERATION_REGISTRY))
    if unknown:
        raise ValueError("unknown_feature_graph_operation_names")
    return selected


def _project_operation(operation: Any) -> dict[str, Any]:
    return {
        "name": operation.name,
        "category": operation.category.value,
        "description": operation.description,
        "required_parameters": operation.get_required_parameters(),
        "optional_parameters": operation.get_optional_parameters(),
        "parameters": [
            {
                "name": parameter.name,
                "param_type": parameter.param_type,
                "required": parameter.required,
                "default": parameter.default,
                "unit": parameter.unit,
                "description": parameter.description,
            }
            for parameter in operation.parameters
        ],
        "min_operands": operation.min_operands,
        "max_operands": operation.max_operands,
        "compiler_support": "supported" if operation.supported else "unsupported",
    }


def _unique_non_empty_strings(values: Sequence[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip() and value.strip() not in out:
            out.append(value.strip())
    return out
