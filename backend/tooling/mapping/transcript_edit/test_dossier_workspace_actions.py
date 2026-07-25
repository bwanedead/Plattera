"""Tests for dossier-scoped transform/save/copy-forward routing."""

from __future__ import annotations

import json
from pathlib import Path

import config.paths as paths_mod
import tooling.mapping.transcript_edit.paths as te_paths

from services.dossier.segment_topology import TopologyRunInput, TopologySegmentInput
from tooling.mapping.transcript_edit.dossier_artifact_hydration import (
    hydrate_dossier_artifact_refs,
)
from tooling.mapping.transcript_edit.dossier_artifact_refs import qualify_leaf_ref
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    build_dossier_transcript_edit_startup_inventory_from_segments,
)
from tooling.mapping.transcript_edit.dossier_workspace_actions import (
    make_dossier_copy_forward_save_workspace_artifact_handler,
    make_dossier_save_workspace_artifact_handler,
    make_dossier_transform_artifact_handler,
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


def _tiny_png_bytes() -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (8, 8), (200, 180, 160)).save(buf, format="PNG")
    return buf.getvalue()


def _write_association(root: Path, dossier_id: str, transcription_id: str, image_path: Path) -> None:
    assoc_dir = root / "associations"
    assoc_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "dossier_id": dossier_id,
        "associations": [
            {
                "transcription_id": transcription_id,
                "position": 1,
                "metadata": {
                    "images": {
                        "original_path": str(image_path),
                        "processed_path": str(image_path),
                    }
                },
            }
        ],
    }
    (assoc_dir / f"assoc_{dossier_id}.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_independent_segment_revision_lineage(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d, ws = "d1", "ws-indep"
    _minimal_run_layout(root, d, "tx_a")
    _minimal_run_layout(root, d, "tx_b")

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
                workspace_id=kwargs.get("workspace_id"),
            ),
            t0_drafts=(
                T0DraftDescriptor(
                    ref_id="t0:raw:draft_1",
                    variant_label="draft 1",
                    source_file_stem=f"{tid}_draft_1",
                ),
            ),
            transcript_edit_drafts=TranscriptEditDraftInventory(
                working_draft_exists=False,
            ),
        )

    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id=d,
        workspace_id=ws,
        segments=(
            TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),
            TopologySegmentInput("seg_b", 1, (TopologyRunInput("tx_b", 0),)),
        ),
        association_positions={"tx_a": 1, "tx_b": 2},
        leaf_inventory_builder=leaf_builder,
    )
    save = make_dossier_save_workspace_artifact_handler(
        dossier_id=d,
        ref_index=bundle.ref_index,
        workspace_key=ws,
    )
    target_a = qualify_leaf_ref(
        segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1"
    )
    target_b = qualify_leaf_ref(
        segment_id="seg_b", transcription_id="tx_b", leaf_ref="t0:raw:draft_1"
    )
    out_a = save(
        {
            "target_ref": target_a,
            "transcript_text": "segment A body",
        }
    )
    out_b = save(
        {
            "target_ref": target_b,
            "transcript_text": "segment B body",
        }
    )
    assert out_a["executed"] is True
    assert out_b["executed"] is True
    rev_a = out_a["outputs"]["working_draft_ref"]
    rev_b = out_b["outputs"]["working_draft_ref"]
    assert rev_a.endswith("transcript_edit:working:rev:0001")
    assert rev_b.endswith("transcript_edit:working:rev:0001")
    assert rev_a != rev_b
    assert "seg_a" in rev_a and "tx_a" in rev_a
    assert "seg_b" in rev_b and "tx_b" in rev_b
    assert out_a["segment_id"] == "seg_a"
    assert out_b["segment_id"] == "seg_b"
    for ref in out_a["artifact_refs"]:
        bundle.ref_index.resolve(str(ref))
    for ref in out_b["artifact_refs"]:
        bundle.ref_index.resolve(str(ref))
    agg_a = out_a["outputs"]["aggregate_working_ref"]
    assert agg_a.endswith("transcript_edit:working")
    bundle.ref_index.resolve(agg_a)

    path_a = transcript_edit_revision_path(d, "tx_a", ws, "0001")
    path_b = transcript_edit_revision_path(d, "tx_b", ws, "0001")
    assert path_a.is_file() and path_b.is_file()
    body_a = json.loads(path_a.read_text(encoding="utf-8"))["payload"]["transcript"]
    body_b = json.loads(path_b.read_text(encoding="utf-8"))["payload"]["transcript"]
    assert body_a == "segment A body"
    assert body_b == "segment B body"

    hydrated = hydrate_dossier_artifact_refs(
        dossier_id=d,
        ref_index=bundle.ref_index,
        ref_ids=[rev_a, rev_b, agg_a],
        workspace_key=ws,
        max_refs=8,
    )
    assert hydrated["executed"] is True
    by_ref = {r["ref_id"]: r for r in hydrated["outputs"]["results"]}
    assert rev_a in by_ref and rev_b in by_ref and agg_a in by_ref
    assert by_ref[rev_a]["transcription_id"] == "tx_a"
    assert by_ref[rev_b]["transcription_id"] == "tx_b"


