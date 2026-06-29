"""Canonical valid examples for feature-graph authoring contracts."""

from __future__ import annotations

from typing import Any

from feature_graph.operations import OperationDef, ParameterSpec

# Tokens that must not appear in example payloads (practice-deed overfit guard).
_FORBIDDEN_EXAMPLE_TOKENS = (
    "parcel_1",
    "parcel_2",
    "p1_",
    "p2_",
    "canal",
    "range seventy",
    "542",
    "68",
    "68°",
    "68.5",
    "158.5",
    "row",
)


def build_complete_supported_graph_example() -> dict[str, Any]:
    """A schema-valid, compiler-supported schematic graph with provenance."""
    return {
        "graph_id": "supported_graph_example",
        "nodes": [
            {
                "id": "example_frame",
                "kind": "frame",
                "label": "Example survey frame context",
                "op_expr": {
                    "op_name": "ReferenceFrame",
                    "params": {
                        "frame_type": "plss_example",
                        "section": "1",
                        "township": "1N",
                        "range": "1E",
                        "meridian": "Example Meridian",
                        "raw_text": "Example survey frame text",
                    },
                    "operands": [],
                },
            },
            {
                "id": "example_start_anchor",
                "kind": "point",
                "label": "Example local beginning anchor",
                "op_expr": {
                    "op_name": "TiedPoint",
                    "params": {},
                    "operands": [],
                },
                "provenance": {
                    "source_entity_links": [
                        {
                            "entity_id": "start_anchor_tie",
                            "entity_type": "resolution_unit",
                            "source_ref": "transcript_edit:resolution_state:example",
                            "relation": "derived_from",
                        }
                    ]
                },
            },
            {
                "id": "example_traverse",
                "kind": "curve",
                "label": "Example boundary traverse",
                "op_expr": {
                    "op_name": "CourseTraverse",
                    "params": {
                        "courses": [
                            {
                                "bearing": 90.0,
                                "distance": 100.0,
                                "bearing_raw": "East",
                                "distance_raw": "100 feet",
                            },
                            {
                                "bearing": 180.0,
                                "distance": 100.0,
                                "bearing_raw": "South",
                                "distance_raw": "100 feet",
                            },
                            {
                                "bearing": 270.0,
                                "distance": 100.0,
                                "bearing_raw": "West",
                                "distance_raw": "100 feet",
                            },
                            {
                                "bearing": 0.0,
                                "distance": 100.0,
                                "bearing_raw": "North",
                                "distance_raw": "100 feet",
                            },
                        ]
                    },
                    "operands": ["example_start_anchor"],
                },
                "provenance": {
                    "source_entity_links": [
                        _resolution_unit_link(f"call_{call_index}_{value_kind}")
                        for call_index in range(1, 5)
                        for value_kind in ("bearing", "distance")
                    ]
                },
            },
            {
                "id": "example_region",
                "kind": "region",
                "label": "Example closed region",
                "op_expr": {
                    "op_name": "Close",
                    "params": {},
                    "operands": ["example_traverse"],
                },
            },
        ],
        "edges": [
            {
                "source_id": "example_start_anchor",
                "target_id": "example_traverse",
                "edge_type": "next_step",
            },
            {
                "source_id": "example_traverse",
                "target_id": "example_region",
                "edge_type": "derived_from",
            },
        ],
        "metadata": {"coordinate_posture": "local_schematic"},
    }


