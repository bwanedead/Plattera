"""Co-located checks for transcript_edit manifest, prompts, projection, and semantics."""

from __future__ import annotations

import json

from domains.mapping.transcript_edit import (
    build_transcript_edit_closure_policy,
    build_transcript_edit_branch_blocks,
    build_transcript_edit_domain_pack,
    build_transcript_edit_manifest,
    build_transcript_edit_tool_specs,
    project_transcript_edit_view,
    transcript_edit_closure_semantics,
    transcript_edit_handoff_semantics,
)
from domains.mapping.transcript_edit.execution.subtask_profiles import (
    TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID,
    build_transcript_edit_subtask_profiles,
)
from domains.mapping.prompting.family_branch import (
    MAPPING_FAMILY_BRANCH_VERSION,
    build_mapping_family_branch_blocks,
)
from domains.mapping.transcript_edit.prompting.branch import TRANSCRIPT_EDIT_BRANCH_VERSION
from domains.mapping.transcript_edit.prompting.surfaces.procedural_guidance import (
    TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION,
)


def test_manifest_tool_ids_match_tool_specs() -> None:
    manifest = build_transcript_edit_manifest()
    specs = build_transcript_edit_tool_specs()
    assert manifest.declared_semantic_tool_ids == tuple(s.tool_id for s in specs)
    assert len(specs) == 5
    assert manifest.closure_policy.hard_enforced is True
    assert manifest.closure_policy.save_action_ids == (
        "save_workspace_artifact",
        "copy_forward_save_workspace_artifact",
    )
    assert manifest.closure_policy.publish_action_ids == ("publish_workspace_artifact",)
    assert manifest.closure_policy.minimum_resolution_items_for_save == 1
    assert manifest.closure_policy.minimum_resolution_items_for_wait == 1
    assert manifest.closure_policy.minimum_resolution_items_for_publish == 1
    assert manifest.closure_policy.minimum_resolution_items_for_complete == 1
    assert len(manifest.closure_policy.standards) == 4


def test_domain_pack_wires_same_tool_count_as_manifest() -> None:
    pack = build_transcript_edit_domain_pack()
    m = pack.manifest
    assert len(pack.build_tool_specs()) == len(m.declared_semantic_tool_ids)
    payload = pack.build_surface_payload()
    assert payload["tool_ids"] == list(m.declared_semantic_tool_ids)
    assert payload["closure_policy"]["hard_enforced"] is True
    assert "subtask_profiles" in payload
    assert len(payload["subtask_profiles"]) >= 1


def test_surface_payload_includes_visual_source_observation_subtask_profile() -> None:
    pack = build_transcript_edit_domain_pack()
    payload = pack.build_surface_payload()
    profiles = payload["subtask_profiles"]
    profile_ids = {row["profile_id"] for row in profiles}
    assert TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID in profile_ids

    profile = next(
        row
        for row in profiles
        if row["profile_id"] == TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID
    )
    assert profile["owner"] == "transcript_edit"
    assert set(profile["allowed_ref_kinds"]) == {"image", "artifact"}
    result_fields = set(profile["result_schema"]["result"].keys())
    assert result_fields == {
        "task_response",
        "source_visible_text",
        "visual_basis",
        "ambiguity",
        "limits",
    }
    preamble = profile["prompt_preamble"].lower()
    assert "source-visible" in preamble or "source visible" in preamble
    assert "peer draft" in preamble or "broader mission context" in preamble
    assert "larger transcript-edit run" in preamble
    assert "mission-critical source atom" in preamble
    assert "requested mark, value, word, or span" in preamble
    assert "do not cleanly contain the target" in preamble
    assert "nearby anchor words" in preamble
    assert "task_response" in preamble
    assert "confidence" in preamble
    assert "do not include confidence" in preamble

    joined = json.dumps(profile).lower()
    assert "confidence" not in joined.replace("do not include confidence", "")


def test_visual_source_observation_profile_registers_through_composed_registry() -> None:
    from harness.runtime.orchestration.subtasks.registry import build_composed_subtask_registry

    payload = build_transcript_edit_domain_pack().build_surface_payload()
    registry = build_composed_subtask_registry(
        surface_payloads={"transcript_edit": payload},
    )
    profile = registry.require(TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID)
    assert set(profile.allowed_ref_kinds) == {"image", "artifact"}
    assert set(profile.result_schema["result"].keys()) == {
        "task_response",
        "source_visible_text",
        "visual_basis",
        "ambiguity",
        "limits",
    }


def test_visual_source_observation_profile_registers_from_nested_runtime_surface_payload() -> None:
    from harness.runtime.orchestration.subtasks.registry import build_composed_subtask_registry

    payload = build_transcript_edit_domain_pack().build_surface_payload()
    registry = build_composed_subtask_registry(
        surface_payloads={"transcript_edit": {"transcript_edit": payload}},
    )
    assert registry.get(TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID) is not None


