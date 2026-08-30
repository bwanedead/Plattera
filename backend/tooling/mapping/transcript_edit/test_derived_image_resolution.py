"""STORAGE-BR-006: recipe-backed derived-image read resolution."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

import config.paths as paths_mod
import tooling.mapping.transcript_edit.paths as te_paths_mod
from tooling.mapping.transcript_edit.artifact_transform import make_transform_artifact_handler
from tooling.mapping.transcript_edit.derived_image_descriptor import (
    DerivedImageDescriptorError,
    load_derived_image_descriptor,
)
from tooling.mapping.transcript_edit.derived_image_recipe import recipe_fingerprint
from tooling.mapping.transcript_edit.derived_image_rendering import compute_image_identity
from tooling.mapping.transcript_edit.derived_image_resolution import (
    MAX_DERIVED_IMAGE_LINEAGE_DEPTH,
    DerivedImageResolutionError,
    resolve_derived_image_for_read,
)
from tooling.mapping.transcript_edit.derived_image_storage_audit import run_derived_image_storage_audit


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


def _make_handler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_file = img_dir / "scan.png"
    img_file.write_bytes(_tiny_png_bytes())
    _write_association(root, "d1", "tx-1", img_file)
    handler = make_transform_artifact_handler(
        dossier_id="d1", transcription_id="tx-1", workspace_key="ws-1"
    )
    return handler, "image:assoc:tx-1:original", root, img_file


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


def _unlink_png(root: Path, ref_id: str) -> Path:
    uid = ref_id.removeprefix("image:derived:")
    png = _derived_dir(root) / f"{uid}.png"
    assert png.is_file()
    png.unlink()
    return png


def _load_desc(root: Path, ref_id: str) -> dict[str, Any]:
    uid = ref_id.removeprefix("image:derived:")
    return json.loads((_derived_dir(root) / f"{uid}.json").read_text(encoding="utf-8"))


def _write_desc(root: Path, ref_id: str, desc: dict[str, Any]) -> None:
    uid = ref_id.removeprefix("image:derived:")
    (_derived_dir(root) / f"{uid}.json").write_text(
        json.dumps(desc, sort_keys=True), encoding="utf-8"
    )


def test_stored_generic_png_resolves_as_stored_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    assert result["executed"] is True, result
    derived = result["outputs"]["derived_ref_id"]
    resolved = resolve_derived_image_for_read(
        dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=derived
    )
    assert resolved.representation_kind == "stored_bytes"
    assert resolved.source_identity_posture == "content_and_pixel_verified"
    assert resolved.lineage_depth == 0
    assert resolved.pixel_sha256


def test_historical_recipeless_png_remains_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    desc = _load_desc(root, derived)
    desc.pop("recipe", None)
    desc.pop("recipe_fingerprint", None)
    _write_desc(root, derived, desc)
    resolved = resolve_derived_image_for_read(
        dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=derived
    )
    assert resolved.representation_kind == "stored_bytes"


def test_missing_generic_png_reconstructs_from_assoc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    before = resolve_derived_image_for_read(
        dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=derived
    )
    _unlink_png(root, derived)
    resolved = resolve_derived_image_for_read(
        dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=derived
    )
    assert resolved.representation_kind == "reconstructed_recipe"
    assert resolved.source_identity_posture == "content_and_pixel_verified"
    assert resolved.pixel_sha256 == before.pixel_sha256
    assert resolved.lineage_depth == 1


def test_two_level_chain_reconstructs_with_parent_pixel_posture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    parent = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.8, 0.8]}}
    )
    parent_ref = parent["outputs"]["derived_ref_id"]
    child = handler(
        {
            "ref_id": parent_ref,
            "sub_action": "zoom",
            "params": {"box_norm": [0.0, 0.0, 0.5, 0.5], "factor": 1.0},
        }
    )
    child_ref = child["outputs"]["derived_ref_id"]
    expected = resolve_derived_image_for_read(
        dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=child_ref
    )
    _unlink_png(root, parent_ref)
    _unlink_png(root, child_ref)
    resolved = resolve_derived_image_for_read(
        dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=child_ref
    )
    assert resolved.representation_kind == "reconstructed_recipe"
    assert resolved.pixel_sha256 == expected.pixel_sha256
    assert resolved.lineage_depth == 2
    assert resolved.source_identity_posture == "reconstructed_parent_pixel_verified"


def test_source_content_mismatch_refuses_even_if_pixels_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    _unlink_png(root, derived)
    desc = _load_desc(root, derived)
    recipe = dict(desc["recipe"])
    recipe["source"] = dict(recipe["source"])
    recipe["source"]["content_sha256"] = "f" * 64
    desc["recipe"] = recipe
    desc["recipe_fingerprint"] = recipe_fingerprint(recipe)
    _write_desc(root, derived, desc)
    with pytest.raises(DerivedImageResolutionError) as exc:
        resolve_derived_image_for_read(
            dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=derived
        )
    assert exc.value.code == "source_identity_mismatch"


def test_source_pixel_mode_dimension_mismatch_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, src = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    _unlink_png(root, derived)
    src.write_bytes(_tiny_png_bytes(color=(1, 2, 3)))
    with pytest.raises(DerivedImageResolutionError) as exc:
        resolve_derived_image_for_read(
            dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=derived
        )
    assert exc.value.code == "source_identity_mismatch"


@pytest.mark.parametrize(
    "mutate,code",
    [
        ("fingerprint", "recipe_incoherent"),
        ("descriptor", "recipe_incoherent"),
        ("expected_output", "reconstructed_output_mismatch"),
    ],
)
def test_recipe_gate_mismatches_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutate: str, code: str
) -> None:
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    _unlink_png(root, derived)
    desc = _load_desc(root, derived)
    if mutate == "fingerprint":
        desc["recipe_fingerprint"] = "sha256:" + ("a" * 64)
    elif mutate == "descriptor":
        desc["parent_ref_id"] = "image:derived:" + ("b" * 32)
    else:
        recipe = dict(desc["recipe"])
        recipe["expected_output"] = dict(recipe["expected_output"])
        recipe["expected_output"]["pixel_sha256"] = "c" * 64
        desc["recipe"] = recipe
        desc["recipe_fingerprint"] = recipe_fingerprint(recipe)
    _write_desc(root, derived, desc)
    with pytest.raises(DerivedImageResolutionError) as exc:
        resolve_derived_image_for_read(
            dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=derived
        )
    assert exc.value.code == code


def test_derived_parent_cycle_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    a = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.8, 0.8]}}
    )
    a_ref = a["outputs"]["derived_ref_id"]
    b = handler(
        {"ref_id": a_ref, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    b_ref = b["outputs"]["derived_ref_id"]
    a_desc = _load_desc(root, a_ref)
    b_desc = _load_desc(root, b_ref)
    # Point each at the other while keeping recipe transforms; force cycle via parent/source.
    for desc, other in ((a_desc, b_ref), (b_desc, a_ref)):
        recipe = dict(desc["recipe"])
        recipe["source"] = dict(recipe["source"])
        recipe["source"]["ref_id"] = other
        desc["parent_ref_id"] = other
        desc["recipe"] = recipe
        desc["recipe_fingerprint"] = recipe_fingerprint(recipe)
    _write_desc(root, a_ref, a_desc)
    _write_desc(root, b_ref, b_desc)
    _unlink_png(root, a_ref)
    _unlink_png(root, b_ref)
    with pytest.raises(DerivedImageResolutionError) as exc:
        resolve_derived_image_for_read(
            dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=b_ref
        )
    assert exc.value.code == "lineage_cycle"


def test_lineage_depth_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert MAX_DERIVED_IMAGE_LINEAGE_DEPTH == 32
    import tooling.mapping.transcript_edit.derived_image_resolution as resolution_mod

    bound = 3
    monkeypatch.setattr(resolution_mod, "MAX_DERIVED_IMAGE_LINEAGE_DEPTH", bound)
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    current = ref_id
    refs: list[str] = []
    for _ in range(bound):
        result = handler(
            {
                "ref_id": current,
                "sub_action": "crop",
                "params": {"box_norm": [0.0, 0.0, 0.9, 0.9]},
            }
        )
        assert result["executed"] is True, result
        current = result["outputs"]["derived_ref_id"]
        refs.append(current)
    for r in refs:
        _unlink_png(root, r)
    ok = resolve_derived_image_for_read(
        dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=refs[-1]
    )
    assert ok.lineage_depth == bound

    handler2, ref_id2, root2, _src2 = _make_handler(tmp_path / "depth_over", monkeypatch)
    cur = ref_id2
    refs_over: list[str] = []
    for _ in range(bound + 1):
        result = handler2(
            {
                "ref_id": cur,
                "sub_action": "crop",
                "params": {"box_norm": [0.0, 0.0, 0.9, 0.9]},
            }
        )
        assert result["executed"] is True, result
        cur = result["outputs"]["derived_ref_id"]
        refs_over.append(cur)
    for r in refs_over:
        uid = r.removeprefix("image:derived:")
        (
            root2
            / "artifacts"
            / "transcript_edit"
            / "d1"
            / "tx-1"
            / "ws-1"
            / "derived_images"
            / f"{uid}.png"
        ).unlink()
    with pytest.raises(DerivedImageResolutionError) as exc:
        resolve_derived_image_for_read(
            dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=refs_over[-1]
        )
    assert exc.value.code == "lineage_depth_exceeded"


def test_missing_point_crop_png_does_not_use_generic_recipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
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
    crop_ref = result["outputs"]["crop_set"]["points"][0]["crop_ref"]
    desc = _load_desc(root, crop_ref)
    assert "recipe" not in desc
    _unlink_png(root, crop_ref)
    with pytest.raises(DerivedImageResolutionError) as exc:
        resolve_derived_image_for_read(
            dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=crop_ref
        )
    assert exc.value.code == "recipe_unavailable"


def test_corrupt_stored_png_does_not_fallback_to_recipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    uid = derived.removeprefix("image:derived:")
    png = _derived_dir(root) / f"{uid}.png"
    png.write_bytes(b"not-a-png")
    with pytest.raises(DerivedImageResolutionError) as exc:
        resolve_derived_image_for_read(
            dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=derived
        )
    assert exc.value.code == "stored_image_corrupt"


def test_absolute_path_tampering_cannot_redirect_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    decoy = tmp_path / "decoy.png"
    Image.new("RGB", (10, 10), color=(9, 9, 9)).save(decoy)
    desc = _load_desc(root, derived)
    desc["absolute_path"] = str(decoy)
    _write_desc(root, derived, desc)
    resolved = resolve_derived_image_for_read(
        dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=derived
    )
    assert resolved.representation_kind == "stored_bytes"
    decoy_id = compute_image_identity(path=decoy)
    assert resolved.pixel_sha256 != decoy_id["pixel_sha256"]


def test_resolver_and_audit_are_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    _unlink_png(root, derived)
    before = _snapshot_tree(root)
    resolve_derived_image_for_read(
        dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=derived
    )
    run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    assert _snapshot_tree(root) == before


def test_audit_recipe_only_missing_image_verified_pixel_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    _unlink_png(root, derived)
    report = run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    row = next(a for a in report["artifacts"] if a.get("ref_id") == derived)
    assert row["storage_posture"] == "missing_image"
    assert row["reconstruction_posture"] == "verified_pixel_exact"
    assert row["byte_equal_to_reconstruction"] is None
    assert row["recipe_source"] == "persisted"


def test_historical_recipeless_audit_behavior_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    desc = _load_desc(root, derived)
    desc.pop("recipe", None)
    desc.pop("recipe_fingerprint", None)
    _write_desc(root, derived, desc)
    before = _snapshot_tree(root)
    report = run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    row = next(a for a in report["artifacts"] if a.get("ref_id") == derived)
    assert row["recipe_source"] == "inferred"
    assert row["reconstruction_posture"] == "verified_pixel_exact"
    assert _snapshot_tree(root) == before


def test_descriptor_loader_rejects_ref_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    desc = _load_desc(root, derived)
    desc["ref_id"] = "image:derived:" + ("d" * 32)
    _write_desc(root, derived, desc)
    with pytest.raises(DerivedImageDescriptorError) as exc:
        load_derived_image_descriptor(
            dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=derived
        )
    assert exc.value.code == "descriptor_invalid"
    assert "\\" not in exc.value.message


@pytest.mark.parametrize(
    "stored_ref",
    [pytest.param(None, id="missing_key"), pytest.param("null", id="json_null"), pytest.param(123, id="numeric"), pytest.param("image:derived:" + ("e" * 32), id="mismatched")],
)
def test_caller_supplied_descriptor_ref_id_must_be_exact_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stored_ref: Any
) -> None:
    from tooling.mapping.transcript_edit.derived_image_resolution import (
        reconstruct_generic_from_persisted_recipe,
    )

    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    desc = _load_desc(root, derived)
    if stored_ref == "null":
        desc["ref_id"] = None
    elif stored_ref is None:
        desc.pop("ref_id", None)
    else:
        desc["ref_id"] = stored_ref
    with pytest.raises(DerivedImageResolutionError) as exc:
        reconstruct_generic_from_persisted_recipe(
            dossier_id="d1",
            transcription_id="tx-1",
            workspace_id="ws-1",
            ref_id=derived,
            descriptor=desc,
        )
    assert exc.value.code == "descriptor_invalid"


def test_broken_symlink_png_does_not_fallback_to_recipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows-safe: mock lexists/islink so a broken symlink is not treated as absent bytes."""
    import os
    from pathlib import Path as PathCls

    import tooling.mapping.transcript_edit.derived_image_descriptor as descriptor_mod

    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    png = _derived_dir(root) / f"{derived.removeprefix('image:derived:')}.png"
    assert png.is_file()
    png.unlink()
    assert not png.exists()
    _install_canonical_png_symlink_mocks(monkeypatch, png)

    with pytest.raises(DerivedImageResolutionError) as exc:
        resolve_derived_image_for_read(
            dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1", ref_id=derived
        )
    assert exc.value.code == "stored_image_corrupt"
    assert descriptor_mod.classify_mechanical_derived_image(
        image_path=png, derived_dir=png.parent
    ) == "unsafe"


