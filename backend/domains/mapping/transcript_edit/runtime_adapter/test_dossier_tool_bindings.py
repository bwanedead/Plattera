"""Tests for unwired dossier transcript-edit runtime tool bindings."""

from __future__ import annotations

import json
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import config.paths as paths_mod
import pytest
import tooling.mapping.transcript_edit.paths as te_paths
from PIL import Image

from domains.mapping.transcript_edit.execution.tool_specs import build_transcript_edit_tool_specs
from domains.mapping.transcript_edit.payloads.dossier_startup_inventory import (
    DossierTranscriptRunInventory,
    DossierTranscriptSegmentInventory,
)
from domains.mapping.transcript_edit.payloads.startup_inventory import (
    SourceImageRefDescriptor,
    T0DraftDescriptor,
    TranscriptEditDraftInventory,
    TranscriptEditScope,
    TranscriptEditStartupInventory,
)
from domains.mapping.transcript_edit.runtime_adapter.composition import (
    build_transcript_edit_tool_bindings,
)
from domains.mapping.transcript_edit.runtime_adapter.dossier_tool_bindings import (
    DossierRuntimeBindingError,
    build_dossier_transcript_edit_tool_bindings,
)
from harness.execution.contracts import ExecutionStepRequest
from services.dossier.segment_topology import TopologyRunInput, TopologySegmentInput
from tooling.mapping.transcript_edit.dossier_artifact_refs import qualify_leaf_ref
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    DossierStartupInventoryBundle,
    build_dossier_transcript_edit_startup_inventory_from_segments,
)
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


def _tiny_png_bytes() -> bytes:
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
    (assoc_dir / f"assoc_{dossier_id}.json").write_text(json.dumps(payload), encoding="utf-8")


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


def _two_segment_bundle(tmp_path, monkeypatch, *, workspace_id: str = "ws-bind"):
    root = _dossiers_root(tmp_path)
    _patch_roots(monkeypatch, root)
    d = "d1"
    _minimal_run_layout(root, d, "tx_a")
    _minimal_run_layout(root, d, "tx_b")
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
    return root, d, workspace_id, bundle


def _binding(bindings, tool_id: str):
    return next(b for b in bindings if b.tool_id == tool_id).handler


def _assert_path_free(result: dict) -> None:
    blob = json.dumps(result)
    assert ":\\" not in blob
    assert "AppData" not in blob
    assert "workspace_root" not in blob
    assert "complete_run" not in blob
    assert "image_b64" not in blob


def test_binding_ids_match_manifest_order(tmp_path, monkeypatch) -> None:
    _, _, _, bundle = _two_segment_bundle(tmp_path, monkeypatch)
    bindings = build_dossier_transcript_edit_tool_bindings(bundle=bundle)
    assert [b.tool_id for b in bindings] == [s.tool_id for s in build_transcript_edit_tool_specs()]


def test_missing_workspace_refuses_composition(tmp_path, monkeypatch) -> None:
    _, _, _, bundle = _two_segment_bundle(tmp_path, monkeypatch)
    bad_scope = replace(bundle.inventory.scope, workspace_id=None, run_id=None)
    bad_inventory = replace(bundle.inventory, scope=bad_scope)
    bad_bundle = DossierStartupInventoryBundle(
        inventory=bad_inventory, ref_index=bundle.ref_index
    )
    with pytest.raises(DossierRuntimeBindingError) as exc:
        build_dossier_transcript_edit_tool_bindings(bundle=bad_bundle)
    assert exc.value.code == "dossier_runtime_workspace_required"


