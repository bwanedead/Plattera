"""BR-026: dossier publication → deed-to-IR handoff boundary tests."""

from __future__ import annotations

import json
from pathlib import Path

import config.paths as paths_mod
import pytest
import tooling.mapping.transcript_edit.paths as te_paths

from domains.mapping.transcript_edit.payloads.startup_inventory import (
    T0DraftDescriptor,
    TranscriptEditDraftInventory,
    TranscriptEditScope,
    TranscriptEditStartupInventory,
)
from services.dossier.segment_topology import TopologyRunInput, TopologySegmentInput
from tooling.mapping.deed_to_ir.transcript_handoff_loading import (
    TranscriptHandoffLoadError,
    load_transcript_edit_output_handoff,
)
from tooling.mapping.transcript_edit.apply_transcript_edits import apply_transcript_edits
from tooling.mapping.transcript_edit.dossier_artifact_refs import qualify_leaf_ref
from tooling.mapping.transcript_edit.dossier_publication_candidate import (
    build_dossier_publication_candidate,
)
from tooling.mapping.transcript_edit.dossier_publication_paths import (
    dossier_transcript_edit_dossier_output_revision_path,
)
from tooling.mapping.transcript_edit.dossier_publication_persistence import (
    publish_dossier_transcript_edit_output,
)
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    build_dossier_transcript_edit_startup_inventory_from_segments,
)
from tooling.mapping.transcript_edit.draft_persistence import save_transcript_edit


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


def _qualify(segment_id: str, transcription_id: str, leaf_ref: str) -> str:
    return qualify_leaf_ref(
        segment_id=segment_id,
        transcription_id=transcription_id,
        leaf_ref=leaf_ref,
    )


def _save(d: str, tx: str, ws: str, verbatim: str, normalized: str) -> str:
    out = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={
            "source_transcript_verbatim": verbatim,
            "normalized_or_mapping_transcript": normalized,
            "issues": [],
        },
    )
    assert out["executed"] is True
    return out["outputs"]["working_draft_ref"]


def test_dossier_publish_handoff_preserves_segment_decisions(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    _patch_roots(monkeypatch, root)
    d, ws = "d1", "ws-br026"
    _minimal_run_layout(root, d, "tx_a")
    _minimal_run_layout(root, d, "tx_b")

    evidence_a = _qualify("seg_a", "tx_a", "t0:raw:draft_1")
    evidence_b = _qualify("seg_b", "tx_b", "t0:raw:draft_1")

    leaf_a = save_transcript_edit(
        dossier_id=d,
        transcription_id="tx_a",
        workspace_id=ws,
        draft_payload={
            "source_transcript_verbatim": "ALPHA",
            "normalized_or_mapping_transcript": "AN",
            "issues": [],
        },
        evidence_refs=[evidence_a],
    )
    assert leaf_a["executed"] is True
    leaf_a_ref = leaf_a["outputs"]["working_draft_ref"]

    leaf_b = save_transcript_edit(
        dossier_id=d,
        transcription_id="tx_b",
        workspace_id=ws,
        draft_payload={
            "source_transcript_verbatim": "BRAVO",
            "normalized_or_mapping_transcript": "BN",
            "issues": [],
        },
        evidence_refs=[evidence_b],
    )
    assert leaf_b["executed"] is True
    leaf_b_ref = leaf_b["outputs"]["working_draft_ref"]

    earned = apply_transcript_edits(
        dossier_id=d,
        transcription_id="tx_a",
        workspace_id=ws,
        request={
            "base_revision_ref": leaf_a_ref,
            "decisions": [
                {
                    "decision_id": "seg-a-earned",
                    "determination": "earned",
                    "uncertainty_reasons": [],
                    "verification_basis": "clear crop",
                    "evidence_refs": [evidence_a],
                    "edits": [
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "ALPHA",
                            "replacement_text": "ALPHA",
                        }
                    ],
                }
            ],
        },
    )
    assert earned["executed"] is True, earned
    leaf_a2 = earned["outputs"]["working_draft_ref"]

    provisional = apply_transcript_edits(
        dossier_id=d,
        transcription_id="tx_b",
        workspace_id=ws,
        request={
            "base_revision_ref": leaf_b_ref,
            "decisions": [
                {
                    "decision_id": "seg-b-prov",
                    "determination": "provisional",
                    "uncertainty_reasons": ["observer_disagreement"],
                    "verification_basis": "observers disagree",
                    "candidate_values": ["BRAVO", "BRAVA"],
                    "evidence_refs": [evidence_b],
                    "edits": [
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "BRAVO",
                            "replacement_text": "BRAVA",
                        }
                    ],
                }
            ],
        },
    )
    assert provisional["executed"] is True, provisional
    leaf_b2 = provisional["outputs"]["working_draft_ref"]

    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id=d,
        workspace_id=ws,
        segments=(
            TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),
            TopologySegmentInput("seg_b", 1, (TopologyRunInput("tx_b", 0),)),
        ),
        association_positions={"tx_a": 1, "tx_b": 2},
        leaf_inventory_builder=_leaf_builder,
    )
    refs = [
        _qualify("seg_a", "tx_a", leaf_a2),
        _qualify("seg_b", "tx_b", leaf_b2),
    ]
    published = publish_dossier_transcript_edit_output(
        bundle=bundle,
        workspace_key=ws,
        source_revision_refs=refs,
    )
    assert published["executed"] is True, published
    fp = published["outputs"]["candidate_fingerprint"]
    output_revision_ref = published["outputs"]["output_revision_ref"]
    rev_path = dossier_transcript_edit_dossier_output_revision_path(d, ws, fp)

    loaded = load_transcript_edit_output_handoff(output_path=rev_path)
    assert loaded["source"]["source_revision_ref"] == output_revision_ref
    assert loaded["source"]["loaded_source_label"] == "transcript_edit_dossier_output"
    assert loaded["source_transcript_verbatim"] == "ALPHA\n\nBRAVA"
    assert loaded["normalized_or_mapping_transcript"] == "AN\n\nBN"
    assert loaded["counts"]["segments"] == 2

    summary = loaded["transcript_edit_decision_summary"]
    by_id = {row["decision_id"]: row for row in summary["decisions"]}
    assert set(by_id) == {"seg-a-earned", "seg-b-prov"}
    assert by_id["seg-a-earned"]["determination"] == "earned"
    assert by_id["seg-a-earned"]["segment_id"] == "seg_a"
    assert by_id["seg-b-prov"]["determination"] == "provisional"
    assert by_id["seg-b-prov"]["segment_id"] == "seg_b"
    # Provisional prioritized in retained order under normal capacity.
    assert [r["decision_id"] for r in summary["decisions"]] == [
        "seg-b-prov",
        "seg-a-earned",
    ]