def _install_canonical_png_symlink_mocks(monkeypatch: pytest.MonkeyPatch, png: Path) -> None:
    """Mock a symlink at *png* without creating a real link (Windows-safe)."""
    import os
    from pathlib import Path as PathCls

    import tooling.mapping.transcript_edit.derived_image_descriptor as descriptor_mod

    target_key = str(png)
    orig_lexists = os.path.lexists
    orig_islink = os.path.islink
    orig_is_symlink = PathCls.is_symlink

    def fake_lexists(path: Any) -> bool:
        if os.fspath(path) == target_key or PathCls(path) == png:
            return True
        return orig_lexists(path)

    def fake_islink(path: Any) -> bool:
        if os.fspath(path) == target_key or PathCls(path) == png:
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


def test_hydration_skips_evidence_for_canonical_png_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tooling.mapping.transcript_edit.artifact_hydration import make_hydrate_artifact_refs_handler

    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    png = _derived_dir(root) / f"{derived.removeprefix('image:derived:')}.png"
    decoy = tmp_path / "outside_hydrate.png"
    Image.new("RGB", (16, 16), color=(4, 5, 6)).save(decoy)
    png.unlink()
    _install_canonical_png_symlink_mocks(monkeypatch, png)

    hydrate = make_hydrate_artifact_refs_handler(
        dossier_id="d1", transcription_id="tx-1", workspace_key="ws-1"
    )
    hydrated = hydrate({"ref_ids": [derived]})
    assert hydrated["executed"] is True
    assert hydrated["outputs"]["hydrated_count"] == 1
    assert not hydrated.get("image_evidence")


