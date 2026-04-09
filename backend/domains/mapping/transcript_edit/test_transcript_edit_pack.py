"""Co-located checks for transcript_edit manifest, prompts, projection, and semantics."""

from __future__ import annotations

from domains.mapping.transcript_edit import (
    build_transcript_edit_branch_blocks,
    build_transcript_edit_domain_pack,
    build_transcript_edit_manifest,
    build_transcript_edit_tool_specs,
    project_transcript_edit_view,
    transcript_edit_closure_semantics,
    transcript_edit_handoff_semantics,
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
    assert len(specs) == 4


def test_domain_pack_wires_same_tool_count_as_manifest() -> None:
    pack = build_transcript_edit_domain_pack()
    m = pack.manifest
    assert len(pack.build_tool_specs()) == len(m.declared_semantic_tool_ids)


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
    assert "layer 4 — mapping-blocking relevance" in text.lower()
    assert "layers 1–3 classify" in text.lower()
    assert "layer 4 classifies" in text.lower()
    assert "closure ledger requirement" in text.lower()
    assert "mission.closure_state" in text


def test_domain_pack_includes_procedural_guidance_block() -> None:
    pack = build_transcript_edit_domain_pack()
    blocks = pack.build_prompt_branch_blocks()
    assert len(blocks) == 2
    ids = {b.block_id for b in blocks}
    assert ids == {
        "transcript_edit_domain_branch",
        "transcript_edit_procedural_guidance",
    }
    guidance = next(b for b in blocks if b.block_id == "transcript_edit_procedural_guidance")
    assert guidance.layer == "domain_guidance"
    assert guidance.version == TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION
    text = guidance.text.lower()
    assert "not a hard script" in text
    assert "targeted move" in text
    assert "peer draft" in text
    assert "t0" in text
    assert "mapping-critical" in text
    assert "recommended transcript-edit movement" in text
    assert "same broad set of refs" in text
    assert "heads/finals" not in text
    assert "peer t0" in text
    assert "closure ledger" in text
    assert "mission.closure_state" in text


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
    proc = build_transcript_edit_domain_pack().build_prompt_branch_blocks()[1].text.lower()
    joined = branch + "\n" + proc
    assert "selected final" not in joined
    assert "segment final" not in joined


def test_prompts_remove_legacy_resource_claims() -> None:
    branch = build_transcript_edit_branch_blocks()[0].text.lower()
    proc = build_transcript_edit_domain_pack().build_prompt_branch_blocks()[1].text.lower()
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
