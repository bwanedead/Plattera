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
        "publish_deed_to_ir_output",
        "hydrate_artifact_refs",
        "list_feature_graph_artifacts",
    )
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


def test_publish_tool_spec_exposes_row_contracts_from_models() -> None:
    from domains.mapping.deed_to_ir.payloads.published_output import (
        ALLOWED_CLOSURE_DIMENSION_IDS,
        MAX_CLOSURE_DIMENSIONS,
        MAX_EXTERNAL_DEPENDENCIES,
        MAX_REF_LENGTH,
        MAX_ROW_REFS,
        MAX_SCOPE_RESULTS,
        MAX_SUMMARY_LENGTH,
    )

    publish = {spec.tool_id: spec for spec in build_deed_to_ir_tool_specs()}["publish_deed_to_ir_output"]
    shape = publish.expected_request_json_shape
    assert shape["additionalProperties"] is False
    assert shape["required"] == ["mapping_artifact_ref"]
    assert "expected_ir_artifact_ref" in shape["properties"]

    scope = shape["properties"]["scope_results"]
    assert scope["maxItems"] == MAX_SCOPE_RESULTS
    scope_item = scope["items"]
    assert scope_item["additionalProperties"] is False
    assert scope_item["required"] == ["scope_id", "status"]
    scope_props = scope_item["properties"]
    assert set(scope_props) == {
        "scope_id",
        "status",
        "summary",
        "basis_refs",
        "blocker_refs",
        "dependency_refs",
    }
    assert scope_props["scope_id"]["maxLength"] == 128
    assert scope_props["basis_refs"]["maxItems"] == MAX_ROW_REFS
    assert scope_props["basis_refs"]["items"]["maxLength"] == MAX_REF_LENGTH
    assert scope_props["blocker_refs"]["maxItems"] == MAX_ROW_REFS
    assert scope_props["blocker_refs"]["items"]["maxLength"] == MAX_REF_LENGTH

    deps = shape["properties"]["external_dependencies"]
    assert deps["maxItems"] == MAX_EXTERNAL_DEPENDENCIES
    dep_item = deps["items"]
    assert dep_item["additionalProperties"] is False
    assert dep_item["required"] == ["dependency_id", "affected_scope", "description", "status"]
    assert set(dep_item["properties"]) == {
        "dependency_id",
        "affected_scope",
        "description",
        "status",
        "available_refs",
    }
    assert dep_item["properties"]["available_refs"]["items"]["maxLength"] == MAX_REF_LENGTH

    closure = shape["properties"]["closure_dimensions"]
    assert closure["maxItems"] == MAX_CLOSURE_DIMENSIONS
    closure_item = closure["items"]
    assert closure_item["additionalProperties"] is False
    assert closure_item["required"] == ["dimension_id", "status"]
    assert closure_item["properties"]["dimension_id"]["enum"] == sorted(ALLOWED_CLOSURE_DIMENSION_IDS)
    assert closure_item["properties"]["basis_refs"]["items"]["minLength"] == 1

    notes = shape["properties"]["notes"]
    note_item = notes["items"]
    assert note_item["additionalProperties"] is False
    assert note_item["required"] == ["note_id", "summary"]
    assert set(note_item["properties"]) == {"note_id", "summary", "basis_refs"}
    assert note_item["properties"]["summary"]["maxLength"] == MAX_SUMMARY_LENGTH

    example = publish.example_request
    assert example["expected_ir_artifact_ref"].startswith("feature_graph:ir:")
    assert example["external_dependencies"][0]["description"]
    assert "summary" not in example["external_dependencies"][0]
    assert isinstance(example["notes"][0], dict)
    assert "note_id" in example["notes"][0]
    assert example["scope_results"][0]["basis_refs"]
    assert example["scope_results"][1]["dependency_refs"] == ["missing_continuation_source"]
    dumped = json.dumps(example).lower()
    for forbidden in ("parcel_1", "parcel_2", "range 74", "range 75", "canal"):
        assert forbidden not in dumped


def test_submit_and_hydrate_tool_specs_mention_mapping_review() -> None:
    specs = {spec.tool_id: spec for spec in build_deed_to_ir_tool_specs()}
    submit = specs["submit_ir_for_mapping"]
    publish = specs["publish_deed_to_ir_output"]
    hydrate = specs["hydrate_artifact_refs"]
    assert "mapping_review" in submit.expected_result_shape.lower()
    assert "recommended_review_refs" in submit.expected_result_shape.lower()
    assert "@this.result.artifact_refs[]" in submit.expected_result_shape
    assert "artifact_refs[]" in submit.expected_request_shape or "artifact_refs" in submit.expected_request_shape
    assert "mapping_review" in hydrate.expected_result_shape.lower()
    assert "recommended_publish_refs" in hydrate.expected_result_shape.lower()
    assert "mapping_review" in hydrate.expected_request_shape.lower()
    assert "mapping_example_scope" in json.dumps(hydrate.example_request)
    assert "recommended_publish_refs" in publish.expected_request_shape.lower()
    assert "mapping_ir_lineage_mismatch" in publish.expected_result_shape.lower()


def test_procedural_guidance_covers_hydration_discipline() -> None:
    guidance = next(
        b.text.lower()
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert "mapping_review" in guidance
    assert "recommended_review_refs" in guidance
    assert "recommended_publish_refs" in guidance
    assert "expected_ir_artifact_ref" in guidance
    assert "patch_ir_draft" in guidance
    assert "resubmit" in guidance
    assert "operand_suite_ref" in guidance
    assert "unpin" in guidance
    assert "@this.result.artifact_refs[]" in guidance
    assert "mapping_ir_lineage_mismatch" in guidance or "stale mapping lineage" in guidance


def test_domain_pack_builds() -> None:
    pack = build_deed_to_ir_domain_pack()
    payload = pack.build_surface_payload()
    assert payload["tool_ids"] == [
        "hydrate_deed_to_ir_input",
        "describe_feature_graph_capabilities",
        "save_ir_artifact",
        "patch_ir_draft",
        "submit_ir_for_mapping",
        "publish_deed_to_ir_output",
        "hydrate_artifact_refs",
        "list_feature_graph_artifacts",
    ]
    assert len(payload["tool_specs"]) == 8
    assert payload["closure_policy"]["hard_enforced"] is False
    assert payload["closure_policy"]["publish_action_ids"] == ["publish_deed_to_ir_output"]
    assert payload["closure_policy"]["required_output_ref_for_complete"] == "deed_to_ir:output"
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
    assert "downstream deed-to-ir responsibilities" in guidance
    assert "draft checkpoint" in guidance
    assert "save_ir_artifact" in guidance or "save a **draft checkpoint**" in guidance
    assert "submit_ir_for_mapping" in guidance
    assert "publish_deed_to_ir_output" in guidance
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