def _published_document(tmp_path, monkeypatch) -> tuple[dict, Path]:
    root = _dossiers_root(tmp_path)
    _patch_roots(monkeypatch, root)
    d, ws = "d1", "ws-mut"
    _minimal_run_layout(root, d, "tx_a")
    _minimal_run_layout(root, d, "tx_b")
    leaf_a = _save(d, "tx_a", ws, "ALPHA", "AN")
    leaf_b = _save(d, "tx_b", ws, "BRAVO", "BN")
    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id=d,
        workspace_id=ws,
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
    published = publish_dossier_transcript_edit_output(
        bundle=bundle, workspace_key=ws, source_revision_refs=refs
    )
    assert published["executed"] is True
    fp = published["outputs"]["candidate_fingerprint"]
    path = dossier_transcript_edit_dossier_output_revision_path(d, ws, fp)
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc, path


def test_dossier_handoff_refuses_non_object_segment(tmp_path, monkeypatch) -> None:
    doc, path = _published_document(tmp_path, monkeypatch)
    doc["candidate"]["segments"].append("not-an-object")
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(TranscriptHandoffLoadError) as raised:
        load_transcript_edit_output_handoff(output_path=path)
    assert "segment_not_object" in str(raised.value)


def test_dossier_handoff_refuses_duplicate_position(tmp_path, monkeypatch) -> None:
    doc, path = _published_document(tmp_path, monkeypatch)
    doc["candidate"]["segments"][1]["position"] = doc["candidate"]["segments"][0]["position"]
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(TranscriptHandoffLoadError) as raised:
        load_transcript_edit_output_handoff(output_path=path)
    assert "duplicate_position" in str(raised.value)


def test_dossier_handoff_refuses_blank_segment_id(tmp_path, monkeypatch) -> None:
    doc, path = _published_document(tmp_path, monkeypatch)
    doc["candidate"]["segments"][0]["segment_id"] = "  "
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(TranscriptHandoffLoadError) as raised:
        load_transcript_edit_output_handoff(output_path=path)
    assert "segment_id_blank" in str(raised.value)


