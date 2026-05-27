"""Tests for descriptor-backed image link resolution in audit timelines."""

from __future__ import annotations

import json
from pathlib import Path

import config.paths as paths_mod

from harness.audit.artifact_ref_links import ArtifactLinkContext, build_run_ref_path_index
from harness.audit.human_timeline import render_timeline
from harness.audit.point_crop_set_timeline import render_point_crop_set_tool_output


def _realistic_point_crops_outputs(*, master_ref: str, crop_ref: str) -> dict:
    return {
        "derived_ref_id": master_ref,
        "parent_ref_id": "image:assoc:tx-1:original",
        "sub_action": "point_crops",
        "basename": f"{master_ref.split(':')[-1]}.png",
        "width_height": [640, 480],
        "crop_set": {
            "master_overlay_ref": master_ref,
            "source_ref": "image:assoc:tx-1:original",
            "points": [
                {
                    "letter": "A",
                    "alias": "parcel_1_tie_bearing",
                    "crop_ref": crop_ref,
                    "point_norm": [0.42, 0.58],
                    "size": "medium",
                    "shape": "wide",
                    "zoom_factor": 2.25,
                }
            ],
        },
        "crop_records": [
            {
                "letter": "A",
                "alias": "parcel_1_tie_bearing",
                "crop_ref": crop_ref,
                "point_norm": [0.42, 0.58],
                "size": "medium",
                "shape": "wide",
                "zoom_factor": 2.25,
            }
        ],
    }


def _write_derived_descriptor(
    derived_dir: Path,
    *,
    ref_id: str,
    absolute_path: Path,
    sub_action: str = "point_crops",
) -> None:
    uuid = ref_id.removeprefix("image:derived:")
    descriptor = {
        "ref_id": ref_id,
        "parent_ref_id": "image:assoc:tx-1:original",
        "sub_action": sub_action,
        "absolute_path": str(absolute_path.resolve()),
        "basename": absolute_path.name,
    }
    (derived_dir / f"{uuid}.json").write_text(json.dumps(descriptor), encoding="utf-8")


def test_point_crop_links_resolve_from_derived_image_descriptors(tmp_path: Path, monkeypatch) -> None:
    run_id = "practice-row-descriptor-test"
    dossier_id = "d1"
    transcription_id = "tx-1"

    te_root = tmp_path / "artifacts" / "transcript_edit"
    derived_dir = te_root / dossier_id / transcription_id / run_id / "derived_images"
    derived_dir.mkdir(parents=True)

    master_ref = "image:derived:master-uuid-001"
    crop_ref = "image:derived:crop-uuid-001"
    master_png = derived_dir / "master-uuid-001.png"
    crop_png = derived_dir / "crop-uuid-001.png"
    master_png.write_bytes(b"png")
    crop_png.write_bytes(b"png")

    _write_derived_descriptor(derived_dir, ref_id=master_ref, absolute_path=master_png)
    _write_derived_descriptor(derived_dir, ref_id=crop_ref, absolute_path=crop_png, sub_action="point_crops_crop")

    monkeypatch.setattr(paths_mod, "dossiers_transcript_edit_artifacts_root", lambda dossier_id=None: te_root)

    run_dir = tmp_path / "cli_runs" / run_id
    audit_dir = run_dir / "audit"
    audit_dir.mkdir(parents=True)
    (audit_dir / "index.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")

    outputs = _realistic_point_crops_outputs(master_ref=master_ref, crop_ref=crop_ref)
    turn = {
        "turn_index": 2,
        "parse_ok": True,
        "run_id": run_id,
        "tool_result_raw": {
            "execution_state": "executed",
            "artifact_refs": [master_ref, crop_ref],
            "outputs": outputs,
        },
    }

    index = build_run_ref_path_index(audit_dir=audit_dir, run_dir=run_dir, turns=[turn])
    assert index[master_ref] == str(master_png.resolve())
    assert index[crop_ref] == str(crop_png.resolve())

    timeline_path = audit_dir / "human" / "timeline.md"
    timeline_path.parent.mkdir(parents=True)
    context = ArtifactLinkContext(timeline_path=timeline_path, ref_path_index=index)
    rendered = "\n".join(render_point_crop_set_tool_output(outputs, link_context=context))

    assert "absolute_path" not in rendered
    assert "b64" not in rendered.lower()
    assert "[open overlay]" in rendered
    assert "[open crop]" in rendered
    assert "`image:derived:master-uuid-001`" in rendered
    assert "`image:derived:crop-uuid-001`" in rendered


def test_timeline_renders_descriptor_backed_point_crop_links(tmp_path: Path, monkeypatch) -> None:
    run_id = "practice-row-descriptor-timeline"
    dossier_id = "d1"
    transcription_id = "tx-1"

    te_root = tmp_path / "artifacts" / "transcript_edit"
    derived_dir = te_root / dossier_id / transcription_id / run_id / "derived_images"
    derived_dir.mkdir(parents=True)

    master_ref = "image:derived:master-uuid-002"
    crop_ref = "image:derived:crop-uuid-002"
    master_png = derived_dir / "master-uuid-002.png"
    crop_png = derived_dir / "crop-uuid-002.png"
    master_png.write_bytes(b"png")
    crop_png.write_bytes(b"png")

    _write_derived_descriptor(derived_dir, ref_id=master_ref, absolute_path=master_png)
    _write_derived_descriptor(derived_dir, ref_id=crop_ref, absolute_path=crop_png, sub_action="point_crops_crop")

    monkeypatch.setattr(paths_mod, "dossiers_transcript_edit_artifacts_root", lambda dossier_id=None: te_root)

    run_dir = tmp_path / "cli_runs" / run_id
    audit_dir = run_dir / "audit"
    audit_dir.mkdir(parents=True)
    (audit_dir / "index.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")

    outputs = _realistic_point_crops_outputs(master_ref=master_ref, crop_ref=crop_ref)
    body = render_timeline(
        [
            {
                "turn_index": 2,
                "parse_ok": True,
                "run_id": run_id,
                "tool_result_raw": {
                    "execution_state": "executed",
                    "artifact_refs": [master_ref, crop_ref],
                    "outputs": outputs,
                },
            }
        ],
        audit_dir=audit_dir,
    )

    assert "Point crop set:" in body
    assert "[open overlay]" in body
    assert "[open crop]" in body
    assert "absolute_path" not in body


def test_point_crops_view_labels_filtered_view_and_prior_overlay() -> None:
    outputs = {
        "derived_ref_id": "image:derived:filtered-view-1",
        "sub_action": "point_crops_view",
        "view_of_crop_set_overlay_ref": "image:derived:prior-master-1",
        "crop_set": {
            "master_overlay_ref": "image:derived:filtered-view-1",
            "view_of_crop_set_overlay_ref": "image:derived:prior-master-1",
            "points": [],
        },
    }
    rendered = "\n".join(render_point_crop_set_tool_output(outputs))
    assert "filtered view overlay: `image:derived:filtered-view-1`" in rendered
    assert "view_of_crop_set_overlay_ref: `image:derived:prior-master-1`" in rendered
    assert "- view overlay:" not in rendered
    assert "- master overlay:" not in rendered