def test_save_target_and_base_lineage_rules(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d, ws = "d1", "ws-save"
    _minimal_run_layout(root, d, "tx_a")
    _minimal_run_layout(root, d, "tx_b")

    from domains.mapping.transcript_edit.payloads.startup_inventory import (
        SourceImageRefDescriptor,
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
            source_images=(
                SourceImageRefDescriptor(
                    ref_id=f"image:assoc:{tid}:original",
                    role="source_original",
                    basename=f"{tid}.png",
                ),
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
        segments=(
            TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),
            TopologySegmentInput("seg_b", 1, (TopologyRunInput("tx_b", 0),)),
        ),
        association_positions={"tx_a": 1, "tx_b": 2},
        leaf_inventory_builder=leaf_builder,
    )
    save = make_dossier_save_workspace_artifact_handler(
        dossier_id=d, ref_index=bundle.ref_index, workspace_key=ws
    )
    target_a = qualify_leaf_ref(
        segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1"
    )
    target_b = qualify_leaf_ref(
        segment_id="seg_b", transcription_id="tx_b", leaf_ref="image:assoc:tx_b:original"
    )
    first = save({"target_ref": target_a, "transcript_text": "v1"})
    assert first["executed"] is True
    base_a = first["outputs"]["working_draft_ref"]
    assert all(str(r).startswith("dossier_segment:") for r in first["artifact_refs"])

    second = save(
        {
            "base_revision_ref": base_a,
            "transcript_text": "v2",
        }
    )
    assert second["executed"] is True
    assert second["outputs"]["working_draft_ref"].endswith("rev:0002")
    assert second["segment_id"] == "seg_a"

    matched = save(
        {
            "target_ref": target_a,
            "base_revision_ref": second["outputs"]["working_draft_ref"],
            "transcript_text": "v3",
        }
    )
    assert matched["executed"] is True

    cross = save(
        {
            "target_ref": target_b,
            "base_revision_ref": base_a,
            "transcript_text": "nope",
        }
    )
    assert cross["executed"] is False
    assert cross["refusal"]["reason_code"] == "dossier_target_lineage_mismatch"
    assert not transcript_edit_revision_path(d, "tx_b", ws, "0001").exists()

    cross_evidence = qualify_leaf_ref(
        segment_id="seg_b",
        transcription_id="tx_b",
        leaf_ref="image:assoc:tx_b:original",
    )
    with_evidence = save(
        {
            "target_ref": target_a,
            "transcript_text": "with evidence",
            "evidence_refs": [cross_evidence],
        }
    )
    assert with_evidence["executed"] is True
    assert cross_evidence in with_evidence["outputs"]["evidence_refs"]

    foreign_unqualified = save(
        {
            "target_ref": target_a,
            "transcript_text": "foreign evidence",
            "evidence_refs": ["image:assoc:tx_b:original"],
        }
    )
    assert foreign_unqualified["executed"] is True
    assert foreign_unqualified["outputs"]["evidence_refs"][0] == cross_evidence

    unknown_assoc_leaf = save(
        {
            "target_ref": target_a,
            "transcript_text": "unknown assoc leaf",
            "evidence_refs": ["image:assoc:tx_a:not_a_real_role"],
        }
    )
    assert unknown_assoc_leaf["executed"] is False
    assert unknown_assoc_leaf["refusal"]["reason_code"] in {
        "dossier_ref_kind_not_runtime_resolvable",
        "unknown_ref",
        "dossier_ref_invalid",
    }
    assert not transcript_edit_revision_path(d, "tx_a", ws, "9998").exists()

    opaque_t0 = save(
        {
            "target_ref": target_a,
            "transcript_text": "opaque t0",
            "evidence_refs": ["t0:raw:draft_1"],
        }
    )
    assert opaque_t0["executed"] is False
    assert opaque_t0["refusal"]["reason_code"] == "dossier_ref_required"

    opaque_derived = save(
        {
            "target_ref": target_a,
            "transcript_text": "opaque derived",
            "evidence_refs": ["image:derived:abcdef0123456789abcdef0123456789"],
        }
    )
    assert opaque_derived["executed"] is False
    assert opaque_derived["refusal"]["reason_code"] == "dossier_ref_required"

    unknown_assoc = save(
        {
            "target_ref": target_a,
            "transcript_text": "unknown evidence",
            "evidence_refs": ["image:assoc:tx_missing:original"],
        }
    )
    assert unknown_assoc["executed"] is False
    assert unknown_assoc["refusal"]["reason_code"] == "dossier_ref_run_not_in_topology"

    missing_base = save(
        {
            "target_ref": target_a,
            "base_revision_ref": qualify_leaf_ref(
                segment_id="seg_a",
                transcription_id="tx_a",
                leaf_ref="transcript_edit:working:rev:9999",
            ),
            "transcript_text": "should refuse",
        }
    )
    assert missing_base["executed"] is False
    assert missing_base["refusal"]["reason_code"] == "dossier_base_revision_not_found"
    assert not transcript_edit_revision_path(d, "tx_a", ws, "9999").exists()

    # Base exists under tx_a but cannot satisfy a save targeting tx_b.
    cross_base = save(
        {
            "target_ref": target_b,
            "base_revision_ref": base_a,
            "transcript_text": "cross",
        }
    )
    assert cross_base["executed"] is False
    assert cross_base["refusal"]["reason_code"] == "dossier_target_lineage_mismatch"

    # Existing base under another workspace does not satisfy this workspace.
    # Use tx_b artifacts that exist only under ws-other.
    other_ws_save = make_dossier_save_workspace_artifact_handler(
        dossier_id=d, ref_index=bundle.ref_index, workspace_key="ws-other"
    )
    other_first = other_ws_save({"target_ref": target_b, "transcript_text": "other-ws-only"})
    assert other_first["executed"] is True
    other_base = other_first["outputs"]["working_draft_ref"]
    wrong_ws = save(
        {
            "base_revision_ref": other_base,
            "transcript_text": "wrong workspace",
        }
    )
    assert wrong_ws["executed"] is False
    assert wrong_ws["refusal"]["reason_code"] == "dossier_base_revision_not_found"


def test_copy_forward_routes_and_qualifies(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d, ws = "d1", "ws-copy"
    _minimal_run_layout(root, d, "tx_a")
    _minimal_run_layout(root, d, "tx_b")

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
                dossier_id=d,
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
        segments=(
            TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),
            TopologySegmentInput("seg_b", 1, (TopologyRunInput("tx_b", 0),)),
        ),
        association_positions={"tx_a": 1, "tx_b": 2},
        leaf_inventory_builder=leaf_builder,
    )
    save = make_dossier_save_workspace_artifact_handler(
        dossier_id=d, ref_index=bundle.ref_index, workspace_key=ws
    )
    copy = make_dossier_copy_forward_save_workspace_artifact_handler(
        dossier_id=d, ref_index=bundle.ref_index, workspace_key=ws
    )
    target_a = qualify_leaf_ref(
        segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1"
    )
    first = save(
        {
            "target_ref": target_a,
            "draft_payload": {"transcript": "base", "flags": {"keep": True, "flip": False}},
        }
    )
    assert first["executed"] is True
    base = first["outputs"]["working_draft_ref"]
    out = copy(
        {
            "base_ref": base,
            "copy_forward_paths": ["payload.flags.keep"],
            "set_paths": {"payload.transcript": "copied-forward"},
        }
    )
    assert out["executed"] is True
    assert out["segment_id"] == "seg_a"
    assert out["outputs"]["working_draft_ref"].endswith("rev:0002")
    assert all(str(r).startswith("dossier_segment:seg_a:") for r in out["artifact_refs"])

    mismatch = copy(
        {
            "base_ref": base,
            "target_ref": qualify_leaf_ref(
                segment_id="seg_b", transcription_id="tx_b", leaf_ref="t0:raw:draft_1"
            ),
            "copy_forward_paths": ["payload.flags.keep"],
            "set_paths": {"payload.transcript": "bad"},
        }
    )
    assert mismatch["executed"] is False
    assert mismatch["refusal"]["reason_code"] == "dossier_target_lineage_mismatch"