def test_visual_source_observation_profile_registers_from_nested_list_payload() -> None:
    from harness.runtime.orchestration.subtasks.registry import build_composed_subtask_registry

    payload = build_transcript_edit_domain_pack().build_surface_payload()
    registry = build_composed_subtask_registry(
        surface_payloads={"transcript_edit": {"payloads": [payload]}},
    )
    assert registry.get(TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID) is not None


def test_visual_source_observation_profile_normalizes_and_projects_end_to_end() -> None:
    import json

    from harness.runtime.orchestration.subtasks.contracts import DelegateSubtaskRequest
    from harness.runtime.orchestration.subtasks.projection import project_subtask_output
    from harness.runtime.orchestration.subtasks.registry import build_composed_subtask_registry
    from harness.runtime.orchestration.subtasks.runner import normalize_child_output

    payload = build_transcript_edit_domain_pack().build_surface_payload()
    registry = build_composed_subtask_registry(
        surface_payloads={"transcript_edit": payload},
    )
    profile = registry.require(TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID)
    normalized = normalize_child_output(
        json.dumps(
            {
                "status": "completed",
                "result": {
                    "task_response": "mark reads as A",
                    "source_visible_text": "A",
                    "visual_basis": ["tight stroke at center"],
                    "ambiguity": "",
                    "limits": [],
                },
            }
        ),
        subtask_id="visual_read",
        request=DelegateSubtaskRequest(
            profile=profile.profile_id,
            task="Read the visible mark in the supplied crop.",
            context_refs=("image:derived:sample:crop_001",),
        ),
        profile=profile,
    )
    projected = project_subtask_output(normalized)

    assert projected is not None
    assert projected["result"]["task_response"] == "mark reads as A"
    assert projected["result"]["source_visible_text"] == "A"
    assert projected["result"]["visual_basis"] == ["tight stroke at center"]


def test_procedural_guidance_teaches_delegate_subtask_lightly() -> None:
    guidance = next(
        b
        for b in build_transcript_edit_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "transcript_edit_procedural_guidance"
    )
    text = guidance.text.lower()
    assert "delegate_subtask" in text
    assert "transcript_edit.visual_source_observation" in text
    assert "should normally go" in text
    assert "concrete reason not to" in text
    assert "source-reading packet is curated" in text
    assert "isolated focus to one micro mission" in text
    assert "run in parallel" in text
    assert "context_refs" in text
    assert "delegation_lines" in text
    assert "atom-oriented" in text
    assert "source neighborhood or anchor" in text
    assert "not the expected value" in text
    assert "visible value/text at the target area" in text
    assert "target atom as the main payload" in text
    assert "higher-signal packet" in text
    assert "larger phrase is clipped" in text
    assert "integrate the atom and move on" in text
    assert "insufficiently anchored" in text
    assert "batch independent delegate reads" in text
    assert "must delegate" not in text
    assert "always delegate" not in text
    assert "required to delegate" not in text


def test_build_transcript_edit_subtask_profiles_has_no_confidence_fields() -> None:
    profiles = build_transcript_edit_subtask_profiles()
    assert profiles
    for profile in profiles:
        schema_blob = json.dumps(profile.get("result_schema", {})).lower()
        assert "confidence" not in schema_blob
        for field_name in profile.get("result_schema", {}).get("result", {}):
            assert "confidence" not in str(field_name).lower()


def test_manifest_classifies_prompt_source_refs() -> None:
    manifest = build_transcript_edit_manifest()
    assert manifest.family_prompt_branch_source_ref == "domains.mapping.prompting.family_branch"
    assert manifest.prompt_branch_source_ref == "domains.mapping.transcript_edit.prompting.branch"
    assert manifest.prompt_support_source_refs == (
        "domains.mapping.transcript_edit.prompting.surfaces.procedural_guidance",
    )
    assert manifest.startup_context_source_ref == "domains.mapping.transcript_edit.prompting.surfaces.startup_context"


