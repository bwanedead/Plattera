"""Mechanical feature-graph contract and vocabulary projection."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from feature_graph.artifact_refs import ARTIFACT_REF_PREFIXES
from feature_graph.models import FeatureKind
from feature_graph.operations import OPERATION_REGISTRY

from .feature_graph_contract_projection import (
    build_core_schema_projection,
    build_feature_node_kind_contract,
    build_provenance_schema_projection,
    canonical_feature_graph_json_schema,
)
from .feature_graph_examples import (
    build_complete_supported_graph_example,
    build_deed_to_ir_authoring_example,
    build_direct_geometry_example,
    build_operation_example,
    build_reference_node_example,
)

DEFAULT_CAPABILITY_SECTIONS = ("starter_contract",)
VALID_CAPABILITY_SECTIONS = frozenset(
    (
        "starter_contract",
        "core_schema",
        "provenance",
        "operations",
        "examples",
        "artifact_refs",
        "validation_schema",
    )
)


def describe_feature_graph_capabilities(
    *,
    sections: Sequence[str] | None = None,
    operation_names: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Project exact contract facts without recommending deed-specific choices."""
    selected_sections = _normalize_sections(sections)
    selected_operations: list[str] | None = None
    ignored_operation_names: list[dict[str, str]] = []
    if operation_names is not None:
        selected_operations, ignored_operation_names = _resolve_operation_names(operation_names)
    result: dict[str, Any] = {"sections": selected_sections}
    if ignored_operation_names:
        result["ignored_operation_names"] = ignored_operation_names

    if "starter_contract" in selected_sections:
        result["starter_contract"] = _build_starter_contract(
            operation_names=selected_operations,
        )

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
        ops = selected_operations if selected_operations is not None else sorted(OPERATION_REGISTRY)
        if operation_names is None:
            result["registered_operations"] = _compact_operation_index(ops)
        else:
            result["registered_operations"] = [
                _project_operation(OPERATION_REGISTRY[name]) for name in ops
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
        ops = selected_operations if selected_operations is not None else sorted(OPERATION_REGISTRY)
        result["examples"] = {
            "warning": (
                "Contract-shape examples only. Never copy example values, geometry, ids, or scope into run IR "
                "unless the deed evidence independently supports them."
            ),
            "complete_supported_graph": build_complete_supported_graph_example(),
            "deed_to_ir_authoring": build_deed_to_ir_authoring_example(),
            "direct_geometry_node": build_direct_geometry_example(),
            "external_feature_reference_node": build_reference_node_example(),
            "operation_expressions": {
                name: build_operation_example(OPERATION_REGISTRY[name])
                for name in ops
            },
        }

    if "artifact_refs" in selected_sections:
        result["artifact_types"] = list(ARTIFACT_REF_PREFIXES.keys())
        result["artifact_ref_prefixes"] = dict(ARTIFACT_REF_PREFIXES)

    if "validation_schema" in selected_sections:
        result["canonical_feature_graph_json_schema"] = canonical_feature_graph_json_schema()

    return result


def _build_starter_contract(*, operation_names: list[str] | None) -> dict[str, Any]:
    core = build_core_schema_projection()
    provenance = build_provenance_schema_projection()
    ops = operation_names if operation_names is not None else sorted(OPERATION_REGISTRY)
    if operation_names is None:
        operations = _compact_operation_index(ops)
    else:
        operations = [_project_operation(OPERATION_REGISTRY[name]) for name in ops]
    return {
        "feature_kinds": [kind.value for kind in FeatureKind],
        "feature_kind_vs_operation_contract": {
            "feature_kinds": (
                "Classify nodes: point, curve, region, frame, constraint, annotation, unknown."
            ),
            "operation_names": (
                "Compute/derive node content: ReferenceFrame, TiedPoint, CourseTraverse, Close, etc."
            ),
            "annotation_note": (
                "annotation is a FeatureKind, not an operation; blocked scope usually uses "
                "kind=annotation with no op_expr."
            ),
        },
        "feature_node_kind_contract": build_feature_node_kind_contract(),
        "node_content_alternatives": core["content_rules"]["feature_node_content"],
        "op_expr_shape": core["models"]["OpExpr"]["fields"],
        "provenance_link_required_fields": provenance["models"]["SourceEntityLink"]["fields"],
        "artifact_ref_prefixes": dict(ARTIFACT_REF_PREFIXES),
        "operations": operations,
    }


def _compact_operation_index(operation_names: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in operation_names:
        operation = OPERATION_REGISTRY[name]
        rows.append(
            {
                "name": operation.name,
                "category": operation.category.value,
                "compiler_support": "supported" if operation.supported else "unsupported",
            }
        )
    return rows


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


def _resolve_operation_names(
    operation_names: Sequence[str] | None,
) -> tuple[list[str], list[dict[str, str]]]:
    if operation_names is None:
        return sorted(OPERATION_REGISTRY), []
    selected = _unique_non_empty_strings(operation_names)
    if not selected:
        raise ValueError("feature_graph_operation_names_required")
    feature_kinds = {kind.value for kind in FeatureKind}
    valid: list[str] = []
    ignored: list[dict[str, str]] = []
    for name in selected:
        if name in OPERATION_REGISTRY:
            valid.append(name)
        elif name in feature_kinds:
            ignored.append({"name": name, "reason": "feature_kind_not_operation"})
        else:
            ignored.append({"name": name, "reason": "unknown_operation_name"})
    if not valid:
        raise ValueError("no_valid_feature_graph_operation_names")
    return valid, ignored


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
