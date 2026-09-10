"""Offline checks for MAPDEP-BR-029 working-transcript rhythm teaching.

Correction, unchanged-text verification, and provisional persistence after apply
are already proven by:
- tooling.mapping.transcript_edit.test_apply_transcript_edits_engine
  (test_one_exact_edit_preserves_unrelated_payload,
   test_unchanged_text_verification_persists_provenance)
- tooling.mapping.transcript_edit.test_transcript_edit_decision_v2
  (test_stable_id_supersession_lifecycle)
This module does not duplicate those persistence suites.
"""

from __future__ import annotations

from domains.mapping.transcript_edit.execution.dossier_tool_specs import (
    build_dossier_transcript_edit_tool_specs,
)
from domains.mapping.transcript_edit.execution.tool_specs import (
    build_transcript_edit_tool_specs,
)
from domains.mapping.transcript_edit.prompting.branch import build_transcript_edit_branch_blocks
from domains.mapping.transcript_edit.prompting.surfaces.dossier_guidance import (
    build_transcript_edit_dossier_guidance_block,
)
from domains.mapping.transcript_edit.prompting.surfaces.procedural_guidance import (
    build_transcript_edit_procedural_guidance_blocks,
)
from tooling.mapping.transcript_edit.apply_transcript_edits_contract import (
    validate_apply_transcript_edits_request,
)

_PREMATURE_SUCCESS_CLAIMS = (
    "the edit succeeded",
    "after applying, the transcript now",
    "the apply succeeded",
    "the working transcript now contains",
)

_WORKING_RHYTHM_MARKERS = (
    "create a transcript-bearing working revision",
    "saving it does not verify those readings",
    "do not wait until the draft looks finished, verified, or publishable",
    "the working transcript is the product taking shape",
    "do not accumulate a second transcript in resolution summaries",
    "apply_transcript_edits",
    "a graph update is not a persisted transcript edit",
    "after a successful apply result",
    "do not reconstruct the entire transcript from accumulated turn history",
    "not a requirement that all decisions be earned before publication",
)


def _apply_spec(specs):
    return next(spec for spec in specs if spec.tool_id == "apply_transcript_edits")


def _teaching_blobs() -> tuple[str, ...]:
    guidance = build_transcript_edit_procedural_guidance_blocks()[0].text
    branch = build_transcript_edit_branch_blocks()[0].text
    leaf_apply = _apply_spec(build_transcript_edit_tool_specs())
    dossier_apply = _apply_spec(build_dossier_transcript_edit_tool_specs())
    return (
        guidance,
        branch,
        leaf_apply.purpose,
        leaf_apply.expected_result_shape,
        dossier_apply.purpose,
        dossier_apply.expected_result_shape,
    )


def test_leaf_and_dossier_surfaces_expose_working_rhythm() -> None:
    guidance = build_transcript_edit_procedural_guidance_blocks()[0].text.lower()
    for marker in _WORKING_RHYTHM_MARKERS:
        assert marker in guidance

    driver = build_transcript_edit_dossier_guidance_block().text.lower()
    assert "segment being worked" in driver
    assert "do not require every segment to be initialized" in driver

    branch = build_transcript_edit_branch_blocks()[0].text.lower()
    assert "the working transcript is the artifact taking shape during investigation" in branch
    assert "publication carries selected working revisions" in branch
    assert "transcript-edit output consumed by deed-to-ir" in branch
    assert "knowing a reading is not the same as persisting it" in branch
    assert "must not imply the working transcript already contains" in branch
    assert 'do not invent an "all decisions earned" publication bar' in branch


