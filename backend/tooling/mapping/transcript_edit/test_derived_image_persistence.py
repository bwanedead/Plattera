"""STORAGE-BR-003: run-owned derived images; canonical sources stay immutable."""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

import config.paths as paths_mod
import tooling.mapping.transcript_edit.paths as te_paths_mod
from tooling.mapping.transcript_edit.artifact_hydration import (
    _load_derived_image_descriptor,
    make_hydrate_artifact_refs_handler,
)
from tooling.mapping.transcript_edit.artifact_transform import make_transform_artifact_handler
from tooling.mapping.transcript_edit.derived_image_persistence import (
    REASON_DERIVED_PERSIST_FAILED,
    REASON_RECIPE_DESCRIPTOR_MISMATCH,
    REASON_RECIPE_FINGERPRINT_MISMATCH,
    REASON_RECIPE_OUTPUT_MISMATCH,
    REASON_RECIPE_REQUIRED,
    DerivedImagePersistError,
    persist_derived_image,
)
from tooling.mapping.transcript_edit.dossier_artifact_refs import qualify_leaf_ref
from tooling.mapping.transcript_edit.derived_image_recipe import (
    build_derived_image_recipe,
    recipe_fingerprint,
)
from tooling.mapping.transcript_edit.derived_image_rendering import (
    compute_image_identity,
    pillow_version,
)
from tooling.mapping.transcript_edit.paths import transcript_edit_derived_images_dir


def _valid_recipe_descriptor(
    *,
    source_path,
    source_ref,
    image,
    parent_ref,
    sub_action,
    params,
    derived_ref,
):
    src = compute_image_identity(path=source_path)
    out = compute_image_identity(image=image)
    recipe = build_derived_image_recipe(
        source_ref_id=source_ref,
        source_content_sha256=src["content_sha256"],
        source_pixel_sha256=src["pixel_sha256"],
        source_mode=src["mode"],
        source_width_height=src["width_height"],
        sub_action=sub_action,
        params=params,
        pillow_version=pillow_version(),
        expected_pixel_sha256=out["pixel_sha256"],
        expected_mode=out["mode"],
        expected_width_height=out["width_height"],
    )
    return {
        "ref_id": derived_ref,
        "parent_ref_id": parent_ref,
        "sub_action": sub_action,
        "params": params,
        "recipe": recipe,
        "recipe_fingerprint": recipe_fingerprint(recipe),
    }


def _dossiers_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    return root


def _tiny_png_bytes(width: int = 100, height: int = 80) -> bytes:
    img = Image.new("RGB", (width, height), color=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _assert_no_derived_residue(derived_dir: Path, uid: str) -> None:
    assert not (derived_dir / f"{uid}.png").exists()
    assert not (derived_dir / f"{uid}.json").exists()
    assert list(derived_dir.glob(f".{uid}.*.staging.*")) == []


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


def _make_handler(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    d: str = "d1",
    tx: str = "tx-1",
    ws: str = "ws-1",
    image_width: int = 100,
    image_height: int = 80,
):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)

    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_file = img_dir / "scan.png"
    img_file.write_bytes(_tiny_png_bytes(width=image_width, height=image_height))
    _write_association(root, d, tx, img_file)

    handler = make_transform_artifact_handler(dossier_id=d, transcription_id=tx, workspace_key=ws)
    return handler, f"image:assoc:{tx}:original", img_file