def test_prompt_branch_block_shape_and_doctrine_markers() -> None:
    blocks = build_transcript_edit_branch_blocks()
    assert len(blocks) == 1
    branch = blocks[0]
    assert branch.block_id == "transcript_edit_domain_branch"
    assert branch.layer == "domain_branch"
    assert branch.version == TRANSCRIPT_EDIT_BRANCH_VERSION
    text = branch.text
    assert "transcript edit" in text.lower()
    assert "source evidence" in text.lower()
    assert "four layers of closure" in text.lower()
    assert "peer t0" in text.lower() or "t0" in text.lower()
    assert "do not elevate one t0 file" in text.lower()
    assert "head / final" not in text.lower()
    assert "layer 1 — delta convergence" in text.lower()
    assert "layer 2 — intrinsic source integrity" in text.lower()
    assert "layer 3 — external dependency completeness" in text.lower()
    assert "layer 4 — downstream handoffability (mapping-blocking)" in text.lower()
    assert "handoffability is scoped" in text.lower()
    assert "deed-to-ir" in text.lower()
    assert "layers 1–3 classify" in text.lower()
    assert "layer 4 classifies" in text.lower()
    assert "closure ledger requirement" in text.lower()
    assert "mission.closure_state" in text
    assert "empty item ledger" in text.lower()
    assert "saved working draft" in text.lower()
    assert "what would have to be true in reality" in text.lower()
    assert "visible mapping-significant claims" in text.lower()
    assert "mapping-family review-coverage rule" in text.lower()
    assert "deliberate layer assessment" in text.lower()
    assert "a partial answer to one layer is not a closure answer to the others" in text.lower()
    assert "earned source-reading standard" in text.lower()
    assert "false visual earning" in text.lower()
    assert "orientation evidence helps find the area" in text.lower()
    assert "do not decide from t0, transcript text, memory, or first impression" in text.lower()
    assert "mapping-critical inventory law" in text.lower()
    assert "structured source readings in the work graph" in text.lower()
    assert "determined_value" in text
    assert "materialize transcript-bearing state" in text.lower()
    assert "`unassessed`, `in_review`, or `open`" in text
    assert "treat `closed` as an earned late-run determination" in text.lower()
    assert "use `determination`" in text.lower()
    assert "material claim" in text.lower()
    assert "visual source-reading audit" not in text.lower()
    assert "practical motion density" not in text.lower()
    assert "80-90 percent" not in text.lower()
    assert "author the crop, box, highlight" not in text.lower()
    assert "baseline-inventory audit" not in text.lower()


def test_domain_pack_declares_semantic_prompt_blocks() -> None:
    pack = build_transcript_edit_domain_pack()
    blocks = pack.build_semantic_prompt_blocks()
    assert len(blocks) == 3
    ids = {b.block_id for b in blocks}
    assert ids == {
        "mapping_family_branch",
        "transcript_edit_domain_branch",
        "transcript_edit_procedural_guidance",
    }
    guidance = next(b for b in blocks if b.block_id == "transcript_edit_procedural_guidance")
    assert guidance.layer == "domain_guidance"
    assert guidance.version == TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION
    text = guidance.text.lower()
    assert "not a hard script" in text
    assert "peer draft" in text
    assert "t0" in text
    assert "mapping-critical" in text
    assert "transcript-edit work universe: t0 gives shape, source gives truth" in text
    assert "packet ref or targeted read is available" in text
    assert "heads/finals" not in text
    assert "`mission.closure_state`" in guidance.text
    assert "`resolution_state.items`" in guidance.text
    assert "use t0 drafts aggressively for initial shape, not for earned truth" in text
    assert "broad model read over the available source image" in text
    assert "not repeat the same broad-read method as if it were a new proof tier" in text
    assert "four closure layers reliable" in text
    assert "downstream operational decisions" in text
    assert "without consuming the same atom-verification budget" in text
    assert "visible document structure" in text
    assert "fast practical substrate for the opening work universe" in text
    assert "build the atomized work universe quickly" in text
    assert "every t0 reading remains candidate/open" in text
    assert "missed, merged, split, or misread a unit" in text
    assert "the early job is not to investigate each atom's truth" in text
    assert "walk the t0 landscape top-to-bottom" in text
    assert "numbers are strongly presumed atomic" in text
    assert "quiet numbers still count" in text
    assert "degrees, bearings, distances, acreage" in text
    assert "paragraph-level or parcel-level group is useful only as an organizer" in text
    assert "fast t0-shaped atomization pass" in text
    assert "obvious t0-visible atoms should not be deferred" in text
    assert "do not crop or source-investigate just to prove inventory exists" in text
    assert "motion_posture: resolution" in guidance.text
    assert "provisional vs earned distinction" in text
    assert "source-reading packet workflow" in text
    assert "instead of closing exact atoms from broad source view" in text
    assert "not normally claim-local proof for a small exact map-critical atom" in text
    assert "intended signal upgrade is deliberate localization" in text
    assert "delegate the focused crop" in text
    assert "conscious exception" in text
    assert "broad reads cannot do well" in text
    assert "targeted packet that directly demonstrates the claimed determination" in text
    assert "poor isolation economics" in text
    assert "same low-locality read pattern as t0" in text
    assert "pivotal atoms" in text
    assert "localized packets for exact atom truth" in text
    assert "point_crops" in guidance.text
    assert "point_crops_adjust" in guidance.text
    assert "point_crops_view" in guidance.text
    assert "master overlay" in text
    assert "small_plus" in guidance.text
    assert "small+" in guidance.text
    assert "bullseye-close" in text
    assert "vague dot near the paragraph is weak targeting" in text
    assert "small_plus` / `small+` wide is the normal atom/line starting shape" in text
    assert "width_norm" in guidance.text
    assert "height_norm" in guidance.text
    assert "scale_x" in guidance.text
    assert "scale_y" in guidance.text
    assert "batch qa and placement-control surface" in text
    assert "control-room artifact" in text
    assert "pin + letter" in text
    assert "did the dot land on the target atom" in text
    assert "stable pinned object" in text
    assert "top-down placement sanity" in text
    assert "master overlay is for packet sanity" in text
    assert "point placement must be precise" in text
    assert "atom must be visible at useful resolution" in text
    assert "sufficiently anchored to the intended source neighborhood" in text
    assert "do not turn an atom-verification task into a span-containment task" in text
    assert "do not accept vague targeting" in text
    assert "a dot near the paragraph is weak evidence" in text
    assert "run-performance, ui, ux, and audit value" in text
    assert "individual per-point" in text or "individual crop refs" in text
    assert "batch motion and integration" in text
    assert "hydrate_next" in guidance.text
    assert "fair hitl packets" in text
    assert "save and handoff rhythm" in text
    assert "hyper-localize it before determining" not in text
    assert "crop and/or zoom it" not in text
    assert "critical exact readings:" not in text
    assert "source-reading hitl evidence packets" not in text
    assert "image evidence: record what you see" not in text
    assert "`unassessed`, `in_review`, or `open`" in guidance.text
    assert "verified visible progress" in text
    assert "use `determination`" in text
    assert "transcript-edit run duration pressure" in text
    assert "run_context.iteration" in guidance.text
    assert "critical_budget" in text
    assert "not an instruction" in text
    assert "not a command to close" in text
    assert "primary_evidence_ref" in text
    assert "annotated_evidence_ref" in text
    assert "question_regions" in text
    assert "unable to determine" in text
    assert "closure ledger requirement" not in text
    assert "earned source-reading standard" not in text