def test_dossier_topology_run_mismatches_refuse_composition(tmp_path, monkeypatch) -> None:
    _, _, _, bundle = _two_segment_bundle(tmp_path, monkeypatch)

    dossier_mismatch = DossierStartupInventoryBundle(
        inventory=replace(
            bundle.inventory,
            scope=replace(bundle.inventory.scope, dossier_id="other"),
        ),
        ref_index=bundle.ref_index,
    )
    with pytest.raises(DossierRuntimeBindingError) as exc:
        build_dossier_transcript_edit_tool_bindings(bundle=dossier_mismatch)
    assert exc.value.code == "dossier_runtime_dossier_mismatch"

    topo_mismatch = DossierStartupInventoryBundle(
        inventory=replace(bundle.inventory, topology_fingerprint="not-matching"),
        ref_index=bundle.ref_index,
    )
    with pytest.raises(DossierRuntimeBindingError) as exc:
        build_dossier_transcript_edit_tool_bindings(bundle=topo_mismatch)
    assert exc.value.code == "dossier_runtime_topology_mismatch"

    phantom = DossierTranscriptSegmentInventory(
        segment_id="seg_x",
        position=99,
        previous_segment_id=None,
        next_segment_id=None,
        runs=(
            DossierTranscriptRunInventory(
                transcription_id="tx_x",
                position=0,
                source_image_refs=(),
                t0_draft_refs=(),
                working_draft_ref=None,
                working_latest_revision_ref=None,
                output_draft_ref=None,
                artifact_fingerprint=None,
                missing_resources=(),
            ),
        ),
    )
    run_mismatch = DossierStartupInventoryBundle(
        inventory=replace(
            bundle.inventory,
            segments=bundle.inventory.segments + (phantom,),
            segment_count=bundle.inventory.segment_count + 1,
        ),
        ref_index=bundle.ref_index,
    )
    with pytest.raises(DossierRuntimeBindingError) as exc:
        build_dossier_transcript_edit_tool_bindings(bundle=run_mismatch)
    assert exc.value.code == "dossier_runtime_run_binding_mismatch"


def test_hydrate_two_segments_with_result_view(tmp_path, monkeypatch) -> None:
    _, _, _, bundle = _two_segment_bundle(tmp_path, monkeypatch)
    bindings = build_dossier_transcript_edit_tool_bindings(bundle=bundle)
    hydrate = _binding(bindings, "hydrate_artifact_refs")
    refs = [
        qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1"),
        qualify_leaf_ref(segment_id="seg_b", transcription_id="tx_b", leaf_ref="t0:raw:draft_1"),
    ]
    result = hydrate(
        ExecutionStepRequest(
            session_id="s1",
            action_id="hydrate_artifact_refs",
            inputs={"ref_ids": refs, "max_refs": 8},
        )
    )
    assert result["executed"] is True
    assert "agent_result_view" in result
    assert len(result["outputs"]["results"]) == 2
    _assert_path_free(result)


def test_transform_routes_and_gets_transform_view(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    _patch_roots(monkeypatch, root)
    d, ws = "d1", "ws-xf"
    _minimal_run_layout(root, d, "tx_a")
    img = tmp_path / "images" / "scan.png"
    img.parent.mkdir(parents=True)
    img.write_bytes(_tiny_png_bytes())
    _write_association(root, d, "tx_a", img)

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
    bindings = build_dossier_transcript_edit_tool_bindings(bundle=bundle)
    transform = _binding(bindings, "transform_artifact")
    source = qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="image:assoc:tx_a:original",
    )
    result = transform(
        ExecutionStepRequest(
            session_id="s1",
            action_id="transform_artifact",
            inputs={
                "ref_id": source,
                "sub_action": "crop",
                "params": {"box_norm": [0.0, 0.0, 1.0, 1.0]},
            },
        )
    )
    assert result["executed"] is True
    assert "agent_result_view" in result
    derived = result["outputs"]["derived_ref_id"]
    assert derived.startswith("dossier_segment:seg_a:run:tx_a:image:derived:")
    _assert_path_free(result)


def test_save_and_later_base_revision(tmp_path, monkeypatch) -> None:
    _, d, ws, bundle = _two_segment_bundle(tmp_path, monkeypatch)
    bindings = build_dossier_transcript_edit_tool_bindings(bundle=bundle)
    save = _binding(bindings, "save_workspace_artifact")
    target = qualify_leaf_ref(
        segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1"
    )
    first = save(
        ExecutionStepRequest(
            session_id="s1",
            action_id="save_workspace_artifact",
            inputs={
                "target_ref": target,
                "draft_payload": {
                    "source_transcript_verbatim": "ALPHA",
                    "normalized_or_mapping_transcript": "AN",
                },
            },
        )
    )
    assert first["executed"] is True
    assert first["outputs"]["working_draft_ref"].startswith("dossier_segment:seg_a:")
    base = first["outputs"]["working_draft_ref"]
    second = save(
        {
            "base_revision_ref": base,
            "draft_payload": {
                "source_transcript_verbatim": "ALPHA-2",
                "normalized_or_mapping_transcript": "AN-2",
            },
        }
    )
    assert second["executed"] is True
    assert second["outputs"]["working_draft_ref"].endswith("rev:0002")
    _assert_path_free(first)
    _assert_path_free(second)
    assert d and ws


