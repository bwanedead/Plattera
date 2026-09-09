"""Failure-injection and immutability coverage for working_revision_transaction."""

from __future__ import annotations

import json
from pathlib import Path

import config.paths as paths_mod
import pytest

from tooling.mapping.transcript_edit.draft_persistence import save_transcript_edit
from tooling.mapping.transcript_edit.paths import (
    transcript_edit_latest_pointer_path,
    transcript_edit_manifest_path,
    transcript_edit_revision_path,
)
from tooling.mapping.transcript_edit import working_revision_transaction as txn
from tooling.mapping.transcript_edit.apply_transcript_edits import apply_transcript_edits


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


def _decision(**kwargs):
    body = {
        "decision_id": kwargs.get("decision_id", "d1"),
        "determination": "provisional",
        "uncertainty_reasons": ["source_ambiguous"],
        "verification_basis": "basis",
        "evidence_refs": [],
        "edits": [
            {
                "lane": "source_transcript_verbatim",
                "expected_text": kwargs.get("expected", "Range 7 west"),
                "replacement_text": kwargs.get("replacement", "Range 77 west"),
            }
        ],
    }
    return body


def test_revision_bytes_never_overwritten_on_conflicting_coordinate(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-conflict"
    _seed(root, d, tx)
    save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west"},
    )
    # Plant an orphan rev_0002 with foreign content while head is still 0001.
    orphan = {
        "schema_version": 1,
        "revision": 2,
        "ref_id": "transcript_edit:working:rev:0002",
        "saved_at": "2020-01-01T00:00:00Z",
        "tool": "apply_transcript_edits",
        "base_revision_ref": "transcript_edit:working:rev:0001",
        "evidence_refs": [],
        "rationale": None,
        "apply_request_identity": "foreign-identity",
        "payload": {"source_transcript_verbatim": "FOREIGN"},
    }
    rev2 = transcript_edit_revision_path(d, tx, ws, "0002")
    rev2.parent.mkdir(parents=True, exist_ok=True)
    rev2.write_text(json.dumps(orphan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    before = rev2.read_bytes()

    out = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [_decision()],
        },
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "conflicting_revision_coordinate"
    assert rev2.read_bytes() == before


@pytest.mark.parametrize(
    "fail_stage,expected_code",
    [
        ("create", "storage_failure"),
        ("latest", "storage_failure_partial"),
        ("manifest", "storage_failure_partial"),
    ],
)
def test_partial_failure_stages(tmp_path, monkeypatch, fail_stage, expected_code):
    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", f"ws-{fail_stage}"
    _seed(root, d, tx)
    save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west"},
    )
    head_before = transcript_edit_latest_pointer_path(d, tx, ws).read_text(encoding="utf-8")

    real_create = txn._create_only_write_json
    real_atomic = txn._atomic_write_json

    def boom_create(path, payload):
        if fail_stage == "create" and "rev_0002" in str(path):
            raise OSError("create failed")
        return real_create(path, payload)

    def boom_atomic(path, payload):
        name = path.name
        if fail_stage == "latest" and name == "latest.json":
            raise OSError("latest failed")
        if fail_stage == "manifest" and name == "manifest.json":
            raise OSError("manifest failed")
        return real_atomic(path, payload)

    monkeypatch.setattr(txn, "_create_only_write_json", boom_create)
    monkeypatch.setattr(txn, "_atomic_write_json", boom_atomic)

    out = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [_decision()],
        },
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == expected_code

    if fail_stage == "create":
        assert not transcript_edit_revision_path(d, tx, ws, "0002").exists()
        assert transcript_edit_latest_pointer_path(d, tx, ws).read_text(encoding="utf-8") == head_before
    if fail_stage == "latest":
        # Revision may exist as orphan; must not be overwritten on retry.
        assert transcript_edit_revision_path(d, tx, ws, "0002").is_file()
        orphan_bytes = transcript_edit_revision_path(d, tx, ws, "0002").read_bytes()
        monkeypatch.setattr(txn, "_create_only_write_json", real_create)
        monkeypatch.setattr(txn, "_atomic_write_json", real_atomic)
        retry = apply_transcript_edits(
            dossier_id=d,
            transcription_id=tx,
            workspace_id=ws,
            request={
                "base_revision_ref": "transcript_edit:working:rev:0001",
                "decisions": [_decision()],
            },
        )
        assert retry["executed"] is True
        assert transcript_edit_revision_path(d, tx, ws, "0002").read_bytes() == orphan_bytes
    if fail_stage == "manifest":
        # Latest advanced; number must not be reused. Replay recovers success facts
        # and heals the lagging manifest.
        latest = json.loads(transcript_edit_latest_pointer_path(d, tx, ws).read_text(encoding="utf-8"))
        assert latest["ref_id"] == "transcript_edit:working:rev:0002"
        monkeypatch.setattr(txn, "_create_only_write_json", real_create)
        monkeypatch.setattr(txn, "_atomic_write_json", real_atomic)
        retry = apply_transcript_edits(
            dossier_id=d,
            transcription_id=tx,
            workspace_id=ws,
            request={
                "base_revision_ref": "transcript_edit:working:rev:0001",
                "decisions": [_decision()],
            },
        )
        assert retry["executed"] is True
        assert retry["outputs"]["idempotent_replay"] is True
        man = json.loads(transcript_edit_manifest_path(d, tx, ws).read_text(encoding="utf-8"))
        assert man["latest_revision"] == 2
        assert man["latest_working_ref_id"] == "transcript_edit:working:rev:0002"
        next_save = save_transcript_edit(
            dossier_id=d,
            transcription_id=tx,
            workspace_id=ws,
            draft_payload={
                "source_transcript_verbatim": "Range 77 west",
                "transcript_edit_decisions": json.loads(
                    transcript_edit_revision_path(d, tx, ws, "0002").read_text(encoding="utf-8")
                )["payload"]["transcript_edit_decisions"],
                "issues": [{"id": "meta"}],
            },
            base_revision_ref="transcript_edit:working:rev:0002",
        )
        assert next_save["executed"] is True
        assert next_save["outputs"]["working_draft_ref"] == "transcript_edit:working:rev:0003"