def test_domain_pack_builds_runtime_prompt_blocks_with_startup_context() -> None:
    from domains.mapping.transcript_edit.payloads import TranscriptEditScope, TranscriptEditStartupInventory

    pack = build_transcript_edit_domain_pack()
    blocks = pack.build_runtime_prompt_blocks(
        startup_inventory=TranscriptEditStartupInventory(
            scope=TranscriptEditScope(dossier_id="d1", transcription_id="tx1"),
        )
    )
    assert [block.block_id for block in blocks] == [
        "mapping_family_branch",
        "transcript_edit_domain_branch",
        "transcript_edit_procedural_guidance",
        "transcript_edit_startup_context",
    ]
    assert blocks[-1].layer == "domain_startup_context"


def test_mapping_family_branch_shape_and_doctrine_markers() -> None:
    blocks = build_mapping_family_branch_blocks()
    assert len(blocks) == 1
    block = blocks[0]
    assert block.block_id == "mapping_family_branch"
    assert block.layer == "family_branch"
    assert block.version == MAPPING_FAMILY_BRANCH_VERSION
    text = block.text.lower()
    assert "mapping family" in text
    assert "truthful source-grounded understanding" in text
    assert "mapping-critical posture" in text
    assert "not every unresolved issue blocks mapping" in text
    assert "visible mapping-critical claims deserve explicit review coverage" in text
    assert "peer agreement is a clue" in text
    assert "review coverage of that material as owed" in text
    assert "internal consistency across section / township / range / survey" in text


def test_projection_closure_state_preserves_provisional_status_strings() -> None:
    view = project_transcript_edit_view(
        mission_opaque_state={
            "closure_state": {
                "dimensions": [
                    {
                        "dimension_id": "layer_1_delta_convergence",
                        "title": "Layer 1",
                        "status": "in_review",
                        "determination": "provisional",
                        "summary": "Visible call review is underway.",
                    },
                    {
                        "dimension_id": "layer_2_intrinsic_source_integrity",
                        "title": "Layer 2",
                        "status": "unassessed",
                        "determination": "provisional",
                        "summary": "Intrinsic source contradictions have not been fully reviewed yet.",
                    },
                ]
            }
        },
    )
    closure = view.semantic_state.closure
    assert closure is not None
    assert closure.layer_1_delta_convergence is not None
    assert closure.layer_1_delta_convergence.status == "in_review"
    assert closure.layer_1_delta_convergence.determination == "provisional"
    assert closure.layer_2_intrinsic_source_integrity is not None
    assert closure.layer_2_intrinsic_source_integrity.status == "unassessed"
    assert closure.layer_2_intrinsic_source_integrity.determination == "provisional"


def test_projection_empty_inputs() -> None:
    view = project_transcript_edit_view()
    assert view.artifact_fingerprint is None
    assert view.semantic_state.ambiguities == ()
    assert view.semantic_state.human_feedback_notes == ()
    for k in ("dossier_id", "segment_id", "run_id", "transcription_id", "draft_id"):
        assert view.scope_ids.get(k) is None


