"""Engine-facing edit behavior coverage for apply_transcript_edits (MAPDEP-BR-024)."""

from __future__ import annotations

import json

import pytest

from domains.mapping.transcript_edit.payloads.transcript_edit_decisions import (
    TRANSCRIPT_EDIT_DECISIONS_FIELD,
)
from tooling.mapping.transcript_edit._apply_transcript_edits_test_helpers import (
    decision,
    root,
    save_base,
    seed_run,
)
from tooling.mapping.transcript_edit.apply_transcript_edits import apply_transcript_edits
from tooling.mapping.transcript_edit.paths import (
    transcript_edit_latest_pointer_path,
    transcript_edit_revision_path,
)


def test_one_exact_edit_preserves_unrelated_payload(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws1"
    seed_run(dossiers, d, tx)
    base = save_base(d=d, tx=tx, ws=ws, source="Begin Range 7 west End")
    assert base["executed"] is True
    out = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [decision(candidate_values=["7", "77"])],
        },
    )
    assert out["executed"] is True
    assert out["outputs"]["working_draft_ref"] == "transcript_edit:working:rev:0002"
    rev = json.loads(transcript_edit_revision_path(d, tx, ws, "0002").read_text(encoding="utf-8"))
    assert rev["payload"]["source_transcript_verbatim"] == "Begin Range 77 west End"
    assert rev["payload"]["issues"] == [{"id": "keep-me"}]
    assert rev["payload"]["parcel_metadata"] == {"parcel_count": 1}
    decisions = rev["payload"][TRANSCRIPT_EDIT_DECISIONS_FIELD]["decisions"]
    assert decisions[0]["decision_id"] == "d1"
    assert decisions[0]["candidate_values"] == ["7", "77"]


def test_multiple_non_overlapping_edits(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws2"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="AAA BBB CCC")
    out = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                decision(
                    decision_id="a",
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "AAA",
                            "replacement_text": "XXX",
                        }
                    ],
                ),
                decision(
                    decision_id="c",
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "CCC",
                            "replacement_text": "ZZZ",
                        }
                    ],
                ),
            ],
        },
    )
    assert out["executed"] is True
    rev = json.loads(transcript_edit_revision_path(d, tx, ws, "0002").read_text(encoding="utf-8"))
    assert rev["payload"]["source_transcript_verbatim"] == "XXX BBB ZZZ"


def test_context_disambiguates_repeated_text(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws3"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="foo Range 7 west bar Range 7 west baz")
    out = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                decision(
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "Range 7 west",
                            "replacement_text": "Range 77 west",
                            "context_before": "bar ",
                            "context_after": " baz",
                        }
                    ]
                )
            ],
        },
    )
    assert out["executed"] is True
    rev = json.loads(transcript_edit_revision_path(d, tx, ws, "0002").read_text(encoding="utf-8"))
    assert rev["payload"]["source_transcript_verbatim"] == (
        "foo Range 7 west bar Range 77 west baz"
    )


@pytest.mark.parametrize(
    "edits,reason",
    [
        (
            [
                {
                    "lane": "source_transcript_verbatim",
                    "expected_text": "missing",
                    "replacement_text": "x",
                }
            ],
            "edit_target_not_found",
        ),
        (
            [
                {
                    "lane": "source_transcript_verbatim",
                    "expected_text": "Range 7 west",
                    "replacement_text": "x",
                }
            ],
            "edit_target_ambiguous",
        ),
        (
            [
                {
                    "lane": "source_transcript_verbatim",
                    "expected_text": "Range 7",
                    "replacement_text": "R",
                },
                {
                    "lane": "source_transcript_verbatim",
                    "expected_text": "7 west",
                    "replacement_text": "W",
                },
            ],
            "overlapping_edit_ranges",
        ),
    ],
)
def test_missing_ambiguous_overlapping_refuse_without_mutation(
    tmp_path, monkeypatch, edits, reason
):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", f"ws-{reason}"
    seed_run(dossiers, d, tx)
    source = (
        "Range 7 west and Range 7 west"
        if reason == "edit_target_ambiguous"
        else "Begin Range 7 west End"
    )
    save_base(d=d, tx=tx, ws=ws, source=source)
    before = transcript_edit_latest_pointer_path(d, tx, ws).read_text(encoding="utf-8")
    out = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [decision(edits=edits)],
        },
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == reason
    assert transcript_edit_latest_pointer_path(d, tx, ws).read_text(encoding="utf-8") == before
    assert not transcript_edit_revision_path(d, tx, ws, "0002").exists()