def test_copy_forward_and_cross_segment_mismatch(tmp_path, monkeypatch) -> None:
    _, _, _, bundle = _two_segment_bundle(tmp_path, monkeypatch)
    bindings = build_dossier_transcript_edit_tool_bindings(bundle=bundle)
    save = _binding(bindings, "save_workspace_artifact")
    copy = _binding(bindings, "copy_forward_save_workspace_artifact")
    target_a = qualify_leaf_ref(
        segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1"
    )
    first = save(
        {
            "target_ref": target_a,
            "draft_payload": {"transcript": "base", "flags": {"keep": True}},
        }
    )
    assert first["executed"] is True
    base = first["outputs"]["working_draft_ref"]
    ok = copy(
        ExecutionStepRequest(
            session_id="s1",
            action_id="copy_forward_save_workspace_artifact",
            inputs={
                "base_ref": base,
                "copy_forward_paths": ["payload.flags.keep"],
                "set_paths": {"payload.transcript": "copied"},
            },
        )
    )
    assert ok["executed"] is True
    assert ok["segment_id"] == "seg_a"
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


def test_publish_requires_plural_and_publishes_output(tmp_path, monkeypatch) -> None:
    root, d, ws, bundle = _two_segment_bundle(tmp_path, monkeypatch)
    bindings = build_dossier_transcript_edit_tool_bindings(bundle=bundle)
    save = _binding(bindings, "save_workspace_artifact")
    publish = _binding(bindings, "publish_workspace_artifact")

    singular = publish(
        ExecutionStepRequest(
            session_id="s1",
            action_id="publish_workspace_artifact",
            inputs={"source_revision_ref": "transcript_edit:working:rev:0001"},
        )
    )
    assert singular["executed"] is False
    assert singular["refusal"]["reason_code"] == "source_revision_refs_required"
    assert singular["refusal"]["retryable"] is True
    assert singular["refusal"]["blocked_by_invariant"] is False

    refs = []
    for sid, tid, text in (("seg_a", "tx_a", "A"), ("seg_b", "tx_b", "B")):
        out = save(
            {
                "target_ref": qualify_leaf_ref(
                    segment_id=sid, transcription_id=tid, leaf_ref="t0:raw:draft_1"
                ),
                "draft_payload": {
                    "source_transcript_verbatim": text,
                    "normalized_or_mapping_transcript": f"{text}N",
                },
            }
        )
        assert out["executed"] is True
        refs.append(out["outputs"]["working_draft_ref"])

    incomplete = publish({"source_revision_refs": refs[:1]})
    assert incomplete["executed"] is False
    assert incomplete["refusal"]["reason_code"] == "incomplete_segment_coverage"
    assert incomplete["refusal"]["retryable"] is True
    assert incomplete["refusal"]["blocked_by_invariant"] is False

    conflict = publish({"source_revision_refs": [refs[0], refs[0]]})
    assert conflict["executed"] is False
    assert conflict["refusal"]["reason_code"] == "duplicate_selected_ref"
    assert conflict["refusal"]["retryable"] is True

    first = publish(
        ExecutionStepRequest(
            session_id="s1",
            action_id="publish_workspace_artifact",
            inputs={"source_revision_refs": refs},
        )
    )
    assert first["executed"] is True
    assert first["outputs"]["output_ref"] == "transcript_edit:output"
    assert first["artifact_refs"][0] == "transcript_edit:output"
    assert first["outputs"]["idempotent_replay"] is False

    replay = publish({"source_revision_refs": refs})
    assert replay["executed"] is True
    assert replay["outputs"]["idempotent_replay"] is True

    for tid in ("tx_a", "tx_b"):
        assert not transcript_edit_output_path(d, tid, ws).exists()
    _assert_path_free(first)
    _assert_path_free(replay)
    assert root is not None


