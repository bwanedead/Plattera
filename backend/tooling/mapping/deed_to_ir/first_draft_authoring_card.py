"""Compact first-draft FeatureGraph authoring card for deed-to-IR orientation."""

from __future__ import annotations

from typing import Any

from feature_graph.models import FeatureKind
from feature_graph.operations import OPERATION_REGISTRY

_FIRST_DRAFT_OPERATIONS = (
    "ReferenceFrame",
    "TiedPoint",
    "CourseTraverse",
    "Close",
)


def build_first_draft_authoring_card() -> dict[str, Any]:
    """Generic deed-to-IR first-draft recipe — no practice-deed values."""
    return {
        "purpose": (
            "Minimal recipe for the common mappable deed path after operand hydration. "
            "Save a draft once this card is visible; reread full capabilities only for "
            "new primitives or concrete validation errors."
        ),
        "valid_node_kinds": [kind.value for kind in FeatureKind],
        "normal_deed_operation_names": list(_FIRST_DRAFT_OPERATIONS),
        "course_traverse_compiler_required_fields": ["bearing", "distance"],
        "course_traverse_source_trace_fields": ["bearing_raw", "distance_raw"],
        "raw_only_course_fields_do_not_compile": (
            "Numeric bearing and distance are compiler-critical; bearing_raw and distance_raw "
            "preserve source text only and do not compile by themselves."
        ),
        "close_policy_shape": {
            "closure_mode": "snap_to_start | explicit policy when endpoints nearly meet",
            "closure_tolerance": "feet; agent-authored when snap is honest",
            "operands": "exactly one curve/traverse feature id",
        },
        "blocked_incomplete_scope": (
            "kind=annotation with no op_expr; cite source_entity_links; do not fabricate geometry"
        ),
        "minimum_source_entity_links_pattern": {
            "entity_id": "exact upstream operand_id or resolution item id",
            "entity_type": "resolution_unit | resolution_item | equivalent upstream type",
            "source_ref": "inherited resolution_state_ref or operand_suite_ref",
            "relation": "derived_from",
        },
        "generic_skeleton": _generic_skeleton(),
        "registered_operation_names": sorted(OPERATION_REGISTRY),
    }


def _generic_skeleton() -> dict[str, Any]:
    return {
        "graph_id": "example_scope_graph",
        "nodes": [
            {
                "id": "example_frame",
                "kind": "frame",
                "op_expr": {
                    "op_name": "ReferenceFrame",
                    "params": {"frame_type": "example_frame", "raw_text": "Example frame text"},
                    "operands": [],
                },
            },
            {
                "id": "example_anchor",
                "kind": "point",
                "op_expr": {"op_name": "TiedPoint", "params": {}, "operands": []},
                "provenance": {
                    "source_entity_links": [
                        {
                            "entity_id": "example_anchor_operand",
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
                "op_expr": {
                    "op_name": "CourseTraverse",
                    "params": {
                        "courses": [
                            {
                                "bearing": 90.0,
                                "distance": 100.0,
                                "bearing_raw": "East",
                                "distance_raw": "100 feet",
                            }
                        ]
                    },
                    "operands": ["example_anchor"],
                },
            },
            {
                "id": "example_region",
                "kind": "region",
                "op_expr": {
                    "op_name": "Close",
                    "params": {"closure_mode": "snap_to_start", "closure_tolerance": 2.0},
                    "operands": ["example_traverse"],
                },
            },
            {
                "id": "example_blocked_scope",
                "kind": "annotation",
                "label": "Example blocked or incomplete scope",
            },
        ],
        "edges": [],
        "metadata": {"coordinate_posture": "local_schematic"},
    }