def test_unchanged_text_verification_persists_provenance(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-verify"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="Range 7 west")
    out = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                decision(
                    determination="provisional",
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "Range 7 west",
                            "replacement_text": "Range 7 west",
                        }
                    ],
                )
            ],
        },
    )
    assert out["executed"] is True
    rev = json.loads(transcript_edit_revision_path(d, tx, ws, "0002").read_text(encoding="utf-8"))
    assert rev["payload"]["source_transcript_verbatim"] == "Range 7 west"
    assert rev["payload"][TRANSCRIPT_EDIT_DECISIONS_FIELD]["decisions"][0]["determination"] == (
        "provisional"
    )


def test_provisional_and_earned_authored_exactly(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-det"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="A B")
    out = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                decision(
                    decision_id="p",
                    determination="provisional",
                    evidence_refs=[],
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "A",
                            "replacement_text": "A",
                        }
                    ],
                ),
                decision(
                    decision_id="e",
                    determination="earned",
                    evidence_refs=["image:assoc:t1:original"],
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "B",
                            "replacement_text": "B",
                        }
                    ],
                ),
            ],
        },
    )
    assert out["executed"] is True
    rev = json.loads(transcript_edit_revision_path(d, tx, ws, "0002").read_text(encoding="utf-8"))
    dets = {
        x["decision_id"]: x["determination"]
        for x in rev["payload"][TRANSCRIPT_EDIT_DECISIONS_FIELD]["decisions"]
    }
    assert dets == {"p": "provisional", "e": "earned"}
    refused = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0002",
            "decisions": [
                decision(
                    determination="earned",
                    evidence_refs=[],
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "A",
                            "replacement_text": "A",
                        }
                    ],
                )
            ],
        },
    )
    assert refused["refusal"]["reason_code"] == "earned_requires_evidence_refs"


def test_lanes_change_only_when_addressed(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-lanes"
    seed_run(dossiers, d, tx)
    save_base(
        d=d,
        tx=tx,
        ws=ws,
        source="source Range 7 west",
        normalized="norm Range 7 west",
    )
    out = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                decision(
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "Range 7 west",
                            "replacement_text": "Range 77 west",
                        }
                    ]
                )
            ],
        },
    )
    assert out["executed"] is True
    rev = json.loads(transcript_edit_revision_path(d, tx, ws, "0002").read_text(encoding="utf-8"))
    assert rev["payload"]["source_transcript_verbatim"] == "source Range 77 west"
    assert rev["payload"]["normalized_or_mapping_transcript"] == "norm Range 7 west"


def test_updating_decision_preserves_history_in_prior_revision(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-upd"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="Range 7 west")
    first = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [decision(basis="first basis")],
        },
    )
    assert first["executed"] is True
    second = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0002",
            "decisions": [
                decision(
                    basis="second basis",
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "Range 77 west",
                            "replacement_text": "Range 77 west",
                        }
                    ],
                )
            ],
        },
    )
    assert second["executed"] is True
    rev1 = json.loads(transcript_edit_revision_path(d, tx, ws, "0002").read_text(encoding="utf-8"))
    rev2 = json.loads(transcript_edit_revision_path(d, tx, ws, "0003").read_text(encoding="utf-8"))
    assert rev1["payload"][TRANSCRIPT_EDIT_DECISIONS_FIELD]["decisions"][0]["verification_basis"] == (
        "first basis"
    )
    assert rev2["payload"][TRANSCRIPT_EDIT_DECISIONS_FIELD]["decisions"][0]["verification_basis"] == (
        "second basis"
    )
    assert rev2["payload"]["source_transcript_verbatim"] == "Range 77 west"


def test_overwrite_other_decision_span_refuses(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-overlap-dec"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="ALPHA BETA")
    first = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                decision(
                    decision_id="keep",
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "ALPHA",
                            "replacement_text": "ALPHA",
                        }
                    ],
                )
            ],
        },
    )
    assert first["executed"] is True
    refused = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0002",
            "decisions": [
                decision(
                    decision_id="other",
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "ALPH",
                            "replacement_text": "XXXX",
                        }
                    ],
                )
            ],
        },
    )
    assert refused["refusal"]["reason_code"] == "overlaps_other_decision_span"
