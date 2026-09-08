"""Contract and provenance integrity coverage for apply_transcript_edits."""

from __future__ import annotations

import json
from pathlib import Path

import config.paths as paths_mod
import pytest

from domains.mapping.transcript_edit.payloads.transcript_edit_decisions import (
    TRANSCRIPT_EDIT_DECISIONS_FIELD,
)
from tooling.mapping.transcript_edit.apply_transcript_edits import apply_transcript_edits
from tooling.mapping.transcript_edit.draft_persistence import save_transcript_edit
from tooling.mapping.transcript_edit.managed_provenance_integrity import (
    ManagedProvenanceIntegrityError,
    payload_has_managed_provenance,
)
from tooling.mapping.transcript_edit.paths import (
    transcript_edit_latest_pointer_path,
    transcript_edit_revision_path,
)
from tooling.mapping.transcript_edit.transcript_edit_decisions_validate import (
    PersistedProvenanceError,
    validate_persisted_transcript_edit_decisions,
)
from tooling.mapping.transcript_edit.working_revision_atomic_io import (
    compact_dumps,
    content_sha256_of_doc,
)


def _root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "dossiers_data"
    root.mkdir(parents=True)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    return root


def _seed(root: Path, d: str, tx: str) -> None:
    run = root / "views" / "transcriptions" / d / tx
    raw = run / "raw"
    raw.mkdir(parents=True)
    (raw / "peer_a.json").write_text("{}", encoding="utf-8")
    (run / "run.json").write_text(json.dumps({"completed_drafts": ["peer_a"]}), encoding="utf-8")


def _rewrite_head_revision(d: str, tx: str, ws: str, digits: str, doc: dict) -> None:
    """Rewrite a revision file and keep latest.json hash/length coherent."""
    rev_path = transcript_edit_revision_path(d, tx, ws, digits)
    body = json.dumps(doc, indent=2, sort_keys=True, allow_nan=False) + "\n"
    rev_path.write_text(body, encoding="utf-8")
    # Hash/length use compact canonical form (same as production pointers).
    compact = compact_dumps(doc)
    latest_path = transcript_edit_latest_pointer_path(d, tx, ws)
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    latest["content_sha256"] = content_sha256_of_doc(doc)
    latest["byte_length"] = len(compact.encode("utf-8"))
    latest_path.write_text(
        json.dumps(latest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

def test_malformed_provenance_field_refuses_unmanaged_fallback():
    with pytest.raises(ManagedProvenanceIntegrityError) as raised:
        payload_has_managed_provenance(
            {TRANSCRIPT_EDIT_DECISIONS_FIELD: {"schema_version": 2, "decisions": []}}
        )
    assert raised.value.reason_code == "unsupported_provenance_schema"

    with pytest.raises(PersistedProvenanceError):
        validate_persisted_transcript_edit_decisions(
            payload={TRANSCRIPT_EDIT_DECISIONS_FIELD: "nope"}
        )

    assert payload_has_managed_provenance({"source_transcript_verbatim": "x"}) is False


def test_boolean_schema_version_refused():
    with pytest.raises(PersistedProvenanceError) as raised:
        validate_persisted_transcript_edit_decisions(
            payload={
                TRANSCRIPT_EDIT_DECISIONS_FIELD: {
                    "schema_version": True,
                    "decisions": [],
                }
            }
        )
    assert raised.value.reason_code == "malformed_provenance"


def test_evidence_list_divergence_refuses(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-ev"
    _seed(root, d, tx)
    save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={
            "source_transcript_verbatim": "Range 7 west",
            "evidence_refs": ["image:assoc:t1:original"],
        },
        evidence_refs=["image:assoc:t1:original"],
    )
    applied = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                {
                    "decision_id": "d1",
                    "determination": "provisional",
                    "verification_basis": "basis",
                    "evidence_refs": [],
                    "edits": [
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "Range 7 west",
                            "replacement_text": "Range 7 west",
                        }
                    ],
                }
            ],
        },
    )
    assert applied["executed"] is True

    # Corrupt payload evidence relative to revision envelope.
    rev_path = transcript_edit_revision_path(d, tx, ws, "0002")
    doc = json.loads(rev_path.read_text(encoding="utf-8"))
    doc["payload"]["evidence_refs"] = ["image:derived:other"]
    _rewrite_head_revision(d, tx, ws, "0002", doc)

    # Point latest at corrupted rev still as head (same file).
    refused = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0002",
            "decisions": [
                {
                    "decision_id": "d1",
                    "determination": "provisional",
                    "verification_basis": "basis",
                    "evidence_refs": [],
                    "edits": [
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "Range 7 west",
                            "replacement_text": "Range 7 west",
                        }
                    ],
                }
            ],
        },
    )
    assert refused["executed"] is False
    assert refused["refusal"]["reason_code"] == "conflicting_evidence_representation"