def test_transform_qualifies_derived_and_hydrates_immediately(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d, ws = "d1", "ws-xf"
    _minimal_run_layout(root, d, "tx_a")
    img = tmp_path / "images" / "scan.png"
    img.parent.mkdir(parents=True)
    img.write_bytes(_tiny_png_bytes())
    _write_association(root, d, "tx_a", img)

    from domains.mapping.transcript_edit.payloads.startup_inventory import (
        SourceImageRefDescriptor,
        TranscriptEditDraftInventory,
        TranscriptEditScope,
        TranscriptEditStartupInventory,
    )

    def leaf_builder(**kwargs):
        tid = kwargs["transcription_id"]
        return TranscriptEditStartupInventory(
            scope=TranscriptEditScope(
                dossier_id=d,
                transcription_id=tid,
                segment_id=kwargs.get("segment_id"),
                workspace_id=ws,
            ),
            source_images=(
                SourceImageRefDescriptor(
                    ref_id=f"image:assoc:{tid}:original",
                    role="source_original",
                    basename="scan.png",
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
    transform = make_dossier_transform_artifact_handler(
        dossier_id=d, ref_index=bundle.ref_index, workspace_key=ws
    )
    source = qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="image:assoc:tx_a:original",
    )
    # Capture leaf result via a thin spy by wrapping factory internals is hard;
    # assert dossier projection properties and immediate hydration instead.
    out = transform(
        {
            "ref_id": source,
            "sub_action": "crop",
            "params": {"box_norm": [0.0, 0.0, 1.0, 1.0]},
        }
    )
    assert out["executed"] is True
    derived = out["outputs"]["derived_ref_id"]
    assert derived.startswith("dossier_segment:seg_a:run:tx_a:image:derived:")
    assert out["segment_id"] == "seg_a"
    assert out["transcription_id"] == "tx_a"
    assert all(str(r).startswith("dossier_segment:") for r in out["artifact_refs"])
    for ref in out["artifact_refs"]:
        bundle.ref_index.resolve(str(ref))
    assert "absolute_path" not in out.get("outputs", {})
    assert "path" not in out.get("outputs", {})
    if "image_evidence" in out:
        ev = out["image_evidence"][0]
        assert ev["ref_id"] == derived
        assert "bytes" in ev or "image_b64" in ev or "b64" in ev

    hydrated = hydrate_dossier_artifact_refs(
        dossier_id=d,
        ref_index=bundle.ref_index,
        ref_ids=[derived],
        workspace_key=ws,
        max_refs=8,
    )
    assert hydrated["executed"] is True
    assert any(r.get("ref_id") == derived for r in hydrated["outputs"]["results"])

    img.unlink()
    missing = transform(
        {
            "ref_id": source,
            "sub_action": "crop",
            "params": {"box_norm": [0.0, 0.0, 1.0, 1.0]},
        }
    )
    assert missing["executed"] is False
    blob = str(missing)
    assert "AppData" not in blob
    assert r"C:\Users" not in blob
    assert missing["segment_id"] == "seg_a"
    err = missing["outputs"]["error"]
    assert isinstance(err, dict)
    assert "code" in err
    for key, value in missing.items():
        if key.endswith("_ref") and isinstance(value, str):
            assert value.startswith("dossier_segment:")


def test_transform_invalid_params_keeps_repair_hint(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d, ws = "d1", "ws-params"
    _minimal_run_layout(root, d, "tx_a")
    img = tmp_path / "images" / "scan.png"
    img.parent.mkdir(parents=True)
    img.write_bytes(_tiny_png_bytes())
    _write_association(root, d, "tx_a", img)

    from domains.mapping.transcript_edit.payloads.startup_inventory import (
        SourceImageRefDescriptor,
        TranscriptEditDraftInventory,
        TranscriptEditScope,
        TranscriptEditStartupInventory,
    )

    def leaf_builder(**kwargs):
        tid = kwargs["transcription_id"]
        return TranscriptEditStartupInventory(
            scope=TranscriptEditScope(
                dossier_id=d,
                transcription_id=tid,
                segment_id=kwargs.get("segment_id"),
                workspace_id=ws,
            ),
            source_images=(
                SourceImageRefDescriptor(
                    ref_id=f"image:assoc:{tid}:original",
                    role="source_original",
                    basename="scan.png",
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
    transform = make_dossier_transform_artifact_handler(
        dossier_id=d, ref_index=bundle.ref_index, workspace_key=ws
    )
    source = qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="image:assoc:tx_a:original",
    )
    out = transform({"ref_id": source, "sub_action": "crop", "params": {}})
    assert out["executed"] is False
    assert out["refusal"]["retryable"] is True
    assert "box" in (out["outputs"]["error"].get("repair_hint") or "").lower() or "box" in (
        out["outputs"]["error"].get("message") or ""
    ).lower()
    assert r"C:\Users" not in str(out)


def test_restart_rebuild_recovers_latest_exact_revision(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d, ws = "d1", "ws-restart"
    _minimal_run_layout(root, d, "tx_a")

    from domains.mapping.transcript_edit.payloads.startup_inventory import (
        T0DraftDescriptor,
        TranscriptEditDraftInventory,
        TranscriptEditScope,
        TranscriptEditStartupInventory,
    )
    from tooling.mapping.transcript_edit.startup_inventory import (
        build_transcript_edit_startup_inventory,
    )

    def leaf_before(**kwargs):
        tid = kwargs["transcription_id"]
        return TranscriptEditStartupInventory(
            scope=TranscriptEditScope(
                dossier_id=d,
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

    segments = (TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),)
    assoc = {"tx_a": 1}
    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id=d,
        workspace_id=ws,
        segments=segments,
        association_positions=assoc,
        leaf_inventory_builder=leaf_before,
    )
    save = make_dossier_save_workspace_artifact_handler(
        dossier_id=d, ref_index=bundle.ref_index, workspace_key=ws
    )
    target = qualify_leaf_ref(
        segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1"
    )
    saved = save({"target_ref": target, "transcript_text": "persisted"})
    assert saved["executed"] is True
    saved_rev = saved["outputs"]["working_draft_ref"]

    rebuilt = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id=d,
        workspace_id=ws,
        segments=segments,
        association_positions=assoc,
        leaf_inventory_builder=build_transcript_edit_startup_inventory,
    )
    run = rebuilt.inventory.segments[0].runs[0]
    assert run.working_draft_ref is not None
    assert run.working_latest_revision_ref == saved_rev
    assert saved_rev in rebuilt.ref_index.by_ref

    copy = make_dossier_copy_forward_save_workspace_artifact_handler(
        dossier_id=d, ref_index=rebuilt.ref_index, workspace_key=ws
    )
    copied = copy(
        {
            "base_ref": run.working_latest_revision_ref,
            "copy_forward_paths": ["payload.transcript"],
            "set_paths": {"payload.note": "after-restart"},
        }
    )
    assert copied["executed"] is True

    hydrated = hydrate_dossier_artifact_refs(
        dossier_id=d,
        ref_index=rebuilt.ref_index,
        ref_ids=[run.working_latest_revision_ref],
        workspace_key=ws,
        max_refs=8,
    )
    assert hydrated["executed"] is True
    assert hydrated["outputs"]["results"]


def test_unqualified_ref_refused_before_write(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)
    d, ws = "d1", "ws-refuse"
    _minimal_run_layout(root, d, "tx_a")
    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id=d,
        workspace_id=ws,
        segments=(TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),),
        association_positions={"tx_a": 1},
    )
    save = make_dossier_save_workspace_artifact_handler(
        dossier_id=d, ref_index=bundle.ref_index, workspace_key=ws
    )
    out = save({"target_ref": "transcript_edit:working", "transcript_text": "x"})
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "dossier_ref_required"
    assert not transcript_edit_revision_path(d, "tx_a", ws, "0001").exists()