def test_projection_mission_overrides_dossier_scope_and_lists() -> None:
    view = project_transcript_edit_view(
        dossier_artifact_slice={
            "dossier_id": "d1",
            "ambiguities": [{"issue_id": "a0", "summary": "from dossier"}],
            "evidence": {"narrative": "dossier ev"},
        },
        mission_opaque_state={
            "dossier_id": "d2",
            "segment_id": "seg-m",
            "ambiguities": [{"issue_id": "a1", "summary": "from mission"}],
            "evidence": {"narrative": "mission ev"},
        },
    )
    assert view.scope_ids["dossier_id"] == "d2"
    assert view.scope_ids["segment_id"] == "seg-m"
    assert len(view.semantic_state.ambiguities) == 1
    assert view.semantic_state.ambiguities[0].issue_id == "a1"
    assert view.semantic_state.evidence is not None
    assert view.semantic_state.evidence.narrative == "mission ev"


def test_projection_nested_scope_overrides_flat_ids() -> None:
    view = project_transcript_edit_view(
        dossier_artifact_slice={
            "dossier_id": "flat-d",
            "scope": {"dossier_id": "nested-d", "segment_id": "nested-seg"},
        },
        mission_opaque_state={},
    )
    assert view.scope_ids["dossier_id"] == "nested-d"
    assert view.scope_ids["segment_id"] == "nested-seg"


def test_projection_human_feedback_and_fingerprint() -> None:
    view = project_transcript_edit_view(
        mission_opaque_state={
            "human_feedback_notes": ["note-a", "note-b"],
            "artifact_fingerprint": "fp-1",
        },
    )
    assert view.semantic_state.human_feedback_notes == ("note-a", "note-b")
    assert view.artifact_fingerprint == "fp-1"


def test_projection_closure_state_maps_four_layers() -> None:
    view = project_transcript_edit_view(
        mission_opaque_state={
            "closure_state": {
                "overall_status": "blocked",
                "summary": "Need explicit classification before close",
                "ready_to_close": False,
                "requires_hitl": True,
                "opaque_payload": {"publish_ready": False},
                "dimensions": [
                    {
                        "dimension_id": "layer_1_delta_convergence",
                        "title": "Layer 1",
                        "status": "closed",
                        "summary": "Transcript matches visible source",
                        "evidence_refs": ["image:assoc:tx:original"],
                    },
                    {
                        "dimension_id": "layer_2_intrinsic_source_integrity",
                        "title": "Layer 2",
                        "status": "open",
                        "summary": "Range contradiction remains in source",
                        "blocking": True,
                    },
                    {
                        "dimension_id": "layer_3_external_dependency_completeness",
                        "title": "Layer 3",
                        "status": "no_further_progress",
                        "summary": "Second parcel continues off image",
                        "no_further_progress": True,
                    },
                    {
                        "dimension_id": "layer_4_mapping_blocking_relevance",
                        "title": "Layer 4",
                        "status": "requires_hitl",
                        "summary": "Need human judgment on whether cutoff blocks mapping",
                        "requires_hitl": True,
                        "blocking": True,
                    },
                ],
            }
        },
    )
    closure = view.semantic_state.closure
    assert closure is not None
    assert closure.overall_status == "blocked"
    assert closure.requires_hitl is True
    assert closure.publish_ready is False
    assert closure.complete_ready is False
    assert closure.layer_1_delta_convergence is not None
    assert closure.layer_1_delta_convergence.status == "closed"
    assert closure.layer_2_intrinsic_source_integrity is not None
    assert closure.layer_2_intrinsic_source_integrity.mapping_blocking is True
    assert closure.layer_3_external_dependency_completeness is not None
    assert closure.layer_3_external_dependency_completeness.no_further_progress is True
    assert closure.layer_4_mapping_blocking_relevance is not None
    assert closure.layer_4_mapping_blocking_relevance.requires_hitl is True


def test_closure_semantics_stable_contract() -> None:
    c = transcript_edit_closure_semantics()
    assert c.summary.strip()
    assert len(c.sufficient_when) >= 3
    assert len(c.must_remain_explicit_if_unresolved) >= 2
    assert len(c.anti_patterns) >= 2
    assert "Closure means" in c.summary


def test_transcript_edit_closure_policy_stable_contract() -> None:
    policy = build_transcript_edit_closure_policy()
    assert policy.hard_enforced is True
    assert policy.enforce_on_publish is True
    assert policy.enforce_on_complete is True
    assert policy.save_action_ids == (
        "save_workspace_artifact",
        "copy_forward_save_workspace_artifact",
    )
    assert policy.publish_action_ids == ("publish_workspace_artifact",)
    assert policy.minimum_resolution_items_for_save == 1
    assert policy.minimum_resolution_items_for_wait == 1
    assert policy.minimum_resolution_items_for_publish == 1
    assert policy.minimum_resolution_items_for_complete == 1
    assert policy.required_output_ref_for_complete == "transcript_edit:output"
    assert len(policy.required_dimension_ids) == 4
    assert len(policy.standards) == 4
    assert policy.standards[0].dimension_id == "layer_1_delta_convergence"


