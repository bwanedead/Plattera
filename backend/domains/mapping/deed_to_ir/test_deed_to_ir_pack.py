"""Co-located checks for deed_to_ir manifest, prompts, pack, and registry."""

from __future__ import annotations

import json
from pathlib import Path

from domains.mapping import build_mapping_domain_adapter_registry
from domains.mapping.deed_to_ir import (
    build_deed_to_ir_branch_blocks,
    build_deed_to_ir_domain_pack,
    build_deed_to_ir_manifest,
    build_deed_to_ir_tool_specs,
    deed_to_ir_closure_semantics,
    deed_to_ir_handoff_semantics,
)
from tooling.mapping.deed_to_ir import load_transcript_edit_output_handoff


_FIXTURE = Path(__file__).resolve().parent / "test_fixtures" / "transcript_edit_output_handoff.json"


def test_manifest_tool_ids_match_tool_specs() -> None:
    manifest = build_deed_to_ir_manifest()
    specs = build_deed_to_ir_tool_specs()
    assert manifest.declared_semantic_tool_ids == tuple(s.tool_id for s in specs)
    assert manifest.declared_semantic_tool_ids == (
        "hydrate_deed_to_ir_input",
        "describe_feature_graph_capabilities",
        "save_ir_artifact",
        "patch_ir_draft",
        "submit_ir_for_mapping",
        "finalize_current_deed_to_ir_output",
        "hydrate_artifact_refs",
        "list_feature_graph_artifacts",
    )
    assert len(manifest.declared_semantic_tool_ids) == 8
    assert manifest.domain_id == "deed_to_ir"
    assert manifest.family_id == "mapping"
    assert manifest.display_name == "Deed To IR"


def test_ir_tool_specs_expose_core_contract_and_capability_filters() -> None:
    specs = {spec.tool_id: spec for spec in build_deed_to_ir_tool_specs()}
    save = specs["save_ir_artifact"]
    assert "at most one" in save.expected_request_shape.lower()
    assert "source_entity_links" in save.expected_request_shape
    describe = specs["describe_feature_graph_capabilities"]
    props = describe.expected_request_json_shape["properties"]
    assert "sections" in props
    assert "operation_names" in props
    section_enum = props["sections"]["items"]["enum"]
    assert "starter_contract" in section_enum
    assert "validation_schema" in section_enum
    assert "defaults to starter_contract" in describe.expected_request_shape.lower()
    assert "starter_contract" in describe.expected_result_shape.lower()


def test_tool_specs_emphasize_operand_lane_and_finalize_flow() -> None:
    specs = {spec.tool_id: spec for spec in build_deed_to_ir_tool_specs()}
    hydrate = specs["hydrate_deed_to_ir_input"]
    hydrate_refs = specs["hydrate_artifact_refs"]
    finalize = specs["finalize_current_deed_to_ir_output"]

    assert "mapping_operands is the compact authoring operand lane" in hydrate.purpose
    assert "deferred_for_operand_lane" in hydrate.expected_result_shape.lower()
    assert "operand_suite_ref" in hydrate.expected_result_shape.lower()
    assert "deed_to_ir:operands:" in hydrate_refs.purpose.lower()
    assert "final_package_preview_ref" in finalize.expected_result_shape.lower()
    assert "next_required_action=complete_run" in finalize.expected_result_shape.lower()


