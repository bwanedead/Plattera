"""Executable tool specs for deed-to-IR foundation tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domains.mapping.deed_to_ir.payloads.final_package_example import (
    build_prepare_deed_to_ir_final_package_example_request,
)
from domains.mapping.deed_to_ir.payloads.finalize_current_output_tool_schema import (
    build_finalize_current_deed_to_ir_output_example_request,
    build_finalize_current_deed_to_ir_output_request_json_shape,
)
from domains.mapping.deed_to_ir.payloads.final_package_preview_tool_schema import (
    build_prepare_deed_to_ir_final_package_request_json_shape,
    build_publish_deed_to_ir_output_request_json_shape_with_preview,
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
                "mapping_operands is the compact authoring operand lane — paired with the feature-graph "
                "capability contract it is usually enough for first IR drafting. "
                "Every successful call also returns inherited_handoff_conditions except when "
                "mapping_operands is the only requested section (operand rows are prioritized; inherited "
                "handoff is deferred with a pointer to startup context). "
                "Sections include inherited_handoff_conditions, transcript lanes, parcel metadata, issues, "
                "HITL decisions, evidence refs, mapping_operands, and resolution_state. "
                "mapping_operands returns operand_suite_ref, compact operand rows, and optional operand_groups "
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
                "outputs.mapping_operands: present when requested — top-level compact lane with "
                "operand_suite_ref, operand_groups when mechanically derivable, and bounded operand rows. "
                "outputs.inherited_handoff_conditions: present — full mechanical copy unless only "
                "mapping_operands was requested (then deferred_for_operand_lane with pointer). "
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
                "source_entity_link_count, placeholder_only_graph), draft_quality_flags "
                "(mechanical only: no_source_entity_links, unknown_nodes_present — not blockers), "
                "current_draft_ir compact lane with "
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
                "Supports course_updates for CourseTraverse row field patches, plus id-exact node/edge "
                "upserts and optional removals. Validates the full FeatureGraph, saves the next "
                "append-only draft version on the same graph_id, and returns the same compile/judge "
                "feedback lane as save_ir_artifact."
            ),
            expected_request_shape=(
                "base_draft_ref: required feature_graph:ir:* ref for the draft to patch. "
                "course_updates: optional array for CourseTraverse row field patches — each entry needs "
                "node_id, 1-based course_index, field (distance|bearing|distance_raw|bearing_raw), and agent-authored "
                "value; optional source_entity_id and basis_refs (audit metadata; not applied by the handler). "
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
                    "course_updates": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "required": ["node_id", "course_index", "field", "value"],
                            "properties": {
                                "node_id": {"type": "string", "minLength": 1},
                                "course_index": {"type": "integer", "minimum": 1},
                                "field": {
                                    "type": "string",
                                    "enum": ["distance", "bearing", "distance_raw", "bearing_raw"],
                                },
                                "value": {},
                                "source_entity_id": {"type": ["string", "null"]},
                                "basis_refs": {
                                    "type": ["array", "null"],
                                    "items": {"type": "string", "minLength": 1},
                                },
                            },
                            "additionalProperties": False,
                        },
                    },
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
                "base_draft_ref": "feature_graph:ir:example_scope_draft_v0",
                "course_updates": [
                    {
                        "node_id": "example_traverse",
                        "course_index": 2,
                        "field": "distance",
                        "value": 410,
                        "source_entity_id": "example_call2_distance",
                        "basis_refs": ["image:derived:example_evidence_ref"],
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
                "course_updates refusals are retryable (course_update_node_missing, "
                "course_update_not_course_traverse, course_update_index_out_of_range, "
                "course_update_field_invalid, course_update_value_invalid). "
                "Nested op_expr.params patches preserve existing op_name/operands when omitted. "
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
                "ir_artifact_ref: required canonical feature_graph:ir:* ref from the current dossier. "
                "After submit, inspect outputs.mapping_review and use recommended_review_refs; "
                "do not hydrate @this.result.artifact_refs[] for ordinary mapping review."
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
                "ir_artifact_ref": "feature_graph:ir:example_scope_v1",
            },
            batching={
                "allowed": False,
                "side_effect_class": "write",
            },
            expected_result_shape=(
                "On success: outputs.mapping_review carries compact refs, counts, recommended_review_refs, "
                "recommended_publish_refs, active_handoff_context (sole hot mapping/IR candidate when lineage "
                "is current and selected for next preview), current_mapping_lineage (canonical current "
                "mapping/IR pair with lineage_current / use_for_next_preview), lineage_lock (compatibility "
                "projection of the same pair), sanity_review (feature_metrics, course_leg_tables, "
                "endpoint_displacement_candidates, recommended_source_evidence_refs, review_questions), "
                "draft_patch_targets (mechanical CourseTraverse patch locations from course leg source entity ids), "
                "and optional correction_posture with matching_patch_target_id / patch_update_shells. "
                "After a successful remap, use active_handoff_context / current_mapping_lineage (or lineage_lock) "
                "for the next intent-first preview — do not mix prior mapping/IR refs. Prefer "
                "mapping_review.recommended_review_refs "
                "over @this.result.artifact_refs[] for post-submit inspection. artifact_refs still lists all "
                "persisted refs. Top-level image_evidence carries clean/control PNG payloads. outputs also "
                "include bounded counts, coordinate_space, world_bbox, and canonical refs without filesystem paths."
            ),
        ),
        SemanticToolSpec(
            tool_id="finalize_current_deed_to_ir_output",
            category="write",
            purpose=(
                "Compact current-head finalizer for the lineage-bound finalization session. Accepts only "
                "unresolved semantic decision maps (scope statuses, correction dispositions, dependency "
                "dispositions, and exceptional rationales). Persists partial progress, prepares the "
                "immutable final-package preview internally, and publishes it. Preferred post-remap path: "
                "submit_ir_for_mapping → finalize_current_deed_to_ir_output → complete_run. "
                "Does not accept mapping/IR/preview refs, closure arrays, or upstream correction rows."
            ),
            expected_request_shape=(
                "All maps optional. Empty request returns exact missing decision IDs. "
                "scope_statuses: map of known scope_id → handoffable|blocked. "
                "correction_dispositions: map of known correction_id → "
                "confirmed_source_repair|ir_only_exception|needs_hitl. "
                "dependency_dispositions: map of known dependency_id → include|not_applicable. "
                "rationales: map of known requirement_id → rationale text; required only for "
                "ir_only_exception and not_applicable. Previously accepted decisions need not be resubmitted. "
                "Rejects artifact refs and unknown top-level fields."
            ),
            expected_request_json_shape=(
                build_finalize_current_deed_to_ir_output_request_json_shape()
            ),
            example_request=build_finalize_current_deed_to_ir_output_example_request(),
            batching={
                "allowed": False,
                "side_effect_class": "write",
            },
            expected_result_shape=(
                "On success: finalization_status=published, final_package_preview_ref, "
                "output_revision_ref, mapping_artifact_ref, ir_artifact_ref, "
                "next_required_action=complete_run, plus publication counts/refs. "
                "Incomplete decisions: retryable missing_finalization_decisions with missing IDs. "
                "needs_hitl: finalization_requires_hitl without preparing/publishing. "
                "preview_ready retry republishes the frozen preview; published replay is idempotent."
            ),
        ),
        SemanticToolSpec(
            tool_id="prepare_deed_to_ir_final_package",
            category="write",
            purpose=(
                "Prepare one confirmable final package preview before publish. Preferred path is intent-first: "
                "use the current mapping lineage and agent-authored correction decisions; deterministic code "
                "assembles strict correction rows and derives mechanical artifact lineage. Advanced path still "
                "accepts explicit mapping refs and full package rows. Does not write final output pointers."
            ),
            expected_request_shape=(
                "Preferred (intent-first): use_current_mapping_lineage=true; "
                "scope_dispositions[] and closure_dispositions[] with agent-authored status "
                "(expanded mechanically into strict rows — statuses are never inferred); "
                "correction_decisions[] with target_entity_id, posture, resolution_used_by_ir, "
                "recommended_action, and rationale when correction posture is active; "
                "dependency_decisions[] when known dependency candidates exist "
                "(disposition include + status, or not_applicable + rationale). "
                "Optional reuse_agent_authored_finalization_state=true reuses a prior agent-authored "
                "preview when one already exists — not required for a fresh-run first preview. "
                "Do not restate mapping/IR/compile/judge/render refs, inherited/selected typed values, "
                "correction IDs, or basis refs already on the candidate. "
                "If any required decision lanes are absent, returns one retryable "
                "missing_finalization_decisions response with finalization_decision_card "
                "(all currently required lanes together) and retry_request_template "
                "(inert carry-forward of already supplied compact rows). Resubmit the "
                "template plus missing agent-authored decisions directly — do not hydrate "
                "artifacts merely to recover facts already on the card. "
                "Malformed or incomplete supplied rows may still return narrow retryable "
                "refusals after lanes are present. "
                "A blocked scope alone is not a dependency row. "
                "If current lineage is missing/stale, returns retryable current_mapping_lineage_missing or "
                "current_mapping_lineage_stale. "
                "Advanced/compatibility: mapping_artifact_ref required; expected_ir_artifact_ref optional; "
                "scope_results, external_dependencies, closure_dimensions, notes, and upstream_corrections as "
                "strict final-package rows. notes are commentary only; upstream_corrections is the machine-readable "
                "lane when final IR intentionally differs from inherited handoff/resolution/mapping operands. "
                "When final IR differs from inherited values and that difference is intentional, "
                "report it in upstream_corrections — not only in notes. "
                "scope_results and all four closure_dimensions are required on the explicit path. "
                "Invalid rows return retryable validation_errors plus rejected_payload_summary, "
                "row_contract_summary, preserve_sections, and repair_hint. "
                "When selected IR mechanically differs from inherited mapping operands/resolution "
                "snapshot and upstream_corrections is empty (explicit path), returns retryable "
                "upstream_corrections_required with correction_posture, correction_contract_card "
                "(deed_to_ir:correction_contract), retry_package_shell (copyable lineage + package rows), "
                "upstream_corrections_template (copyable strict row with rationale/upstream_value/corrected_value), "
                "candidate deltas, and repair_hint — no preview is persisted. "
                "Invalid upstream_corrections rows are validated before lineage checks; combined row + "
                "mapping_ir_lineage_mismatch failures return bounded validation_errors plus lineage_mismatch. "
                "Expected IR mismatch returns retryable mapping_ir_lineage_mismatch and persists nothing. "
                "Missing mapping ref (explicit path) returns retryable mapping_artifact_not_found with "
                "valid_mapping_refs and repair_hint; nothing is persisted."
            ),
            expected_request_json_shape=build_prepare_deed_to_ir_final_package_request_json_shape(),
            example_request=build_prepare_deed_to_ir_final_package_example_request(),
            batching={
                "allowed": False,
                "side_effect_class": "write",
            },
            expected_result_shape=(
                "On success: final_package_preview_ref, final_package_preview_revision_ref, working_preview_ref "
                "(alias of revision ref), derived selected artifact refs, review_summary (compile/judge/render "
                "counts, coordinate space, world bbox), bounded row summaries, publish_ready_candidate "
                "(mechanical only — not semantic correctness), optional correction_lane_advisory (non-blocking "
                "steering when upstream_corrections is empty but package text mentions correction language), "
                "recommended_publish_request with final_package_preview_ref, and preview_ready_summary when "
                "publish_ready_candidate=true "
                "(expected_next=publish_deed_to_ir_output; hydrate_preview_optional=true). "
                "Intent-first success also returns finalization_status=preview_ready, selected_lineage, "
                "correction_summary (typed selected_ir_value when available), and current_mapping_lineage. "
                "On upstream_corrections_required refusal: correction_posture, correction_contract_card, "
                "retry_package_shell, upstream_corrections_template, forbidden_fields, field_mapping_hints, "
                "candidate_deltas, repair_hint — hydrate deed_to_ir:correction_contract "
                "for the full card. Retry by reusing retry_package_shell refs/rows, copying "
                "upstream_corrections_template with exact field names (no summary/inherited_value/ir_value), and adding "
                "upstream_corrections only — or prefer intent-first correction_decisions. "
                "Use recommended_publish_request for publish. Use working_preview_ref only when targeted "
                "preview hydration is genuinely needed. This tool does not emit a derived_ref_id hydrate-next "
                "placeholder. On validation failure: validation_errors, rejected_payload_summary "
                "(counts/keys only), row_contract_summary, preserve_sections, repair_hint. On incomplete "
                "package: missing_sections, missing_closure_dimensions, repair_hint. No filesystem paths or "
                "image bytes."
            ),
        ),
        SemanticToolSpec(
            tool_id="publish_deed_to_ir_output",
            category="write",
            purpose=(
                "Publish one agent-authored deed-to-IR handoff package. Preferred path: pass "
                "final_package_preview_ref only — rows are frozen from the preview. Direct mapping_artifact_ref "
                "publish remains supported for backward compatibility but is advanced."
            ),
            expected_request_shape=(
                "Preferred after preview: copy recommended_publish_request from prepare_deed_to_ir_final_package, "
                "or pass final_package_preview_ref only — do not pass row fields; prepare a new preview to change "
                "scope/dependency/closure/notes. When preview_ready_summary.expected_next=publish_deed_to_ir_output, "
                "publish is the normal next artifact-writing move. Do not wait for perfect local posture if the "
                "preview is valid and remaining local state patch is only audit mirroring. "
                "Direct (advanced): mapping_artifact_ref plus agent-authored scope_results, external_dependencies, "
                "closure_dimensions, notes, optional upstream_corrections, and optional expected_ir_artifact_ref. "
                "upstream_corrections document upstream handoff/transcript/resolution deltas the final IR relied "
                "on — not ordinary external dependencies and not live transcript repair. Set "
                "resolution_used_by_ir=true when the final IR used the corrected value; do not report the same "
                "delta only in notes. "
                "Publish revalidates preview identity and mapping lineage; stale preview returns retryable "
                "final_package_preview_stale or mapping_ir_lineage_mismatch."
            ),
            expected_request_json_shape=build_publish_deed_to_ir_output_request_json_shape_with_preview(),
            example_request={
                "final_package_preview_ref": "deed_to_ir:final_package_preview:rev:0001",
            },
            batching={
                "allowed": False,
                "side_effect_class": "write",
            },
            expected_result_shape=(
                "On success: artifact_refs begin with deed_to_ir:output and revision ref, then mapping package "
                "and render refs. outputs include output_ref, output_revision_ref, selected artifact refs, "
                "bounded scope/dependency/closure counts, upstream_correction_count and compact correction summaries "
                "when present, final_output_summary "
                "(ready_for_completion_candidate=true means the final package is mechanically ready for "
                "completion review; hydrate_output_ref_optional=true means hydration is normally unnecessary). "
                "Normal next move after successful publish: inspect the returned summary and, if it matches "
                "intent, call complete_run — do not do posture-only state repair. "
                "Without filesystem paths or image bytes. Hydrating deed_to_ir:output after publish is optional "
                "unless deeper package inspection is needed. On refusal: publish_gate_category, "
                "publish_gate_reason_code, preview_still_valid when applicable, and repair_hint. "
                "Posture/audit gate refusals do not invalidate a prepared preview — retry the same "
                "final_package_preview_ref after patching posture. When expected_ir_artifact_ref mismatches "
                "the mapping source IR, publish refuses retryably with mapping_ir_lineage_mismatch."
            ),
        ),
        SemanticToolSpec(
            tool_id="hydrate_artifact_refs",
            category="read",
            purpose=(
                "Hydrate feature-graph artifact refs (ir, compile, judge, bundle, mapping), mapping "
                "sidecar refs (geometry.geojson, clean.png, control.png), deed-to-IR operand suite refs "
                "(deed_to_ir:operands, deed_to_ir:operands:run:*, deed_to_ir:operands:ws:*), deed-to-IR "
                "final package preview refs (deed_to_ir:final_package_preview, deed_to_ir:final_package_preview:rev:NNNN), "
                "deed-to-IR output refs (deed_to_ir:output, deed_to_ir:output:rev:NNNN), and targeted "
                "transcript-edit source evidence refs (image:derived:*, image:assoc:*) for read-only upstream "
                "source inspection. Hydrating deed_to_ir:operands:* is the preferred way to inspect full compact "
                "operands when mapping_operands from hydrate_deed_to_ir_input is not already sufficient. Returns "
                "bounded payloads without filesystem paths. PNG sidecars and upstream source evidence return "
                "top-level image_evidence."
            ),
            expected_request_shape=(
                "ref_ids: required non-empty array of feature_graph:*, artifact://dossiers/feature_graphs/*, "
                "deed_to_ir:operands*, deed_to_ir:final_package_preview*, deed_to_ir:output*, image:derived:*, "
                "or image:assoc:* refs. max_refs: optional cap (default 8, max 32). "
                "working_draft_ref: optional feature_graph:ir:* ref used to label compile/judge hydration rows "
                "with is_current_for_working_draft. Hydrating feature_graph:mapping:* returns mapping_review "
                "(compact lineage, counts, recommended_review_refs, recommended_publish_refs, sanity_review, "
                "draft_patch_targets, and correction_posture when available). Hydrating "
                "deed_to_ir:final_package_preview:* returns selected artifact refs, row summaries, review_summary, "
                "publish_ready_candidate, and recommended_publish_request. Hydrating image:derived:* or "
                "image:assoc:* returns bounded upstream source-evidence descriptors (read-only; no transcript-edit "
                "mutation). Prefer mapping/preview ref hydration over bulk artifact hydration; hydrate control/"
                "geometry sidecars or targeted source evidence only when visual, coordinate, or source inspection "
                "is needed."
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
                "ref_ids": [
                    "feature_graph:mapping:mapping_example_scope_ab12cd34",
                    "artifact://dossiers/feature_graphs/d-example/mappings/mapping_example/control.png",
                ],
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
                "Mapping rows include mapping_review with source IR, sidecar refs, counts, "
                "recommended_publish_refs, draft_patch_targets, and correction_posture when available. "
                "Preview rows include selected_artifacts, scope_summaries, "
                "review_summary, publish_ready_candidate, and recommended_publish_request. Compile/judge rows "
                "include artifact_ref, parent_ir_ref, parent_graph_id, parent_draft_version, and optional "
                "is_current_for_working_draft when working_draft_ref is supplied. To publish, prefer "
                "recommended_publish_request.final_package_preview_ref from a prepared preview. "
                "PNG sidecars return top-level image_evidence. outputs.errors: per-ref not_found, prefix, or scope errors."
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
