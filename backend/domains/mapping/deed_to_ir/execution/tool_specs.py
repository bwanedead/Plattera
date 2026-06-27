"""Executable tool specs for deed-to-IR foundation tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domains.mapping.deed_to_ir.payloads.published_output_tool_schema import (
    build_publish_deed_to_ir_output_request_json_shape,
)
from tooling.mapping.deed_to_ir.feature_graph_contract_projection import (
    build_compact_feature_node_request_schema,
    build_feature_node_kind_contract,
)
from tooling.mapping.deed_to_ir.feature_graph_capabilities import (
    DEFAULT_CAPABILITY_SECTIONS,
    VALID_CAPABILITY_SECTIONS,
)
from tooling.mapping.deed_to_ir.input_hydration import MAX_RESOLUTION_UNIT_IDS, VALID_SECTIONS
from tooling.mapping.deed_to_ir.mapping_operands_projection import (
    MAX_MAPPING_OPERANDS,
    MAX_OPERAND_CANDIDATE_VALUES,
    MAX_OPERAND_DETERMINED_VALUE_CHARS,
    MAX_OPERAND_EVIDENCE_REFS,
)
from tooling.mapping.deed_to_ir.resolution_state_projection import (
    MAX_INDEX_ITEMS,
    MAX_INDEX_RELATIONS,
    MAX_INDEX_UNITS,
    MAX_SELECTED_ITEM_ROWS,
    MAX_SELECTED_UNITS_TOTAL,
)

_RESOLUTION_UNIT_ID_MAX_LENGTH = 128


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
                "Every successful call also returns inherited_handoff_conditions — a compact mechanical "
                "copy of upstream parcel/issue/HITL/evidence/transcript lanes (not agent conclusions). "
                "Sections include inherited_handoff_conditions, transcript lanes, parcel metadata, issues, "
                "HITL decisions, evidence refs, mapping_operands, and resolution_state. "
                "mapping_operands returns a compact table of upstream determined values and scope blockers "
                "for IR authoring without nested resolution-state rereads. "
                "resolution_state returns a compact index by default (projection_mode=index: item/unit/relation "
                "inventory without opaque payloads). When resolution_unit_ids is supplied, returns selected_rows "
                "projections for the requested ids only. Deterministic code copies fields mechanically — "
                "no semantic summaries or filesystem paths."
            ),
            expected_request_shape=(
                "sections: required non-empty array of section names. "
                "resolution_unit_ids: optional exact item or covered-unit ids (max 64) to switch "
                "resolution_state into selected_rows mode."
            ),
            expected_request_json_shape={
                "type": "object",
                "required": ["sections"],
                "properties": {
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": sorted(VALID_SECTIONS),
                        },
                        "minItems": 1,
                    },
                    "resolution_unit_ids": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": _RESOLUTION_UNIT_ID_MAX_LENGTH,
                        },
                        "maxItems": MAX_RESOLUTION_UNIT_IDS,
                        "description": (
                            "Optional exact resolution item or covered-unit ids. When present, "
                            "resolution_state hydrates as projection_mode=selected_rows instead of index."
                        ),
                    },
                },
                "additionalProperties": False,
            },
            example_request={
                "sections": ["mapping_operands", "normalized_transcript"],
            },
            batching={
                "allowed": True,
                "max_calls_per_batch": 3,
                "side_effect_class": "read_only",
                "can_run_parallel": True,
            },
            expected_result_shape=(
                "outputs.inherited_handoff_conditions: always present — bounded mechanical copy of upstream "
                "parcel forwardability, issues, HITL decisions, evidence refs, and transcript lane excerpts. "
                "outputs.results: map of section -> bounded payload. "
                "mapping_operands: projection_mode=mapping_operands with compact operand rows for closed/earned "
                f"atoms and scope blockers (max {MAX_MAPPING_OPERANDS} emitted rows; per-row caps on "
                f"determined_value ({MAX_OPERAND_DETERMINED_VALUE_CHARS} chars), candidate_values "
                f"(max {MAX_OPERAND_CANDIDATE_VALUES}), evidence_refs (max {MAX_OPERAND_EVIDENCE_REFS}); "
                "explicit truncation counts; operand_suite_ref for pin/hydrate; optional operand_groups when "
                "operand ids mechanically encode call numbers). "
                "resolution_state without resolution_unit_ids: projection_mode=index with compact "
                f"items (max {MAX_INDEX_ITEMS}), units (max {MAX_INDEX_UNITS}), relations (max {MAX_INDEX_RELATIONS}), "
                "and optional truncation counts. "
                "resolution_state with resolution_unit_ids: projection_mode=selected_rows with up to "
                f"{MAX_SELECTED_ITEM_ROWS} item rows and {MAX_SELECTED_UNITS_TOTAL} matched units total, "
                "filter echoing the capped id list, and optional truncation/not_found errors. "
                "outputs.errors: unavailable/not_found entries per section or resolution_unit_id. "
                "Selected-row unit matches include parent_item_id and parent_item_title when available."
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
                "sections: optional non-empty subset of starter_contract|core_schema|provenance|operations|"
                "examples|artifact_refs|validation_schema; defaults to starter_contract when omitted. "
                "operation_names: optional exact registered operation names filtering operations/examples."
            ),
            expected_request_json_shape={
                "type": "object",
                "properties": {
                    "sections": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "string",
                            "enum": sorted(VALID_CAPABILITY_SECTIONS),
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
                "sections": list(DEFAULT_CAPABILITY_SECTIONS),
            },
            batching={
                "allowed": True,
                "max_calls_per_batch": 2,
                "side_effect_class": "read_only",
                "can_run_parallel": True,
            },
            expected_result_shape=(
                "Selected contract sections. Default starter_contract returns compact feature kinds, "
                "feature_kind_vs_operation_contract, node-content rules, provenance link fields, artifact ref "
                "prefixes, and a bounded operation index. "
                "When operation_names filters are supplied, ignored_operation_names lists invalid entries "
                "(feature_kind_not_operation for feature kinds like annotation; unknown_operation_name otherwise). "
                "Refuse only when no valid operation names remain (no_valid_feature_graph_operation_names). "
                "core_schema includes model_schemas, feature_kinds, content rules, geometry, and edge conventions. "
                "Operations include exact params, units, operands, support status, and examples. "
                "Provenance includes source_entity_links. Examples include complete_supported_graph and "
                "deed_to_ir_authoring patterns."
            ),
        ),
        SemanticToolSpec(
            tool_id="save_ir_artifact",
            category="write",
            purpose=(
                "Save a draft IR checkpoint (working, versioned FeatureGraph artifact). "
                "Schema validation runs first; on success the draft is persisted and deterministic "
                "compile/judge feedback is returned immediately. This is not final publication and "
                "does not render maps. Use describe_feature_graph_capabilities for contract details."
            ),
            expected_request_shape=(
                "feature_graph: required FeatureGraph {graph_id:string, nodes?:FeatureNode[], edges?:FeatureEdge[], "
                "metadata?:object}; graph_id is the stable logical graph id — do not embed draft version numbers "
                "(use base_draft_ref to continue a working draft). "
                "nodes/edges default empty but should be supplied for authored work. "
                "FeatureNode requires id + kind (point|curve|region|frame|constraint|annotation|unknown) and permits "
                "AT MOST ONE of geometry|op_expr|feature_ref; omitting all three is valid only with kind=unknown. "
                "FeatureEdge uses exact source_id, target_id, and edge_type. OpExpr is {op_name, params?, operands?}. "
                "Optional provenance.source_entity_links rows are {entity_id, entity_type, source_ref, relation?}. "
                "base_draft_ref: optional feature_graph:ir:* ref to continue a working draft on the same graph_id. "
                "artifact_id, source_document_id, created_by: optional strings."
            ),
            expected_request_json_shape={
                "type": "object",
                "required": ["feature_graph"],
                "properties": {
                    "feature_graph": {
                        "type": "object",
                        "required": ["graph_id"],
                        "properties": {
                            "graph_id": {"type": "string", "minLength": 1},
                            "nodes": {
                                "type": "array",
                                "items": build_compact_feature_node_request_schema(),
                            },
                            "edges": {"type": "array"},
                            "metadata": {"type": ["object", "null"]},
                        },
                        "additionalProperties": True,
                    },
                    "artifact_id": {"type": ["string", "null"]},
                    "base_draft_ref": {"type": ["string", "null"]},
                    "source_document_id": {"type": ["string", "null"]},
                    "created_by": {"type": ["string", "null"]},
                },
                "additionalProperties": False,
            },
            example_request={
                "feature_graph": {
                    "graph_id": "schematic_graph_example",
                    "nodes": [
                        {
                            "id": "example_call_1",
                            "kind": "curve",
                            "op_expr": {
                                "op_name": "LineStep",
                                "params": {
                                    "bearing": 45.0,
                                    "distance": 100.0,
                                    "bearing_raw": "N. 45° E.",
                                    "distance_raw": "100 feet",
                                },
                                "operands": [],
                            },
                            "provenance": {
                                "source_entity_links": [
                                    {
                                        "entity_id": "call_1_distance",
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
                "On success: draft checkpoint identity — outputs.ir_artifact_ref (canonical), "
                "outputs.draft_ir_ref and outputs.working_draft_ref (ergonomic aliases of the same ref), "
                "draft_version (v0, v1, ...), draft_sequence_index, is_draft=true, structural draft metrics "
                "(node/edge counts, unknown/renderable/geometry/op_expr/feature_ref counts, "
                "source_entity_link_count, placeholder_only_graph), current_draft_ir compact lane with "
                "bounded draft_repair_items (node_id, node_kind, current_operation, issue, reason), "
                "compile_artifact_ref, judge_artifact_ref, working_compile_ref, working_judge_ref, compile_gap_count, judge_finding_count, "
                "bounded compile_gaps/judge_findings (node-precise feature_id/node_id, gap_kind, operation, reason), "
                "mechanically_mappable_candidate (compile/judge-only), "
                "and mapping_submission_ready_candidate (structural + compile/judge readiness — not deed-correct). "
                "CourseTraverse courses require numeric bearing/distance; use operand-suite parsed fields "
                "(bearing, distance, bearing_degrees, distance_feet) — raw-only rows do not compile. "
                "On validation failure: executed=false, reason_codes=[feature_graph_validation_failed], "
                "retryable refusal, and bounded outputs.validation_errors (no artifact saved). "
                "On graph_id mismatch with base_draft_ref: executed=false, reason_code=draft_graph_id_mismatch, "
                "expected_graph_id and actual_graph_id (no artifact saved)."
            ),
        ),
        SemanticToolSpec(
            tool_id="patch_ir_draft",
            category="write",
            purpose=(
                "Surgically patch an existing draft IR checkpoint without resubmitting the whole graph. "
                "Loads base_draft_ref, applies id-exact node/edge upserts and optional removals, validates "
                "the full FeatureGraph, saves the next append-only draft version on the same graph_id, and "
                "returns the same compile/judge feedback lane as save_ir_artifact."
            ),
            expected_request_shape=(
                "base_draft_ref: required feature_graph:ir:* ref for the draft to patch. "
                "node_upserts: optional array of FeatureNode patches keyed by exact id (deep-merge dictionaries; "
                "arrays/scalars replace; null clears a field). "
                "edge_upserts: optional array of FeatureEdge patches keyed by source_id+target_id+edge_type. "
                "node_removals / edge_removals: optional exact-id removals (missing ids are no-ops with warnings). "
                "graph_id: optional; when supplied must match the base draft graph_id."
            ),
            expected_request_json_shape={
                "type": "object",
                "required": ["base_draft_ref"],
                "properties": {
                    "base_draft_ref": {"type": "string", "minLength": 1},
                    "graph_id": {"type": ["string", "null"]},
                    "node_upserts": {
                        "type": ["array", "null"],
                        "items": build_compact_feature_node_request_schema(),
                    },
                    "edge_upserts": {"type": ["array", "null"], "items": {"type": "object"}},
                    "node_removals": {
                        "type": ["array", "null"],
                        "items": {"type": "string", "minLength": 1},
                    },
                    "edge_removals": {"type": ["array", "null"], "items": {"type": "object"}},
                },
                "additionalProperties": False,
            },
            example_request={
                "base_draft_ref": "feature_graph:ir:right_of_way_deed_ir_v0",
                "node_upserts": [
                    {
                        "id": "parcel_1_traverse",
                        "kind": "curve",
                        "op_expr": {
                            "op_name": "CourseTraverse",
                            "operands": ["parcel_1_anchor"],
                            "params": {"courses": []},
                        },
                    }
                ],
                "edge_upserts": [
                    {
                        "source_id": "parcel_1_traverse",
                        "target_id": "parcel_1_region",
                        "edge_type": "derived_from",
                    }
                ],
            },
            batching={
                "allowed": False,
                "side_effect_class": "write",
            },
            expected_result_shape=(
                "Same success/failure outputs as save_ir_artifact (working_draft_ref, working_compile_ref, "
                "working_judge_ref, draft_version, current_draft_ir, draft_repair_items, compile/judge refs and gaps). "
                "Nested op_expr.params patches preserve existing op_name/operands when omitted. "
                "CourseTraverse course rows need numeric bearing/distance from operand-suite parsed fields. "
                "Optional outputs.patch_warnings when removals target missing ids. "
                "Validation failure is retryable and persists nothing."
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
            tool_id="publish_deed_to_ir_output",
            category="write",
            purpose=(
                "Publish one agent-authored deed-to-IR handoff package from a selected mapping revision. "
                "Mechanically derives exact IR, compile, judge, geometry, and render lineage from the mapping "
                "artifact. Records agent-authored scope, dependency, and closure posture; does not determine closure."
            ),
            expected_request_shape=(
                "mapping_artifact_ref: required feature_graph:mapping:* ref from the current dossier. "
                "scope_results, external_dependencies, closure_dimensions, notes: agent-authored bounded rows."
            ),
            expected_request_json_shape=build_publish_deed_to_ir_output_request_json_shape(),
            example_request={
                "mapping_artifact_ref": "feature_graph:mapping:mapping_parcel_1_ab12cd34",
                "scope_results": [
                    {
                        "scope_id": "parcel_1",
                        "status": "mapped",
                        "summary": "Primary parcel mapped with partial dependency pending on adjoiner call.",
                    }
                ],
                "closure_dimensions": [
                    {
                        "dimension_id": "layer_4_map_handoffability_scoped_completion",
                        "status": "partial",
                        "summary": "Parcel 1 mapped; parcel 2 blocked pending external dependency.",
                        "basis_refs": ["feature_graph:mapping:mapping_parcel_1_ab12cd34"],
                    }
                ],
            },
            batching={
                "allowed": False,
                "side_effect_class": "write",
            },
            expected_result_shape=(
                "On success: artifact_refs begin with deed_to_ir:output and revision ref, then mapping package "
                "and render refs. outputs include output_ref, output_revision_ref, selected artifact refs, "
                "and bounded scope/dependency/closure counts without filesystem paths or image bytes."
            ),
        ),
        SemanticToolSpec(
            tool_id="hydrate_artifact_refs",
            category="read",
            purpose=(
                "Hydrate feature-graph artifact refs (ir, compile, judge, bundle, mapping), mapping "
                "sidecar refs (geometry.geojson, clean.png, control.png), deed-to-IR operand suite refs "
                "(deed_to_ir:operands, deed_to_ir:operands:run:*, deed_to_ir:operands:ws:*), and deed-to-IR "
                "output refs (deed_to_ir:output, deed_to_ir:output:rev:NNNN). Returns bounded payloads "
                "without filesystem paths. PNG sidecars return top-level image_evidence."
            ),
            expected_request_shape=(
                "ref_ids: required non-empty array of feature_graph:*, artifact://dossiers/feature_graphs/*, "
                "deed_to_ir:operands*, or deed_to_ir:output* refs. max_refs: optional cap (default 8, max 32). "
                "working_draft_ref: optional feature_graph:ir:* ref used to label compile/judge hydration rows "
                "with is_current_for_working_draft."
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
                    "working_draft_ref": {"type": ["string", "null"]},
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
                "Compile/judge rows include artifact_ref, parent_ir_ref, parent_graph_id, parent_draft_version, "
                "and optional is_current_for_working_draft when working_draft_ref is supplied. "
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
