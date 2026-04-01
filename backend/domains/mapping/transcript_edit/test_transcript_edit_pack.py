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
from domains.mapping.transcript_edit.prompting.branch import TRANSCRIPT_EDIT_BRANCH_VERSION


def test_manifest_tool_ids_match_tool_specs() -> None:
    manifest = build_transcript_edit_manifest()
    specs = build_transcript_edit_tool_specs()
    assert manifest.declared_semantic_tool_ids == tuple(s.tool_id for s in specs)
    assert len(specs) == 15


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
    assert "semantic" in text.lower() and "facet" in text.lower()
    assert "harness orchestrates" in text.lower()
    assert "mapping-family mission" in text.lower()
    assert "t0 transcript drafts" in text.lower()
    assert "deed-to-ir" in text.lower()
    assert "layer 1 — delta convergence" in text.lower()
    assert "layer 2 — intrinsic source integrity" in text.lower()
    assert "layer 3 — external dependency completeness" in text.lower()
    assert "layer 4 — mapping-blocking relevance" in text.lower()
    assert "layers 1–3 classify" in text.lower()
    assert "layer 4 classifies" in text.lower()


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
    text = guidance.text.lower()
    assert "not a hard script" in text
    assert "mission state" in text
    assert "t0" in text
    assert "mapping-critical" in text
    assert "recommended movement pattern" in text
    assert "baseline closure accounting" in text


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