def test_copy_forward_race_competitor_cannot_be_lost(tmp_path, monkeypatch):
    """Competing writer advancing head between validate and append is refused."""
    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-race"
    _seed(root, d, tx)
    first = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={
            "source_transcript_verbatim": "Range 7 west",
            "issues": [],
        },
    )
    assert first["executed"] is True

    applied = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [_decision()],
        },
    )
    assert applied["executed"] is True

    # Advance head again via ordinary save while preserving managed provenance.
    from tooling.mapping.transcript_edit.draft_persistence import copy_forward_save

    rev2 = json.loads(transcript_edit_revision_path(d, tx, ws, "0002").read_text(encoding="utf-8"))
    advanced = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={
            "source_transcript_verbatim": rev2["payload"]["source_transcript_verbatim"],
            "transcript_edit_decisions": rev2["payload"]["transcript_edit_decisions"],
            "issues": [{"id": "advance"}],
        },
        base_revision_ref="transcript_edit:working:rev:0002",
    )
    assert advanced["executed"] is True, advanced

    stale = copy_forward_save(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        base_ref="transcript_edit:working:rev:0002",
        copy_forward_paths=[
            "payload.source_transcript_verbatim",
            "payload.transcript_edit_decisions",
        ],
        set_paths={"payload.issues": [{"id": "x"}]},
    )
    assert stale["executed"] is False
    assert stale["refusal"]["reason_code"] == "stale_base_revision"
    latest = json.loads(transcript_edit_latest_pointer_path(d, tx, ws).read_text(encoding="utf-8"))
    assert latest["ref_id"] == "transcript_edit:working:rev:0003"


