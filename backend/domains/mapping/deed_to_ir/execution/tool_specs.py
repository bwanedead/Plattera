"""Executable tool specs for deed-to-IR foundation tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SemanticToolSpec:
    tool_id: str
    category: str
    purpose: str
    expected_request_shape: str
    expected_request_json_shape: dict[str, Any]
    expected_result_shape: str
    example_request: dict[str, Any]
    batching: dict[str, Any] | None = None


def build_deed_to_ir_tool_specs() -> tuple[SemanticToolSpec, ...]:
    return (
        SemanticToolSpec(
            tool_id="hydrate_deed_to_ir_input",
            category="read",
            purpose=(
                "Hydrate bounded upstream deed-to-IR input lanes from the startup handoff context. "
                "Sections include transcript lanes, parcel metadata, issues, HITL decisions, evidence refs, "
                "and the full resolution_state work graph. Deterministic code copies fields mechanically — "
                "no semantic summaries or filesystem paths."
            ),
            expected_request_shape=(
                "sections: required non-empty array of section names. "
                "resolution_unit_ids: optional exact ids to filter resolution_state items or covered units."
            ),
            expected_request_json_shape={
                "type": "object",
                "required": ["sections"],
                "properties": {
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "normalized_transcript",
                                "verbatim_transcript",
                                "parcel_metadata",
                                "issues",
                                "hitl_decisions",
                                "evidence_refs",
                                "resolution_state",
                            ],
                        },
                        "minItems": 1,
                    },
                    "resolution_unit_ids": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": "Optional exact resolution item or covered-unit ids.",
                    },
                },
                "additionalProperties": False,
            },
            example_request={
                "sections": ["normalized_transcript", "resolution_state"],
                "resolution_unit_ids": ["p1_call1_distance"],
            },
            batching={
                "allowed": True,
                "max_calls_per_batch": 3,
                "side_effect_class": "read_only",
                "can_run_parallel": True,
            },
            expected_result_shape=(
                "outputs.results: map of section -> bounded payload. "
                "outputs.errors: unavailable/not_found entries per section or resolution_unit_id. "
                "Covered-unit filter results include parent_item_id and parent_item_title."
            ),
        ),
        SemanticToolSpec(
            tool_id="describe_feature_graph_capabilities",
            category="read",
            purpose=(
                "Hydrate exact feature-graph authoring contracts: compact model schemas, provenance, "
                "registered operations, parameter/operand constraints, compiler-support status, and valid examples. "
                "Use operation_names for a focused vocabulary packet and validation_schema only when the raw "
                "canonical Pydantic schema is needed. Does not recommend which operation the deed should use."
            ),
            expected_request_shape=(
                "sections: optional non-empty subset of core_schema|provenance|operations|examples|artifact_refs|"
                "validation_schema; defaults to all ergonomic sections except validation_schema. "
                "operation_names: optional exact registered operation names filtering operations/examples."
            ),
            expected_request_json_shape={
                "type": "object",
                "properties": {
                    "sections": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "string",
                            "enum": [
                                "core_schema",
                                "provenance",
                                "operations",
                                "examples",
                                "artifact_refs",
                                "validation_schema",
                            ],
                        },
                        "minItems": 1,
                    },
                    "operation_names": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                },
                "additionalProperties": False,
            },
            example_request={
                "sections": ["core_schema", "provenance", "operations", "examples"],
                "operation_names": ["TiedPoint", "CourseTraverse", "Close"],
            },
            batching={
                "allowed": True,
                "max_calls_per_batch": 2,
                "side_effect_class": "read_only",
                "can_run_parallel": True,
            },
            expected_result_shape=(
                "Selected contract sections. Core includes model_schemas, feature_kinds, content rules, geometry, "
                "and edge conventions. Operations include exact params, units, operands, support status, and examples. "
                "Provenance includes source_entity_links. Examples include one complete supported graph."
            ),
        ),
        SemanticToolSpec(
            tool_id="save_ir_artifact",
            category="write",
            purpose=(
                "Validate and persist an agent-authored FeatureGraph IR artifact. "
                "Schema validation only — no compile, judge, render, repair, or closure behavior. "
                "The compact core contract is always visible here; use describe_feature_graph_capabilities for details."
            ),
            expected_request_shape=(
                "feature_graph: required FeatureGraph {graph_id:string, nodes?:FeatureNode[], edges?:FeatureEdge[], "
                "metadata?:object}; nodes/edges default empty but should be supplied for authored work. "
                "FeatureNode requires id + kind and permits AT MOST ONE of geometry|op_expr|"
                "feature_ref; none is valid for unresolved/semantic nodes. FeatureEdge uses exact source_id, target_id, "
                "and edge_type. OpExpr is {op_name, params?, operands?}. Optional provenance.source_entity_links rows "
                "are {entity_id, entity_type, source_ref, relation?}. "
                "artifact_id, source_document_id, created_by: optional strings."
            ),
            expected_request_json_shape={
                "type": "object",
                "required": ["feature_graph"],
                "properties": {
                    "feature_graph": {
                        "type": "object",
                        "description": (
                            "Agent-authored FeatureGraph with graph_id, nodes, edges, and optional metadata. "
                            "Node content is at most one of geometry, op_expr, or feature_ref."
                        ),
                    },
                    "artifact_id": {"type": ["string", "null"]},
                    "source_document_id": {"type": ["string", "null"]},
                    "created_by": {"type": ["string", "null"]},
                },
                "additionalProperties": False,
            },
            example_request={
                "feature_graph": {
                    "graph_id": "parcel_1_ir",
                    "nodes": [
                        {
                            "id": "parcel_1_call_1",
                            "kind": "curve",
                            "op_expr": {
                                "op_name": "LineStep",
                                "params": {
                                    "bearing": 45.0,
                                    "distance": 100.0,
                                    "bearing_raw": "N 45 degrees E",
                                    "distance_raw": "100 feet",
                                },
                                "operands": [],
                            },
                            "provenance": {
                                "source_entity_links": [
                                    {
                                        "entity_id": "parcel_1_call_1",
                                        "entity_type": "resolution_unit",
                                        "source_ref": "transcript_edit:resolution_state:example",
                                        "relation": "derived_from",
                                    }
                                ]
                            },
                        }
                    ],
                    "edges": [],
                }
            },
            batching={
                "allowed": False,
                "side_effect_class": "write",
            },
            expected_result_shape=(
                "On success: artifact_refs include feature_graph:ir:* ref; outputs.ir_artifact_ref, "
                "graph_id, node_count, edge_count, source_entity_link_count. "
                "On validation failure: executed=false with outputs.validation_errors."
            ),
        ),
        SemanticToolSpec(
            tool_id="submit_ir_for_mapping",
            category="write",
            purpose=(
                "Submit one saved IR artifact for mapping. Internally compiles, judges, projects geometry, "
                "and renders clean/control maps as deterministic stages of this single submission. "
                "Compile, judge, and render are not separate agent workflow actions."
            ),
            expected_request_shape=(
                "ir_artifact_ref: required canonical feature_graph:ir:* ref from the current dossier."
            ),
            expected_request_json_shape={
                "type": "object",
                "required": ["ir_artifact_ref"],
                "properties": {
                    "ir_artifact_ref": {"type": "string"},
                },
                "additionalProperties": False,
            },
            example_request={
                "ir_artifact_ref": "feature_graph:ir:ir_parcel_1_ab12cd34",
            },
            batching={
                "allowed": False,
                "side_effect_class": "write",
            },
            expected_result_shape=(
                "On success: artifact_refs include mapping, compile, judge, IR, and sidecar refs. "
                "Top-level image_evidence carries clean/control PNG payloads. outputs include bounded "
                "counts, coordinate_space, world_bbox, and canonical refs without filesystem paths."
            ),
        ),
        SemanticToolSpec(
            tool_id="hydrate_artifact_refs",
            category="read",
            purpose=(
                "Hydrate feature-graph artifact refs (ir, compile, judge, bundle, mapping) and mapping "
                "sidecar refs (geometry.geojson, clean.png, control.png). Returns bounded payloads "
                "without filesystem paths. PNG sidecars return top-level image_evidence."
            ),
            expected_request_shape=(
                "ref_ids: required non-empty array of feature_graph:* or artifact://dossiers/feature_graphs/* refs. "
                "max_refs: optional cap (default 8, max 32)."
            ),
            expected_request_json_shape={
                "type": "object",
                "required": ["ref_ids"],
                "properties": {
                    "ref_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "max_refs": {"type": ["integer", "null"]},
                },
                "additionalProperties": False,
            },
            example_request={
                "ref_ids": ["feature_graph:ir:ir_parcel_1_ab12cd34"],
                "max_refs": 4,
            },
            batching={
                "allowed": True,
                "max_calls_per_batch": 3,
                "side_effect_class": "read_only",
                "can_run_parallel": True,
            },
            expected_result_shape=(
                "outputs.results: hydrated artifacts or sidecars keyed by ref with bounded payloads. "
                "outputs.errors: per-ref not_found, prefix, or scope errors. "
                "image_evidence: present for PNG sidecar refs only."
            ),
        ),
        SemanticToolSpec(
            tool_id="list_feature_graph_artifacts",
            category="read",
            purpose=(
                "List indexed feature-graph artifacts for the current dossier. "
                "Supports ir, compile, judge, bundle, and mapping artifact types."
            ),
            expected_request_shape=(
                "artifact_type: optional filter (ir|compile|judge|bundle|mapping). "
                "limit: optional cap (default 32, max 64)."
            ),
            expected_request_json_shape={
                "type": "object",
                "properties": {
                    "artifact_type": {
                        "type": ["string", "null"],
                        "enum": ["ir", "compile", "judge", "bundle", "mapping", None],
                    },
                    "limit": {"type": ["integer", "null"]},
                },
                "additionalProperties": False,
            },
            example_request={"artifact_type": "ir", "limit": 16},
            batching={
                "allowed": True,
                "max_calls_per_batch": 2,
                "side_effect_class": "read_only",
                "can_run_parallel": True,
            },
            expected_result_shape=(
                "outputs.artifacts: list of {artifact_ref, artifact_id, artifact_type, saved_at}. "
                "No filesystem paths."
            ),
        ),
    )