def test_handoff_semantics_stable_contract() -> None:
    h = transcript_edit_handoff_semantics()
    assert h.summary.strip()
    assert len(h.ready_when) >= 3
    assert len(h.artifact_expectations) >= 2
    assert len(h.should_not_hand_off_yet) >= 2
    assert "Handoff means" in h.summary
    blob = (h.summary + "\n" + "\n".join(h.ready_when)).lower()
    assert "pinned" not in blob
    assert "per-segment" not in blob


def test_prompts_avoid_first_slice_final_selection_vocabulary() -> None:
    branch = build_transcript_edit_branch_blocks()[0].text.lower()
    proc = next(
        b.text.lower()
        for b in build_transcript_edit_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "transcript_edit_procedural_guidance"
    )
    joined = branch + "\n" + proc
    assert "selected final" not in joined
    assert "segment final" not in joined


def test_prompts_remove_legacy_resource_claims() -> None:
    branch = build_transcript_edit_branch_blocks()[0].text.lower()
    proc = next(
        b.text.lower()
        for b in build_transcript_edit_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "transcript_edit_procedural_guidance"
    )
    joined = branch + "\n" + proc
    # Legacy resource claims removed — not part of real runtime surface
    assert "alignment or consensus variants" not in joined
    assert "prior human feedback" not in joined
    assert "external references or related materials" not in joined
    # Image evidence claim must be present — images ARE model-visible
    assert "model-visible" in joined


def test_projection_legacy_final_selection_maps_to_authored_only() -> None:
    view = project_transcript_edit_view(
        mission_opaque_state={
            "final_selection": {
                "narrative": "working toward authored draft",
                "selected_final_ref": "must_not_surface",
                "authored_transcript_edit_ref": "transcript_edit:working",
            },
        },
    )
    ap = view.semantic_state.authored_draft_posture
    assert ap is not None
    assert ap.working_draft_ref == "transcript_edit:working"
    assert ap.output_draft_ref is None


# ---------------------------------------------------------------------------
# Source-image doctrine: original only
# ---------------------------------------------------------------------------


def test_startup_context_lists_only_original_source_image_ref() -> None:
    """Startup context should surface only the canonical original source-image ref."""
    from domains.mapping.transcript_edit.payloads import (
        TranscriptEditStartupInventory,
        TranscriptEditScope,
    )
    from domains.mapping.transcript_edit.payloads.startup_inventory import SourceImageRefDescriptor
    from domains.mapping.transcript_edit.prompting.surfaces.startup_context import build_startup_context_block

    inventory = TranscriptEditStartupInventory(
        scope=TranscriptEditScope(dossier_id="d1", transcription_id="tx1"),
        source_images=(
            SourceImageRefDescriptor(ref_id="image:assoc:tx1:original", role="source_original"),
        ),
    )
    block = build_startup_context_block(inventory)
    text = block.text.lower()

    assert "image:assoc:tx1:original" in text
    assert ":processed" not in text


def test_tool_spec_hydrate_exposes_original_source_only() -> None:
    """hydrate_artifact_refs should describe only the canonical original source-image ref."""
    specs = build_transcript_edit_tool_specs()
    hydrate = next(s for s in specs if s.tool_id == "hydrate_artifact_refs")
    purpose_lower = hydrate.purpose.lower()
    result_lower = hydrate.expected_result_shape.lower()

    assert "original" in purpose_lower or "original" in result_lower
    assert "processed" not in purpose_lower
    assert "processed" not in result_lower


def test_tool_spec_transform_returns_next_turn_image_evidence() -> None:
    """transform_artifact should not teach an immediate hydrate turn for new crops."""
    specs = build_transcript_edit_tool_specs()
    transform = next(s for s in specs if s.tool_id == "transform_artifact")
    purpose_lower = transform.purpose.lower()
    request_lower = transform.expected_request_shape.lower()
    result_lower = transform.expected_result_shape.lower()

    assert "model-visible image evidence for the next turn" in purpose_lower
    assert "typical workflow" not in request_lower
    assert "separate hydrate_artifact_refs call is not required" in result_lower


def test_tool_spec_transform_teaches_evidence_locator_rendering() -> None:
    specs = build_transcript_edit_tool_specs()
    transform = next(s for s in specs if s.tool_id == "transform_artifact")
    text = " ".join(
        [
            transform.purpose,
            transform.expected_request_shape,
            transform.expected_result_shape,
            str(transform.expected_request_json_shape),
        ]
    ).lower()

    assert "render_evidence_locators" in text
    assert "image_region" in text
    assert "rendered_evidence_refs" in text
    assert "source_ref" in text
    assert "rendered_ref" in text
    assert "summary_only_locator_count" in text
    assert "unsupported_locator_count" in text