def _source_snapshot(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    parent = path.parent
    return {
        "bytes": data,
        "sha256": hashlib.sha256(data).hexdigest(),
        "mtime_ns": path.stat().st_mtime_ns,
        "size": path.stat().st_size,
        "parent_members": sorted(p.name for p in parent.iterdir()),
    }


def _assert_source_unchanged(
    path: Path,
    before: dict[str, Any],
    *,
    check_parent_members: bool = True,
) -> None:
    after = _source_snapshot(path)
    assert after["sha256"] == before["sha256"]
    assert after["bytes"] == before["bytes"]
    assert after["mtime_ns"] == before["mtime_ns"]
    assert after["size"] == before["size"]
    if check_parent_members:
        assert after["parent_members"] == before["parent_members"]


def _assert_under_derived_dir(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    derived_ref: str,
) -> Path:
    derived_dir = transcript_edit_derived_images_dir(dossier_id, transcription_id, workspace_id).resolve()
    desc = _load_derived_image_descriptor(dossier_id, transcription_id, workspace_id, derived_ref)
    assert desc is not None
    abs_path = Path(desc["absolute_path"]).resolve()
    assert abs_path.is_file()
    assert abs_path.parent == derived_dir
    assert abs_path.name.endswith(".png")
    descriptor_path = derived_dir / f"{derived_ref.removeprefix('image:derived:')}.json"
    assert descriptor_path.is_file()
    return abs_path


_GENERIC_CASES: list[tuple[str, dict[str, Any]]] = [
    ("crop", {"box_norm": [0.0, 0.0, 0.5, 0.5]}),
    ("zoom", {"factor": 1.5}),
    ("expand", {"padding": [2, 2, 2, 2]}),
    ("reference_overlay", {"cols": 3, "rows": 3}),
    (
        "annotate",
        {
            "annotations": [
                {"type": "bbox", "box_norm": [0.1, 0.1, 0.4, 0.4], "color": [255, 0, 0], "width": 2}
            ]
        },
    ),
    (
        "render_evidence_locators",
        {
            "locators": [
                {
                    "ref_id": "image:assoc:tx-1:original",
                    "locator_kind": "image_region",
                    "label": "region",
                    "box_norm": [0.1, 0.2, 0.4, 0.5],
                }
            ]
        },
    ),
]


@pytest.mark.parametrize("sub_action,params", _GENERIC_CASES, ids=[c[0] for c in _GENERIC_CASES])
def test_canonical_source_immutable_for_generic_sub_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sub_action: str, params: dict[str, Any]
) -> None:
    handler, ref_id, source = _make_handler(tmp_path, monkeypatch)
    if sub_action == "render_evidence_locators":
        params = {
            "locators": [
                {
                    "ref_id": ref_id,
                    "locator_kind": "image_region",
                    "label": "region",
                    "box_norm": [0.1, 0.2, 0.4, 0.5],
                }
            ]
        }
    before = _source_snapshot(source)
    result = handler({"ref_id": ref_id, "sub_action": sub_action, "params": params})
    assert result["executed"] is True, result
    derived = result["outputs"]["derived_ref_id"]
    assert derived.startswith("image:derived:")
    assert derived in result["artifact_refs"]
    abs_path = _assert_under_derived_dir(
        dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", derived_ref=derived
    )
    assert abs_path.name == result["outputs"]["basename"]
    _assert_source_unchanged(source, before)
    assert source.parent not in {abs_path.parent}


def test_derived_to_derived_chaining_stays_run_owned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, source = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    before_source = _source_snapshot(source)

    parent = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.8, 0.8]}}
    )
    assert parent["executed"] is True
    parent_ref = parent["outputs"]["derived_ref_id"]
    parent_path = _assert_under_derived_dir(
        dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", derived_ref=parent_ref
    )
    parent_before = _source_snapshot(parent_path)

    child = handler(
        {
            "ref_id": parent_ref,
            "sub_action": "zoom",
            "params": {"box_norm": [0.0, 0.0, 0.5, 0.5], "factor": 1.0},
        }
    )
    assert child["executed"] is True
    child_ref = child["outputs"]["derived_ref_id"]
    child_path = _assert_under_derived_dir(
        dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", derived_ref=child_ref
    )
    assert child_path.parent == parent_path.parent
    assert child["outputs"]["parent_ref_id"] == parent_ref

    _assert_source_unchanged(source, before_source)
    # Child lands in the same derived_images dir; parent file bytes must stay intact.
    _assert_source_unchanged(parent_path, parent_before, check_parent_members=False)

    hydrate = make_hydrate_artifact_refs_handler(
        dossier_id="d1", transcription_id="tx-1", workspace_key="ws-1"
    )
    hydrated = hydrate({"ref_ids": [parent_ref, child_ref]})
    assert hydrated["executed"] is True
    kinds = {row["ref_id"]: row["kind"] for row in hydrated["outputs"]["results"]}
    assert kinds[parent_ref] == "derived_image"
    assert kinds[child_ref] == "derived_image"
    assert len(hydrated["image_evidence"]) == 2


