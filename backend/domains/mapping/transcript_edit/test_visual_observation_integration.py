"""Offline teaching checks for MAPDEP-BR-030 visual-observation integration.

Schema projection, packet-outcome cases, and provisional persistence are already
proven by:
- domains.mapping.transcript_edit.test_transcript_edit_pack
  (visual_source_observation profile/schema/cases)
- domains.mapping.transcript_edit.test_delegate_subtask_phase6_mechanical
- tooling.mapping.transcript_edit.test_transcript_edit_decision_v2
- tooling.mapping.transcript_edit.test_apply_transcript_edits_engine
This module does not duplicate those contract or persistence suites.
It does not claim improved reading accuracy.
"""

from __future__ import annotations

from domains.mapping.transcript_edit.execution.delegate_observation_reminder import (
    TRANSCRIPT_EDIT_DELEGATE_OBSERVATION_REMINDER,
)
from domains.mapping.transcript_edit.prompting.branch import build_transcript_edit_branch_blocks
from domains.mapping.transcript_edit.prompting.surfaces.procedural_guidance import (
    build_transcript_edit_procedural_guidance_blocks,
)


def _guidance() -> str:
    return build_transcript_edit_procedural_guidance_blocks()[0].text


def _guidance_lower() -> str:
    return _guidance().lower()


def test_parent_interprets_observation_as_a_whole() -> None:
    text = _guidance_lower()
    for marker in (
        "a delegate result is an observation, not a self-authenticating determination",
        "status: completed",
        "does not earn a value",
        "read the observation as a whole",
        "target_presence",
        "packet_assessment",
        "target_anchor_text",
        "task_response",
        "source_visible_text",
        "must tell a coherent story",
        "preserve that qualification",
        "does not independently earn a reading",
        "that is still only an observation",
        "earn the reading only when the source evidence supports it and material uncertainty has been resolved",
        "if credible observations still conflict, preserve that conflict",
        "keep the selected reading provisional",
        "later discriminating evidence may justify revising or earning the decision",
        "record why the earlier alternative no longer holds",
        "`absent` means not visible in this packet, never absent from the deed",
        "packet outcome, not proof that the source lacks the target",
    ):
        assert marker in text, f"missing observation-interpretation teaching: {marker!r}"


def test_parent_sanity_stays_inside_current_work_group() -> None:
    text = _guidance_lower()
    for marker in (
        "ordinary integration of the current work group",
        "incompatible readings of the same identifiable mark",
        "does not answer the requested target",
        "claimed anchor does not match the packet",
        "not a separate sanity turn per atom",
        "not a mandatory reread of every crop",
        "not a document-wide comparison sweep after every delegate wave",
        "master overlay remains the normal surface for assessing placement",
        "inspect a particular crop when a concrete unresolved question warrants it",
        "against the master overlay rather than paying to reread every crop",
        "when integrating short visual readings, assess the mark itself",
        "that assessment happens during ordinary integration of the current work group",
        "do not introduce a second read merely because a group is about to close",
    ):
        assert marker in text, f"missing work-group sanity teaching: {marker!r}"


def test_disagreement_is_preserved_without_forced_consensus() -> None:
    text = _guidance_lower()
    for marker in (
        "preserve the disagreement",
        "please do not silently let the latest answer replace the earlier one",
        "neither recency, majority agreement, candidate familiarity, nor an observer's confidence establishes source truth",
        "matching observations to the same detail is your judgment",
        "do not invent a mechanical comparison",
        "choose the best-supported current reading",
        "retain it as provisional while the material uncertainty remains",
        "a further check is useful when it can distinguish the alternatives",
        "repeating the same observation merely to obtain agreement is not progress",
        "do not require immediate adjudication of every discrepancy",
        "if further investigation is unlikely to improve the answer economically",
        "preserve the uncertainty and continue other work",
        "delegate outputs do not become true by vote",
    ):
        assert marker in text, f"missing disagreement teaching: {marker!r}"


def test_delegate_worklist_reminds_in_place_without_demanding_an_extra_check() -> None:
    reminder = TRANSCRIPT_EDIT_DELEGATE_OBSERVATION_REMINDER.lower()
    assert "during that integration" in reminder
    assert "materially overlapping visible text already in this worklist" in reminder
    assert "preserve a material mismatch as disagreement" in reminder
    assert "rather than earning either reading" in reminder
    assert "rerun until" not in reminder
    assert "consensus" not in reminder


def test_qualified_selections_use_existing_provisional_apply_contract() -> None:
    text = _guidance_lower()
    for marker in (
        "determination: provisional",
        "uncertainty_reasons",
        "candidate_values",
        "verification_basis",
        "evidence refs that support or contest the selection",
        "a correction to the text does not itself resolve the uncertainty",
        "keep the same `decision_id`",
        "apply_transcript_edits",
        "do not leave the best-current text only in the graph",
        "do not add another contested-value ledger",
        "continuing work is not permission to fabricate text",
        "preserve an honest unresolved reading or source limitation",
    ):
        assert marker in text, f"missing provisional-apply teaching: {marker!r}"


def test_downstream_revisitation_does_not_promise_rescue() -> None:
    text = _guidance_lower()
    for marker in (
        "available for later review and deed-to-ir investigation",
        "geometric convenience does not establish what the source says",
        "do not ignore a material issue because deed-to-ir will supposedly fix it",
        "whether uncertainty permits handoff remains your existing scoped closure judgment",
        "relies on the transcript and its recorded determinations to construct geometry",
        "a wrong earned reading can propagate into the map",
        "accurate text and honest uncertainty here directly affect downstream reliability",
    ):
        assert marker in text, f"missing downstream-revisitation teaching: {marker!r}"


def test_delegate_is_bounded_by_supplied_evidence_packet_not_crop_only() -> None:
    text = _guidance()
    assert "A delegate can only verify what its supplied evidence packet shows." in text
    assert "A delegate can only verify what its crop shows." not in text
    assert "The delegate's entire world is the packet you curated" in text


def test_contradictory_immediate_corroboration_gates_are_absent() -> None:
    text = _guidance_lower()
    for banned in (
        "grounds for corroboration",
        "no material contradiction remains",
        "must corroborate",
        "immediate corroboration",
        "vote the delegates",
        "automatic contradiction flag",
        "does not re-litigate",
        "nothing credible already contests",
        "closure earns itself",
        "delegate reads → earned values",
        "one bounded pass",
    ):
        assert banned not in text, f"found contradictory integration gate: {banned!r}"


def test_branch_authority_is_unchanged_and_not_echoed_as_workflow() -> None:
    branch = build_transcript_edit_branch_blocks()[0].text.lower()
    guidance = _guidance_lower()
    assert "the source image is authority for what the source says" in branch
    assert "do not invent an \"all decisions earned\" publication bar" in branch
    assert "read the observation as a whole" not in branch
    assert "grounds for corroboration" not in guidance
    assert "visual_source_observation" not in branch