def test_transform_refuses_canonical_png_symlink_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    parent = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.8, 0.8]}}
    )
    assert parent["executed"] is True
    parent_ref = parent["outputs"]["derived_ref_id"]
    png = _derived_dir(root) / f"{parent_ref.removeprefix('image:derived:')}.png"
    png.unlink()
    _install_canonical_png_symlink_mocks(monkeypatch, png)

    child = handler(
        {
            "ref_id": parent_ref,
            "sub_action": "crop",
            "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]},
        }
    )
    assert child["executed"] is False
    assert child["refusal"]["reason_code"] == "derived_image_missing"


def test_hydration_ignores_tampered_absolute_path_for_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tooling.mapping.transcript_edit.artifact_hydration import make_hydrate_artifact_refs_handler
    from tooling.mapping.transcript_edit.derived_image_rendering import compute_image_identity

    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    result = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    derived = result["outputs"]["derived_ref_id"]
    canon_png = _derived_dir(root) / f"{derived.removeprefix('image:derived:')}.png"
    before = canon_png.read_bytes()
    decoy = tmp_path / "decoy_hydrate.png"
    Image.new("RGB", (12, 12), color=(1, 2, 3)).save(decoy)
    decoy_id = compute_image_identity(path=decoy)
    desc = _load_desc(root, derived)
    desc["absolute_path"] = str(decoy)
    _write_desc(root, derived, desc)

    hydrate = make_hydrate_artifact_refs_handler(
        dossier_id="d1", transcription_id="tx-1", workspace_key="ws-1"
    )
    hydrated = hydrate({"ref_ids": [derived]})
    assert hydrated["executed"] is True
    evidence = hydrated.get("image_evidence") or []
    assert len(evidence) == 1
    assert evidence[0]["ref_id"] == derived
    # Evidence must come from canonical PNG bytes, not the decoy.
    import base64

    evidence_bytes = base64.b64decode(evidence[0]["b64"])
    assert evidence_bytes == before
    assert compute_image_identity(path=canon_png)["pixel_sha256"] != decoy_id["pixel_sha256"]
    assert canon_png.read_bytes() == before


