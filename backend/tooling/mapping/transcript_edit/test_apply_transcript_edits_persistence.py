"""Persistence / replay / hydration coverage for apply_transcript_edits (MAPDEP-BR-024)."""

from __future__ import annotations

import json

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
from tooling.mapping.transcript_edit.draft_loading import hydrate_transcript_edit_working_draft
from tooling.mapping.transcript_edit.draft_persistence import (
    copy_forward_save,
    publish_transcript_edit_output,
    save_transcript_edit,
)
from tooling.mapping.transcript_edit.paths import (
    transcript_edit_latest_pointer_path,
    transcript_edit_revision_path,
)


def test_stale_base_refuses(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-stale"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="Range 7 west")
    save_base(d=d, tx=tx, ws=ws, source="Range 7 west again")
    out = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [decision()],
        },
    )
    assert out["refusal"]["reason_code"] == "stale_base_revision"


def test_idempotent_replay_and_no_rewind(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-replay"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="Range 7 west | TRAILER")
    req = {
        "base_revision_ref": "transcript_edit:working:rev:0001",
        "decisions": [decision()],
    }
    first = apply_transcript_edits(
        dossier_id=d, transcription_id=tx, workspace_id=ws, request=req
    )
    assert first["executed"] is True
    assert first["outputs"]["idempotent_replay"] is False
    second = apply_transcript_edits(
        dossier_id=d, transcription_id=tx, workspace_id=ws, request=req
    )
    assert second["executed"] is True
    assert second["outputs"]["idempotent_replay"] is True
    assert second["outputs"]["working_draft_ref"] == first["outputs"]["working_draft_ref"]
    later = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0002",
            "decisions": [
                decision(
                    decision_id="d2",
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "TRAILER",
                            "replacement_text": "DONE",
                        }
                    ],
                )
            ],
        },
    )
    assert later["executed"] is True, later
    rewind = apply_transcript_edits(
        dossier_id=d, transcription_id=tx, workspace_id=ws, request=req
    )
    assert rewind["executed"] is False
    assert rewind["refusal"]["reason_code"] == "stale_base_revision"
    latest = json.loads(transcript_edit_latest_pointer_path(d, tx, ws).read_text(encoding="utf-8"))
    assert latest["ref_id"] == "transcript_edit:working:rev:0003"


def test_save_copy_cannot_bypass_managed_provenance(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-integrity"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="Range 7 west")
    applied = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [decision()],
        },
    )
    assert applied["executed"] is True
    mutated = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={
            "source_transcript_verbatim": "silently mutated",
            "issues": [],
        },
    )
    assert mutated["refusal"]["reason_code"] == (
        "managed_provenance_requires_apply_transcript_edits"
    )
    dropped = copy_forward_save(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        base_ref="transcript_edit:working:rev:0002",
        copy_forward_paths=["payload.source_transcript_verbatim"],
        set_paths={"payload.issues": []},
    )
    assert dropped["refusal"]["reason_code"] == (
        "managed_provenance_requires_apply_transcript_edits"
    )
    # Unrelated metadata with coherent provenance+lanes remains allowed via copy-forward.
    ok = copy_forward_save(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        base_ref="transcript_edit:working:rev:0002",
        copy_forward_paths=[
            "payload.source_transcript_verbatim",
            f"payload.{TRANSCRIPT_EDIT_DECISIONS_FIELD}",
        ],
        set_paths={"payload.issues": [{"id": "new"}]},
    )
    assert ok["executed"] is True


def test_hydration_and_publication_preserve_provenance(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-pub"
    seed_run(dossiers, d, tx)
    save_base(
        d=d,
        tx=tx,
        ws=ws,
        source="Range 7 west",
        evidence_refs=["image:assoc:t1:original"],
    )
    applied = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                decision(evidence_refs=["image:derived:abc"])
            ],
        },
    )
    assert applied["executed"] is True
    pub = publish_transcript_edit_output(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        source_revision_ref="transcript_edit:working:rev:0002",
    )
    assert pub["executed"] is True
    hydrated = hydrate_transcript_edit_working_draft(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        ref_id="transcript_edit:working:rev:0002",
    )
    assert hydrated.get("status") != "error"
    payload = hydrated.get("payload") if isinstance(hydrated, dict) else None
    if isinstance(payload, dict) and "payload" in payload:
        # Some hydrate shapes nest revision document under payload.
        payload = payload.get("payload")
    rev = json.loads(transcript_edit_revision_path(d, tx, ws, "0002").read_text(encoding="utf-8"))
    assert TRANSCRIPT_EDIT_DECISIONS_FIELD in rev["payload"]
    assert "image:assoc:t1:original" in rev["evidence_refs"]
    assert "image:derived:abc" in rev["evidence_refs"]
    if isinstance(payload, dict):
        assert TRANSCRIPT_EDIT_DECISIONS_FIELD in payload


def test_storage_failure_no_false_success(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-fail"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="Range 7 west")

    import tooling.mapping.transcript_edit.working_revision_transaction as txn_mod

    real_create = txn_mod._create_only_write_json

    def boom(path, payload):
        if "rev_0002" in str(path):
            raise OSError("disk full")
        return real_create(path, payload)

    monkeypatch.setattr(txn_mod, "_create_only_write_json", boom)
    out = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [decision()],
        },
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "storage_failure"
    latest = json.loads(transcript_edit_latest_pointer_path(d, tx, ws).read_text(encoding="utf-8"))
    assert latest["ref_id"] == "transcript_edit:working:rev:0001"