def test_point_crops_remain_run_owned_and_source_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, source = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    before = _source_snapshot(source)
    derived_dir = transcript_edit_derived_images_dir("d1", "tx-1", "ws-1")

    result = handler(
        {
            "ref_id": ref_id,
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
    crop = result["outputs"]["crop_set"]["points"][0]["crop_ref"]
    master_path = _assert_under_derived_dir(
        dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", derived_ref=master
    )
    crop_path = _assert_under_derived_dir(
        dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", derived_ref=crop
    )
    assert master_path.parent == derived_dir.resolve()
    assert crop_path.parent == derived_dir.resolve()
    assert result["image_evidence"][0]["ref_id"] == master
    _assert_source_unchanged(source, before)


def test_persist_staged_write_failure_contains(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    source = tmp_path / "canon.png"
    source.write_bytes(_tiny_png_bytes())
    before = _source_snapshot(source)
    uid = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    parent = "image:assoc:tx-1:original"
    params = {"box_norm": [0.0, 0.0, 0.5, 0.5]}
    proxy = Image.new("RGB", (100, 80), color=(10, 20, 30))
    descriptor = _valid_recipe_descriptor(
        source_path=source,
        source_ref=parent,
        image=proxy,
        parent_ref=parent,
        sub_action="crop",
        params=params,
        derived_ref=f"image:derived:{uid}",
    )

    class _Boom:
        def save(self, *_a: Any, **_k: Any) -> None:
            raise OSError("disk full")

    with pytest.raises(DerivedImagePersistError) as excinfo:
        persist_derived_image(
            dossier_id="d1",
            transcription_id="tx-1",
            workspace_id="ws-1",
            derived_uuid=uid,
            image=_Boom(),
            descriptor=descriptor,
            expected_width_height=(100, 80),
        )
    assert excinfo.value.code == REASON_DERIVED_PERSIST_FAILED
    assert "disk" not in str(excinfo.value.message).lower()
    assert "\\" not in excinfo.value.message
    assert "/" not in excinfo.value.message or "Could not stage" in excinfo.value.message
    derived_dir = transcript_edit_derived_images_dir("d1", "tx-1", "ws-1")
    _assert_no_derived_residue(derived_dir, uid)
    _assert_source_unchanged(source, before)


def test_persist_verify_failure_cleans_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    source = tmp_path / "canon.png"
    source.write_bytes(_tiny_png_bytes())
    before = _source_snapshot(source)
    img = Image.new("RGB", (100, 80), color=(10, 20, 30))
    uid = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    parent = "image:assoc:tx-1:original"
    params = {"box_norm": [0.0, 0.0, 0.5, 0.5]}
    descriptor = _valid_recipe_descriptor(
        source_path=source,
        source_ref=parent,
        image=img,
        parent_ref=parent,
        sub_action="crop",
        params=params,
        derived_ref=f"image:derived:{uid}",
    )

    def _bad_verify(
        path: Path, *, expected_wh: tuple[int, int] | None
    ) -> tuple[tuple[int, int], dict[str, Any]]:
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Staged derived image could not be verified as a readable image.",
        )

    monkeypatch.setattr(
        "tooling.mapping.transcript_edit.derived_image_persistence._staged_image_identity",
        _bad_verify,
    )
    with pytest.raises(DerivedImagePersistError):
        persist_derived_image(
            dossier_id="d1",
            transcription_id="tx-1",
            workspace_id="ws-1",
            derived_uuid=uid,
            image=img,
            descriptor=descriptor,
            expected_width_height=(100, 80),
        )
    derived_dir = transcript_edit_derived_images_dir("d1", "tx-1", "ws-1")
    leftovers = list(derived_dir.glob(f"*{uid}*"))
    assert leftovers == []
    _assert_source_unchanged(source, before)


def test_persist_promotion_conflict_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    source = tmp_path / "canon.png"
    source.write_bytes(_tiny_png_bytes())
    before = _source_snapshot(source)

    derived_dir = transcript_edit_derived_images_dir("d1", "tx-1", "ws-1")
    derived_dir.mkdir(parents=True, exist_ok=True)
    uid = "cccccccccccccccccccccccccccccccc"
    preexisting = derived_dir / f"{uid}.png"
    preexisting.write_bytes(b"preexisting")

    img = Image.new("RGB", (100, 80), color=(1, 2, 3))
    parent = "image:assoc:tx-1:original"
    params = {"box_norm": [0.0, 0.0, 0.5, 0.5]}
    descriptor = _valid_recipe_descriptor(
        source_path=source,
        source_ref=parent,
        image=img,
        parent_ref=parent,
        sub_action="crop",
        params=params,
        derived_ref=f"image:derived:{uid}",
    )
    with pytest.raises(DerivedImagePersistError) as excinfo:
        persist_derived_image(
            dossier_id="d1",
            transcription_id="tx-1",
            workspace_id="ws-1",
            derived_uuid=uid,
            image=img,
            descriptor=descriptor,
            expected_width_height=(100, 80),
        )
    assert "already exists" in excinfo.value.message.lower()
    assert preexisting.read_bytes() == b"preexisting"
    assert not (derived_dir / f"{uid}.json").exists()
    _assert_source_unchanged(source, before)


def test_persist_descriptor_failure_removes_unreferenced_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    source = tmp_path / "canon.png"
    source.write_bytes(_tiny_png_bytes())
    before = _source_snapshot(source)
    img = Image.new("RGB", (100, 80), color=(9, 9, 9))
    uid = "dddddddddddddddddddddddddddddddd"
    parent = "image:assoc:tx-1:original"
    params = {"box_norm": [0.0, 0.0, 0.5, 0.5]}
    descriptor = _valid_recipe_descriptor(
        source_path=source,
        source_ref=parent,
        image=img,
        parent_ref=parent,
        sub_action="crop",
        params=params,
        derived_ref=f"image:derived:{uid}",
    )

    def _fail_desc(path: Path, descriptor: Any) -> None:
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Could not persist derived image descriptor.",
        )

    monkeypatch.setattr(
        "tooling.mapping.transcript_edit.derived_image_persistence._write_descriptor_atomic",
        _fail_desc,
    )
    with pytest.raises(DerivedImagePersistError):
        persist_derived_image(
            dossier_id="d1",
            transcription_id="tx-1",
            workspace_id="ws-1",
            derived_uuid=uid,
            image=img,
            descriptor=descriptor,
            expected_width_height=(100, 80),
        )
    derived_dir = transcript_edit_derived_images_dir("d1", "tx-1", "ws-1")
    _assert_no_derived_residue(derived_dir, uid)
    _assert_source_unchanged(source, before)


def test_persist_cleanup_failure_still_refuses_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    source = tmp_path / "canon.png"
    source.write_bytes(_tiny_png_bytes())
    before = _source_snapshot(source)
    img = Image.new("RGB", (100, 80), color=(4, 5, 6))
    uid = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    parent = "image:assoc:tx-1:original"
    params = {"box_norm": [0.0, 0.0, 0.5, 0.5]}
    descriptor = _valid_recipe_descriptor(
        source_path=source,
        source_ref=parent,
        image=img,
        parent_ref=parent,
        sub_action="crop",
        params=params,
        derived_ref=f"image:derived:{uid}",
    )

    def _fail_desc(path: Path, descriptor: Any) -> None:
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Could not persist derived image descriptor.",
        )

    real_unlink = Path.unlink

    def _flaky_unlink(self: Path, *args: Any, **kwargs: Any) -> None:
        if self.name.endswith(".png") and uid in self.name:
            raise OSError("cleanup blocked")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(
        "tooling.mapping.transcript_edit.derived_image_persistence._write_descriptor_atomic",
        _fail_desc,
    )
    monkeypatch.setattr(Path, "unlink", _flaky_unlink)
    with pytest.raises(DerivedImagePersistError) as excinfo:
        persist_derived_image(
            dossier_id="d1",
            transcription_id="tx-1",
            workspace_id="ws-1",
            derived_uuid=uid,
            image=img,
            descriptor=descriptor,
            expected_width_height=(100, 80),
        )
    assert excinfo.value.code == REASON_DERIVED_PERSIST_FAILED
    assert not (transcript_edit_derived_images_dir("d1", "tx-1", "ws-1") / f"{uid}.json").exists()
    _assert_source_unchanged(source, before)