def test_idempotent_replay_preserves_changed_lanes(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-replay-facts"
    _seed(root, d, tx)
    save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west"},
    )
    req = {
        "base_revision_ref": "transcript_edit:working:rev:0001",
        "decisions": [
            {
                "decision_id": "d1",
                "determination": "provisional",
                "verification_basis": "basis",
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
    first = apply_transcript_edits(
        dossier_id=d, transcription_id=tx, workspace_id=ws, request=req
    )
    assert first["executed"] is True
    assert first["outputs"]["changed_lanes"]["source_transcript_verbatim"] >= 1
    second = apply_transcript_edits(
        dossier_id=d, transcription_id=tx, workspace_id=ws, request=req
    )
    assert second["executed"] is True
    assert second["outputs"]["idempotent_replay"] is True
    assert second["outputs"]["changed_lanes"] == first["outputs"]["changed_lanes"]
    assert second["outputs"]["applied_decision_ids"] == first["outputs"]["applied_decision_ids"]


def test_evidence_union_order_and_dedupe(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-union"
    _seed(root, d, tx)
    save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west"},
        evidence_refs=["image:assoc:t1:original", "image:derived:a"],
    )
    out = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                {
                    "decision_id": "d1",
                    "determination": "provisional",
                    "verification_basis": "basis",
                    "evidence_refs": [
                        "image:derived:a",
                        "image:derived:b",
                        "image:assoc:t1:original",
                    ],
                    "edits": [
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "Range 7 west",
                            "replacement_text": "Range 77 west",
                        }
                    ],
                }
            ],
        },
    )
    assert out["executed"] is True
    # Inherited order preserved; new refs appended; duplicates dropped.
    assert out["outputs"]["evidence_refs"] == [
        "image:assoc:t1:original",
        "image:derived:a",
        "image:derived:b",
    ]
    rev = json.loads(transcript_edit_revision_path(d, tx, ws, "0002").read_text(encoding="utf-8"))
    assert rev["evidence_refs"] == out["outputs"]["evidence_refs"]
    assert rev["payload"]["evidence_refs"] == out["outputs"]["evidence_refs"]


def test_corrupt_replay_metadata_refuses(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-corrupt-replay"
    _seed(root, d, tx)
    save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west"},
    )
    req = {
        "base_revision_ref": "transcript_edit:working:rev:0001",
        "decisions": [
            {
                "decision_id": "d1",
                "determination": "provisional",
                "verification_basis": "basis",
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
    first = apply_transcript_edits(
        dossier_id=d, transcription_id=tx, workspace_id=ws, request=req
    )
    assert first["executed"] is True
    rev_path = transcript_edit_revision_path(d, tx, ws, "0002")
    doc = json.loads(rev_path.read_text(encoding="utf-8"))
    # Corrupt by removing the summary key entirely.
    del doc["apply_result_summary"]
    _rewrite_head_revision(d, tx, ws, "0002", doc)
    second = apply_transcript_edits(
        dossier_id=d, transcription_id=tx, workspace_id=ws, request=req
    )
    assert second["executed"] is False
    assert second["refusal"]["reason_code"] == "corrupt_replay_metadata"


def test_earned_without_evidence_blocks_save(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-earned"
    _seed(root, d, tx)
    save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west"},
    )
    bad = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={
            "source_transcript_verbatim": "Range 7 west",
            "transcript_edit_decisions": {
                "schema_version": 1,
                "decisions": [
                    {
                        "decision_id": "d1",
                        "determination": "earned",
                        "verification_basis": "basis",
                        "evidence_refs": [],
                        "base_revision_ref": "transcript_edit:working:rev:0001",
                        "edits": [
                            {
                                "lane": "source_transcript_verbatim",
                                "expected_text": "Range 7 west",
                                "replacement_text": "Range 7 west",
                                "start_offset": 0,
                                "end_offset": 13,
                            }
                        ],
                    }
                ],
            },
        },
        base_revision_ref="transcript_edit:working:rev:0001",
    )
    assert bad["executed"] is False
    assert bad["refusal"]["reason_code"] == "earned_requires_evidence_refs"


def test_oversized_decision_id_blocks_copy_forward(tmp_path, monkeypatch):
    from domains.mapping.transcript_edit.payloads.transcript_edit_decisions import (
        MAX_DECISION_ID_CHARS,
    )
    from tooling.mapping.transcript_edit.draft_persistence import copy_forward_save

    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-oversize"
    _seed(root, d, tx)
    save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west"},
    )
    rev_path = transcript_edit_revision_path(d, tx, ws, "0001")
    doc = json.loads(rev_path.read_text(encoding="utf-8"))
    doc["payload"]["transcript_edit_decisions"] = {
        "schema_version": 1,
        "decisions": [
            {
                "decision_id": "x" * (MAX_DECISION_ID_CHARS + 1),
                "determination": "provisional",
                "verification_basis": "basis",
                "evidence_refs": [],
                "base_revision_ref": "transcript_edit:working:rev:0001",
                "edits": [
                    {
                        "lane": "source_transcript_verbatim",
                        "expected_text": "Range 7 west",
                        "replacement_text": "Range 7 west",
                        "start_offset": 0,
                        "end_offset": 13,
                    }
                ],
            }
        ],
    }
    _rewrite_head_revision(d, tx, ws, "0001", doc)

    out = copy_forward_save(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        base_ref="transcript_edit:working:rev:0001",
        copy_forward_paths=[
            "payload.source_transcript_verbatim",
            "payload.transcript_edit_decisions",
        ],
        set_paths={"payload.issues": [{"id": "meta"}]},
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "decision_id_too_long"
