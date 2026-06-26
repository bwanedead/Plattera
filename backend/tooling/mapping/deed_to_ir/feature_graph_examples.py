"""Canonical valid examples for feature-graph authoring contracts."""

from __future__ import annotations

from typing import Any

from feature_graph.operations import OperationDef, ParameterSpec


def build_complete_supported_graph_example() -> dict[str, Any]:
    """A schema-valid, compiler-supported local parcel example with provenance."""
    return {
        "graph_id": "parcel_1_ir",
        "nodes": [
            {
                "id": "parcel_1_frame",
                "kind": "frame",
                "label": "PLSS section context",
                "op_expr": {
                    "op_name": "ReferenceFrame",
                    "params": {
                        "frame_type": "plss",
                        "section": "12",
                        "township": "3N",
                        "range": "2W",
                        "meridian": "Principal Meridian",
                        "raw_text": "Section 12, Township 3 North, Range 2 West",
                    },
                    "operands": [],
                },
            },
            {
                "id": "parcel_1_origin",
                "kind": "point",
                "label": "Local beginning point",
                "op_expr": {
                    "op_name": "TiedPoint",
                    "params": {},
                    "operands": [],
                },
                "provenance": {
                    "source_entity_links": [
                        {
                            "entity_id": "parcel_1_beginning_point",
                            "entity_type": "resolution_unit",
                            "source_ref": "transcript_edit:resolution_state:example",
                            "relation": "derived_from",
                        }
                    ]
                },
            },
            {
                "id": "parcel_1_boundary",
                "kind": "curve",
                "label": "Parcel boundary traverse",
                "op_expr": {
                    "op_name": "CourseTraverse",
                    "params": {
                        "courses": [
                            {"bearing": 90.0, "distance": 100.0, "bearing_raw": "East", "distance_raw": "100 feet"},
                            {"bearing": 180.0, "distance": 100.0, "bearing_raw": "South", "distance_raw": "100 feet"},
                            {"bearing": 270.0, "distance": 100.0, "bearing_raw": "West", "distance_raw": "100 feet"},
                            {"bearing": 0.0, "distance": 100.0, "bearing_raw": "North", "distance_raw": "100 feet"},
                        ]
                    },
                    "operands": ["parcel_1_origin"],
                },
                "provenance": {
                    "source_entity_links": [
                        _resolution_unit_link(f"parcel_1_call_{call_index}_{value_kind}")
                        for call_index in range(1, 5)
                        for value_kind in ("bearing", "distance")
                    ]
                },
            },
            {
                "id": "parcel_1_region",
                "kind": "region",
                "label": "Parcel region",
                "op_expr": {
                    "op_name": "Close",
                    "params": {},
                    "operands": ["parcel_1_boundary"],
                },
            },
        ],
        "edges": [
            {"source_id": "parcel_1_origin", "target_id": "parcel_1_boundary", "edge_type": "next_step"},
            {"source_id": "parcel_1_boundary", "target_id": "parcel_1_region", "edge_type": "derived_from"},
        ],
        "metadata": {"coordinate_posture": "local_schematic"},
    }


def build_deed_to_ir_authoring_example() -> dict[str, Any]:
    """Compact deed-to-IR authoring pattern with operand provenance and blocked scope."""
    graph = {
        "graph_id": "parcel_1_deed_to_ir_example",
        "nodes": [
            {
                "id": "parcel_1_frame",
                "kind": "frame",
                "label": "PLSS section context",
                "op_expr": {
                    "op_name": "ReferenceFrame",
                    "params": {
                        "frame_type": "plss",
                        "section": "12",
                        "township": "3N",
                        "range": "2W",
                        "meridian": "Principal Meridian",
                        "raw_text": "Section 12, Township 3 North, Range 2 West",
                    },
                    "operands": [],
                },
            },
            {
                "id": "parcel_1_origin",
                "kind": "point",
                "label": "Parcel 1 beginning point",
                "op_expr": {
                    "op_name": "TiedPoint",
                    "params": {},
                    "operands": [],
                },
                "provenance": {
                    "source_entity_links": [
                        _resolution_unit_link("p1_pob_canal_offset"),
                    ]
                },
            },
            {
                "id": "parcel_1_boundary",
                "kind": "curve",
                "label": "Parcel 1 deed call sequence",
                "op_expr": {
                    "op_name": "CourseTraverse",
                    "params": {
                        "courses": [
                            {
                                "bearing": 68.5,
                                "distance": 542.0,
                                "bearing_raw": "N. 68° 30' East",
                                "distance_raw": "542 feet, more or less",
                            },
                            {
                                "bearing": 158.5,
                                "distance": 200.0,
                                "bearing_raw": "S. 68° 30' East",
                                "distance_raw": "200 feet",
                            },
                        ]
                    },
                    "operands": ["parcel_1_origin"],
                },
                "provenance": {
                    "source_entity_links": [
                        _resolution_unit_link("p1_call1_bearing"),
                        _resolution_unit_link("p1_call1_distance"),
                    ]
                },
            },
            {
                "id": "parcel_1_region",
                "kind": "region",
                "label": "Parcel 1 region (explicit closure policy when needed)",
                "op_expr": {
                    "op_name": "Close",
                    "params": {
                        "closure_mode": "snap_to_start",
                        "closure_tolerance": 5.0,
                    },
                    "operands": ["parcel_1_boundary"],
                },
            },
            {
                "id": "parcel_2_blocked_scope",
                "kind": "annotation",
                "label": "Parcel 2 visible opening only — continuation unavailable",
                "provenance": {
                    "source_entity_links": [
                        _resolution_unit_link("parcel_2_continuation_scope"),
                    ]
                },
            },
        ],
        "edges": [
            {
                "source_id": "parcel_1_origin",
                "target_id": "parcel_1_boundary",
                "edge_type": "next_step",
            },
            {
                "source_id": "parcel_1_boundary",
                "target_id": "parcel_1_region",
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
            "Show compiler-supported deed authoring: ReferenceFrame for PLSS context, TiedPoint for "
            "POB, CourseTraverse as the canonical deed call sequence, Close with explicit closure "
            "policy when endpoints do not meet exactly, and annotation for blocked scope without "
            "invented geometry."
        ),
        "operand_source": "hydrate_deed_to_ir_input sections=[mapping_operands]",
        "supported_authoring_pattern": [
            "ReferenceFrame — PLSS/frame context (non-rendered descriptor)",
            "TiedPoint — POB / tied descriptive anchor",
            "CourseTraverse — ordered deed calls (canonical deed call sequence primitive)",
            "Close — parcel region; set closure_mode/closure_tolerance when more-or-less calls leave a small gap",
            "annotation — blocked/incomplete scopes (e.g. Parcel 2 continuation unavailable)",
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
                "Use annotation or unknown without geometry/op_expr/feature_ref when continuation "
                "is unavailable."
            ),
            "do_not": (
                "Do not park deed meaning only in graph.metadata or fabricate unavailable calls."
            ),
        },
    }


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
                "bearing_raw": "N 45 degrees E",
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