def test_hydrate_tool_spec_exposes_resolution_projection_limits() -> None:
    from tooling.mapping.deed_to_ir.feature_graph_contract_projection import (
        build_compact_feature_node_request_schema,
    )
    from tooling.mapping.deed_to_ir.input_hydration import MAX_RESOLUTION_UNIT_IDS, VALID_SECTIONS

    hydrate = {spec.tool_id: spec for spec in build_deed_to_ir_tool_specs()}["hydrate_deed_to_ir_input"]
    assert "inherited_handoff_conditions" in hydrate.purpose
    assert "inherited_handoff_conditions" in VALID_SECTIONS
    assert "projection_mode=index" in hydrate.purpose
    assert "selected_rows" in hydrate.purpose
    assert "full resolution_state work graph" not in hydrate.purpose.lower()

    unit_ids = hydrate.expected_request_json_shape["properties"]["resolution_unit_ids"]
    assert unit_ids["maxItems"] == MAX_RESOLUTION_UNIT_IDS
    assert unit_ids["items"]["maxLength"] == 128
    assert unit_ids["items"]["minLength"] == 1

    result = hydrate.expected_result_shape.lower()
    assert "projection_mode=index" in result
    assert "projection_mode=selected_rows" in result
    assert "truncation" in result

    save = {spec.tool_id: spec for spec in build_deed_to_ir_tool_specs()}["save_ir_artifact"]
    node_schema = build_compact_feature_node_request_schema()
    assert save.expected_request_json_shape["properties"]["feature_graph"]["properties"]["nodes"]["items"] == node_schema
    assert "unknown" in node_schema["properties"]["kind"]["enum"]
    assert "semantic" not in save.expected_request_shape.lower()


def test_submit_and_hydrate_tool_specs_mention_mapping_review() -> None:
    specs = {spec.tool_id: spec for spec in build_deed_to_ir_tool_specs()}
    submit = specs["submit_ir_for_mapping"]
    hydrate = specs["hydrate_artifact_refs"]
    assert "mapping_review" in submit.expected_result_shape.lower()
    assert "recommended_review_refs" in submit.expected_result_shape.lower()
    assert "@this.result.artifact_refs[]" in submit.expected_result_shape
    assert "artifact_refs[]" in submit.expected_request_shape or "artifact_refs" in submit.expected_request_shape
    assert "mapping_review" in hydrate.expected_result_shape.lower()
    assert "recommended_publish_refs" in hydrate.expected_result_shape.lower()
    assert "mapping_review" in hydrate.expected_request_shape.lower()
    assert "mapping_example_scope" in json.dumps(hydrate.example_request)
    assert "recommended_publish_refs" in hydrate.expected_result_shape.lower()
    assert "finalize_current_deed_to_ir_output" in hydrate.expected_result_shape
    assert "to publish, prefer" not in hydrate.expected_result_shape.lower()
    assert "recommended_publish_request" not in hydrate.expected_result_shape
    assert "intent-first preview" not in submit.expected_result_shape.lower()
    for spec in specs.values():
        blob = " ".join(
            [
                spec.purpose,
                spec.expected_request_shape,
                spec.expected_result_shape,
                json.dumps(spec.example_request),
            ]
        )
        assert "prepare_deed_to_ir_final_package" not in blob
        assert "publish_deed_to_ir_output" not in blob


def test_prepare_and_publish_tool_schemas_expose_upstream_corrections() -> None:
    from domains.mapping.deed_to_ir.payloads.final_package_preview_tool_schema import (
        build_prepare_deed_to_ir_final_package_request_json_shape,
    )
    from domains.mapping.deed_to_ir.payloads.published_output_tool_schema import (
        build_publish_deed_to_ir_output_request_json_shape,
    )

    prepare_shape = build_prepare_deed_to_ir_final_package_request_json_shape()
    publish_shape = build_publish_deed_to_ir_output_request_json_shape()
    assert "oneOf" in prepare_shape
    explicit = next(
        branch
        for branch in prepare_shape["oneOf"]
        if "mapping_artifact_ref" in branch.get("properties", {})
    )
    intent = next(
        branch
        for branch in prepare_shape["oneOf"]
        if "use_current_mapping_lineage" in branch.get("properties", {})
    )
    prepare_items = explicit["properties"]["upstream_corrections"]["items"]
    publish_items = publish_shape["properties"]["upstream_corrections"]["items"]
    for items in (prepare_items, publish_items):
        required = set(items["required"])
        assert {"correction_id", "posture", "resolution_used_by_ir", "recommended_action", "basis_refs", "rationale"} <= required
        assert items["additionalProperties"] is False
        assert "posture" in items["properties"]
        assert "recommended_action" in items["properties"]
    assert intent["properties"]["use_current_mapping_lineage"]["const"] is True
    assert "correction_decisions" in intent["properties"]
    assert "dependency_decisions" in intent["properties"]
    assert "scope_dispositions" in intent["properties"]
    assert "closure_dispositions" in intent["properties"]
    dep_item = intent["properties"]["dependency_decisions"]["items"]
    assert set(dep_item["required"]) == {"candidate_id", "disposition"}
    assert dep_item["properties"]["disposition"]["enum"] == ["include", "not_applicable"]