def build_deed_to_ir_authoring_example() -> dict[str, Any]:
    """Compact deed-to-IR authoring pattern with operand provenance and blocked scope."""
    graph = {
        "graph_id": "deed_to_ir_authoring_example",
        "nodes": [
            {
                "id": "example_frame",
                "kind": "frame",
                "label": "Example survey frame context",
                "op_expr": {
                    "op_name": "ReferenceFrame",
                    "params": {
                        "frame_type": "survey_frame_example",
                        "section": "1",
                        "township": "1N",
                        "range": "1E",
                        "meridian": "Example Meridian",
                        "raw_text": "Example survey frame text",
                    },
                    "operands": [],
                },
            },
            {
                "id": "example_start_anchor",
                "kind": "point",
                "label": "Example local beginning anchor",
                "op_expr": {
                    "op_name": "TiedPoint",
                    "params": {},
                    "operands": [],
                },
                "provenance": {
                    "source_entity_links": [
                        _resolution_unit_link("start_anchor_tie"),
                    ]
                },
            },
            {
                "id": "example_traverse",
                "kind": "curve",
                "label": "Example ordered course traverse",
                "op_expr": {
                    "op_name": "CourseTraverse",
                    "params": {
                        "courses": [
                            {
                                "bearing": 45.0,
                                "distance": 100.0,
                                "bearing_raw": "N. 45° E.",
                                "distance_raw": "100 feet",
                            },
                            {
                                "bearing": 135.0,
                                "distance": 100.0,
                                "bearing_raw": "S. 45° E.",
                                "distance_raw": "100 feet",
                            },
                        ]
                    },
                    "operands": ["example_start_anchor"],
                },
                "provenance": {
                    "source_entity_links": [
                        _resolution_unit_link("call_1_bearing"),
                        _resolution_unit_link("call_1_distance"),
                    ]
                },
            },
            {
                "id": "example_region",
                "kind": "region",
                "label": "Example region (explicit closure policy when needed)",
                "op_expr": {
                    "op_name": "Close",
                    "params": {
                        "closure_mode": "snap_to_start",
                        "closure_tolerance": 5.0,
                    },
                    "operands": ["example_traverse"],
                },
            },
            {
                "id": "example_blocked_scope",
                "kind": "annotation",
                "label": "Example blocked scope — continuation unavailable",
                "provenance": {
                    "source_entity_links": [
                        _resolution_unit_link("blocked_scope_continuation"),
                    ]
                },
            },
        ],
        "edges": [
            {
                "source_id": "example_start_anchor",
                "target_id": "example_traverse",
                "edge_type": "next_step",
            },
            {
                "source_id": "example_traverse",
                "target_id": "example_region",
                "edge_type": "derived_from",
            },
        ],
        "metadata": {
            "notes": (
                "Bounded metadata only. Determined deed values belong on op-backed nodes with "
                "provenance.source_entity_links — not as a metadata substitute for IR structure."
            ),
        },
    }
    return {
        "intent": (
            "Show compiler-supported deed authoring: ReferenceFrame for survey/frame context, "
            "TiedPoint for a local anchor, CourseTraverse as the canonical ordered call sequence, "
            "Close with explicit closure policy when endpoints do not meet exactly, and annotation "
            "for blocked scope without invented geometry."
        ),
        "operand_source": "hydrate_deed_to_ir_input sections=[mapping_operands]",
        "supported_authoring_pattern": [
            "ReferenceFrame — survey/frame context such as PLSS, local stationing, plat grid, or other external basis (non-rendered descriptor)",
            "TiedPoint — local anchor / beginning point",
            "CourseTraverse — ordered calls (canonical deed call sequence primitive)",
            "Close — region from a traverse; set closure_mode/closure_tolerance when calls leave a small endpoint gap",
            "annotation — blocked/incomplete scopes without fake geometry",
        ],
        "unsupported_ops_note": (
            "Invented operation names may preserve meaning in prose but are not mapping-ready. "
            "For a mapped scope, use compiler-supported primitives unless deliberately recording "
            "an unresolved representability gap."
        ),
        "graph": graph,
        "blocked_scope_pattern": {
            "operand_role": "scope_blocker",
            "supported_representation": (
                "Use kind=annotation with source/provenance links and handoff notes when the blocked "
                "scope is known but continuation is unavailable. Reserve unknown for genuinely unknown "
                "feature kinds — not for known blocked/partial/dependency-pending scope."
            ),
            "do_not": (
                "Do not park deed meaning only in graph.metadata, use unknown as the default blocked-scope "
                "representation, or fabricate unavailable calls/geometry."
            ),
        },
    }


def example_forbidden_tokens() -> tuple[str, ...]:
    """Practice-deed tokens that must not appear in canonical example payloads."""
    return _FORBIDDEN_EXAMPLE_TOKENS


def build_operation_example(operation: OperationDef) -> dict[str, Any]:
    params = {
        parameter.name: _parameter_example(parameter)
        for parameter in operation.parameters
        if parameter.required
    }
    operands = [f"feature_{index + 1}" for index in range(operation.min_operands)]
    return {
        "op_name": operation.name,
        "params": params,
        "operands": operands,
    }


def build_reference_node_example() -> dict[str, Any]:
    return {
        "id": "external_station_reference",
        "kind": "point",
        "feature_ref": {
            "feature_id": "station_42",
            "graph_id": "external_station_graph",
            "label": "Referenced station",
            "is_external": True,
        },
    }


def build_direct_geometry_example() -> dict[str, Any]:
    return {
        "id": "known_local_point",
        "kind": "point",
        "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
        "metadata": {"coordinate_posture": "local_schematic"},
    }


def _parameter_example(parameter: ParameterSpec) -> Any:
    if parameter.name == "courses":
        return [
            {
                "bearing": 45.0,
                "distance": 100.0,
                "bearing_raw": "N. 45° E.",
                "distance_raw": "100 feet",
            }
        ]
    if parameter.param_type == "number":
        return 45.0 if parameter.unit == "degrees" else 100.0
    if parameter.param_type == "boolean":
        return True
    if parameter.param_type == "array":
        return []
    return f"example_{parameter.name}"


def _resolution_unit_link(entity_id: str) -> dict[str, str]:
    return {
        "entity_id": entity_id,
        "entity_type": "resolution_unit",
        "source_ref": "transcript_edit:resolution_state:example",
        "relation": "derived_from",
    }