def test_apply_examples_validate_against_v2_edit_contract() -> None:
    leaf = _apply_spec(build_transcript_edit_tool_specs())
    dossier = _apply_spec(build_dossier_transcript_edit_tool_specs())

    leaf_validated = validate_apply_transcript_edits_request(leaf.example_request)
    dossier_validated = validate_apply_transcript_edits_request(dossier.example_request)

    assert leaf_validated.decisions[0].decision_id == "example-provisional-token"
    assert leaf_validated.decisions[0].determination == "provisional"
    assert leaf_validated.decisions[0].uncertainty_reasons == ("observer_disagreement",)
    assert leaf_validated.decisions[0].candidate_values == ("candidate_a", "candidate_b")
    assert leaf_validated.decisions[0].edits[0].expected_text == "[uncertain token]"
    assert leaf_validated.decisions[0].edits[0].replacement_text == "[provisional reading]"
    assert leaf_validated.decisions[1].decision_id == "example-verified-token"
    assert leaf_validated.decisions[1].determination == "earned"
    assert leaf_validated.decisions[1].uncertainty_reasons == ()
    assert (
        leaf_validated.decisions[1].edits[0].expected_text
        == leaf_validated.decisions[1].edits[0].replacement_text
        == "[already correct token]"
    )
    assert leaf_validated.decisions[0].evidence_refs != leaf_validated.decisions[1].evidence_refs

    assert dossier.example_request["base_revision_ref"].startswith("dossier_segment:")
    assert "transcript_edit:working:rev:" in dossier.example_request["base_revision_ref"]
    assert [decision.decision_id for decision in dossier_validated.decisions] == [
        decision.decision_id for decision in leaf_validated.decisions
    ]
    assert [decision.determination for decision in dossier_validated.decisions] == [
        decision.determination for decision in leaf_validated.decisions
    ]
    assert [decision.edits for decision in dossier_validated.decisions] == [
        decision.edits for decision in leaf_validated.decisions
    ]
    assert all(
        ref.startswith("dossier_segment:") for ref in dossier_validated.decisions[0].evidence_refs
    )
    assert all(
        ref.startswith("dossier_segment:") for ref in dossier_validated.decisions[1].evidence_refs
    )
    assert dossier_validated.decisions[0].evidence_refs != leaf_validated.decisions[0].evidence_refs


def test_dossier_examples_ban_bare_opaque_refs() -> None:
    for spec in build_dossier_transcript_edit_tool_specs():
        for value in _walk_strings(spec.example_request):
            assert not _is_bare_opaque_ref(value), (
                f"{spec.tool_id} example contains bare opaque ref {value!r}"
            )


def test_changed_surfaces_have_no_evaluation_deed_contamination() -> None:
    blobs = list(_teaching_blobs())
    for spec in (
        *build_transcript_edit_tool_specs(),
        *build_dossier_transcript_edit_tool_specs(),
    ):
        blobs.extend(_walk_strings(spec.example_request))
        blobs.append(spec.purpose)
        blobs.append(spec.expected_request_shape)
        blobs.append(spec.expected_result_shape)
    combined = "\n".join(blobs).lower()
    for banned in (
        "range 7 west",
        "range 77 west",
        "range 75",
        "range 74",
        "nw corner",
        "n 4°",
        "n 4 deg",
        "1638",
        "seg1-location",
        "marked corner",
        '"7", "77"',
        "'7', '77'",
    ):
        assert banned not in combined, f"found evaluation-deed contamination {banned!r}"


def test_examples_do_not_claim_apply_success_before_result() -> None:
    for blob in _teaching_blobs():
        lowered = blob.lower()
        for claim in _PREMATURE_SUCCESS_CLAIMS:
            assert claim not in lowered
    result_shape = _apply_spec(build_transcript_edit_tool_specs()).expected_result_shape.lower()
    assert "observe this result before treating the edit as persisted" in result_shape


def _walk_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        found: list[str] = []
        for item in value.values():
            found.extend(_walk_strings(item))
        return found
    if isinstance(value, (list, tuple)):
        found: list[str] = []
        for item in value:
            found.extend(_walk_strings(item))
        return found
    return []


def _is_bare_opaque_ref(value: str) -> bool:
    return value.startswith(("image:", "t0:", "transcript_edit:"))

