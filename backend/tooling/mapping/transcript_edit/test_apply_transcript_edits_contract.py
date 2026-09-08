"""Contract refusal coverage for apply_transcript_edits (MAPDEP-BR-024)."""

from __future__ import annotations

import pytest

from tooling.mapping.transcript_edit._apply_transcript_edits_test_helpers import (
    decision,
    root,
    save_base,
    seed_run,
)
from tooling.mapping.transcript_edit.apply_transcript_edits import apply_transcript_edits
from tooling.mapping.transcript_edit.apply_transcript_edits_contract import (
    ApplyTranscriptEditsContractError,
    validate_apply_transcript_edits_request,
)


def test_strict_types_and_oversized_refuse(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-strict"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="Range 7 west")
    bad_type = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                {
                    "decision_id": "d1",
                    "determination": "provisional",
                    "verification_basis": "ok",
                    "evidence_refs": "not-a-list",
                    "edits": [
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "Range 7 west",
                            "replacement_text": "x",
                        }
                    ],
                }
            ],
        },
    )
    assert bad_type["executed"] is False
    assert bad_type["refusal"]["reason_code"] == "invalid_string_list"
    unknown = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [decision()],
            "extra": True,
        },
    )
    assert unknown["refusal"]["reason_code"] == "unknown_request_fields"
    aggregate = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working",
            "decisions": [decision()],
        },
    )
    assert aggregate["refusal"]["reason_code"] == "aggregate_base_revision_ref_rejected"


def test_missing_evidence_refs_refuses_as_invalid_string_list(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-missing-ev"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="Range 7 west")
    missing = {
        "decision_id": "d1",
        "determination": "provisional",
        "verification_basis": "ok",
        "edits": [
            {
                "lane": "source_transcript_verbatim",
                "expected_text": "Range 7 west",
                "replacement_text": "x",
            }
        ],
    }
    assert "evidence_refs" not in missing
    out = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [missing],
        },
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "invalid_string_list"


def test_empty_evidence_refs_list_is_not_missing():
    """Pure contract: explicit [] is allowed for provisional (required field present)."""
    validated = validate_apply_transcript_edits_request(
        {
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                {
                    "decision_id": "d1",
                    "determination": "provisional",
                    "verification_basis": "ok",
                    "evidence_refs": [],
                    "edits": [
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "Range 7 west",
                            "replacement_text": "Range 77 west",
                        }
                    ],
                }
            ],
        }
    )
    assert validated.decisions[0].evidence_refs == ()


def test_missing_evidence_refs_key_raises_invalid_string_list():
    with pytest.raises(ApplyTranscriptEditsContractError) as raised:
        validate_apply_transcript_edits_request(
            {
                "base_revision_ref": "transcript_edit:working:rev:0001",
                "decisions": [
                    {
                        "decision_id": "d1",
                        "determination": "provisional",
                        "verification_basis": "ok",
                        "edits": [
                            {
                                "lane": "source_transcript_verbatim",
                                "expected_text": "Range 7 west",
                                "replacement_text": "x",
                            }
                        ],
                    }
                ],
            }
        )
    assert raised.value.reason_code == "invalid_string_list"