def test_dossier_handoff_refuses_stitched_content_mismatch(tmp_path, monkeypatch) -> None:
    doc, path = _published_document(tmp_path, monkeypatch)
    doc["candidate"]["source_transcript_verbatim"] = "TAMPERED"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(TranscriptHandoffLoadError) as raised:
        load_transcript_edit_output_handoff(output_path=path)
    assert "stitched_content_mismatch" in str(raised.value)


def test_dossier_handoff_refuses_conflicting_parcel_metadata(tmp_path, monkeypatch) -> None:
    doc, path = _published_document(tmp_path, monkeypatch)
    segs = doc["candidate"]["segments"]
    segs[0]["revision_snapshot"]["payload"]["parcel_metadata"] = {
        "parcels": [{"parcel_id": "p1"}]
    }
    segs[1]["revision_snapshot"]["payload"]["parcel_metadata"] = {
        "parcels": [{"parcel_id": "p2"}]
    }
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(TranscriptHandoffLoadError) as raised:
        load_transcript_edit_output_handoff(output_path=path)
    assert "conflicting_parcel_metadata" in str(raised.value)


def test_dossier_handoff_uses_output_revision_ref_not_missing_ref_id(
    tmp_path, monkeypatch
) -> None:
    doc, path = _published_document(tmp_path, monkeypatch)
    assert "ref_id" not in doc
    assert doc.get("output_revision_ref")
    loaded = load_transcript_edit_output_handoff(output_path=path)
    assert loaded["source"]["source_revision_ref"] == doc["output_revision_ref"]


def test_dossier_handoff_refuses_malformed_evidence_that_previously_normalized(
    tmp_path, monkeypatch
) -> None:
    doc, path = _published_document(tmp_path, monkeypatch)
    # Both sides get the same non-string junk — old _bounded_str_list would drop both
    # and falsely compare equal [].
    doc["candidate"]["evidence_refs"] = [123, None, ""]
    for seg in doc["candidate"]["segments"]:
        seg["evidence_refs"] = [123, None, ""]
        seg["revision_snapshot"]["evidence_refs"] = [123, None, ""]
        seg["revision_snapshot"]["payload"]["evidence_refs"] = [123, None, ""]
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(TranscriptHandoffLoadError) as raised:
        load_transcript_edit_output_handoff(output_path=path)
    assert "evidence" in str(raised.value)


def test_dossier_handoff_refuses_source_revision_refs_mismatch(tmp_path, monkeypatch) -> None:
    doc, path = _published_document(tmp_path, monkeypatch)
    doc["candidate"]["source_revision_refs"] = list(
        reversed(doc["candidate"]["source_revision_refs"])
    )
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(TranscriptHandoffLoadError) as raised:
        load_transcript_edit_output_handoff(output_path=path)
    assert "source_revision_refs_mismatch" in str(raised.value)


def test_dossier_handoff_refuses_duplicate_segment_id(tmp_path, monkeypatch) -> None:
    doc, path = _published_document(tmp_path, monkeypatch)
    doc["candidate"]["segments"][1]["segment_id"] = doc["candidate"]["segments"][0][
        "segment_id"
    ]
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(TranscriptHandoffLoadError) as raised:
        load_transcript_edit_output_handoff(output_path=path)
    assert "duplicate_segment_id" in str(raised.value)


def test_dossier_handoff_refuses_duplicate_transcription_id(tmp_path, monkeypatch) -> None:
    doc, path = _published_document(tmp_path, monkeypatch)
    doc["candidate"]["segments"][1]["transcription_id"] = doc["candidate"]["segments"][0][
        "transcription_id"
    ]
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(TranscriptHandoffLoadError) as raised:
        load_transcript_edit_output_handoff(output_path=path)
    assert "duplicate_transcription_id" in str(raised.value)


def test_dossier_handoff_refuses_segment_snapshot_evidence_disagreement(
    tmp_path, monkeypatch
) -> None:
    doc, path = _published_document(tmp_path, monkeypatch)
    seg = doc["candidate"]["segments"][0]
    # Keep segment.evidence_refs as published; diverge snapshot list.
    seg["revision_snapshot"]["evidence_refs"] = ["dossier_segment:forged:evidence"]
    if "evidence_refs" in seg["revision_snapshot"]["payload"]:
        seg["revision_snapshot"]["payload"]["evidence_refs"] = [
            "dossier_segment:forged:evidence"
        ]
    # Candidate top-level evidence still matches old segment lists → fail at segment/snapshot.
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(TranscriptHandoffLoadError) as raised:
        load_transcript_edit_output_handoff(output_path=path)
    assert "segment_snapshot_evidence_mismatch" in str(raised.value)
