"""Offline acceptance for initialize_working_transcript (MAPDEP-BR-033)."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import config.paths as paths_mod
import pytest
import tooling.mapping.transcript_edit.paths as te_paths

from domains.mapping.transcript_edit.payloads.initialization_provenance import (
    COPY_POSTURE_UNVERIFIED_CANDIDATE,
    INITIALIZATION_PROVENANCE_FIELD,
)
from domains.mapping.transcript_edit.payloads.transcript_edit_decisions import (
    TRANSCRIPT_EDIT_DECISIONS_FIELD,
)
from services.dossier.segment_topology import TopologyRunInput, TopologySegmentInput
from tooling.mapping.transcript_edit.apply_transcript_edits import apply_transcript_edits
from tooling.mapping.transcript_edit.dossier_artifact_refs import qualify_leaf_ref
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    build_dossier_transcript_edit_startup_inventory_from_segments,
)
from tooling.mapping.transcript_edit.dossier_workspace_actions import (
    make_dossier_initialize_working_transcript_handler,
)
from tooling.mapping.transcript_edit.draft_loading import (
    hydrate_transcript_edit_working_draft,
    load_exact_working_revision_document,
)
from tooling.mapping.transcript_edit.initialize_working_transcript import (
    initialize_working_transcript,
)
from tooling.mapping.transcript_edit.paths import (
    transcript_edit_latest_pointer_path,
    transcript_edit_manifest_path,
    transcript_edit_revision_path,
)
from tooling.mapping.transcript_edit import working_revision_transaction as wrt
from tooling.mapping.transcript_edit.working_write_lock import working_write_lock


PEER_A_TEXT = "PEER_A_SYNTHETIC_BODY exact text"
PEER_B_TEXT = "PEER_B_DIFFERENT_SYNTHETIC_BODY other text"


def _root(tmp_path: Path, monkeypatch) -> Path:
    dossiers = tmp_path / "dossiers_data"
    dossiers.mkdir(parents=True)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: dossiers)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: dossiers)
    return dossiers


def _seed_peers(
    root: Path,
    *,
    dossier_id: str = "d1",
    transcription_id: str = "t1",
    peer_a: str = PEER_A_TEXT,
    peer_b: str = PEER_B_TEXT,
) -> Path:
    run = root / "views" / "transcriptions" / dossier_id / transcription_id
    raw = run / "raw"
    raw.mkdir(parents=True)
    path_a = raw / f"{transcription_id}_draft_1.json"
    path_b = raw / f"{transcription_id}_draft_2.json"
    path_a.write_text(json.dumps({"sections": [{"body": peer_a}]}), encoding="utf-8")
    path_b.write_text(json.dumps({"sections": [{"body": peer_b}]}), encoding="utf-8")
    (run / "run.json").write_text(
        json.dumps(
            {
                "completed_drafts": [
                    f"{transcription_id}_draft_1",
                    f"{transcription_id}_draft_2",
                ]
            }
        ),
        encoding="utf-8",
    )
    return path_a


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_fingerprint(path: Path) -> tuple[str, float]:
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime


def test_leaf_initialize_from_exact_t0_ref(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    t0_path = _seed_peers(root)
    before = _file_fingerprint(t0_path)

    out = initialize_working_transcript(
        dossier_id="d1",
        transcription_id="t1",
        workspace_id="ws-init",
        request={"source_ref": "t0:raw:draft_1"},
    )
    assert out["executed"] is True
    assert out["outputs"]["working_draft_ref"] == "transcript_edit:working:rev:0001"
    assert out["outputs"]["aggregate_working_ref"] == "transcript_edit:working"
    assert out["outputs"]["source_ref"] == "t0:raw:draft_1"
    assert out["outputs"]["initialization_posture"] == COPY_POSTURE_UNVERIFIED_CANDIDATE
    assert out["outputs"]["copied_lanes"] == [
        "source_transcript_verbatim",
        "normalized_or_mapping_transcript",
    ]
    assert out["outputs"]["idempotent_replay"] is False
    assert "workspace_root" not in out["outputs"]
    assert "path" not in json.dumps(out)

    rev = json.loads(
        transcript_edit_revision_path("d1", "t1", "ws-init", "0001").read_text(encoding="utf-8")
    )
    payload = rev["payload"]
    assert payload["source_transcript_verbatim"] == PEER_A_TEXT
    assert payload["normalized_or_mapping_transcript"] == PEER_A_TEXT
    assert payload["evidence_refs"] == ["t0:raw:draft_1"]
    assert rev["evidence_refs"] == ["t0:raw:draft_1"]
    assert payload[TRANSCRIPT_EDIT_DECISIONS_FIELD] == {
        "schema_version": 2,
        "decisions": [],
    }
    prov = payload[INITIALIZATION_PROVENANCE_FIELD]
    assert prov["schema_version"] == 1
    assert prov["source_ref"] == "t0:raw:draft_1"
    assert prov["source_text_sha256"] == _sha(PEER_A_TEXT)
    assert prov["copy_posture"] == COPY_POSTURE_UNVERIFIED_CANDIDATE
    assert "issues" not in payload
    assert "parcel_metadata" not in payload
    assert before == _file_fingerprint(t0_path)


def test_only_named_peer_is_copied(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _seed_peers(root)
    out = initialize_working_transcript(
        dossier_id="d1",
        transcription_id="t1",
        workspace_id="ws-peer",
        request={"source_ref": "t0:raw:draft_2"},
    )
    assert out["executed"] is True
    rev = json.loads(
        transcript_edit_revision_path("d1", "t1", "ws-peer", "0001").read_text(encoding="utf-8")
    )
    assert rev["payload"]["source_transcript_verbatim"] == PEER_B_TEXT
    assert PEER_A_TEXT not in json.dumps(rev["payload"])


def test_idempotent_replay_is_no_write(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _seed_peers(root)
    first = initialize_working_transcript(
        dossier_id="d1",
        transcription_id="t1",
        workspace_id="ws-replay",
        request={"source_ref": "t0:raw:draft_1"},
    )
    rev_path = transcript_edit_revision_path("d1", "t1", "ws-replay", "0001")
    latest_path = transcript_edit_latest_pointer_path("d1", "t1", "ws-replay")
    before_rev = _file_fingerprint(rev_path)
    before_latest = _file_fingerprint(latest_path)
    time.sleep(0.02)
    second = initialize_working_transcript(
        dossier_id="d1",
        transcription_id="t1",
        workspace_id="ws-replay",
        request={"source_ref": "t0:raw:draft_1"},
    )
    assert second["executed"] is True
    assert second["outputs"]["idempotent_replay"] is True
    assert second["outputs"]["working_draft_ref"] == first["outputs"]["working_draft_ref"]
    assert before_rev == _file_fingerprint(rev_path)
    assert before_latest == _file_fingerprint(latest_path)


def test_different_source_replay_refuses_without_mutation(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    t0_a = _seed_peers(root)
    initialize_working_transcript(
        dossier_id="d1",
        transcription_id="t1",
        workspace_id="ws-diff",
        request={"source_ref": "t0:raw:draft_1"},
    )
    rev_path = transcript_edit_revision_path("d1", "t1", "ws-diff", "0001")
    before = _file_fingerprint(rev_path)
    before_t0 = _file_fingerprint(t0_a)
    refused = initialize_working_transcript(
        dossier_id="d1",
        transcription_id="t1",
        workspace_id="ws-diff",
        request={"source_ref": "t0:raw:draft_2"},
    )
    assert refused["executed"] is False
    assert refused["refusal"]["reason_code"] == "conflicting_initialization_replay"
    assert before == _file_fingerprint(rev_path)
    assert before_t0 == _file_fingerprint(t0_a)


def test_advanced_head_cannot_reinitialize(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _seed_peers(root)
    initialize_working_transcript(
        dossier_id="d1",
        transcription_id="t1",
        workspace_id="ws-adv",
        request={"source_ref": "t0:raw:draft_1"},
    )
    applied = apply_transcript_edits(
        dossier_id="d1",
        transcription_id="t1",
        workspace_id="ws-adv",
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                {
                    "decision_id": "d-synth",
                    "determination": "provisional",
                    "uncertainty_reasons": ["source_ambiguous"],
                    "verification_basis": "synthetic basis",
                    "evidence_refs": [],
                    "edits": [
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "PEER_A_SYNTHETIC_BODY",
                            "replacement_text": "PEER_A_SYNTHETIC_BODY",
                        }
                    ],
                }
            ],
        },
    )
    assert applied["executed"] is True
    assert applied["outputs"]["working_draft_ref"] == "transcript_edit:working:rev:0002"
    refused = initialize_working_transcript(
        dossier_id="d1",
        transcription_id="t1",
        workspace_id="ws-adv",
        request={"source_ref": "t0:raw:draft_1"},
    )
    assert refused["executed"] is False
    assert refused["refusal"]["reason_code"] == "working_lineage_already_initialized"


def test_invalid_refs_and_unknown_fields_refuse(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _seed_peers(root)
    cases = [
        ({}, "source_ref_required"),
        ({"source_ref": "t0:raw:draft_1", "extra": 1}, "unknown_request_fields"),
        ({"source_ref": 12}, "source_ref_invalid_type"),
        ({"source_ref": "  t0:raw:draft_1  "}, "source_ref_invalid_type"),
        ({"source_ref": ""}, "source_ref_required"),
        ({"source_ref": "transcript_edit:working:rev:0001"}, "unsupported_source_ref"),
        ({"source_ref": "t0:raw:t1"}, "unsupported_source_ref"),
        ({"source_ref": "t0:raw:draft_99"}, "source_ref_unresolved"),
        ({"source_ref": "image:assoc:t1:original"}, "unsupported_source_ref"),
        ({"source_ref": "fabricated:ref"}, "unsupported_source_ref"),
    ]
    for request, code in cases:
        out = initialize_working_transcript(
            dossier_id="d1",
            transcription_id="t1",
            workspace_id="ws-bad",
            request=request,
        )
        assert out["executed"] is False, request
        assert out["refusal"]["reason_code"] == code, request
        assert not transcript_edit_revision_path("d1", "t1", "ws-bad", "0001").exists()


def test_returned_revision_hydrates_and_supports_apply(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _seed_peers(root)
    init = initialize_working_transcript(
        dossier_id="d1",
        transcription_id="t1",
        workspace_id="ws-apply",
        request={"source_ref": "t0:raw:draft_1"},
    )
    ref = init["outputs"]["working_draft_ref"]
    hydrated = hydrate_transcript_edit_working_draft(
        dossier_id="d1",
        transcription_id="t1",
        workspace_id="ws-apply",
        ref_id=ref,
    )
    assert hydrated["status"] == "ok"
    assert hydrated["payload"]["payload"]["source_transcript_verbatim"] == PEER_A_TEXT
    loaded = load_exact_working_revision_document(
        dossier_id="d1",
        transcription_id="t1",
        workspace_id="ws-apply",
        revision_ref=ref,
    )
    assert loaded.document["payload"]["source_transcript_verbatim"] == PEER_A_TEXT
    applied = apply_transcript_edits(
        dossier_id="d1",
        transcription_id="t1",
        workspace_id="ws-apply",
        request={
            "base_revision_ref": ref,
            "decisions": [
                {
                    "decision_id": "earn-later",
                    "determination": "provisional",
                    "uncertainty_reasons": ["evidence_incomplete"],
                    "verification_basis": "initialized baseline still provisional",
                    "evidence_refs": [],
                    "edits": [
                        {
                            "lane": "normalized_or_mapping_transcript",
                            "expected_text": PEER_A_TEXT,
                            "replacement_text": PEER_A_TEXT + " [normalized-scaffold]",
                        }
                    ],
                }
            ],
        },
    )
    assert applied["executed"] is True
    assert applied["outputs"]["working_draft_ref"] == "transcript_edit:working:rev:0002"


def test_concurrent_initialization_at_most_one_success(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _seed_peers(root)
    results: list[dict] = []
    barrier = threading.Barrier(2)

    def worker():
        barrier.wait(timeout=5)
        results.append(
            initialize_working_transcript(
                dossier_id="d1",
                transcription_id="t1",
                workspace_id="ws-race",
                request={"source_ref": "t0:raw:draft_1"},
            )
        )

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    successes = [r for r in results if r.get("executed") is True]
    failures = [r for r in results if r.get("executed") is False]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0]["refusal"]["reason_code"] in {
        "working_write_in_progress",
        "working_lineage_already_initialized",
        "conflicting_initialization_replay",
    }
    assert transcript_edit_revision_path("d1", "t1", "ws-race", "0001").is_file()
    assert not transcript_edit_revision_path("d1", "t1", "ws-race", "0002").exists()


def test_failure_injection_no_false_success(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _seed_peers(root)

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(wrt, "_create_only_write_json", boom)
    out = initialize_working_transcript(
        dossier_id="d1",
        transcription_id="t1",
        workspace_id="ws-fail",
        request={"source_ref": "t0:raw:draft_1"},
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] in {
        "storage_failure",
        "storage_failure_partial",
        "revision_coordinate_exists",
    }
    assert not transcript_edit_latest_pointer_path("d1", "t1", "ws-fail").exists()


def test_lock_contention_refuses(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _seed_peers(root)
    with working_write_lock(dossier_id="d1", transcription_id="t1", workspace_id="ws-lock"):
        out = initialize_working_transcript(
            dossier_id="d1",
            transcription_id="t1",
            workspace_id="ws-lock",
            request={"source_ref": "t0:raw:draft_1"},
        )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "working_write_in_progress"


def _leaf_inventory_builder(**kwargs):
    from domains.mapping.transcript_edit.payloads.startup_inventory import (
        T0DraftDescriptor,
        TranscriptEditDraftInventory,
        TranscriptEditScope,
        TranscriptEditStartupInventory,
    )

    tid = kwargs["transcription_id"]
    return TranscriptEditStartupInventory(
        scope=TranscriptEditScope(
            dossier_id=kwargs["dossier_id"],
            transcription_id=tid,
            segment_id=kwargs.get("segment_id"),
            workspace_id=kwargs.get("workspace_id"),
        ),
        t0_drafts=(
            T0DraftDescriptor(
                ref_id="t0:raw:draft_1",
                variant_label="draft 1",
                source_file_stem=f"{tid}_draft_1",
            ),
            T0DraftDescriptor(
                ref_id="t0:raw:draft_2",
                variant_label="draft 2",
                source_file_stem=f"{tid}_draft_2",
            ),
        ),
        transcript_edit_drafts=TranscriptEditDraftInventory(working_draft_exists=False),
    )


def test_dossier_qualified_initialization(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _seed_peers(root, transcription_id="tx_a", peer_a="SEG_A_TEXT", peer_b="SEG_A_PEER2")
    _seed_peers(root, transcription_id="tx_b", peer_a="SEG_B_TEXT", peer_b="SEG_B_PEER2")
    segments = (
        TopologySegmentInput("seg-a", 0, (TopologyRunInput("tx_a", 0),)),
        TopologySegmentInput("seg-b", 1, (TopologyRunInput("tx_b", 0),)),
    )
    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id="d1",
        workspace_id="ws-dossier",
        segments=segments,
        association_positions={"tx_a": 1, "tx_b": 2},
        leaf_inventory_builder=_leaf_inventory_builder,
    )
    handler = make_dossier_initialize_working_transcript_handler(
        dossier_id="d1",
        ref_index=bundle.ref_index,
        workspace_key="ws-dossier",
    )
    source = qualify_leaf_ref(
        segment_id="seg-a",
        transcription_id="tx_a",
        leaf_ref="t0:raw:draft_1",
    )
    out = handler({"source_ref": source})
    assert out["executed"] is True
    assert out["outputs"]["source_ref"] == source
    assert out["outputs"]["evidence_refs"] == [source]
    working = out["outputs"]["working_draft_ref"]
    assert working.startswith("dossier_segment:seg-a:run:tx_a:")
    assert working.endswith("transcript_edit:working:rev:0001")
    # Projection must not double-qualify an already-qualified source_ref.
    assert out["outputs"]["source_ref"].count("dossier_segment:") == 1

    rev = json.loads(
        transcript_edit_revision_path("d1", "tx_a", "ws-dossier", "0001").read_text(
            encoding="utf-8"
        )
    )
    assert rev["payload"]["source_transcript_verbatim"] == "SEG_A_TEXT"
    assert rev["evidence_refs"] == [source]
    assert rev["payload"]["evidence_refs"] == [source]
    assert rev["payload"][INITIALIZATION_PROVENANCE_FIELD]["source_ref"] == source
    assert "t0:raw:draft_1" not in rev["evidence_refs"]
    assert not transcript_edit_revision_path("d1", "tx_b", "ws-dossier", "0001").exists()

    rev_path = transcript_edit_revision_path("d1", "tx_a", "ws-dossier", "0001")
    latest_path = transcript_edit_latest_pointer_path("d1", "tx_a", "ws-dossier")
    before_rev = _file_fingerprint(rev_path)
    before_latest = _file_fingerprint(latest_path)
    replay = handler({"source_ref": source})
    assert replay["executed"] is True
    assert replay["outputs"]["idempotent_replay"] is True
    assert replay["outputs"]["source_ref"] == source
    assert replay["outputs"]["source_ref"].count("dossier_segment:") == 1
    assert before_rev == _file_fingerprint(rev_path)
    assert before_latest == _file_fingerprint(latest_path)

    foreign = qualify_leaf_ref(
        segment_id="seg-b",
        transcription_id="tx_b",
        leaf_ref="t0:raw:draft_1",
    )
    bad = handler({"source_ref": "t0:raw:draft_1"})
    assert bad["executed"] is False
    assert bad["refusal"]["reason_code"] == "dossier_ref_required"

    other = handler({"source_ref": foreign})
    assert other["executed"] is True
    assert other["outputs"]["working_draft_ref"].startswith("dossier_segment:seg-b:run:tx_b:")
    other_rev = json.loads(
        transcript_edit_revision_path("d1", "tx_b", "ws-dossier", "0001").read_text(
            encoding="utf-8"
        )
    )
    assert other_rev["payload"]["source_transcript_verbatim"] == "SEG_B_TEXT"
    assert other_rev["evidence_refs"] == [foreign]
    assert other_rev["payload"][INITIALIZATION_PROVENANCE_FIELD]["source_ref"] == foreign


def test_restart_resolves_initialized_head(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _seed_peers(root)
    initialize_working_transcript(
        dossier_id="d1",
        transcription_id="t1",
        workspace_id="ws-restart",
        request={"source_ref": "t0:raw:draft_1"},
    )
    loaded = load_exact_working_revision_document(
        dossier_id="d1",
        transcription_id="t1",
        workspace_id="ws-restart",
        revision_ref="transcript_edit:working:rev:0001",
    )
    assert loaded.document["payload"][INITIALIZATION_PROVENANCE_FIELD]["source_ref"] == (
        "t0:raw:draft_1"
    )
    latest = json.loads(
        transcript_edit_latest_pointer_path("d1", "t1", "ws-restart").read_text(encoding="utf-8")
    )
    assert latest["ref_id"] == "transcript_edit:working:rev:0001"


def _write_init_revision_doc(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    text: str,
    durable_source_ref: str,
    extra_payload: dict | None = None,
) -> dict:
    digest = _sha(text)
    payload = {
        "source_transcript_verbatim": text,
        "normalized_or_mapping_transcript": text,
        "evidence_refs": [durable_source_ref],
        TRANSCRIPT_EDIT_DECISIONS_FIELD: {"schema_version": 2, "decisions": []},
        INITIALIZATION_PROVENANCE_FIELD: {
            "schema_version": 1,
            "source_ref": durable_source_ref,
            "source_text_sha256": digest,
            "copy_posture": COPY_POSTURE_UNVERIFIED_CANDIDATE,
            "copied_lanes": [
                "source_transcript_verbatim",
                "normalized_or_mapping_transcript",
            ],
        },
    }
    if extra_payload:
        payload.update(extra_payload)
    doc = {
        "schema_version": 1,
        "revision": 1,
        "ref_id": "transcript_edit:working:rev:0001",
        "saved_at": "2020-01-01T00:00:00Z",
        "tool": "initialize_working_transcript",
        "base_revision_ref": None,
        "evidence_refs": [durable_source_ref],
        "rationale": None,
        "payload": payload,
    }
    path = transcript_edit_revision_path(dossier_id, transcription_id, workspace_id, "0001")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return doc


def test_recoverable_orphan_equivalent_heals_to_coherent(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _seed_peers(root)
    d, tx, ws = "d1", "t1", "ws-orphan-ok"
    _write_init_revision_doc(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        text=PEER_A_TEXT,
        durable_source_ref="t0:raw:draft_1",
    )
    assert not transcript_edit_latest_pointer_path(d, tx, ws).exists()
    out = initialize_working_transcript(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={"source_ref": "t0:raw:draft_1"},
    )
    assert out["executed"] is True
    assert out["outputs"]["idempotent_replay"] is True
    latest = json.loads(transcript_edit_latest_pointer_path(d, tx, ws).read_text(encoding="utf-8"))
    assert latest["ref_id"] == "transcript_edit:working:rev:0001"
    man = json.loads(transcript_edit_manifest_path(d, tx, ws).read_text(encoding="utf-8"))
    assert man["latest_revision"] == 1
    from tooling.mapping.transcript_edit.working_revision_state import read_working_storage_state

    state = read_working_storage_state(dossier_id=d, transcription_id=tx, workspace_id=ws)
    assert state.kind == "coherent"


def test_conflicting_orphan_refuses_without_overwrite(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _seed_peers(root)
    d, tx, ws = "d1", "t1", "ws-orphan-bad"
    _write_init_revision_doc(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        text="FOREIGN_ORPHAN_TEXT",
        durable_source_ref="t0:raw:draft_1",
    )
    rev_path = transcript_edit_revision_path(d, tx, ws, "0001")
    before = _file_fingerprint(rev_path)
    out = initialize_working_transcript(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={"source_ref": "t0:raw:draft_1"},
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "conflicting_revision_coordinate"
    assert before == _file_fingerprint(rev_path)
    assert not transcript_edit_latest_pointer_path(d, tx, ws).exists()


def test_manifest_lag_heals_before_idempotent_success(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _seed_peers(root)
    d, tx, ws = "d1", "t1", "ws-lag"
    first = initialize_working_transcript(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={"source_ref": "t0:raw:draft_1"},
    )
    assert first["executed"] is True
    man_path = transcript_edit_manifest_path(d, tx, ws)
    man = json.loads(man_path.read_text(encoding="utf-8"))
    man["latest_revision"] = 0
    man["revision_count"] = 0
    man["latest_working_ref_id"] = None
    man_path.write_text(json.dumps(man, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    from tooling.mapping.transcript_edit.working_revision_state import read_working_storage_state

    assert (
        read_working_storage_state(dossier_id=d, transcription_id=tx, workspace_id=ws).kind
        == "manifest_lag"
    )
    rev_path = transcript_edit_revision_path(d, tx, ws, "0001")
    before = _file_fingerprint(rev_path)
    out = initialize_working_transcript(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={"source_ref": "t0:raw:draft_1"},
    )
    assert out["executed"] is True
    assert out["outputs"]["idempotent_replay"] is True
    assert before == _file_fingerprint(rev_path)
    healed = json.loads(man_path.read_text(encoding="utf-8"))
    assert healed["latest_revision"] == 1
    assert healed["latest_working_ref_id"] == "transcript_edit:working:rev:0001"
    assert (
        read_working_storage_state(dossier_id=d, transcription_id=tx, workspace_id=ws).kind
        == "coherent"
    )


def _write_coherent_init_head(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    text: str,
    durable_source_ref: str,
    mutator=None,
) -> tuple[Path, Path]:
    from tooling.mapping.transcript_edit.working_revision_atomic_io import content_sha256_of_doc

    doc = _write_init_revision_doc(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        text=text,
        durable_source_ref=durable_source_ref,
    )
    if mutator is not None:
        mutator(doc)
    rev_path = transcript_edit_revision_path(dossier_id, transcription_id, workspace_id, "0001")
    rev_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = content_sha256_of_doc(doc)
    from tooling.mapping.transcript_edit.working_revision_atomic_io import compact_dumps

    byte_length = len(compact_dumps(doc).encode("utf-8"))
    pointer_saved_at = doc.get("saved_at")
    if type(pointer_saved_at) is not str or not str(pointer_saved_at).strip():
        pointer_saved_at = "2020-01-01T00:00:00Z"
    latest = {
        "schema_version": 1,
        "revision": 1,
        "ref_id": "transcript_edit:working:rev:0001",
        "relative_path": "working/rev_0001.json",
        "content_sha256": digest,
        "byte_length": byte_length,
        "saved_at": pointer_saved_at,
        "tool": "initialize_working_transcript",
    }
    latest_path = transcript_edit_latest_pointer_path(dossier_id, transcription_id, workspace_id)
    latest_path.write_text(json.dumps(latest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "updated_at": pointer_saved_at,
        "revision_count": 1,
        "latest_revision": 1,
        "latest_working_ref_id": "transcript_edit:working:rev:0001",
        "latest_saved_at": pointer_saved_at,
        "latest_content_sha256": digest,
        "last_save_tool": "initialize_working_transcript",
    }
    transcript_edit_manifest_path(dossier_id, transcription_id, workspace_id).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return rev_path, latest_path


def test_replay_requires_full_payload_equality(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _seed_peers(root)
    d, tx = "d1", "t1"

    cases = [
        (
            "extra-field",
            lambda doc: doc["payload"].__setitem__("issues", [{"id": "x"}]),
        ),
        (
            "altered-lane",
            lambda doc: doc["payload"].__setitem__(
                "source_transcript_verbatim", PEER_A_TEXT + " TAMPER"
            ),
        ),
        (
            "altered-provenance",
            lambda doc: doc["payload"][INITIALIZATION_PROVENANCE_FIELD].__setitem__(
                "extra", True
            ),
        ),
        (
            "conflicting-evidence",
            lambda doc: doc.__setitem__("evidence_refs", ["t0:raw:draft_2"]),
        ),
    ]
    for name, mutator in cases:
        ws = f"ws-eq-{name}"
        rev_path, latest_path = _write_coherent_init_head(
            dossier_id=d,
            transcription_id=tx,
            workspace_id=ws,
            text=PEER_A_TEXT,
            durable_source_ref="t0:raw:draft_1",
            mutator=mutator,
        )
        before_rev = _file_fingerprint(rev_path)
        before_latest = _file_fingerprint(latest_path)
        refused = initialize_working_transcript(
            dossier_id=d,
            transcription_id=tx,
            workspace_id=ws,
            request={"source_ref": "t0:raw:draft_1"},
        )
        assert refused["executed"] is False, name
        assert refused["refusal"]["reason_code"] == "conflicting_initialization_replay", (
            name,
            refused,
        )
        assert before_rev == _file_fingerprint(rev_path), name
        assert before_latest == _file_fingerprint(latest_path), name


def test_malformed_source_text_is_type_strict(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-strict"
    run = root / "views" / "transcriptions" / d / tx
    raw = run / "raw"
    raw.mkdir(parents=True)
    cases = [
        {"sections": [{"body": {"nested": "map"}}]},
        {"sections": [{"body": ["list", "body"]}]},
        {"sections": [{"body": 123}]},
        {"text": {"not": "string"}},
        {"transcript": ["x"]},
        {"body": 9},
    ]
    for i, payload in enumerate(cases):
        stem = f"{tx}_draft_1"
        (raw / f"{stem}.json").write_text(json.dumps(payload), encoding="utf-8")
        (run / "run.json").write_text(
            json.dumps({"completed_drafts": [stem]}),
            encoding="utf-8",
        )
        ws_i = f"{ws}-{i}"
        out = initialize_working_transcript(
            dossier_id=d,
            transcription_id=tx,
            workspace_id=ws_i,
            request={"source_ref": "t0:raw:draft_1"},
        )
        assert out["executed"] is False, payload
        assert out["refusal"]["reason_code"] == "source_text_invalid", payload
        assert not transcript_edit_revision_path(d, tx, ws_i, "0001").exists()
        dumped = json.dumps(out)
        assert "dossiers_data" not in dumped
        assert "Traceback" not in dumped
        assert str(tmp_path) not in dumped


_SAVED_AT_MALFORMED = (
    ("missing", "_MISSING_"),
    ("null", None),
    ("numeric", 123),
    ("boolean", True),
    ("mapping", {"ts": "2020-01-01T00:00:00Z"}),
    ("blank", "   "),
)


def test_coherent_replay_requires_typed_saved_at(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _seed_peers(root)
    d, tx = "d1", "t1"
    for name, value in _SAVED_AT_MALFORMED:
        ws = f"ws-savedat-coherent-{name}"

        def mutator(doc, *, _value=value):
            if _value == "_MISSING_":
                doc.pop("saved_at", None)
            else:
                doc["saved_at"] = _value

        rev_path, latest_path = _write_coherent_init_head(
            dossier_id=d,
            transcription_id=tx,
            workspace_id=ws,
            text=PEER_A_TEXT,
            durable_source_ref="t0:raw:draft_1",
            mutator=mutator,
        )
        before_rev = _file_fingerprint(rev_path)
        before_latest = _file_fingerprint(latest_path)
        refused = initialize_working_transcript(
            dossier_id=d,
            transcription_id=tx,
            workspace_id=ws,
            request={"source_ref": "t0:raw:draft_1"},
        )
        assert refused["executed"] is False, name
        assert refused["refusal"]["reason_code"] == "invalid_working_storage_state", (
            name,
            refused,
        )
        assert before_rev == _file_fingerprint(rev_path), name
        assert before_latest == _file_fingerprint(latest_path), name


def test_orphan_recovery_requires_typed_saved_at(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _seed_peers(root)
    d, tx = "d1", "t1"
    for name, value in _SAVED_AT_MALFORMED:
        ws = f"ws-savedat-orphan-{name}"
        doc = _write_init_revision_doc(
            dossier_id=d,
            transcription_id=tx,
            workspace_id=ws,
            text=PEER_A_TEXT,
            durable_source_ref="t0:raw:draft_1",
        )
        if value == "_MISSING_":
            doc.pop("saved_at", None)
        else:
            doc["saved_at"] = value
        rev_path = transcript_edit_revision_path(d, tx, ws, "0001")
        rev_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        before_rev = _file_fingerprint(rev_path)
        refused = initialize_working_transcript(
            dossier_id=d,
            transcription_id=tx,
            workspace_id=ws,
            request={"source_ref": "t0:raw:draft_1"},
        )
        assert refused["executed"] is False, name
        assert refused["refusal"]["reason_code"] == "invalid_working_storage_state", (
            name,
            refused,
        )
        assert before_rev == _file_fingerprint(rev_path), name
        assert not transcript_edit_latest_pointer_path(d, tx, ws).exists(), name