def test_descriptor_race_after_discovery_never_overwrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A descriptor created after the initial absence check must not be replaced."""
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    source = tmp_path / "canon.png"
    source.write_bytes(_tiny_png_bytes())
    before = _source_snapshot(source)

    uid = "f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1"
    derived_dir = transcript_edit_derived_images_dir("d1", "tx-1", "ws-1")
    derived_dir.mkdir(parents=True, exist_ok=True)
    foreign = derived_dir / "foreign-keep.bin"
    foreign.write_bytes(b"foreign-bytes")
    foreign_before = foreign.read_bytes()

    desc_path = derived_dir / f"{uid}.json"
    preexisting = b'{"ref_id":"image:derived:preexisting","keep":true}'

    real_link = os.link

    def _link_inject_descriptor_race(src: str | bytes | os.PathLike[str], dst: str | bytes | os.PathLike[str]) -> None:
        dst_path = Path(dst)
        if dst_path.suffix == ".json" and dst_path.name == f"{uid}.json":
            dst_path.write_bytes(preexisting)
        return real_link(src, dst)

    monkeypatch.setattr(
        "tooling.mapping.transcript_edit.derived_image_persistence.os.link",
        _link_inject_descriptor_race,
    )
    img = Image.new("RGB", (100, 80), color=(7, 8, 9))
    parent = "image:assoc:tx-1:original"
    params = {"box_norm": [0.0, 0.0, 0.5, 0.5]}
    descriptor = _valid_recipe_descriptor(
        source_path=source,
        source_ref=parent,
        image=img,
        parent_ref=parent,
        sub_action="crop",
        params=params,
        derived_ref=f"image:derived:{uid}",
    )
    with pytest.raises(DerivedImagePersistError) as excinfo:
        persist_derived_image(
            dossier_id="d1",
            transcription_id="tx-1",
            workspace_id="ws-1",
            derived_uuid=uid,
            image=img,
            descriptor=descriptor,
            expected_width_height=(100, 80),
        )
    assert excinfo.value.code == REASON_DERIVED_PERSIST_FAILED
    assert "already exists" in excinfo.value.message.lower()
    assert desc_path.read_bytes() == preexisting
    assert foreign.read_bytes() == foreign_before
    assert not (derived_dir / f"{uid}.png").exists()
    _assert_source_unchanged(source, before)


def test_preexisting_descriptor_bytes_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    source = tmp_path / "canon.png"
    source.write_bytes(_tiny_png_bytes())
    before = _source_snapshot(source)

    uid = "a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2"
    derived_dir = transcript_edit_derived_images_dir("d1", "tx-1", "ws-1")
    derived_dir.mkdir(parents=True, exist_ok=True)
    desc_path = derived_dir / f"{uid}.json"
    preexisting = b'{"ref_id":"image:derived:locked","immutable":1}'
    desc_path.write_bytes(preexisting)
    before_desc = _source_snapshot(desc_path)

    img = Image.new("RGB", (100, 80), color=(11, 12, 13))
    parent = "image:assoc:tx-1:original"
    params = {"box_norm": [0.0, 0.0, 0.5, 0.5]}
    descriptor = _valid_recipe_descriptor(
        source_path=source,
        source_ref=parent,
        image=img,
        parent_ref=parent,
        sub_action="crop",
        params=params,
        derived_ref=f"image:derived:{uid}",
    )
    with pytest.raises(DerivedImagePersistError) as excinfo:
        persist_derived_image(
            dossier_id="d1",
            transcription_id="tx-1",
            workspace_id="ws-1",
            derived_uuid=uid,
            image=img,
            descriptor=descriptor,
            expected_width_height=(100, 80),
        )
    assert "already exists" in excinfo.value.message.lower()
    _assert_source_unchanged(desc_path, before_desc)
    assert not (derived_dir / f"{uid}.png").exists()
    _assert_source_unchanged(source, before)


def test_non_json_native_descriptor_refuses_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    source = tmp_path / "canon.png"
    source.write_bytes(_tiny_png_bytes())
    before = _source_snapshot(source)
    uid = "b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3"
    derived_dir = transcript_edit_derived_images_dir("d1", "tx-1", "ws-1")
    derived_dir.mkdir(parents=True, exist_ok=True)
    keep = derived_dir / "keep-me.txt"
    keep.write_text("stay", encoding="utf-8")

    img = Image.new("RGB", (100, 80), color=(14, 15, 16))
    parent = "image:assoc:tx-1:original"
    params = {"box_norm": [0.0, 0.0, 0.5, 0.5]}
    descriptor = _valid_recipe_descriptor(
        source_path=source,
        source_ref=parent,
        image=img,
        parent_ref=parent,
        sub_action="crop",
        params=params,
        derived_ref=f"image:derived:{uid}",
    )
    descriptor["bad"] = float("nan")
    with pytest.raises(DerivedImagePersistError) as excinfo:
        persist_derived_image(
            dossier_id="d1",
            transcription_id="tx-1",
            workspace_id="ws-1",
            derived_uuid=uid,
            image=img,
            descriptor=descriptor,
            expected_width_height=(100, 80),
        )
    assert excinfo.value.code == REASON_DERIVED_PERSIST_FAILED
    assert "json" in excinfo.value.message.lower() or "serializ" in excinfo.value.message.lower()
    _assert_no_derived_residue(derived_dir, uid)
    assert keep.read_text(encoding="utf-8") == "stay"
    _assert_source_unchanged(source, before)


def test_staging_unlink_failure_after_image_link_refuses_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    source = tmp_path / "canon.png"
    source.write_bytes(_tiny_png_bytes())
    before = _source_snapshot(source)

    uid = "c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4"
    derived_dir = transcript_edit_derived_images_dir("d1", "tx-1", "ws-1")
    derived_dir.mkdir(parents=True, exist_ok=True)
    foreign = derived_dir / "foreign-artifact.bin"
    foreign.write_bytes(b"do-not-delete")
    foreign_before = foreign.read_bytes()

    real_unlink = Path.unlink

    def _fail_staging_unlink(self: Path, *args: Any, **kwargs: Any) -> None:
        name = self.name
        if ".staging.png" in name and uid in name:
            raise OSError("staging busy")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _fail_staging_unlink)
    img = Image.new("RGB", (100, 80), color=(17, 18, 19))
    parent = "image:assoc:tx-1:original"
    params = {"box_norm": [0.0, 0.0, 0.5, 0.5]}
    descriptor = _valid_recipe_descriptor(
        source_path=source,
        source_ref=parent,
        image=img,
        parent_ref=parent,
        sub_action="crop",
        params=params,
        derived_ref=f"image:derived:{uid}",
    )
    with pytest.raises(DerivedImagePersistError) as excinfo:
        persist_derived_image(
            dossier_id="d1",
            transcription_id="tx-1",
            workspace_id="ws-1",
            derived_uuid=uid,
            image=img,
            descriptor=descriptor,
            expected_width_height=(100, 80),
        )
    assert excinfo.value.code == REASON_DERIVED_PERSIST_FAILED
    assert "clean up" in excinfo.value.message.lower() or "staging" in excinfo.value.message.lower()
    assert not (derived_dir / f"{uid}.png").exists()
    assert not (derived_dir / f"{uid}.json").exists()
    assert foreign.read_bytes() == foreign_before
    _assert_source_unchanged(source, before)


def test_handler_persist_failure_is_stable_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, source = _make_handler(tmp_path, monkeypatch)
    before = _source_snapshot(source)

    def _boom(**_kwargs: Any) -> Any:
        raise DerivedImagePersistError(
            REASON_DERIVED_PERSIST_FAILED,
            "Could not persist derived image into the run workspace.",
        )

    monkeypatch.setattr(
        "tooling.mapping.transcript_edit.artifact_transform.persist_derived_image",
        _boom,
    )
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == REASON_DERIVED_PERSIST_FAILED
    assert result["refusal"]["retryable"] is False
    assert result["refusal"]["blocked_by_invariant"] is True
    _assert_source_unchanged(source, before)


def test_audit_and_hydration_use_run_local_derived_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from harness.audit.artifact_ref_links import (
        ArtifactLinkContext,
        build_ref_path_index,
        resolve_artifact_image_link,
    )
    from harness.audit.human_timeline import _render_tool_result

    handler, ref_id, source = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    before = _source_snapshot(source)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    assert result["executed"] is True
    derived = result["outputs"]["derived_ref_id"]
    abs_path = _assert_under_derived_dir(
        dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", derived_ref=derived
    )

    hydrate = make_hydrate_artifact_refs_handler(
        dossier_id="d1", transcription_id="tx-1", workspace_key="ws-1"
    )
    hydrated = hydrate({"ref_ids": [derived]})
    assert hydrated["executed"] is True
    assert hydrated["image_evidence"][0]["ref_id"] == derived

    desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", derived)
    assert desc is not None
    turn = {
        "turn_index": 1,
        "parse_ok": True,
        "tool_result_raw": {
            "execution_state": "executed",
            "artifact_refs": [derived],
            "outputs": {
                "derived_ref_id": derived,
                "parent_ref_id": ref_id,
                "sub_action": "crop",
                "basename": result["outputs"]["basename"],
            },
        },
    }
    index = build_ref_path_index(
        turn=turn,
        shared_index={derived: str(abs_path.resolve())},
    )
    assert index[derived] == str(abs_path.resolve())

    timeline_path = tmp_path / "audit" / "human" / "timeline.md"
    timeline_path.parent.mkdir(parents=True)
    context = ArtifactLinkContext(timeline_path=timeline_path, ref_path_index=index)
    link = resolve_artifact_image_link(derived, context)
    assert link is not None
    assert abs_path.name in link.path
    assert abs_path.name in link.markdown_link
    assert str(abs_path.resolve()) not in link.markdown_link

    rendered = "\n".join(_render_tool_result(turn, link_context=context))
    assert derived in rendered
    assert "[open image]" in rendered
    assert "absolute_path" not in rendered
    assert str(abs_path.resolve()) not in rendered

    # Descriptor-backed absolute_path still resolves the leaf and dossier-qualified wrapper.
    leaf_index = build_ref_path_index(
        turn={
            "tool_result_raw": {
                "outputs": {
                    "derived_ref_id": derived,
                    "absolute_path": desc["absolute_path"],
                }
            }
        },
        shared_index={},
    )
    assert leaf_index[derived] == str(abs_path.resolve())

    qualified = qualify_leaf_ref(
        leaf_ref=derived,
        segment_id="seg_a",
        transcription_id="tx-1",
    )
    assert qualified.startswith("dossier_segment:seg_a:run:tx-1:image:derived:")
    q_index = build_ref_path_index(
        turn={
            "tool_result_raw": {
                "artifact_refs": [qualified],
                "outputs": {"derived_ref_id": qualified},
            }
        },
        shared_index={derived: str(abs_path.resolve())},
    )
    assert q_index[qualified] == str(abs_path.resolve())
    _assert_source_unchanged(source, before)


def test_transform_production_does_not_derive_output_from_source_parent() -> None:
    """Mechanical guard: generic transform path must not write beside the source."""
    root = Path(__file__).resolve().parent
    targets = [
        root / "artifact_transform.py",
        root / "derived_image_persistence.py",
    ]
    violations: list[str] = []
    for path in targets:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            # Attribute access: source.parent
            if isinstance(node, ast.Attribute) and node.attr == "parent":
                if isinstance(node.value, ast.Name) and node.value.id == "source":
                    violations.append(f"{path.name}:{node.lineno}: source.parent")
            # Subscript/call patterns embedding ".parent /" near derived naming
        if "source.parent" in source:
            # Allow only in comments/docstrings that forbid the pattern.
            for i, line in enumerate(source.splitlines(), start=1):
                stripped = line.strip()
                if "source.parent" not in stripped:
                    continue
                if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                if 'Does not write beside the source' in stripped:
                    continue
                violations.append(f"{path.name}:{i}: {stripped}")

    assert violations == [], "source.parent used for transform output paths:\n" + "\n".join(
        violations
    )


def test_scope_containment_modules_do_not_touch_forbidden_surfaces() -> None:
    root = Path(__file__).resolve().parent
    for name in ("derived_image_persistence.py", "artifact_transform.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "harness.runtime" not in text
        assert "dossiers_data/images/original" not in text
        assert "images/original" not in text or "read-only" in text.lower()
        tree = ast.parse(text, filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("harness.runtime"):
                pytest.fail(f"{name} imports harness.runtime")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("harness.runtime")


_PERSIST_RECIPE_SMOKE = [
    ("crop", {"box_norm": [0.0, 0.0, 0.5, 0.5]}),
    (
        "render_evidence_locators",
        {
            "locators": [
                {
                    "ref_id": "image:assoc:tx-1:original",
                    "locator_kind": "image_region",
                    "label": "region",
                    "box_norm": [0.1, 0.2, 0.4, 0.5],
                }
            ]
        },
    ),
]


@pytest.mark.parametrize(
    "sub_action,params",
    _PERSIST_RECIPE_SMOKE,
    ids=[c[0] for c in _PERSIST_RECIPE_SMOKE],
)
def test_generic_handler_persists_recipe_and_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sub_action: str, params: dict[str, Any]
) -> None:
    handler, ref_id, _source = _make_handler(tmp_path, monkeypatch)
    if sub_action == "render_evidence_locators":
        params = {
            "locators": [
                {
                    "ref_id": ref_id,
                    "locator_kind": "image_region",
                    "label": "region",
                    "box_norm": [0.1, 0.2, 0.4, 0.5],
                }
            ]
        }
    result = handler({"ref_id": ref_id, "sub_action": sub_action, "params": params})
    assert result["executed"] is True, result
    derived = result["outputs"]["derived_ref_id"]
    desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", derived)
    assert desc is not None
    assert "recipe" in desc
    assert desc["recipe_fingerprint"].startswith("sha256:")
    assert desc["recipe"]["source"]["ref_id"] == ref_id
    assert desc["recipe"]["transform"]["sub_action"] == sub_action


def test_derived_to_derived_recipe_binds_immediate_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, _source = _make_handler(tmp_path, monkeypatch)
    parent = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.8, 0.8]}}
    )
    assert parent["executed"] is True
    parent_ref = parent["outputs"]["derived_ref_id"]
    child = handler(
        {
            "ref_id": parent_ref,
            "sub_action": "zoom",
            "params": {"box_norm": [0.0, 0.0, 0.5, 0.5], "factor": 1.0},
        }
    )
    assert child["executed"] is True
    child_ref = child["outputs"]["derived_ref_id"]
    child_desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", child_ref)
    assert child_desc is not None
    assert child_desc["parent_ref_id"] == parent_ref
    assert child_desc["recipe"]["source"]["ref_id"] == parent_ref


@pytest.mark.parametrize(
    "mutate,expected_code",
    [
        ("descriptor", REASON_RECIPE_DESCRIPTOR_MISMATCH),
        ("fingerprint", REASON_RECIPE_FINGERPRINT_MISMATCH),
        ("output", REASON_RECIPE_OUTPUT_MISMATCH),
        ("missing", REASON_RECIPE_REQUIRED),
    ],
    ids=["descriptor", "fingerprint", "output", "required"],
)
def test_recipe_gate_refuses_without_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate: str,
    expected_code: str,
) -> None:
    from tooling.mapping.transcript_edit.derived_image_recipe import recipe_fingerprint

    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    source = tmp_path / "canon.png"
    source.write_bytes(_tiny_png_bytes())
    img = Image.new("RGB", (100, 80), color=(21, 22, 23))
    uid = "11111111111111111111111111111111"
    parent = "image:assoc:tx-1:original"
    params = {"box_norm": [0.0, 0.0, 0.5, 0.5]}
    derived_dir = transcript_edit_derived_images_dir("d1", "tx-1", "ws-1")
    derived_dir.mkdir(parents=True, exist_ok=True)

    if mutate == "missing":
        descriptor = {
            "ref_id": f"image:derived:{uid}",
            "parent_ref_id": parent,
            "sub_action": "crop",
            "params": params,
        }
    else:
        descriptor = _valid_recipe_descriptor(
            source_path=source,
            source_ref=parent,
            image=img,
            parent_ref=parent,
            sub_action="crop",
            params=params,
            derived_ref=f"image:derived:{uid}",
        )
        if mutate == "descriptor":
            descriptor["recipe"] = dict(descriptor["recipe"])
            descriptor["recipe"]["source"] = dict(descriptor["recipe"]["source"])
            descriptor["recipe"]["source"]["ref_id"] = (
                "image:derived:ffffffffffffffffffffffffffffffff"
            )
            descriptor["recipe_fingerprint"] = recipe_fingerprint(descriptor["recipe"])
        elif mutate == "fingerprint":
            descriptor["recipe_fingerprint"] = "sha256:" + ("f" * 64)
        elif mutate == "output":
            bad_recipe = dict(descriptor["recipe"])
            bad_recipe["expected_output"] = dict(bad_recipe["expected_output"])
            bad_recipe["expected_output"]["pixel_sha256"] = "e" * 64
            descriptor["recipe"] = bad_recipe
            descriptor["recipe_fingerprint"] = recipe_fingerprint(bad_recipe)

    with pytest.raises(DerivedImagePersistError) as excinfo:
        persist_derived_image(
            dossier_id="d1",
            transcription_id="tx-1",
            workspace_id="ws-1",
            derived_uuid=uid,
            image=img,
            descriptor=descriptor,
            expected_width_height=(100, 80),
        )
    assert excinfo.value.code == expected_code
    _assert_no_derived_residue(derived_dir, uid)


def test_point_crops_descriptors_have_no_recipe_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, _source = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {
            "ref_id": ref_id,
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
    crop = result["outputs"]["crop_set"]["points"][0]["crop_ref"]
    for ref in (master, crop):
        desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", ref)
        assert desc is not None
        assert "recipe" not in desc
        assert "recipe_fingerprint" not in desc
