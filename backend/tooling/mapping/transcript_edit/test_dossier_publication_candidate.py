"""Tests for read-only dossier publication candidate assembly."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
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
from tooling.mapping.transcript_edit.dossier_artifact_refs import qualify_leaf_ref
from tooling.mapping.transcript_edit.dossier_publication_candidate import (
    DossierPublicationCandidateError,
    build_dossier_publication_candidate,
)
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    DossierStartupInventoryBundle,
    build_dossier_transcript_edit_startup_inventory_from_segments,
)
from tooling.mapping.transcript_edit.draft_persistence import save_transcript_edit
from tooling.mapping.transcript_edit.paths import transcript_edit_revision_path


def _dossiers_root(tmp_path: Path) -> Path:
    root = tmp_path / "dossiers_data"
    root.mkdir(parents=True)
    return root


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


def _tree_fp(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return out


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


def _payload(*, verbatim: str | dict, normalized: str | dict) -> dict:
    return {
        "source_transcript_verbatim": verbatim,
        "normalized_or_mapping_transcript": normalized,
        "issues": [],
    }


def _save_revision(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    verbatim: str | dict,
    normalized: str | dict,
    evidence_refs: list[str] | None = None,
) -> str:
    out = save_transcript_edit(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        draft_payload=_payload(verbatim=verbatim, normalized=normalized),
        evidence_refs=list(evidence_refs or []),
    )
    assert out["executed"] is True
    return out["outputs"]["working_draft_ref"]


def _qualify(segment_id: str, transcription_id: str, leaf_ref: str) -> str:
    return qualify_leaf_ref(
        segment_id=segment_id,
        transcription_id=transcription_id,
        leaf_ref=leaf_ref,
    )


def test_reverse_selection_orders_by_topology(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d, ws = "d1", "ws-pub"
    _minimal_run_layout(root, d, "tx_a")
    _minimal_run_layout(root, d, "tx_b")
    leaf_a = _save_revision(
        dossier_id=d,
        transcription_id="tx_a",
        workspace_id=ws,
        verbatim="ALPHA VERBATIM",
        normalized="ALPHA NORM",
    )
    leaf_b = _save_revision(
        dossier_id=d,
        transcription_id="tx_b",
        workspace_id=ws,
        verbatim="BRAVO VERBATIM",
        normalized="BRAVO NORM",
    )
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
    q_a = _qualify("seg_a", "tx_a", leaf_a)
    q_b = _qualify("seg_b", "tx_b", leaf_b)
    candidate = build_dossier_publication_candidate(
        bundle=bundle,
        workspace_key=ws,
        source_revision_refs=[q_b, q_a],
    )
    assert candidate.source_revision_refs == (q_a, q_b)
    assert [s.segment_id for s in candidate.segments] == ["seg_a", "seg_b"]
    assert candidate.source_transcript_verbatim == "ALPHA VERBATIM\n\nBRAVO VERBATIM"
    assert candidate.normalized_or_mapping_transcript == "ALPHA NORM\n\nBRAVO NORM"
    assert "path" not in str(candidate)
    assert ":\\" not in str(candidate.segments[0].revision_snapshot)


def test_multi_run_segment_requires_explicit_choice(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d, ws = "d1", "ws-multi"
    _minimal_run_layout(root, d, "tx_a1")
    _minimal_run_layout(root, d, "tx_a2")
    _minimal_run_layout(root, d, "tx_b")
    leaf_a1 = _save_revision(
        dossier_id=d,
        transcription_id="tx_a1",
        workspace_id=ws,
        verbatim="A1",
        normalized="A1N",
    )
    leaf_a2 = _save_revision(
        dossier_id=d,
        transcription_id="tx_a2",
        workspace_id=ws,
        verbatim="A2",
        normalized="A2N",
    )
    leaf_b = _save_revision(
        dossier_id=d,
        transcription_id="tx_b",
        workspace_id=ws,
        verbatim="B",
        normalized="BN",
    )
    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id=d,
        workspace_id=ws,
        segments=(
            TopologySegmentInput(
                "seg_a",
                0,
                (TopologyRunInput("tx_a1", 0), TopologyRunInput("tx_a2", 1)),
            ),
            TopologySegmentInput("seg_b", 1, (TopologyRunInput("tx_b", 0),)),
        ),
        association_positions={"tx_a1": 1, "tx_a2": 2, "tx_b": 3},
        leaf_inventory_builder=_leaf_builder,
    )
    q_a2 = _qualify("seg_a", "tx_a2", leaf_a2)
    q_b = _qualify("seg_b", "tx_b", leaf_b)
    candidate = build_dossier_publication_candidate(
        bundle=bundle,
        workspace_key=ws,
        source_revision_refs=[q_a2, q_b],
    )
    assert candidate.segments[0].transcription_id == "tx_a2"
    assert candidate.source_transcript_verbatim.startswith("A2")

    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle,
            workspace_key=ws,
            source_revision_refs=[
                _qualify("seg_a", "tx_a1", leaf_a1),
                q_a2,
                q_b,
            ],
        )
    assert exc.value.code == "segment_selection_conflict"


def test_selection_refusals(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d, ws = "d1", "ws-refuse"
    _minimal_run_layout(root, d, "tx_a")
    _minimal_run_layout(root, d, "tx_b")
    leaf_a = _save_revision(
        dossier_id=d, transcription_id="tx_a", workspace_id=ws, verbatim="A", normalized="AN"
    )
    leaf_b = _save_revision(
        dossier_id=d, transcription_id="tx_b", workspace_id=ws, verbatim="B", normalized="BN"
    )
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
    q_a = _qualify("seg_a", "tx_a", leaf_a)
    q_b = _qualify("seg_b", "tx_b", leaf_b)

    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle, workspace_key=ws, source_revision_refs=q_a  # type: ignore[arg-type]
        )
    assert exc.value.code == "invalid_selection_collection"

    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle, workspace_key=ws, source_revision_refs=[q_a]
        )
    assert exc.value.code == "incomplete_segment_coverage"

    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle, workspace_key=ws, source_revision_refs=[q_a, q_a, q_b]
        )
    assert exc.value.code == "duplicate_selected_ref"

    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle,
            workspace_key=ws,
            source_revision_refs=[
                q_a,
                q_b,
                _qualify("seg_c", "tx_a", leaf_a),
            ],
        )
    assert exc.value.code in {"ref_outside_topology", "unexpected_segment_selection"}

    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle,
            workspace_key=ws,
            source_revision_refs=[
                _qualify("seg_a", "tx_a", "transcript_edit:working"),
                q_b,
            ],
        )
    assert exc.value.code == "ref_not_exact_working_revision"

    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle,
            workspace_key=ws,
            source_revision_refs=[
                _qualify("seg_a", "tx_a", "transcript_edit:output"),
                q_b,
            ],
        )
    assert exc.value.code == "ref_not_exact_working_revision"

    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle,
            workspace_key=ws,
            source_revision_refs=[
                "dossier_segment:seg_a:run:tx_a:evil:artifact",
                q_b,
            ],
        )
    assert exc.value.code == "ref_not_exact_working_revision"

    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle,
            workspace_key=ws,
            source_revision_refs=[
                _qualify("seg_a", "tx_a", "transcript_edit:working:rev:9999"),
                q_b,
            ],
        )
    assert exc.value.code == "source_revision_not_found"


def test_malformed_revision_and_lane_forms(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d, ws = "d1", "ws-lanes"
    _minimal_run_layout(root, d, "tx_a")
    _minimal_run_layout(root, d, "tx_b")
    leaf_a = _save_revision(
        dossier_id=d,
        transcription_id="tx_a",
        workspace_id=ws,
        verbatim={"text": "  string-map A  "},
        normalized={"text": "norm A"},
    )
    leaf_b = _save_revision(
        dossier_id=d,
        transcription_id="tx_b",
        workspace_id=ws,
        verbatim="plain B",
        normalized={"text": "norm B"},
    )
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
    q_a = _qualify("seg_a", "tx_a", leaf_a)
    q_b = _qualify("seg_b", "tx_b", leaf_b)
    candidate = build_dossier_publication_candidate(
        bundle=bundle,
        workspace_key=ws,
        source_revision_refs=[q_a, q_b],
    )
    assert candidate.segments[0].source_transcript_verbatim == "string-map A"
    assert candidate.source_transcript_verbatim == "string-map A\n\nplain B"

    # Corrupt revision ref_id on disk.
    path = transcript_edit_revision_path(d, "tx_a", ws, "0001")
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["ref_id"] = "transcript_edit:working:rev:0002"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle, workspace_key=ws, source_revision_refs=[q_a, q_b]
        )
    assert exc.value.code == "malformed_revision_document"


def test_blank_transcript_lane_refuses_without_fallback(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d, ws = "d1", "ws-blank"
    _minimal_run_layout(root, d, "tx_a")
    _minimal_run_layout(root, d, "tx_b")
    leaf_a = _save_revision(
        dossier_id=d,
        transcription_id="tx_a",
        workspace_id=ws,
        verbatim={"text": "   "},
        normalized="ok",
    )
    leaf_b = _save_revision(
        dossier_id=d,
        transcription_id="tx_b",
        workspace_id=ws,
        verbatim="B",
        normalized="BN",
    )
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
    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle,
            workspace_key=ws,
            source_revision_refs=[
                _qualify("seg_a", "tx_a", leaf_a),
                _qualify("seg_b", "tx_b", leaf_b),
            ],
        )
    assert exc.value.code == "transcript_lane_invalid"


def test_evidence_refs_must_be_qualified_and_resolvable(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d, ws = "d1", "ws-ev"
    _minimal_run_layout(root, d, "tx_a")
    _minimal_run_layout(root, d, "tx_b")
    evidence_b = _qualify("seg_b", "tx_b", "t0:raw:draft_1")
    leaf_a = _save_revision(
        dossier_id=d,
        transcription_id="tx_a",
        workspace_id=ws,
        verbatim="A",
        normalized="AN",
        evidence_refs=[evidence_b],
    )
    leaf_b = _save_revision(
        dossier_id=d,
        transcription_id="tx_b",
        workspace_id=ws,
        verbatim="B",
        normalized="BN",
    )
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
    candidate = build_dossier_publication_candidate(
        bundle=bundle,
        workspace_key=ws,
        source_revision_refs=[
            _qualify("seg_a", "tx_a", leaf_a),
            _qualify("seg_b", "tx_b", leaf_b),
        ],
    )
    assert candidate.segments[0].evidence_refs == (evidence_b,)
    assert candidate.evidence_refs == (evidence_b,)

    bad = _save_revision(
        dossier_id=d,
        transcription_id="tx_b",
        workspace_id=ws,
        verbatim="B2",
        normalized="BN2",
        evidence_refs=["t0:raw:draft_1"],
    )
    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle,
            workspace_key=ws,
            source_revision_refs=[
                _qualify("seg_a", "tx_a", leaf_a),
                _qualify("seg_b", "tx_b", bad),
            ],
        )
    assert exc.value.code == "invalid_evidence_ref"


def test_fingerprint_stable_under_reordered_input(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d, ws = "d1", "ws-fp"
    _minimal_run_layout(root, d, "tx_a")
    _minimal_run_layout(root, d, "tx_b")
    leaf_a = _save_revision(
        dossier_id=d, transcription_id="tx_a", workspace_id=ws, verbatim="A", normalized="AN"
    )
    leaf_b = _save_revision(
        dossier_id=d, transcription_id="tx_b", workspace_id=ws, verbatim="B", normalized="BN"
    )
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
    q_a = _qualify("seg_a", "tx_a", leaf_a)
    q_b = _qualify("seg_b", "tx_b", leaf_b)
    first = build_dossier_publication_candidate(
        bundle=bundle, workspace_key=ws, source_revision_refs=[q_a, q_b]
    )
    second = build_dossier_publication_candidate(
        bundle=bundle, workspace_key=ws, source_revision_refs=[q_b, q_a]
    )
    assert first.candidate_fingerprint == second.candidate_fingerprint
    assert first.source_revision_refs == second.source_revision_refs


def test_fifteen_segments_no_cap_and_read_only(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d, ws = "d1", "ws-15"
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
    before = _tree_fp(root)
    candidate = build_dossier_publication_candidate(
        bundle=bundle,
        workspace_key=ws,
        source_revision_refs=list(reversed(refs)),
    )
    after = _tree_fp(root)
    assert before == after
    assert len(candidate.segments) == 15
    assert candidate.source_transcript_verbatim == "\n\n".join(f"V{i}" for i in range(15))
    blob = json.dumps(
        {
            "fingerprint": candidate.candidate_fingerprint,
            "refs": list(candidate.source_revision_refs),
            "verbatim": candidate.source_transcript_verbatim,
        }
    )
    assert ":\\" not in blob
    assert "AppData" not in blob


def test_foreign_run_and_wrong_workspace_refuse(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d, ws, other_ws = "d1", "ws-ok", "ws-other"
    _minimal_run_layout(root, d, "tx_a")
    _minimal_run_layout(root, d, "tx_b")
    leaf_a = _save_revision(
        dossier_id=d, transcription_id="tx_a", workspace_id=ws, verbatim="A", normalized="AN"
    )
    leaf_b = _save_revision(
        dossier_id=d, transcription_id="tx_b", workspace_id=ws, verbatim="B", normalized="BN"
    )
    # Two saves in another workspace so its latest leaf ref does not exist under ws.
    _save_revision(
        dossier_id=d,
        transcription_id="tx_b",
        workspace_id=other_ws,
        verbatim="B-other",
        normalized="BN-other",
    )
    leaf_b_other_only = _save_revision(
        dossier_id=d,
        transcription_id="tx_b",
        workspace_id=other_ws,
        verbatim="B-other-2",
        normalized="BN-other-2",
    )
    assert leaf_b_other_only != leaf_b
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
    # Qualify tx_b revision under seg_a (foreign run for that segment binding).
    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle,
            workspace_key=ws,
            source_revision_refs=[
                _qualify("seg_a", "tx_b", leaf_b),
                _qualify("seg_b", "tx_b", leaf_b),
            ],
        )
    assert exc.value.code == "ref_outside_topology"

    # Grammar-valid revision that only exists in another workspace.
    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle,
            workspace_key=ws,
            source_revision_refs=[
                _qualify("seg_a", "tx_a", leaf_a),
                _qualify("seg_b", "tx_b", leaf_b_other_only),
            ],
        )
    assert exc.value.code == "source_revision_not_found"


def _two_segment_bundle(tmp_path, monkeypatch, *, workspace_id: str = "ws-a"):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
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


def test_workspace_key_must_match_inventory_scope(tmp_path, monkeypatch) -> None:
    root, d, ws_a, bundle, leaf_a, leaf_b, refs = _two_segment_bundle(
        tmp_path, monkeypatch, workspace_id="ws-a"
    )
    # Matching revision files also exist under ws-b, but the bundle is bound to ws-a.
    for tid, leaf, verbatim in (
        ("tx_a", leaf_a, "ALPHA-B"),
        ("tx_b", leaf_b, "BRAVO-B"),
    ):
        saved = _save_revision(
            dossier_id=d,
            transcription_id=tid,
            workspace_id="ws-b",
            verbatim=verbatim,
            normalized=f"{verbatim}-N",
        )
        assert saved == leaf
    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle,
            workspace_key="ws-b",
            source_revision_refs=refs,
        )
    assert exc.value.code == "invalid_workspace_scope"
    candidate = build_dossier_publication_candidate(
        bundle=bundle,
        workspace_key=ws_a,
        source_revision_refs=refs,
    )
    assert candidate.workspace_id == ws_a
    assert candidate.source_transcript_verbatim.startswith("ALPHA")
    assert root is not None


def test_topology_fingerprint_mismatch_refuses(tmp_path, monkeypatch) -> None:
    _, _, ws, bundle, _, _, refs = _two_segment_bundle(tmp_path, monkeypatch)
    mismatched = DossierStartupInventoryBundle(
        inventory=replace(bundle.inventory, topology_fingerprint="not-the-index-fp"),
        ref_index=bundle.ref_index,
    )
    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=mismatched,
            workspace_key=ws,
            source_revision_refs=refs,
        )
    assert exc.value.code == "ref_outside_topology"


def test_revision_schema_ref_id_evidence_and_nan_refuse(tmp_path, monkeypatch) -> None:
    _, d, ws, bundle, leaf_a, leaf_b, refs = _two_segment_bundle(tmp_path, monkeypatch)
    path_a = transcript_edit_revision_path(d, "tx_a", ws, "0001")
    assert leaf_a.endswith("0001")

    doc = json.loads(path_a.read_text(encoding="utf-8"))
    doc["schema_version"] = 2
    path_a.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle, workspace_key=ws, source_revision_refs=refs
        )
    assert exc.value.code == "malformed_revision_document"

    doc["schema_version"] = 1
    doc["ref_id"] = 1
    path_a.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle, workspace_key=ws, source_revision_refs=refs
        )
    assert exc.value.code == "malformed_revision_document"

    doc["ref_id"] = leaf_a
    del doc["evidence_refs"]
    path_a.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle, workspace_key=ws, source_revision_refs=refs
        )
    assert exc.value.code == "malformed_revision_document"

    doc["evidence_refs"] = None
    path_a.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle, workspace_key=ws, source_revision_refs=refs
        )
    assert exc.value.code == "malformed_revision_document"

    doc["evidence_refs"] = []
    doc["payload"] = {
        "source_transcript_verbatim": "ALPHA",
        "normalized_or_mapping_transcript": "AN",
        "score": math.nan,
    }
    path_a.write_text(json.dumps(doc, allow_nan=True), encoding="utf-8")
    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle, workspace_key=ws, source_revision_refs=refs
        )
    assert exc.value.code == "malformed_revision_document"
    assert leaf_b


def test_nested_host_binary_content_refuses_without_leaking(tmp_path, monkeypatch) -> None:
    _, d, ws, bundle, leaf_a, _, refs = _two_segment_bundle(tmp_path, monkeypatch)
    path_a = transcript_edit_revision_path(d, "tx_a", ws, "0001")
    doc = json.loads(path_a.read_text(encoding="utf-8"))
    secret = r"C:\Users\example\AppData\Local\secret.png"
    doc["payload"]["nested"] = {
        "absolute_path": secret,
        "workspace_root": r"C:\Users\example\workspace",
        "image_b64": "iVBORw0KGgo=",
    }
    path_a.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bundle, workspace_key=ws, source_revision_refs=refs
        )
    assert exc.value.code == "unsafe_revision_content"
    detail = exc.value.detail
    message = str(exc.value)
    assert secret not in detail
    assert secret not in message
    assert "AppData" not in detail
    assert "AppData" not in message
    assert "iVBORw0KGgo=" not in detail
    assert leaf_a in detail or leaf_a in message


def test_reordered_inventory_segments_assemble_by_position(tmp_path, monkeypatch) -> None:
    _, _, ws, bundle, _, _, refs = _two_segment_bundle(tmp_path, monkeypatch)
    reversed_segments = tuple(reversed(bundle.inventory.segments))
    assert [s.segment_id for s in reversed_segments] == ["seg_b", "seg_a"]
    reordered_bundle = DossierStartupInventoryBundle(
        inventory=replace(bundle.inventory, segments=reversed_segments),
        ref_index=bundle.ref_index,
    )
    candidate = build_dossier_publication_candidate(
        bundle=reordered_bundle,
        workspace_key=ws,
        source_revision_refs=refs,
    )
    assert [s.segment_id for s in candidate.segments] == ["seg_a", "seg_b"]
    assert candidate.source_transcript_verbatim == "ALPHA\n\nBRAVO"


def test_duplicate_segment_ids_or_positions_refuse(tmp_path, monkeypatch) -> None:
    _, _, ws, bundle, _, _, refs = _two_segment_bundle(tmp_path, monkeypatch)
    seg_a, seg_b = bundle.inventory.segments
    dup_id_bundle = DossierStartupInventoryBundle(
        inventory=replace(
            bundle.inventory,
            segments=(seg_a, replace(seg_b, segment_id=seg_a.segment_id)),
        ),
        ref_index=bundle.ref_index,
    )
    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=dup_id_bundle,
            workspace_key=ws,
            source_revision_refs=refs,
        )
    assert exc.value.code == "invalid_topology_segments"

    dup_pos_bundle = DossierStartupInventoryBundle(
        inventory=replace(
            bundle.inventory,
            segments=(seg_a, replace(seg_b, position=seg_a.position)),
        ),
        ref_index=bundle.ref_index,
    )
    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=dup_pos_bundle,
            workspace_key=ws,
            source_revision_refs=refs,
        )
    assert exc.value.code == "invalid_topology_segments"

    bool_pos_bundle = DossierStartupInventoryBundle(
        inventory=replace(
            bundle.inventory,
            segments=(replace(seg_a, position=True), seg_b),  # type: ignore[arg-type]
        ),
        ref_index=bundle.ref_index,
    )
    with pytest.raises(DossierPublicationCandidateError) as exc:
        build_dossier_publication_candidate(
            bundle=bool_pos_bundle,
            workspace_key=ws,
            source_revision_refs=list(refs),
        )
    assert exc.value.code == "invalid_topology_segments"