def test_transform_ignores_tampered_absolute_path_for_chained_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_handler(tmp_path, monkeypatch)
    parent = handler(
        {"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.8, 0.8]}}
    )
    assert parent["executed"] is True
    parent_ref = parent["outputs"]["derived_ref_id"]
    canon_png = _derived_dir(root) / f"{parent_ref.removeprefix('image:derived:')}.png"
    before = canon_png.read_bytes()
    decoy = tmp_path / "decoy_transform.png"
    # Distinct pixels so a redirected transform would produce a different child.
    Image.new("RGB", (80, 64), color=(9, 8, 7)).save(decoy)
    desc = _load_desc(root, parent_ref)
    desc["absolute_path"] = str(decoy)
    _write_desc(root, parent_ref, desc)

    child = handler(
        {
            "ref_id": parent_ref,
            "sub_action": "crop",
            "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]},
        }
    )
    assert child["executed"] is True, child
    child_ref = child["outputs"]["derived_ref_id"]
    child_png = _derived_dir(root) / f"{child_ref.removeprefix('image:derived:')}.png"
    assert child_png.is_file()
    # Canonical parent PNG unchanged; child came from mechanical path, not decoy.
    assert canon_png.read_bytes() == before
    decoy_crop = Image.open(decoy).crop((0, 0, 40, 32))
    decoy_id = compute_image_identity(image=decoy_crop)
    child_id = compute_image_identity(path=child_png)
    assert child_id["pixel_sha256"] != decoy_id["pixel_sha256"]
