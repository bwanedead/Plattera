"""Dossier-scoped apply_transcript_edits parity with leaf contract (MAPDEP-BR-024)."""

from __future__ import annotations

import json
from pathlib import Path

import config.paths as paths_mod
import tooling.mapping.transcript_edit.paths as te_paths

from services.dossier.segment_topology import TopologyRunInput, TopologySegmentInput
from tooling.mapping.transcript_edit.dossier_artifact_refs import qualify_leaf_ref
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    build_dossier_transcript_edit_startup_inventory_from_segments,
)
from tooling.mapping.transcript_edit.dossier_workspace_actions import (
    make_dossier_apply_transcript_edits_handler,
    make_dossier_save_workspace_artifact_handler,
)
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
        json.dumps({"sections": [{"body": f"t0 for {transcription_id}"}]}),
        encoding="utf-8",
    )
    (run / "run.json").write_text(
        json.dumps({"completed_drafts": [f"{transcription_id}_draft_1"]}),
        encoding="utf-8",
    )


def _seed_apply_workspace(tmp_path, monkeypatch, *, ws: str = "ws-apply"):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d = "d1"
    _minimal_run_layout(root, d, "tx_a")

    from domains.mapping.transcript_edit.payloads.startup_inventory import (
        T0DraftDescriptor,
        TranscriptEditDraftInventory,
        TranscriptEditScope,
        TranscriptEditStartupInventory,
    )

    def leaf_builder(**kwargs):
        tid = kwargs["transcription_id"]
        return TranscriptEditStartupInventory(
            scope=TranscriptEditScope(
                dossier_id=kwargs["dossier_id"],
                transcription_id=tid,
                segment_id=kwargs.get("segment_id"),
                workspace_id=ws,
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

    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id=d,
        workspace_id=ws,
        segments=(TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),),
        association_positions={"tx_a": 1},
        leaf_inventory_builder=leaf_builder,
    )
    save = make_dossier_save_workspace_artifact_handler(
        dossier_id=d, ref_index=bundle.ref_index, workspace_key=ws
    )
    target = qualify_leaf_ref(
        segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1"
    )
    seeded = save(
        {
            "target_ref": target,
            "draft_payload": {
                "source_transcript_verbatim": "Range 7 west",
                "issues": [],
            },
        }
    )
    assert seeded["executed"] is True
    base_ref = seeded["outputs"]["working_draft_ref"]
    apply = make_dossier_apply_transcript_edits_handler(
        dossier_id=d, ref_index=bundle.ref_index, workspace_key=ws
    )
    return d, ws, base_ref, apply


def test_dossier_apply_unknown_top_level_field_refuses(tmp_path, monkeypatch) -> None:
    _d, _ws, base_ref, apply = _seed_apply_workspace(tmp_path, monkeypatch, ws="ws-unknown")
    out = apply(
        {
            "base_revision_ref": base_ref,
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
            "extra": True,
        }
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "unknown_request_fields"


def test_dossier_apply_missing_evidence_refs_matches_leaf_contract(
    tmp_path, monkeypatch
) -> None:
    _d, _ws, base_ref, apply = _seed_apply_workspace(tmp_path, monkeypatch, ws="ws-missing-ev")
    decision = {
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
    assert "evidence_refs" not in decision
    out = apply(
        {
            "base_revision_ref": base_ref,
            "decisions": [decision],
        }
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "invalid_string_list"


def test_dossier_apply_empty_evidence_refs_allows_provisional(tmp_path, monkeypatch) -> None:
    d, ws, base_ref, apply = _seed_apply_workspace(tmp_path, monkeypatch, ws="ws-empty-ev")
    out = apply(
        {
            "base_revision_ref": base_ref,
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
    assert out["executed"] is True, out
    rev = json.loads(transcript_edit_revision_path(d, "tx_a", ws, "0002").read_text(encoding="utf-8"))
    assert rev["payload"]["source_transcript_verbatim"] == "Range 77 west"


def test_dossier_non_string_evidence_refuses_without_coercion(tmp_path, monkeypatch) -> None:
    _d, ws, base_ref, apply = _seed_apply_workspace(tmp_path, monkeypatch, ws="ws-nonstr-ev")
    out = apply(
        {
            "base_revision_ref": base_ref,
            "decisions": [
                {
                    "decision_id": "d1",
                    "determination": "provisional",
                    "verification_basis": "ok",
                    "evidence_refs": [123],
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
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "dossier_ref_invalid"
    assert not transcript_edit_revision_path(_d, "tx_a", ws, "0002").exists()