def test_same_identity_altered_orphan_payload_refuses_without_advancing(tmp_path, monkeypatch):
    from tooling.mapping.transcript_edit.apply_transcript_edits_contract import (
        validate_apply_transcript_edits_request,
    )

    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-id-corrupt"
    _seed(root, d, tx)
    save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west"},
    )
    request = {
        "base_revision_ref": "transcript_edit:working:rev:0001",
        "decisions": [_decision()],
    }
    identity = validate_apply_transcript_edits_request(request).request_identity
    orphan = {
        "schema_version": 1,
        "revision": 2,
        "ref_id": "transcript_edit:working:rev:0002",
        "saved_at": "2020-01-01T00:00:00Z",
        "tool": "apply_transcript_edits",
        "base_revision_ref": "transcript_edit:working:rev:0001",
        "evidence_refs": [],
        "rationale": None,
        "apply_request_identity": identity,
        "payload": {"source_transcript_verbatim": "CORRUPTED ORPHAN"},
    }
    rev2 = transcript_edit_revision_path(d, tx, ws, "0002")
    rev2.parent.mkdir(parents=True, exist_ok=True)
    rev2.write_text(json.dumps(orphan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    before = rev2.read_bytes()
    latest_before = transcript_edit_latest_pointer_path(d, tx, ws).read_text(encoding="utf-8")

    out = apply_transcript_edits(
        dossier_id=d, transcription_id=tx, workspace_id=ws, request=request
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "conflicting_revision_coordinate"
    assert rev2.read_bytes() == before
    assert transcript_edit_latest_pointer_path(d, tx, ws).read_text(encoding="utf-8") == latest_before


def test_malformed_latest_manifest_refuses_without_writing(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-bad-latest"
    _seed(root, d, tx)
    save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west"},
    )
    latest_path = transcript_edit_latest_pointer_path(d, tx, ws)
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    latest["revision"] = "1"  # malformed: string instead of int
    latest_path.write_text(json.dumps(latest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    man_before = transcript_edit_manifest_path(d, tx, ws).read_text(encoding="utf-8")

    out = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west", "issues": []},
        base_revision_ref="transcript_edit:working:rev:0001",
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "invalid_working_storage_state"
    assert not transcript_edit_revision_path(d, tx, ws, "0002").exists()
    assert transcript_edit_manifest_path(d, tx, ws).read_text(encoding="utf-8") == man_before


def test_revision_capacity_refusal(tmp_path, monkeypatch):
    from tooling.mapping.transcript_edit import working_revision_state as state_mod
    from tooling.mapping.transcript_edit import working_revision_transaction as txn_mod
    from tooling.mapping.transcript_edit.working_revision_atomic_io import (
        compact_dumps,
        content_sha256_of_doc,
    )

    monkeypatch.setattr(state_mod, "MAX_WORKING_REVISION", 2)
    monkeypatch.setattr(txn_mod, "MAX_WORKING_REVISION", 2)

    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-cap"
    _seed(root, d, tx)
    first = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west"},
    )
    assert first["executed"] is True
    second = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west", "issues": []},
        base_revision_ref="transcript_edit:working:rev:0001",
    )
    assert second["executed"] is True
    assert second["outputs"]["working_draft_ref"] == "transcript_edit:working:rev:0002"

    out = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west", "issues": [{"id": "x"}]},
        base_revision_ref="transcript_edit:working:rev:0002",
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "revision_capacity_exceeded"


def test_malformed_latest_json_not_treated_as_absent(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-malformed-latest"
    _seed(root, d, tx)
    save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west"},
    )
    latest_path = transcript_edit_latest_pointer_path(d, tx, ws)
    latest_before = latest_path.read_bytes()
    latest_path.write_text("{not-json", encoding="utf-8")

    out = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west", "issues": []},
        base_revision_ref="transcript_edit:working:rev:0001",
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "invalid_working_storage_state"
    assert not transcript_edit_revision_path(d, tx, ws, "0002").exists()
    # Pointer not "healed" into a new valid latest by treating corrupt as absent.
    assert latest_path.read_text(encoding="utf-8") == "{not-json"


def test_malformed_manifest_schema_refuses(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-bad-man"
    _seed(root, d, tx)
    save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west"},
    )
    man_path = transcript_edit_manifest_path(d, tx, ws)
    man = json.loads(man_path.read_text(encoding="utf-8"))
    man["schema_version"] = "1"
    man_path.write_text(json.dumps(man, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    man_before = man_path.read_bytes()

    out = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west", "issues": []},
        base_revision_ref="transcript_edit:working:rev:0001",
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "invalid_working_storage_state"
    assert man_path.read_bytes() == man_before
    assert not transcript_edit_revision_path(d, tx, ws, "0002").exists()


def test_gapped_orphan_rev_0003_refuses(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-gap"
    _seed(root, d, tx)
    save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west"},
    )
    orphan = {
        "schema_version": 1,
        "revision": 3,
        "ref_id": "transcript_edit:working:rev:0003",
        "saved_at": "2020-01-01T00:00:00Z",
        "tool": "save_transcript_edit",
        "base_revision_ref": "transcript_edit:working:rev:0001",
        "evidence_refs": [],
        "rationale": None,
        "payload": {"source_transcript_verbatim": "GAP"},
    }
    rev3 = transcript_edit_revision_path(d, tx, ws, "0003")
    rev3.write_text(json.dumps(orphan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest_before = transcript_edit_latest_pointer_path(d, tx, ws).read_bytes()

    out = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west", "issues": []},
        base_revision_ref="transcript_edit:working:rev:0001",
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "invalid_working_storage_state"
    assert transcript_edit_latest_pointer_path(d, tx, ws).read_bytes() == latest_before


def test_multiple_orphans_refuse(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-multi-orphan"
    _seed(root, d, tx)
    save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west"},
    )
    for n in (2, 3):
        orphan = {
            "schema_version": 1,
            "revision": n,
            "ref_id": f"transcript_edit:working:rev:{n:04d}",
            "saved_at": "2020-01-01T00:00:00Z",
            "tool": "save_transcript_edit",
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "evidence_refs": [],
            "rationale": None,
            "payload": {"source_transcript_verbatim": f"O{n}"},
        }
        transcript_edit_revision_path(d, tx, ws, f"{n:04d}").write_text(
            json.dumps(orphan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    out = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west", "issues": []},
        base_revision_ref="transcript_edit:working:rev:0001",
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "invalid_working_storage_state"


def test_pointer_hash_length_mismatch_refuses(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-hash"
    _seed(root, d, tx)
    save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west"},
    )
    latest_path = transcript_edit_latest_pointer_path(d, tx, ws)
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    latest["content_sha256"] = "0" * 64
    latest_path.write_text(json.dumps(latest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest_before = latest_path.read_bytes()

    out = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west", "issues": []},
        base_revision_ref="transcript_edit:working:rev:0001",
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "invalid_working_storage_state"
    assert latest_path.read_bytes() == latest_before
    assert not transcript_edit_revision_path(d, tx, ws, "0002").exists()


def test_nan_payload_refuses_without_mutation(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-nan"
    _seed(root, d, tx)
    first = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"source_transcript_verbatim": "Range 7 west"},
    )
    assert first["executed"] is True
    latest_before = transcript_edit_latest_pointer_path(d, tx, ws).read_bytes()

    out = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={
            "source_transcript_verbatim": "Range 7 west",
            "score": float("nan"),
        },
        base_revision_ref="transcript_edit:working:rev:0001",
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "noncanonical_revision_payload"
    assert transcript_edit_latest_pointer_path(d, tx, ws).read_bytes() == latest_before
    assert not transcript_edit_revision_path(d, tx, ws, "0002").exists()


def test_parse_working_revision_ref_rejects_non_strings():
    from tooling.mapping.transcript_edit.working_revision_io import parse_working_revision_ref

    assert parse_working_revision_ref("transcript_edit:working:rev:0001") == "0001"
    assert parse_working_revision_ref(b"transcript_edit:working:rev:0001") is None
    assert parse_working_revision_ref(1) is None
    assert parse_working_revision_ref(None) is None
