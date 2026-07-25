"""Tests for dossier-level transcript-edit output persistence."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import asdict
from pathlib import Path

import config.paths as paths_mod
import pytest
import tooling.mapping.transcript_edit.dossier_publication_persistence as pub_mod
import tooling.mapping.transcript_edit.paths as te_paths

from domains.mapping.transcript_edit.payloads.startup_inventory import (
    T0DraftDescriptor,
    TranscriptEditDraftInventory,
    TranscriptEditScope,
    TranscriptEditStartupInventory,
)
from services.dossier.segment_topology import TopologyRunInput, TopologySegmentInput
from tooling.mapping.transcript_edit.dossier_artifact_refs import qualify_leaf_ref
from tooling.mapping.transcript_edit.dossier_publication_candidate import (
    build_dossier_publication_candidate,
)
from tooling.mapping.transcript_edit.dossier_publication_paths import (
    dossier_transcript_edit_dossier_output_dir,
    dossier_transcript_edit_dossier_output_latest_pointer_path,
    dossier_transcript_edit_dossier_output_revision_path,
)
from tooling.mapping.transcript_edit.dossier_publication_persistence import (
    OUTPUT_REF,
    POINTER_SCHEMA_VERSION,
    publish_dossier_transcript_edit_output,
)
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    build_dossier_transcript_edit_startup_inventory_from_segments,
)
from tooling.mapping.transcript_edit.draft_persistence import save_transcript_edit
from tooling.mapping.transcript_edit.paths import transcript_edit_output_path


def _dossiers_root(tmp_path: Path) -> Path:
    root = tmp_path / "dossiers_data"
    root.mkdir(parents=True)
    return root


def _patch_roots(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)


def _minimal_run_layout(root: Path, dossier_id: str, transcription_id: str) -> None:
    run = root / "views" / "transcriptions" / dossier_id / transcription_id
    raw = run / "raw"
    raw.mkdir(parents=True)
    (raw / f"{transcription_id}_draft_1.json").write_text(
        json.dumps({"sections": [{"body": f"t0 {transcription_id}"}]}),
        encoding="utf-8",
    )
    (run / "run.json").write_text(
        json.dumps({"completed_drafts": [f"{transcription_id}_draft_1"]}),
        encoding="utf-8",
    )


def _leaf_builder(**kwargs):
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
        ),
        transcript_edit_drafts=TranscriptEditDraftInventory(working_draft_exists=False),
    )


def _save_revision(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    verbatim: str,
    normalized: str,
) -> str:
    out = save_transcript_edit(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        draft_payload={
            "source_transcript_verbatim": verbatim,
            "normalized_or_mapping_transcript": normalized,
            "issues": [],
        },
    )
    assert out["executed"] is True
    return out["outputs"]["working_draft_ref"]


def _qualify(segment_id: str, transcription_id: str, leaf_ref: str) -> str:
    return qualify_leaf_ref(
        segment_id=segment_id,
        transcription_id=transcription_id,
        leaf_ref=leaf_ref,
    )


def _tree_fp(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return out


def _file_mtime_ns(path: Path) -> int:
    return path.stat().st_mtime_ns


def _two_segment_ready(tmp_path, monkeypatch, *, workspace_id: str = "ws-pub"):
    root = _dossiers_root(tmp_path)
    _patch_roots(monkeypatch, root)
    d = "d1"
    _minimal_run_layout(root, d, "tx_a")
    _minimal_run_layout(root, d, "tx_b")
    leaf_a = _save_revision(
        dossier_id=d,
        transcription_id="tx_a",
        workspace_id=workspace_id,
        verbatim="ALPHA",
        normalized="AN",
    )
    leaf_b = _save_revision(
        dossier_id=d,
        transcription_id="tx_b",
        workspace_id=workspace_id,
        verbatim="BRAVO",
        normalized="BN",
    )
    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id=d,
        workspace_id=workspace_id,
        segments=(
            TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),
            TopologySegmentInput("seg_b", 1, (TopologyRunInput("tx_b", 0),)),
        ),
        association_positions={"tx_a": 1, "tx_b": 2},
        leaf_inventory_builder=_leaf_builder,
    )
    refs = [
        _qualify("seg_a", "tx_a", leaf_a),
        _qualify("seg_b", "tx_b", leaf_b),
    ]
    return root, d, workspace_id, bundle, leaf_a, leaf_b, refs


def test_first_publication_writes_revision_and_pointer(tmp_path, monkeypatch) -> None:
    root, d, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    before = _tree_fp(root)
    result = publish_dossier_transcript_edit_output(
        bundle=bundle,
        workspace_key=ws,
        source_revision_refs=refs,
    )
    assert result["executed"] is True
    assert result["outputs"]["idempotent_replay"] is False
    assert result["outputs"]["recovered_existing_revision"] is False
    fp = result["outputs"]["candidate_fingerprint"]
    rev_path = dossier_transcript_edit_dossier_output_revision_path(d, ws, fp)
    pointer_path = dossier_transcript_edit_dossier_output_latest_pointer_path(d, ws)
    assert rev_path.is_file()
    assert pointer_path.is_file()
    after = _tree_fp(root)
    new_paths = set(after) - set(before)
    assert any(p.endswith(f"revisions/{fp}.json") for p in new_paths)
    assert any(p.endswith("output/latest.json") for p in new_paths)


def test_persisted_candidate_matches_br004(tmp_path, monkeypatch) -> None:
    _, d, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    expected = build_dossier_publication_candidate(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    result = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert result["executed"] is True
    fp = result["outputs"]["candidate_fingerprint"]
    assert fp == expected.candidate_fingerprint
    stored = json.loads(
        dossier_transcript_edit_dossier_output_revision_path(d, ws, fp).read_text(
            encoding="utf-8"
        )
    )
    assert stored["candidate_fingerprint"] == fp
    assert stored["candidate"] == json.loads(
        json.dumps(asdict(expected), sort_keys=True, separators=(",", ":"), allow_nan=False)
    )


def test_success_artifact_refs_are_publication_only(tmp_path, monkeypatch) -> None:
    _, _, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    result = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert result["artifact_refs"] == [
        OUTPUT_REF,
        result["outputs"]["output_revision_ref"],
    ]
    assert len(result["artifact_refs"]) == 2
    assert result["outputs"]["output_revision_ref"].startswith(
        "transcript_edit:dossier_output:sha256:"
    )


def test_exact_replay_preserves_bytes_and_timestamps(tmp_path, monkeypatch) -> None:
    _, d, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    first = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert first["executed"] is True
    fp = first["outputs"]["candidate_fingerprint"]
    rev_path = dossier_transcript_edit_dossier_output_revision_path(d, ws, fp)
    pointer_path = dossier_transcript_edit_dossier_output_latest_pointer_path(d, ws)
    rev_bytes = rev_path.read_bytes()
    pointer_bytes = pointer_path.read_bytes()
    rev_mtime = _file_mtime_ns(rev_path)
    pointer_mtime = _file_mtime_ns(pointer_path)
    time.sleep(0.05)
    second = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert second["executed"] is True
    assert second["outputs"]["idempotent_replay"] is True
    assert second["outputs"]["published_at"] == first["outputs"]["published_at"]
    assert rev_path.read_bytes() == rev_bytes
    assert pointer_path.read_bytes() == pointer_bytes
    assert _file_mtime_ns(rev_path) == rev_mtime
    assert _file_mtime_ns(pointer_path) == pointer_mtime


def test_changed_revision_advances_pointer_keeps_previous(tmp_path, monkeypatch) -> None:
    root, d, ws, bundle, leaf_a, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    first = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    fp1 = first["outputs"]["candidate_fingerprint"]
    rev1 = dossier_transcript_edit_dossier_output_revision_path(d, ws, fp1)
    rev1_bytes = rev1.read_bytes()

    leaf_a2 = _save_revision(
        dossier_id=d,
        transcription_id="tx_a",
        workspace_id=ws,
        verbatim="ALPHA-2",
        normalized="AN-2",
    )
    refs2 = [_qualify("seg_a", "tx_a", leaf_a2), refs[1]]
    second = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs2
    )
    assert second["executed"] is True
    assert second["outputs"]["idempotent_replay"] is False
    fp2 = second["outputs"]["candidate_fingerprint"]
    assert fp2 != fp1
    rev2 = dossier_transcript_edit_dossier_output_revision_path(d, ws, fp2)
    assert rev2.is_file()
    assert rev1.read_bytes() == rev1_bytes
    pointer = json.loads(
        dossier_transcript_edit_dossier_output_latest_pointer_path(d, ws).read_text(
            encoding="utf-8"
        )
    )
    assert pointer["candidate_fingerprint"] == fp2
    assert leaf_a != leaf_a2
    assert root is not None


def test_valid_pointer_missing_revision_refuses(tmp_path, monkeypatch) -> None:
    _, d, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    first = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    fp = first["outputs"]["candidate_fingerprint"]
    rev_path = dossier_transcript_edit_dossier_output_revision_path(d, ws, fp)
    rev_path.unlink()
    result = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "dossier_publication_pointer_invalid"
    assert result["refusal"]["retryable"] is False


def test_malformed_pointer_refuses_before_write(tmp_path, monkeypatch) -> None:
    root, d, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    output_dir = dossier_transcript_edit_dossier_output_dir(d, ws)
    output_dir.mkdir(parents=True, exist_ok=True)
    pointer_path = dossier_transcript_edit_dossier_output_latest_pointer_path(d, ws)
    pointer_path.write_text(
        json.dumps(
            {
                "schema_version": POINTER_SCHEMA_VERSION,
                "output_ref": OUTPUT_REF,
                "output_revision_ref": "transcript_edit:dossier_output:sha256:" + ("a" * 64),
                "candidate_fingerprint": "a" * 64,
                "relative_path": "revisions/" + ("a" * 64) + ".json",
                "document_sha256": "b" * 64,
                "published_at": "2020-01-01T00:00:00Z",
                "topology_fingerprint": "topo",
            }
        ),
        encoding="utf-8",
    )
    before = _tree_fp(root)
    result = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "dossier_publication_pointer_invalid"
    after = _tree_fp(root)
    # No new immutable revision allocated for the requested candidate.
    assert not any("/revisions/" in p and p.endswith(".json") for p in set(after) - set(before))


def test_corrupt_same_fingerprint_revision_refuses_without_overwrite(
    tmp_path, monkeypatch
) -> None:
    _, d, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    expected = build_dossier_publication_candidate(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    fp = expected.candidate_fingerprint
    rev_path = dossier_transcript_edit_dossier_output_revision_path(d, ws, fp)
    rev_path.parent.mkdir(parents=True, exist_ok=True)
    corrupt = {"schema_version": "wrong", "marker": "keep-me"}
    rev_path.write_text(json.dumps(corrupt), encoding="utf-8")
    original = rev_path.read_bytes()
    result = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "dossier_publication_revision_invalid"
    assert rev_path.read_bytes() == original


def test_pointer_write_failure_leaves_orphan_and_retry_recovers(
    tmp_path, monkeypatch
) -> None:
    _, d, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    expected = build_dossier_publication_candidate(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    fp = expected.candidate_fingerprint
    original = pub_mod._atomic_write_json

    def _fail_pointer(path: Path, payload: dict) -> None:
        if path.name == "latest.json":
            raise OSError("pointer boom")
        original(path, payload)

    monkeypatch.setattr(pub_mod, "_atomic_write_json", _fail_pointer)
    failed = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert failed["executed"] is False
    assert failed["refusal"]["reason_code"] == "dossier_publication_pointer_write_failed"
    assert failed["refusal"]["retryable"] is True
    rev_path = dossier_transcript_edit_dossier_output_revision_path(d, ws, fp)
    assert rev_path.is_file()
    pointer_path = dossier_transcript_edit_dossier_output_latest_pointer_path(d, ws)
    assert not pointer_path.is_file()
    orphan_bytes = rev_path.read_bytes()

    monkeypatch.setattr(pub_mod, "_atomic_write_json", original)
    recovered = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert recovered["executed"] is True
    assert recovered["outputs"]["recovered_existing_revision"] is True
    assert recovered["outputs"]["idempotent_replay"] is False
    assert rev_path.read_bytes() == orphan_bytes
    assert pointer_path.is_file()
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert pointer["candidate_fingerprint"] == fp


def test_lock_contention_is_retryable_and_writes_nothing(tmp_path, monkeypatch) -> None:
    root, d, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    output_dir = dossier_transcript_edit_dossier_output_dir(d, ws)
    started = threading.Event()
    release = threading.Event()

    def _hold() -> None:
        with pub_mod._workspace_publish_lock(dossier_id=d, workspace_id=ws):
            started.set()
            release.wait(timeout=5)

    holder = threading.Thread(target=_hold, daemon=True)
    holder.start()
    assert started.wait(timeout=5)
    try:
        result = publish_dossier_transcript_edit_output(
            bundle=bundle, workspace_key=ws, source_revision_refs=refs
        )
    finally:
        release.set()
        holder.join(timeout=5)
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "dossier_publication_in_progress"
    assert result["refusal"]["retryable"] is True
    revisions_dir = output_dir / "revisions"
    assert not revisions_dir.exists() or not any(revisions_dir.glob("*.json"))
    assert not (output_dir / "latest.json").exists()
    assert root is not None


def test_candidate_failure_creates_no_publication_directory(tmp_path, monkeypatch) -> None:
    root, _, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    result = publish_dossier_transcript_edit_output(
        bundle=bundle,
        workspace_key=ws,
        source_revision_refs=refs[:1],
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "incomplete_segment_coverage"
    assert not (root / "artifacts" / "transcript_edit_dossier").exists()


def test_invalid_scope_path_writes_nothing(tmp_path, monkeypatch) -> None:
    root, _, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)

    def _boom(*_args, **_kwargs):
        from tooling.mapping.transcript_edit.paths import UnsafeArtifactPathSegmentError

        raise UnsafeArtifactPathSegmentError("dossier_id_unsafe_path_characters")

    monkeypatch.setattr(
        pub_mod,
        "dossier_transcript_edit_dossier_output_dir",
        _boom,
    )
    result = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "invalid_scope_path"
    assert not (root / "artifacts" / "transcript_edit_dossier").exists()


def test_no_host_paths_or_binary_in_results_and_store(tmp_path, monkeypatch) -> None:
    _, d, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    result = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    blob = json.dumps(result)
    assert ":\\" not in blob
    assert "AppData" not in blob
    assert "workspace_root" not in blob
    assert "image_b64" not in blob
    fp = result["outputs"]["candidate_fingerprint"]
    stored = dossier_transcript_edit_dossier_output_revision_path(d, ws, fp).read_text(
        encoding="utf-8"
    )
    assert ":\\" not in stored
    assert "AppData" not in stored
    assert "workspace_root" not in stored


def test_fifteen_segments_publish_without_cap(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    _patch_roots(monkeypatch, root)
    d, ws = "d15", "ws-15"
    refs: list[str] = []
    segments: list[TopologySegmentInput] = []
    assoc: dict[str, int] = {}
    for i in range(15):
        tid = f"tx_{i}"
        sid = f"seg_{i}"
        _minimal_run_layout(root, d, tid)
        leaf = _save_revision(
            dossier_id=d,
            transcription_id=tid,
            workspace_id=ws,
            verbatim=f"V{i}",
            normalized=f"N{i}",
        )
        segments.append(TopologySegmentInput(sid, i, (TopologyRunInput(tid, 0),)))
        assoc[tid] = i + 1
        refs.append(_qualify(sid, tid, leaf))
    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id=d,
        workspace_id=ws,
        segments=tuple(segments),
        association_positions=assoc,
        leaf_inventory_builder=_leaf_builder,
    )
    result = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=list(reversed(refs))
    )
    assert result["executed"] is True
    assert result["outputs"]["segment_count"] == 15
    assert result["outputs"]["source_revision_count"] == 15


def test_no_per_segment_output_or_legacy_final_files(tmp_path, monkeypatch) -> None:
    root, d, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    result = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert result["executed"] is True
    for tid in ("tx_a", "tx_b"):
        assert not transcript_edit_output_path(d, tid, ws).exists()
    assert not list(root.rglob("dossier_final.json"))
    assert not list(root.rglob("*finalized*"))
    assert not (root / "artifacts" / "transcript_edit_dossier" / d / ws / "final").exists()


def _mutate_stored_candidate_transcript_and_rehash(
    *,
    dossier_id: str,
    workspace_id: str,
    fingerprint: str,
    update_pointer: bool,
) -> Path:
    rev_path = dossier_transcript_edit_dossier_output_revision_path(
        dossier_id, workspace_id, fingerprint
    )
    doc = json.loads(rev_path.read_text(encoding="utf-8"))
    doc["candidate"]["source_transcript_verbatim"] = (
        str(doc["candidate"]["source_transcript_verbatim"]) + "\nTAMPERED"
    )
    # Fingerprint fields intentionally left unchanged (coordinated content corruption).
    rev_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if update_pointer:
        pointer_path = dossier_transcript_edit_dossier_output_latest_pointer_path(
            dossier_id, workspace_id
        )
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        pointer["document_sha256"] = pub_mod._canonical_document_sha256(doc)
        pointer_path.write_text(
            json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return rev_path


def test_replay_refuses_when_stored_candidate_content_diverges(
    tmp_path, monkeypatch
) -> None:
    _, d, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    first = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert first["executed"] is True
    fp = first["outputs"]["candidate_fingerprint"]
    rev_path = _mutate_stored_candidate_transcript_and_rehash(
        dossier_id=d, workspace_id=ws, fingerprint=fp, update_pointer=True
    )
    original = rev_path.read_bytes()
    replay = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert replay["executed"] is False
    assert replay["refusal"]["reason_code"] == "dossier_publication_revision_invalid"
    assert replay["refusal"]["retryable"] is False
    assert rev_path.read_bytes() == original
    blob = json.dumps(replay)
    assert ":\\" not in blob
    assert "AppData" not in blob
    assert "TAMPERED" not in blob


def test_orphan_recovery_refuses_diverged_candidate_payload(
    tmp_path, monkeypatch
) -> None:
    _, d, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    expected = build_dossier_publication_candidate(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    fp = expected.candidate_fingerprint
    # Create orphan revision only (no pointer), then corrupt candidate content.
    rev_path = dossier_transcript_edit_dossier_output_revision_path(d, ws, fp)
    rev_path.parent.mkdir(parents=True, exist_ok=True)
    published_at = "2020-01-01T00:00:00Z"
    revision_doc = pub_mod._build_revision_document(
        candidate=expected,
        fingerprint=fp,
        output_revision_ref=f"transcript_edit:dossier_output:sha256:{fp}",
        published_at=published_at,
    )
    pub_mod._atomic_write_json(rev_path, revision_doc)
    rev_path = _mutate_stored_candidate_transcript_and_rehash(
        dossier_id=d, workspace_id=ws, fingerprint=fp, update_pointer=False
    )
    original = rev_path.read_bytes()
    result = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "dossier_publication_revision_invalid"
    assert rev_path.read_bytes() == original
    assert not dossier_transcript_edit_dossier_output_latest_pointer_path(d, ws).exists()


def test_unknown_pointer_field_refuses(tmp_path, monkeypatch) -> None:
    _, d, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    first = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert first["executed"] is True
    pointer_path = dossier_transcript_edit_dossier_output_latest_pointer_path(d, ws)
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["extra_compat_field"] = "residue"
    pointer_path.write_text(json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "dossier_publication_pointer_invalid"


def test_unknown_revision_field_refuses(tmp_path, monkeypatch) -> None:
    _, d, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    first = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert first["executed"] is True
    fp = first["outputs"]["candidate_fingerprint"]
    rev_path = dossier_transcript_edit_dossier_output_revision_path(d, ws, fp)
    doc = json.loads(rev_path.read_text(encoding="utf-8"))
    doc["injected_state"] = True
    rev_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Pointer hash no longer matches; pointer path should refuse before reuse.
    via_pointer = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert via_pointer["executed"] is False
    assert via_pointer["refusal"]["reason_code"] == "dossier_publication_pointer_invalid"

    # Orphan path (delete pointer) should surface revision_invalid for unknown fields.
    dossier_transcript_edit_dossier_output_latest_pointer_path(d, ws).unlink()
    orphan = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert orphan["executed"] is False
    assert orphan["refusal"]["reason_code"] == "dossier_publication_revision_invalid"


def test_output_directory_creation_failure_is_contained(tmp_path, monkeypatch) -> None:
    _, _, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    secret = r"C:\Users\example\AppData\Local\secret-output"
    original_mkdir = Path.mkdir

    def _mkdir(self: Path, *args, **kwargs):
        if self.name == "output" and "transcript_edit_dossier" in self.as_posix():
            raise OSError(f"cannot create directory {secret}")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", _mkdir)
    result = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "dossier_publication_storage_failed"
    assert result["refusal"]["retryable"] is False
    blob = json.dumps(result)
    assert secret not in blob
    assert "AppData" not in blob
    assert "cannot create directory" not in blob


def test_lock_file_open_failure_is_contained(tmp_path, monkeypatch) -> None:
    _, _, ws, bundle, _, _, refs = _two_segment_ready(tmp_path, monkeypatch)
    secret = r"C:\Users\example\AppData\Local\.publish.lock"
    real_open = open

    def _open(file, *args, **kwargs):
        path_text = str(file)
        if path_text.endswith(".publish.lock"):
            raise OSError(f"cannot open {secret}")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", _open)
    result = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "dossier_publication_storage_failed"
    blob = json.dumps(result)
    assert secret not in blob
    assert "AppData" not in blob
    assert "cannot open" not in blob