def test_startup_context_artifact_description_names_original_only() -> None:
    """The artifact kind table at the bottom of startup context must describe only :original."""
    from domains.mapping.transcript_edit.payloads import (
        TranscriptEditStartupInventory,
        TranscriptEditScope,
    )
    from domains.mapping.transcript_edit.prompting.surfaces.startup_context import build_startup_context_block

    # Build with empty inventory — the artifact table is always rendered
    inventory = TranscriptEditStartupInventory(
        scope=TranscriptEditScope(dossier_id="d1", transcription_id="tx1"),
    )
    block = build_startup_context_block(inventory)
    text = block.text

    assert ":original" in text
    assert ":processed" not in text


def test_startup_context_advertises_point_crop_capabilities() -> None:
    """Startup context should name point-crop sub-actions without teaching workflow doctrine."""
    from domains.mapping.transcript_edit.payloads import (
        TranscriptEditStartupInventory,
        TranscriptEditScope,
    )
    from domains.mapping.transcript_edit.prompting.surfaces.startup_context import (
        TRANSCRIPT_EDIT_STARTUP_CONTEXT_VERSION,
        build_startup_context_block,
    )

    inventory = TranscriptEditStartupInventory(
        scope=TranscriptEditScope(dossier_id="d1", transcription_id="tx1"),
    )
    block = build_startup_context_block(inventory)
    text = block.text.lower()

    assert block.version == TRANSCRIPT_EDIT_STARTUP_CONTEXT_VERSION
    assert "point_crops" in text
    assert "point_crops_adjust" in text
    assert "point_crops_view" in text
    assert "image:derived:*" in block.text
    assert "model-visible evidence" in text
    assert "master overlay" not in text
    assert "packet workflow" not in text


def test_tool_spec_transform_teaches_point_crops_as_default_path() -> None:
    specs = build_transcript_edit_tool_specs()
    transform = next(s for s in specs if s.tool_id == "transform_artifact")
    combined = " ".join(
        [
            transform.purpose,
            transform.expected_request_shape,
            transform.expected_result_shape,
        ]
    ).lower()

    for sub_action in (
        "point_crops",
        "point_crops_adjust",
        "point_crops_view",
        "reference_overlay",
    ):
        assert sub_action in combined

    assert "ergonomic default" in combined
    assert "coordinate-grid fallback" in combined or "fallback coordinate grid" in combined
    assert "typical workflow" not in combined
    assert "outputs.crop_set.points" in combined or "crop_set.points" in combined
    assert "crop_records" in combined
    assert "only the master overlay" in combined or "only that master overlay" in combined
    assert "zoom_factor" in combined
    assert "coordinate grid" in combined or "grid" in combined
    assert "projection_available" in combined or "root_point_norm" in combined
    assert "old refs are not mutated" in combined
    assert "does not mint new per-point crop refs" in combined
    assert "delegate_subtask.context_refs" in combined or "delegate_subtask" in combined


# ---------------------------------------------------------------------------
# Workstream 2: turn-local image evidence doctrine
# ---------------------------------------------------------------------------


def test_branch_teaches_turn_local_image_evidence() -> None:
    """Branch doctrine must teach turn-local image evidence without tool choreography."""
    blocks = build_transcript_edit_branch_blocks()
    text = blocks[0].text.lower()
    assert "turn-local" in text
    assert "model-visible image content" in text
    assert "record" in text
    assert "same turn" in text
    assert "transform_artifact" not in text


def test_procedural_guidance_reinforces_image_observation_recording() -> None:
    """Procedural guidance must instruct the model to record image observations before moving on."""
    from domains.mapping.transcript_edit.prompting.surfaces.procedural_guidance import (
        build_transcript_edit_procedural_guidance_blocks,
    )
    blocks = build_transcript_edit_procedural_guidance_blocks()
    text = blocks[0].text.lower()
    assert "image evidence" in text or "visual content" in text or "hydrate" in text
    # Must mention recording/updating state from the image observation
    assert "record" in text or "update" in text
    # Must warn against moving on without recording
    assert "moving on" in text or "move" in text or "without recording" in text


def test_branch_teaches_verbatim_first_output_contract() -> None:
    blocks = build_transcript_edit_branch_blocks()
    text = blocks[0].text
    lowered = text.lower()
    assert "transcript-edit output contract" in lowered
    assert "first output obligation" in lowered
    assert "verbatim transcript of the source" in lowered
    assert "downstream handoff metadata and normalized views are secondary lanes" in lowered
    assert "not replacements for this transcript" in lowered
    assert "unavailable portion" in lowered and "inline" in lowered
    assert "corrected / mapping view" in lowered
    assert "must not overwrite the verbatim" in lowered
    assert "handoffable" in lowered
    assert "output contract has been materially satisfied" in lowered
    assert "source-faithful transcript lane" in lowered
    assert "the right move is to repair the artifact" in lowered


def test_branch_teaches_no_silent_verbatim_mutation_rule() -> None:
    blocks = build_transcript_edit_branch_blocks()
    text = blocks[0].text
    lowered = text.lower()
    assert "do not silently mutate the verbatim transcript" in lowered
    assert "authorized adjudication" in lowered
    assert "corrected / mapping transcript" in lowered
    assert "associated metadata" in lowered
    assert "original source wording" in lowered