def test_prepare_example_places_operand_delta_in_upstream_corrections_not_notes() -> None:
    from domains.mapping.deed_to_ir.payloads.final_package_example import (
        build_prepare_deed_to_ir_final_package_explicit_example_request,
    )

    example = build_prepare_deed_to_ir_final_package_explicit_example_request()
    correction = example["upstream_corrections"][0]
    note_text = json.dumps(example["notes"]).lower()
    correction_text = json.dumps(correction).lower()

    assert correction["resolution_used_by_ir"] is True
    assert correction["upstream_value"]
    assert correction["corrected_value"]
    assert correction["upstream_value"] != correction["corrected_value"]
    assert "upstream correction" not in note_text or "not an upstream correction" in note_text
    assert correction["upstream_value"] not in note_text
    assert correction["corrected_value"] not in note_text
    assert "mapping sanity" in correction["rationale"].lower() or "source evidence" in correction["rationale"].lower()
    assert correction_text  # keep used


def test_procedural_guidance_covers_hydration_discipline() -> None:
    guidance = next(
        b.text.lower()
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert "mapping_review" in guidance
    assert "recommended_review_refs" in guidance
    assert "current_mapping_lineage" in guidance or "lineage_lock" in guidance
    assert "patch_ir_draft" in guidance
    assert "resubmit" in guidance
    assert "operand_suite_ref" in guidance
    assert "core deed-to-ir anchor" in guidance or "core anchor" in guidance
    assert "unpin `operand_suite_ref`" not in guidance
    assert "prefer short ttl" not in guidance
    assert "do not unpin or shrink operand-suite visibility by default" in guidance
    assert "not disposable context" in guidance
    assert "@this.result.artifact_refs[]" in guidance
    assert "mapping_ir_lineage_mismatch" in guidance or "stale mapping lineage" in guidance


def test_procedural_guidance_emphasizes_draft_first_and_source_repair() -> None:
    guidance = next(
        b.text.lower()
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert "draft-first" in guidance or "draft the ir" in guidance
    assert "save a bounded supported draft" in guidance or "save a draft" in guidance
    assert "finalize_current_deed_to_ir_output" in guidance
    assert "prepare_deed_to_ir_final_package" not in guidance
    assert "publish_deed_to_ir_output" not in guidance
    assert "zero `source_entity_links`" in guidance or "zero source_entity_links" in guidance
    assert "do not reread them again just to feel safer" in guidance
    assert "known blocked" in guidance or "dependency-pending scope" in guidance
    assert "represent it as an `annotation`" in guidance or "represent it as an annotation" in guidance


def test_procedural_guidance_v23_upstream_corrections_discipline() -> None:
    block = next(
        b
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert block.version == "v34"
    text = block.text.lower()
    assert "finalize_current_deed_to_ir_output" in text
    assert "prepare_deed_to_ir_final_package" not in text
    assert "publish_deed_to_ir_output" not in text
    assert "mapping_operands" in text
    assert "image:derived" in block.text or "image:derived:*" in block.text
    assert "source_entity_links" in text
    assert "external dependencies" in text


def test_procedural_guidance_v22_upstream_corrections() -> None:
    test_procedural_guidance_v23_upstream_corrections_discipline()


def test_procedural_guidance_v24_mapping_sanity_discipline() -> None:
    block = next(
        b
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert block.version == "v34"
    text = block.text.lower()
    assert "sanity_review" in text
    assert "endpoint displacement" in text
    assert "source-sanity trigger" in text
    assert "not automatically a deed defect" in text
    assert "full canonical refs" in text
    assert "intentionally open alignments" in text


def test_procedural_guidance_v25_correction_lane_discipline() -> None:
    block = next(
        b
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert block.version == "v34"
    text = block.text.lower()
    assert "finalize_current_deed_to_ir_output" in text
    assert "prepare_deed_to_ir_final_package" not in text
    assert "publish_deed_to_ir_output" not in text
    assert "correction" in text
    assert "confirmed_source_repair" in text or "ir_only_exception" in text


def test_procedural_guidance_v26_correction_posture_gate() -> None:
    block = next(
        b
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert block.version == "v34"
    text = block.text.lower()
    assert "correction_posture" in text
    assert "finalize_current_deed_to_ir_output" in text


def test_procedural_guidance_v27_lineage_lock_discipline() -> None:
    block = next(
        b
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert block.version == "v34"
    text = block.text.lower()
    assert "lineage_lock" in text or "recommended_publish_refs" in text
    assert "finalize_current_deed_to_ir_output" in text


def test_procedural_guidance_v28_source_repair_and_finalization_discipline() -> None:
    block = next(
        b
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert block.version == "v34"
    text = block.text.lower()
    assert "finalize_current_deed_to_ir_output" in text
    assert "prepare_deed_to_ir_final_package" not in text
    assert "publish_deed_to_ir_output" not in text
    assert "correction" in text
    assert "source repair" in text or "confirmed_source_repair" in text


def test_procedural_guidance_v29_course_updates_and_no_delegate_repair() -> None:
    block = next(
        b
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert block.version == "v34"
    text = block.text.lower()
    assert "course_updates" in text
    assert "draft_patch_targets" in text
    assert "delegate_subtask" in text
    assert "mapping sanity repair" in text
    assert "reconstructing full" in text and "courses[]" in text


def test_procedural_guidance_v33_intent_first_preflight() -> None:
    block = next(
        b
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert block.version == "v34"
    text = block.text.lower()
    assert "current_mapping_lineage" in text or "canonical finalization" in text
    assert "preferred endgame" in text or "canonical finalization" in text
    assert "correction" in text and "disposition" in text
    assert "dependency dispositions" in text or "dependency_dispositions" in text
    assert "blocked scope" in text
    assert "not_applicable" in text or "include" in text
    assert "finalize_current_deed_to_ir_output" in text
    assert "active_handoff_context" in text
    assert "scoped blocked continuation" in text
    assert "durable package limitation" in text


def test_procedural_guidance_v32_intent_first_preflight() -> None:
    test_procedural_guidance_v33_intent_first_preflight()


def test_procedural_guidance_v30_intent_first_finalization() -> None:
    test_procedural_guidance_v33_intent_first_preflight()


def test_patch_ir_draft_tool_spec_documents_course_updates_without_practice_tokens() -> None:
    from tooling.mapping.deed_to_ir.correction_contract_card import (
        agent_facing_example_contains_practice_deed_tokens,
    )

    specs = {spec.tool_id: spec for spec in build_deed_to_ir_tool_specs()}
    patch = specs["patch_ir_draft"]
    assert "course_updates" in patch.expected_request_shape
    assert "course_updates" in patch.purpose.lower()
    assert "coursetraverse" in patch.purpose.lower()
    props = patch.expected_request_json_shape["properties"]
    assert "course_updates" in props
    example = patch.example_request
    assert "course_updates" in example
    assert agent_facing_example_contains_practice_deed_tokens(example) == []
    example_text = str(example).lower()
    for token in ("518", "618", "p1_call2_distance", "parcel_1"):
        assert token not in example_text


def test_startup_context_notes_no_deed_to_ir_delegate_repair_workflow() -> None:
    from domains.mapping.deed_to_ir.prompting.surfaces.startup_context import (
        DEED_TO_IR_STARTUP_CONTEXT_VERSION,
        build_startup_context_block,
    )
    from domains.mapping.deed_to_ir.payloads.startup_handoff import (
        DeedToIrScope,
        DeedToIrStartupHandoff,
        TranscriptEditSourceMetadata,
    )

    assert DEED_TO_IR_STARTUP_CONTEXT_VERSION == "v7"
    handoff = DeedToIrStartupHandoff(
        scope=DeedToIrScope(
            dossier_id="d-example",
            run_id="run-example",
            workspace_id="ws-example",
            transcription_id="tx-example",
        ),
        source=TranscriptEditSourceMetadata(
            loaded_source_label="example",
            source_revision_ref="transcript_edit:output:rev:0001",
        ),
    )
    block = build_startup_context_block(handoff)
    text = block.text.lower()
    assert "delegate_subtask" in text
    assert "course_updates" in text
    assert "ir course repair" in text


def test_startup_context_marks_operand_suite_as_core_anchor() -> None:
    from domains.mapping.deed_to_ir.prompting.surfaces.startup_context import (
        build_startup_context_block,
    )
    from domains.mapping.deed_to_ir.payloads.startup_handoff import (
        DeedToIrScope,
        DeedToIrStartupHandoff,
        TranscriptEditSourceMetadata,
    )

    handoff = DeedToIrStartupHandoff(
        scope=DeedToIrScope(
            dossier_id="d-example",
            run_id="run-example",
            workspace_id="ws-example",
            transcription_id="tx-example",
        ),
        source=TranscriptEditSourceMetadata(
            loaded_source_label="example",
            source_revision_ref="transcript_edit:output:rev:0001",
        ),
        operand_suite_ref="deed_to_ir:operands:run:run-example",
    )
    block = build_startup_context_block(handoff)
    text = block.text.lower()
    assert "operand suite (core anchor)" in text
    assert "canonical compact operand source" in text
    assert "deed_to_ir:operands:run:run-example" in block.text


def test_procedural_guidance_covers_finalize_flow() -> None:
    guidance = next(
        b.text.lower()
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert "finalize_current_deed_to_ir_output" in guidance
    assert "prepare_deed_to_ir_final_package" not in guidance
    assert "publish_deed_to_ir_output" not in guidance
    assert "material defect" in guidance
    assert "preview_ready" in guidance
    assert "complete_run" in guidance


def test_procedural_guidance_discourages_post_finalize_re_hydration() -> None:
    guidance = next(
        b.text.lower()
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert "finalize_current_deed_to_ir_output" in guidance
    assert "do not hydrate" in guidance or "just to restate" in guidance
    assert "complete_run" in guidance


def test_tool_specs_state_hydrate_refs_correction_lane() -> None:
    specs = {spec.tool_id: spec for spec in build_deed_to_ir_tool_specs()}
    hydrate = specs["hydrate_artifact_refs"].expected_request_shape.lower()
    assert "image:derived" in hydrate
    assert "image:assoc" in hydrate


def test_domain_pack_builds() -> None:
    pack = build_deed_to_ir_domain_pack()
    payload = pack.build_surface_payload()
    assert payload["tool_ids"] == [
        "hydrate_deed_to_ir_input",
        "describe_feature_graph_capabilities",
        "save_ir_artifact",
        "patch_ir_draft",
        "submit_ir_for_mapping",
        "finalize_current_deed_to_ir_output",
        "hydrate_artifact_refs",
        "list_feature_graph_artifacts",
    ]
    assert len(payload["tool_specs"]) == 8
    assert payload["closure_policy"]["hard_enforced"] is False
    assert payload["closure_policy"]["publish_action_ids"] == []
    assert payload["closure_policy"]["required_output_ref_for_complete"] == "deed_to_ir:output"
    assert payload["closure_policy"]["completion_anchor"]["enabled"] is True
    assert payload["closure_policy"]["completion_anchor"]["publish_action_ids"] == [
        "finalize_current_deed_to_ir_output"
    ]
    assert payload["closure_policy"]["completion_anchor"]["published_preview_ref_field"] == (
        "final_package_preview_ref"
    )
    assert payload["closure_policy"]["completion_anchor"]["preview_ready_publish_bypass"] is False
    assert payload["closure_policy"]["completion_anchor"]["preview_prepare_action_ids"] == []
    assert payload["closure_policy"]["required_dimension_ids"] == [
        "layer_1_deed_meaning_to_ir_fidelity",
        "layer_2_ir_geometry_integrity",
        "layer_3_external_dependency_representability_completeness",
        "layer_4_map_handoffability_scoped_completion",
    ]
    assert len(pack.build_semantic_prompt_blocks()) == 4


def test_branch_and_guidance_mission_markers() -> None:
    branch = build_deed_to_ir_branch_blocks()[0].text.lower()
    assert "deed-to-ir" in branch
    assert "transcript-edit handoff" in branch
    assert "normalized_or_mapping_transcript" in branch
    assert "source_transcript_verbatim" in branch
    assert "parcel_metadata" in branch
    assert "feature-graph ir" in branch
    assert "source-traceable geometric program" in branch
    assert "starting substrate" in branch
    assert "not a prison" in branch
    assert "source evidence -> transcript-edit resolution units -> feature-graph ir" in branch
    assert "four closure obligations" in branch
    assert "deed meaning to ir fidelity" in branch
    assert "ir and geometry integrity" in branch
    assert "external dependency and representability completeness" in branch
    assert "map handoffability and scoped completion" in branch
    assert "a map that renders is not necessarily a correct map" in branch
    assert "do not launder a bad interpretation" in branch
    assert "deterministic mapping feedback informs these layers but does not close them" in branch
    assert "agent_kernel" not in branch
    assert "draft_ir" not in branch
    assert "hydrate_deed" not in branch

    guidance = next(
        b.text.lower()
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert "inherited_handoff_conditions" in guidance
    assert "first_draft_authoring_card" in guidance
    assert "finalize_current_deed_to_ir_output" in guidance
    assert "prepare_deed_to_ir_final_package" not in guidance
    assert "publish_deed_to_ir_output" not in guidance
    assert "mechanically_mappable_candidate" in guidance
    assert "not transcript-edit atoms" in guidance
    assert "copy inherited covered units into local covered units" in guidance
    assert "starting inputs" in guidance
    assert "self-heal" in guidance
    assert "submit ir for mapping" in guidance
    assert "tool specs" in guidance
    assert "source_entity_links" in guidance
    assert "hydrate_feature_graph_artifact_refs" not in guidance
    assert "local stationing" in guidance or "plat grid" in guidance
    assert "referenceframe" in guidance.replace("_", "").replace("-", "")

    authoring = next(
        b.text.lower()
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_feature_graph_authoring_guide"
    )
    assert "deed meaning" in authoring
    assert "featuregraph node kind" in authoring
    assert "compiler operation" in authoring
    assert "operation params" in authoring
    assert "rendered geometry" in authoring
    assert "kind=curve" in authoring
    assert "op_name=coursetraverse" in authoring
    assert "params.courses" in authoring
    assert "do not use `params.calls`" in authoring
    assert "raw-only rows do not compile" in authoring
    assert "close` requires exactly one operand" in authoring
    assert "annotation` is a featurekind" in authoring
    assert "deed_call_sequence" in authoring
    assert "example_boundary_chain" in authoring
    assert "123.25" in authoring
    for practice_token in (
        "parcel1_",
        "parcel_1",
        "p1_",
        "542",
        "68.5",
        "right_of_way",
        "canal",
    ):
        assert practice_token not in authoring


def test_starter_contract_projection_includes_first_draft_authoring_card() -> None:
    from tooling.mapping.deed_to_ir.feature_graph_capabilities import describe_feature_graph_capabilities
    from tooling.mapping.deed_to_ir.feature_graph_examples import example_forbidden_tokens

    caps = describe_feature_graph_capabilities(sections=["starter_contract"])
    card = caps["starter_contract"]["first_draft_authoring_card"]
    combined = json.dumps(card).lower()
    for token in example_forbidden_tokens():
        assert token not in combined
    assert "referenceframe" in combined.replace("_", "")
    assert "coursetraverse" in combined.replace("_", "")
    assert "annotation" in combined


def test_tool_and_capability_examples_expose_generic_authoring_pattern() -> None:
    import json

    from tooling.mapping.deed_to_ir.feature_graph_capabilities import describe_feature_graph_capabilities
    from tooling.mapping.deed_to_ir.feature_graph_examples import example_forbidden_tokens

    save = {spec.tool_id: spec for spec in build_deed_to_ir_tool_specs()}["save_ir_artifact"]
    caps = describe_feature_graph_capabilities(sections=["examples"])
    combined = json.dumps(
        {
            "save_example_request": save.example_request,
            "capability_examples": caps["examples"],
        }
    ).lower()
    for token in example_forbidden_tokens():
        assert token not in combined
    assert "deed_call_sequence" not in combined
    assert "referenceframe" in combined.replace("_", "")
    assert "coursetraverse" in combined.replace("_", "")
    assert "annotation" in combined


def test_mapping_registry_resolves_deed_to_ir() -> None:
    registry = build_mapping_domain_adapter_registry()
    adapter = registry.require("deed_to_ir")
    assert adapter.domain_id == "deed_to_ir"


def test_loader_copies_handoff_fields_without_inference() -> None:
    loaded = load_transcript_edit_output_handoff(output_path=_FIXTURE)
    assert loaded["counts"]["parcels"] == 2
    assert loaded["counts"]["issues"] == 1
    assert loaded["counts"]["hitl_decisions"] == 1
    assert "normalized_or_mapping_transcript" in loaded
    assert "source_transcript_verbatim" in loaded
    parcels = loaded["parcel_metadata"]["parcels"]
    assert parcels[0]["forwardable"] is True
    assert parcels[1]["forwardable"] is False
    # Loader must not invent blockers or rewrite forwardability
    assert parcels[0]["parcel_id"] == "parcel_1"
    assert "mapping_blocking" not in loaded


def test_closure_and_handoff_semantics_stable() -> None:
    c = deed_to_ir_closure_semantics()
    h = deed_to_ir_handoff_semantics()
    assert c.summary.strip()
    assert h.summary.strip()
    assert "mapped, which are incomplete or dependency-pending" in " ".join(c.sufficient_when)
    assert "rendered image as closure by itself" in " ".join(c.anti_patterns)
    assert "agent_kernel" not in (c.summary + h.summary).lower()


def test_loader_does_not_author_semantic_fields() -> None:
    loaded = load_transcript_edit_output_handoff(output_path=_FIXTURE)
    # Mechanical copy only — no harness-authored blocker/forwardability inference keys
    assert "mapping_blocking" not in loaded
    assert "forwardable" not in loaded
    assert loaded["parcel_metadata"]["parcels"][0]["forwardable"] is True
    assert "transcript_edit_output_path" not in loaded.get("source", {})
    assert loaded["source"]["loaded_source_label"] == "transcript_edit_output"


def test_loader_output_excludes_filesystem_path_from_source() -> None:
    loaded = load_transcript_edit_output_handoff(output_path=_FIXTURE)
    dumped = str(loaded)
    assert str(_FIXTURE) not in dumped
    assert "test_fixtures" not in dumped.lower()


def test_partial_finalizer_not_treated_as_pre_dispatch_publish() -> None:
    """Outer publish_action_ids empty → finalize is not a generic publish attempt."""
    from dataclasses import asdict

    from domains.mapping.deed_to_ir.semantics.closure import build_deed_to_ir_closure_policy
    from harness.mission_state import ClosureState, new_mission_state
    from harness.runtime.memory import LoopMemoryState
    from harness.runtime.orchestration.contracts import ActionPlan
    from harness.runtime.orchestration.orchestrator_policy import closure_enforcement_failure

    policy = asdict(build_deed_to_ir_closure_policy())
    # Even if hard publish enforcement were on, empty outer publish_action_ids
    # must keep finalize off the generic pre-dispatch publish path.
    policy["hard_enforced"] = True
    policy["enforce_on_publish"] = True

    ms = new_mission_state(mission_id="m-finalizer", loop_family="orchestration_kernel")
    ms = ms.model_copy(
        update={
            "work_universe_posture": "unaudited",
            "closure_state": ClosureState(
                dimensions=[],
                ready_to_close=False,
                ready_to_publish=False,
                requires_hitl=False,
            ),
        }
    )
    mem = LoopMemoryState()
    mem.continuity.mission_state = ms
    plan = ActionPlan(
        action_type="finalize_current_deed_to_ir_output",
        action_inputs={"scope_decisions": {"scope_a": "handoffable"}},
    )
    failure = closure_enforcement_failure(
        run_ctx={"domain_closure_policy": policy},
        loop_memory=mem,
        action_plan=plan,
    )
    assert failure is None
