"""STORAGE-BR-008: hydration and chained-transform reconstruction fallback."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

import config.paths as paths_mod
import tooling.mapping.transcript_edit.paths as te_paths_mod
from tooling.mapping.transcript_edit.artifact_hydration import make_hydrate_artifact_refs_handler
from tooling.mapping.transcript_edit.artifact_transform import make_transform_artifact_handler
from tooling.mapping.transcript_edit.derived_image_rendering import compute_image_identity
from tooling.mapping.transcript_edit.dossier_artifact_hydration import hydrate_dossier_artifact_refs
from tooling.mapping.transcript_edit.dossier_artifact_refs import qualify_leaf_ref
from tooling.mapping.transcript_edit.transform_source_image import (
    REASON_SOURCE_CONTENT_IDENTITY_UNAVAILABLE,
)


def _dossiers_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _tiny_png_bytes(width: int = 100, height: int = 80, color=(200, 200, 200)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _write_association(root: Path, dossier_id: str, transcription_id: str, image_path: Path) -> None:
    assoc_dir = root / "associations"
    assoc_dir.mkdir(parents=True, exist_ok=True)
    (assoc_dir / f"assoc_{dossier_id}.json").write_text(
        json.dumps(
            {
                "associations": [
                    {
                        "transcription_id": transcription_id,
                        "metadata": {
                            "images": {
                                "original_path": str(image_path),
                                "processed_path": str(image_path),
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _make_handlers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_file = img_dir / "scan.png"
    img_file.write_bytes(_tiny_png_bytes())
    _write_association(root, "d1", "tx-1", img_file)
    transform = make_transform_artifact_handler(
        dossier_id="d1", transcription_id="tx-1", workspace_key="ws-1"
    )
    hydrate = make_hydrate_artifact_refs_handler(
        dossier_id="d1", transcription_id="tx-1", workspace_key="ws-1"
    )
    return transform, hydrate, root, "image:assoc:tx-1:original"


def _derived_dir(root: Path) -> Path:
    return root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "derived_images"


def _snapshot_tree(root: Path) -> dict[str, tuple[int, int, str]]:
    out: dict[str, tuple[int, int, str]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            rel = path.relative_to(root).as_posix()
            out[rel] = (path.stat().st_mtime_ns, len(data), hashlib.sha256(data).hexdigest())
    return out


def _unlink_png(root: Path, ref_id: str) -> None:
    uid = ref_id.removeprefix("image:derived:")
    png = _derived_dir(root) / f"{uid}.png"
    assert png.is_file()
    png.unlink()


def _load_desc(root: Path, ref_id: str) -> dict[str, Any]:
    uid = ref_id.removeprefix("image:derived:")
    return json.loads((_derived_dir(root) / f"{uid}.json").read_text(encoding="utf-8"))


def _write_desc(root: Path, ref_id: str, desc: dict[str, Any]) -> None:
    uid = ref_id.removeprefix("image:derived:")
    (_derived_dir(root) / f"{uid}.json").write_text(
        json.dumps(desc, sort_keys=True), encoding="utf-8"
    )


def test_stored_derived_hydration_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, hydrate, root, assoc = _make_handlers(tmp_path, monkeypatch)
    result = transform(
        {"ref_id": assoc, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    assert result["executed"] is True, result
    derived = result["outputs"]["derived_ref_id"]
    png = _derived_dir(root) / f"{derived.removeprefix('image:derived:')}.png"
    file_bytes = png.read_bytes()
    hydrated = hydrate({"ref_ids": [derived]})
    assert hydrated["executed"] is True
    evidence = hydrated.get("image_evidence") or []
    assert len(evidence) == 1
    assert evidence[0]["ref_id"] == derived
    assert base64.b64decode(evidence[0]["b64"]) == file_bytes
    assert evidence[0]["representation_kind"] == "stored_bytes"
    assert evidence[0]["content_identity_posture"] == "stored_bytes_verified"
    rows = hydrated["outputs"]["results"]
    assert len(rows) == 1
    assert rows[0]["representation_kind"] == "stored_bytes"
    assert rows[0]["content_identity_posture"] == "stored_bytes_verified"
    assert rows[0]["source_identity_posture"] == "content_and_pixel_verified"
    assert rows[0]["lineage_depth"] == 0
    assert hydrated["outputs"]["hydrated_count"] == 1


def test_missing_generic_png_hydrates_reconstructed_evidence_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, hydrate, root, assoc = _make_handlers(tmp_path, monkeypatch)
    result = transform(
        {"ref_id": assoc, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    _unlink_png(root, derived)
    before = _snapshot_tree(root)
    hydrated = hydrate({"ref_ids": [derived]})
    assert hydrated["executed"] is True
    assert not hydrated["outputs"]["errors"]
    evidence = hydrated.get("image_evidence") or []
    assert len(evidence) == 1
    assert evidence[0]["ref_id"] == derived
    assert evidence[0]["representation_kind"] == "reconstructed_recipe"
    assert evidence[0]["content_identity_posture"] == "persisted_descriptor_coordinate"
    assert evidence[0]["b64"]
    row = hydrated["outputs"]["results"][0]
    assert row["representation_kind"] == "reconstructed_recipe"
    assert row["content_identity_posture"] == "persisted_descriptor_coordinate"
    assert row["lineage_depth"] == 1
    assert _snapshot_tree(root) == before
    assert not (_derived_dir(root) / f"{derived.removeprefix('image:derived:')}.png").exists()


def test_multi_level_missing_lineage_hydrates_without_restoring_ancestors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, hydrate, root, assoc = _make_handlers(tmp_path, monkeypatch)
    parent = transform(
        {"ref_id": assoc, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.8, 0.8]}}
    )
    parent_ref = parent["outputs"]["derived_ref_id"]
    child = transform(
        {
            "ref_id": parent_ref,
            "sub_action": "zoom",
            "params": {"box_norm": [0.0, 0.0, 0.5, 0.5], "factor": 1.0},
        }
    )
    child_ref = child["outputs"]["derived_ref_id"]
    _unlink_png(root, parent_ref)
    _unlink_png(root, child_ref)
    before = _snapshot_tree(root)
    hydrated = hydrate({"ref_ids": [child_ref]})
    assert hydrated["executed"] is True
    assert not hydrated["outputs"]["errors"]
    evidence = hydrated.get("image_evidence") or []
    assert len(evidence) == 1
    assert evidence[0]["representation_kind"] == "reconstructed_recipe"
    assert evidence[0]["lineage_depth"] == 2
    assert _snapshot_tree(root) == before
    assert not (_derived_dir(root) / f"{parent_ref.removeprefix('image:derived:')}.png").exists()
    assert not (_derived_dir(root) / f"{child_ref.removeprefix('image:derived:')}.png").exists()


def test_missing_point_crop_png_explicit_per_ref_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, hydrate, root, assoc = _make_handlers(tmp_path, monkeypatch)
    result = transform(
        {
            "ref_id": assoc,
            "sub_action": "point_crops",
            "params": {
                "points": [
                    {
                        "alias": "parcel_1_tie_bearing",
                        "point_norm": [0.42, 0.58],
                        "size": "medium",
                        "shape": "wide",
                    }
                ]
            },
        }
    )
    assert result["executed"] is True, result
    master = result["outputs"]["derived_ref_id"]
    _unlink_png(root, master)
    before = _snapshot_tree(root)
    hydrated = hydrate({"ref_ids": [master]})
    assert hydrated["executed"] is True
    assert hydrated["outputs"]["hydrated_count"] == 0
    assert hydrated["outputs"]["results"] == []
    errors = hydrated["outputs"]["errors"]
    assert any(e.get("ref_id") == master for e in errors)
    err = next(e for e in errors if e.get("ref_id") == master)
    assert err["code"] == "recipe_unavailable"
    assert not hydrated.get("image_evidence")
    assert _snapshot_tree(root) == before


def test_unsafe_stored_png_refuses_without_recipe_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    from pathlib import Path as PathCls

    import tooling.mapping.transcript_edit.derived_image_descriptor as descriptor_mod

    transform, hydrate, root, assoc = _make_handlers(tmp_path, monkeypatch)
    result = transform(
        {"ref_id": assoc, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    png = _derived_dir(root) / f"{derived.removeprefix('image:derived:')}.png"
    png.unlink()

    orig_lexists = os.path.lexists
    orig_islink = os.path.islink
    orig_is_symlink = PathCls.is_symlink
    target_key = str(png)

    def fake_lexists(path: Any) -> bool:
        if str(path) == target_key or path == png:
            return True
        return orig_lexists(path)

    def fake_islink(path: Any) -> bool:
        if str(path) == target_key or path == png:
            return True
        return orig_islink(path)

    def fake_is_symlink(self: PathCls) -> bool:
        if self == png or str(self) == target_key:
            return True
        return orig_is_symlink(self)

    monkeypatch.setattr(os.path, "lexists", fake_lexists)
    monkeypatch.setattr(os.path, "islink", fake_islink)
    monkeypatch.setattr(PathCls, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(descriptor_mod.os.path, "lexists", fake_lexists)
    monkeypatch.setattr(descriptor_mod.os.path, "islink", fake_islink)

    before = _snapshot_tree(root)
    hydrated = hydrate({"ref_ids": [derived]})
    errors = hydrated["outputs"]["errors"]
    assert any(e.get("ref_id") == derived and e.get("code") == "stored_image_corrupt" for e in errors)
    assert hydrated["outputs"]["hydrated_count"] == 0
    assert hydrated["outputs"]["results"] == []
    assert not hydrated.get("image_evidence")
    assert _snapshot_tree(root) == before


def test_transform_from_missing_generic_parent_persists_only_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, _hydrate, root, assoc = _make_handlers(tmp_path, monkeypatch)
    parent = transform(
        {"ref_id": assoc, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.8, 0.8]}}
    )
    parent_ref = parent["outputs"]["derived_ref_id"]
    parent_coord = _load_desc(root, parent_ref)["content_sha256"]
    parent_pixel = compute_image_identity(
        path=_derived_dir(root) / f"{parent_ref.removeprefix('image:derived:')}.png"
    )["pixel_sha256"]
    _unlink_png(root, parent_ref)
    before = _snapshot_tree(root)

    child = transform(
        {
            "ref_id": parent_ref,
            "sub_action": "crop",
            "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]},
        }
    )
    assert child["executed"] is True, child
    child_ref = child["outputs"]["derived_ref_id"]
    after = _snapshot_tree(root)
    # Parent PNG remains absent; only new child files appear.
    assert not (_derived_dir(root) / f"{parent_ref.removeprefix('image:derived:')}.png").exists()
    child_uid = child_ref.removeprefix("image:derived:")
    assert (_derived_dir(root) / f"{child_uid}.png").is_file()
    assert (_derived_dir(root) / f"{child_uid}.json").is_file()
    new_keys = set(after) - set(before)
    assert new_keys == {
        f"artifacts/transcript_edit/d1/tx-1/ws-1/derived_images/{child_uid}.png",
        f"artifacts/transcript_edit/d1/tx-1/ws-1/derived_images/{child_uid}.json",
    }
    # Parent descriptor untouched.
    parent_json_rel = (
        f"artifacts/transcript_edit/d1/tx-1/ws-1/derived_images/"
        f"{parent_ref.removeprefix('image:derived:')}.json"
    )
    assert after[parent_json_rel] == before[parent_json_rel]

    child_desc = _load_desc(root, child_ref)
    assert child_desc["recipe"]["source"]["content_sha256"] == parent_coord
    assert child_desc["recipe"]["source"]["pixel_sha256"] == parent_pixel


def test_historical_missing_parent_without_content_sha_refuses_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, _hydrate, root, assoc = _make_handlers(tmp_path, monkeypatch)
    parent = transform(
        {"ref_id": assoc, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.8, 0.8]}}
    )
    parent_ref = parent["outputs"]["derived_ref_id"]
    desc = _load_desc(root, parent_ref)
    desc.pop("content_sha256", None)
    _write_desc(root, parent_ref, desc)
    _unlink_png(root, parent_ref)
    before = _snapshot_tree(root)

    child = transform(
        {
            "ref_id": parent_ref,
            "sub_action": "crop",
            "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]},
        }
    )
    assert child["executed"] is False
    assert child["refusal"]["reason_code"] == REASON_SOURCE_CONTENT_IDENTITY_UNAVAILABLE
    assert _snapshot_tree(root) == before


def test_dossier_qualified_hydration_preserves_reconstructed_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tooling.mapping.transcript_edit.dossier_artifact_refs import (
        build_dossier_artifact_ref_index,
    )

    transform, _hydrate, root, assoc = _make_handlers(tmp_path, monkeypatch)
    result = transform(
        {"ref_id": assoc, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    _unlink_png(root, derived)
    before = _snapshot_tree(root)

    qualified = qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx-1",
        leaf_ref=derived,
    )
    ref_index = build_dossier_artifact_ref_index(
        dossier_id="d1",
        topology_fingerprint="fp-test",
        entries=[],
        run_bindings=frozenset({("seg_a", "tx-1")}),
    )
    out = hydrate_dossier_artifact_refs(
        dossier_id="d1",
        ref_index=ref_index,
        ref_ids=[qualified],
        workspace_key="ws-1",
    )
    assert out["executed"] is True, out
    evidence = out.get("image_evidence") or []
    assert len(evidence) == 1
    assert evidence[0]["ref_id"] == qualified
    assert evidence[0]["representation_kind"] == "reconstructed_recipe"
    assert evidence[0]["content_identity_posture"] == "persisted_descriptor_coordinate"
    assert _snapshot_tree(root) == before


def test_dossier_qualified_missing_point_crop_surfaces_qualified_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tooling.mapping.transcript_edit.dossier_artifact_refs import (
        build_dossier_artifact_ref_index,
    )

    transform, _hydrate, root, assoc = _make_handlers(tmp_path, monkeypatch)
    result = transform(
        {
            "ref_id": assoc,
            "sub_action": "point_crops",
            "params": {
                "points": [
                    {
                        "alias": "parcel_1_tie_bearing",
                        "point_norm": [0.42, 0.58],
                        "size": "medium",
                        "shape": "wide",
                    }
                ]
            },
        }
    )
    assert result["executed"] is True, result
    master = result["outputs"]["derived_ref_id"]
    _unlink_png(root, master)
    before = _snapshot_tree(root)
    qualified = qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx-1",
        leaf_ref=master,
    )
    ref_index = build_dossier_artifact_ref_index(
        dossier_id="d1",
        topology_fingerprint="fp-test",
        entries=[],
        run_bindings=frozenset({("seg_a", "tx-1")}),
    )
    out = hydrate_dossier_artifact_refs(
        dossier_id="d1",
        ref_index=ref_index,
        ref_ids=[qualified],
        workspace_key="ws-1",
    )
    assert out["executed"] is True, out
    assert out["outputs"]["hydrated_count"] == 0
    assert out["outputs"]["results"] == []
    errors = out["outputs"]["errors"]
    assert any(e.get("ref_id") == qualified for e in errors)
    err = next(e for e in errors if e.get("ref_id") == qualified)
    assert err["code"] == "recipe_unavailable"
    # Dossier router remaps leaf codes; ensure no successful result masked the error.
    assert err.get("leaf_ref_id") == master
    assert not out.get("image_evidence")
    assert _snapshot_tree(root) == before


def test_stored_evidence_encode_failure_is_exclusive_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, hydrate, root, assoc = _make_handlers(tmp_path, monkeypatch)
    result = transform(
        {"ref_id": assoc, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    before = _snapshot_tree(root)

    def _boom(_ref_id: str, _path: Path) -> None:
        return None

    monkeypatch.setattr(
        "tooling.mapping.transcript_edit.artifact_hydration.image_evidence_from_path",
        _boom,
    )
    hydrated = hydrate({"ref_ids": [derived]})
    assert hydrated["executed"] is True
    assert hydrated["outputs"]["hydrated_count"] == 0
    assert hydrated["outputs"]["results"] == []
    errors = hydrated["outputs"]["errors"]
    assert len([e for e in errors if e.get("ref_id") == derived]) == 1
    err = next(e for e in errors if e.get("ref_id") == derived)
    assert err["code"] == "image_evidence_encode_failed"
    assert not hydrated.get("image_evidence")
    assert _snapshot_tree(root) == before


def test_point_crops_from_missing_reconstructible_generic_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, _hydrate, root, assoc = _make_handlers(tmp_path, monkeypatch)
    parent = transform(
        {"ref_id": assoc, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.8, 0.8]}}
    )
    parent_ref = parent["outputs"]["derived_ref_id"]
    _unlink_png(root, parent_ref)
    before = _snapshot_tree(root)

    crops = transform(
        {
            "ref_id": parent_ref,
            "sub_action": "point_crops",
            "params": {
                "points": [
                    {
                        "alias": "parcel_1_tie_bearing",
                        "point_norm": [0.42, 0.58],
                        "size": "medium",
                        "shape": "wide",
                    }
                ]
            },
        }
    )
    assert crops["executed"] is True, crops
    master = crops["outputs"]["derived_ref_id"]
    crop_ref = crops["outputs"]["crop_set"]["points"][0]["crop_ref"]
    after = _snapshot_tree(root)

    # Parent PNG remains absent; only authorized point-crop outputs appear.
    assert not (_derived_dir(root) / f"{parent_ref.removeprefix('image:derived:')}.png").exists()
    parent_json_rel = (
        f"artifacts/transcript_edit/d1/tx-1/ws-1/derived_images/"
        f"{parent_ref.removeprefix('image:derived:')}.json"
    )
    assert after[parent_json_rel] == before[parent_json_rel]

    new_keys = set(after) - set(before)
    master_uid = master.removeprefix("image:derived:")
    crop_uid = crop_ref.removeprefix("image:derived:")
    # Point-crop set typically writes master + crop (+ optional sidecar).
    assert f"artifacts/transcript_edit/d1/tx-1/ws-1/derived_images/{master_uid}.png" in new_keys
    assert f"artifacts/transcript_edit/d1/tx-1/ws-1/derived_images/{master_uid}.json" in new_keys
    assert f"artifacts/transcript_edit/d1/tx-1/ws-1/derived_images/{crop_uid}.png" in new_keys
    assert f"artifacts/transcript_edit/d1/tx-1/ws-1/derived_images/{crop_uid}.json" in new_keys
    # No parent PNG backfill.
    assert (
        f"artifacts/transcript_edit/d1/tx-1/ws-1/derived_images/"
        f"{parent_ref.removeprefix('image:derived:')}.png"
    ) not in new_keys
    # Point-crop descriptors remain recipe-free.
    master_desc = _load_desc(root, master)
    crop_desc = _load_desc(root, crop_ref)
    assert "recipe" not in master_desc
    assert "recipe" not in crop_desc