def test_branch_teaches_expected_saved_payload_shape() -> None:
    blocks = build_transcript_edit_branch_blocks()
    text = blocks[0].text
    assert "source_transcript_verbatim" in text
    assert "normalized_or_mapping_transcript" in text
    assert "issues" in text
    assert "parcel_metadata" in text
    assert "hitl_decisions" in text
    assert "evidence_refs" in text


def test_branch_teaches_full_visible_available_source_scope_and_lane_divergence_metadata() -> None:
    blocks = build_transcript_edit_branch_blocks()
    text = blocks[0].text.lower()
    assert "full visible / available" in text or "full visible/available" in text
    assert "may be identical" in text
    assert "what changed and why" in text
    assert "unavailable portion" in text


def test_procedural_guidance_teaches_saved_payload_shape() -> None:
    from domains.mapping.transcript_edit.prompting.surfaces.procedural_guidance import (
        build_transcript_edit_procedural_guidance_blocks,
    )
    blocks = build_transcript_edit_procedural_guidance_blocks()
    text = blocks[0].text
    lowered = text.lower()
    assert "save and handoff rhythm" in lowered
    assert "source_transcript_verbatim" in text
    assert "domain branch owns the detailed lane contract" in lowered
    assert "first output obligation" in lowered
    assert "review as reconciliation rather than a fresh investigation" in lowered
    assert "publish/complete instead of stretching the run" in lowered


def test_procedural_guidance_defers_payload_lane_contract_to_branch() -> None:
    from domains.mapping.transcript_edit.prompting.surfaces.procedural_guidance import (
        build_transcript_edit_procedural_guidance_blocks,
    )

    blocks = build_transcript_edit_procedural_guidance_blocks()
    text = blocks[0].text.lower()
    assert "`source_transcript_verbatim` remains the first output obligation" in text
    assert "domain branch owns the detailed lane contract" in text
    assert "expected saved payload shape" not in text


def test_save_tool_spec_mentions_source_faithful_payload_shape() -> None:
    specs = build_transcript_edit_tool_specs()
    save_spec = next(s for s in specs if s.tool_id == "save_workspace_artifact")
    text = save_spec.purpose + " " + save_spec.expected_request_shape
    lowered = text.lower()
    assert "source-faithful" in lowered
    assert "source_transcript_verbatim" in text
    assert "normalized_or_mapping_transcript" in text
    assert "issues" in text
    assert "parcel_metadata" in text
    assert "hitl_decisions" in text
    assert "evidence_refs" in text
    assert "do not silently mutate the verbatim" in lowered


def test_transcript_edit_output_contract_sections_have_no_current_deed_examples() -> None:
    branch = build_transcript_edit_branch_blocks()[0].text.lower()
    branch_start = branch.find("## transcript-edit output contract")
    branch_end = branch.find("## working draft posture")
    assert branch_start >= 0 and branch_end > branch_start
    branch_contract = branch[branch_start:branch_end]

    guidance = next(
        b.text.lower()
        for b in build_transcript_edit_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "transcript_edit_procedural_guidance"
    )
    guidance_start = guidance.find("## save and handoff rhythm")
    guidance_end = guidance.find("## what not to do")
    assert guidance_start >= 0 and guidance_end > guidance_start
    guidance_contract = guidance[guidance_start:guidance_end]

    specs = build_transcript_edit_tool_specs()
    save_spec = next(s for s in specs if s.tool_id == "save_workspace_artifact")
    combined = "\n".join(
        (
            branch_contract,
            guidance_contract,
            save_spec.purpose.lower(),
            save_spec.expected_request_shape.lower(),
        )
    )
    for banned in ("range 75", "range 74", "parcel 1", "parcel 2", "nw corner", "1638"):
        assert banned not in combined, f"Found banned current-deed example {banned!r} in transcript-edit contract text"


def test_branch_does_not_teach_procedural_source_reading_workflow() -> None:
    branch = build_transcript_edit_branch_blocks()[0].text.lower()
    for removed in (
        "## visual source-reading audit",
        "practical motion density",
        "source-evidence refinement should have a reason",
        "explicit baseline-inventory audit",
        "zoom is a source-reading move",
    ):
        assert removed not in branch, f"Procedural workflow text should not remain in branch: {removed!r}"


def test_procedural_guidance_discourages_fresh_transform_rehydrate_waste() -> None:
    """Procedural guidance should tell the model not to burn a turn re-hydrating a fresh overlay."""
    from domains.mapping.transcript_edit.prompting.surfaces.procedural_guidance import (
        build_transcript_edit_procedural_guidance_blocks,
    )

    blocks = build_transcript_edit_procedural_guidance_blocks()
    text = blocks[0].text.lower()
    assert "master overlay" in text
    assert "next-turn evidence" in text or "next turn" in text
    assert "re-hydrating a freshly returned master overlay" in text or "separate turn re-hydrating" in text