def test_publish_request_shape_and_retryability(tmp_path, monkeypatch) -> None:
    _, d, ws, bundle = _two_segment_bundle(tmp_path, monkeypatch)
    bindings = build_dossier_transcript_edit_tool_bindings(bundle=bundle)
    save = _binding(bindings, "save_workspace_artifact")
    publish = _binding(bindings, "publish_workspace_artifact")

    missing = publish({})
    assert missing["refusal"]["reason_code"] == "source_revision_refs_required"
    assert missing["refusal"]["retryable"] is True
    assert missing["refusal"]["blocked_by_invariant"] is False

    for singular_inputs in (
        {"source_revision_ref": "transcript_edit:working:rev:0001"},
        {"source_revision_ref": ""},
        {"source_revision_ref": None},
        {
            "source_revision_ref": None,
            "source_revision_refs": ["dossier_segment:seg_a:run:tx_a:transcript_edit:working:rev:0001"],
        },
    ):
        refused = publish(singular_inputs)
        assert refused["executed"] is False
        assert refused["refusal"]["reason_code"] == "source_revision_refs_required"
        assert refused["refusal"]["retryable"] is True

    unknown = publish(
        {
            "source_revision_refs": [],
            "extra": True,
        }
    )
    assert unknown["executed"] is False
    assert unknown["refusal"]["reason_code"] == "invalid_publish_request"
    assert unknown["refusal"]["retryable"] is True

    non_list = publish({"source_revision_refs": "not-a-list"})
    assert non_list["refusal"]["reason_code"] == "source_revision_refs_required"
    assert non_list["refusal"]["retryable"] is True

    transport = publish("not-a-mapping")  # type: ignore[arg-type]
    assert transport["executed"] is False
    assert transport["refusal"]["reason_code"] == "invalid_request_transport"
    assert transport["refusal"]["retryable"] is False
    assert transport["refusal"]["blocked_by_invariant"] is True

    refs = []
    for sid, tid, text in (("seg_a", "tx_a", "A"), ("seg_b", "tx_b", "B")):
        out = save(
            {
                "target_ref": qualify_leaf_ref(
                    segment_id=sid, transcription_id=tid, leaf_ref="t0:raw:draft_1"
                ),
                "draft_payload": {
                    "source_transcript_verbatim": text,
                    "normalized_or_mapping_transcript": f"{text}N",
                },
            }
        )
        assert out["executed"] is True
        refs.append(out["outputs"]["working_draft_ref"])

    published = publish({"source_revision_refs": refs})
    assert published["executed"] is True
    fp = published["outputs"]["candidate_fingerprint"]

    from tooling.mapping.transcript_edit.dossier_publication_paths import (
        dossier_transcript_edit_dossier_output_latest_pointer_path,
        dossier_transcript_edit_dossier_output_revision_path,
    )

    pointer_path = dossier_transcript_edit_dossier_output_latest_pointer_path(d, ws)
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["extra_compat_field"] = "residue"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    corrupt_pointer = publish({"source_revision_refs": refs})
    assert corrupt_pointer["executed"] is False
    assert corrupt_pointer["refusal"]["reason_code"] == "dossier_publication_pointer_invalid"
    assert corrupt_pointer["refusal"]["retryable"] is False

    # Restore a coherent pointer, then corrupt the immutable revision in place.
    pointer.pop("extra_compat_field")
    pointer_path.write_text(json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rev_path = dossier_transcript_edit_dossier_output_revision_path(d, ws, fp)
    rev = json.loads(rev_path.read_text(encoding="utf-8"))
    rev["injected_state"] = True
    rev_path.write_text(json.dumps(rev), encoding="utf-8")
    corrupt_revision = publish({"source_revision_refs": refs})
    assert corrupt_revision["executed"] is False
    assert corrupt_revision["refusal"]["reason_code"] == "dossier_publication_pointer_invalid"
    assert corrupt_revision["refusal"]["retryable"] is False


def test_leaf_mode_composition_unchanged(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    _patch_roots(monkeypatch, root)
    d, tx, ws = "d-leaf", "tx-leaf", "ws-leaf"
    _minimal_run_layout(root, d, tx)
    leaf_bindings = build_transcript_edit_tool_bindings(
        dossier_id=d,
        transcription_id=tx,
        workspace_key=ws,
    )
    assert [b.tool_id for b in leaf_bindings] == [
        s.tool_id for s in build_transcript_edit_tool_specs()
    ]
    save = _binding(leaf_bindings, "save_workspace_artifact")
    result = save(
        ExecutionStepRequest(
            session_id="s1",
            action_id="save_workspace_artifact",
            inputs={
                "draft_payload": {
                    "source_transcript_verbatim": "LEAF",
                    "normalized_or_mapping_transcript": "LN",
                }
            },
        )
    )
    assert result["executed"] is True
    assert result["outputs"]["working_draft_ref"] == "transcript_edit:working:rev:0001"
    publish = _binding(leaf_bindings, "publish_workspace_artifact")
    refused = publish(
        ExecutionStepRequest(
            session_id="s1",
            action_id="publish_workspace_artifact",
            inputs={},
        )
    )
    assert refused["executed"] is False
    assert refused["refusal"]["reason_code"] == "source_revision_ref_required"
