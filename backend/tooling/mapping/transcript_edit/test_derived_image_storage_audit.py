"""STORAGE-BR-004: read-only derived-image reconstruction and reference audit."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

import config.paths as paths_mod
import tooling.mapping.transcript_edit.paths as te_paths_mod
from tooling.mapping.transcript_edit.artifact_transform import make_transform_artifact_handler
from tooling.mapping.transcript_edit.derived_image_recipe import (
    RENDERER_ID as RECIPE_RENDERER_ID,
)
from tooling.mapping.transcript_edit.derived_image_rendering import (
    GENERIC_SUB_ACTIONS,
    RENDERER_ID,
    compute_image_identity,
    render_generic_derived_image,
)
from tooling.mapping.transcript_edit.derived_image_storage_audit import (
    SCHEMA_VERSION,
    StorageAuditScopeError,
    run_derived_image_storage_audit,
)
from tooling.mapping.transcript_edit.dossier_artifact_refs import qualify_leaf_ref

_RECONSTRUCTION_POSTURES = frozenset(
    {
        "verified_pixel_exact",
        "verified_pixel_mismatch",
        "not_attempted_missing_source",
        "not_attempted_incomplete_recipe",
        "not_attempted_unsupported_sub_action",
        "not_attempted_renderer_unknown",
        "render_failed",
        "stored_image_unreadable",
    }
)
_REFERENCE_POSTURES = frozenset(
    {
        "externally_referenced",
        "descriptor_only",
        "unreferenced_observed",
        "reference_ambiguous",
    }
)


def _root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "dossiers_data"
    root.mkdir()
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    return root


def _png_bytes(w: int = 100, h: int = 80, color: tuple[int, int, int] = (200, 200, 200)) -> bytes:
    img = Image.new("RGB", (w, h), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _write_assoc(root: Path, d: str, tx: str, image_path: Path) -> None:
    assoc_dir = root / "associations"
    assoc_dir.mkdir(parents=True, exist_ok=True)
    (assoc_dir / f"assoc_{d}.json").write_text(
        json.dumps(
            {
                "associations": [
                    {
                        "transcription_id": tx,
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


def _make_transform(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, d="d1", tx="tx-1", ws="ws-1"):
    root = _root(tmp_path, monkeypatch)
    original_dir = root / "images" / "original"
    original_dir.mkdir(parents=True)
    img = original_dir / "scan.png"
    img.write_bytes(_png_bytes())
    _write_assoc(root, d, tx, img)
    handler = make_transform_artifact_handler(dossier_id=d, transcription_id=tx, workspace_key=ws)
    return handler, f"image:assoc:{tx}:original", root, img


def _snapshot_tree(root: Path) -> dict[str, tuple[bytes, int]]:
    out: dict[str, tuple[bytes, int]] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            out[rel] = (p.read_bytes(), p.stat().st_mtime_ns)
    return out


def _assert_complete_postures(report: dict[str, Any]) -> None:
    for a in report["artifacts"]:
        assert a["reconstruction_posture"] in _RECONSTRUCTION_POSTURES
        assert a["reference_posture"] in _REFERENCE_POSTURES


_GENERIC_CASES = [
    ("crop", {"box_norm": [0.0, 0.0, 0.5, 0.5]}),
    ("zoom", {"factor": 1.5}),
    ("expand", {"padding": [2, 2, 2, 2]}),
    ("reference_overlay", {"cols": 3, "rows": 3}),
    (
        "annotate",
        {"annotations": [{"type": "bbox", "box_norm": [0.1, 0.1, 0.4, 0.4], "color": [255, 0, 0]}]},
    ),
    (
        "render_evidence_locators",
        {
            "locators": [
                {
                    "ref_id": "image:assoc:tx-1:original",
                    "locator_kind": "image_region",
                    "label": "r",
                    "box_norm": [0.1, 0.2, 0.4, 0.5],
                }
            ]
        },
    ),
]


def test_renderer_identity_single_owner() -> None:
    assert RECIPE_RENDERER_ID == RENDERER_ID == "transcript_edit.pillow.v1"
    assert GENERIC_SUB_ACTIONS == frozenset(
        {"crop", "zoom", "expand", "reference_overlay", "annotate", "render_evidence_locators"}
    )


@pytest.mark.parametrize("sub_action,params", _GENERIC_CASES, ids=[c[0] for c in _GENERIC_CASES])
def test_generic_reconstruction_verified_pixel_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sub_action: str, params: dict[str, Any]
) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    if sub_action == "render_evidence_locators":
        params = {
            "locators": [
                {
                    "ref_id": ref_id,
                    "locator_kind": "image_region",
                    "label": "r",
                    "box_norm": [0.1, 0.2, 0.4, 0.5],
                }
            ]
        }
    result = handler({"ref_id": ref_id, "sub_action": sub_action, "params": params})
    assert result["executed"] is True
    report = run_derived_image_storage_audit(dossier_id="d1", transcription_id="tx-1", workspace_id="ws-1")
    assert report["schema_version"] == SCHEMA_VERSION
    _assert_complete_postures(report)
    derived = result["outputs"]["derived_ref_id"]
    rows = [a for a in report["artifacts"] if a.get("ref_id") == derived]
    assert len(rows) == 1
    assert rows[0]["storage_posture"] == "run_owned"
    assert rows[0]["reconstruction_posture"] == "verified_pixel_exact"
    assert rows[0]["recipe_source"] == "persisted"
    assert rows[0]["recipe_fingerprint"] and rows[0]["recipe_fingerprint"].startswith("sha256:")
    # Pixel match must not be mislabeled as byte equality.
    assert rows[0]["byte_equal_to_reconstruction"] in {True, False, None}


def test_pixel_versus_byte_identity(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    img = Image.new("RGB", (40, 30), color=(10, 20, 30))
    img.save(a, format="PNG", optimize=False)
    img.save(b, format="PNG", optimize=True, compress_level=9)
    ia = compute_image_identity(path=a)
    ib = compute_image_identity(path=b)
    assert ia["pixel_sha256"] == ib["pixel_sha256"]
    assert ia["width_height"] == ib["width_height"]
    c = tmp_path / "c.png"
    Image.new("RGB", (40, 30), color=(99, 99, 99)).save(c, format="PNG")
    ic = compute_image_identity(path=c)
    assert ic["pixel_sha256"] != ia["pixel_sha256"]
    d = tmp_path / "d.png"
    d.write_bytes(a.read_bytes())
    assert compute_image_identity(path=d)["content_sha256"] == ia["content_sha256"]


def test_audit_pixel_exact_byte_equal_false_when_encoding_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pixel-exact reconstruction with intentionally different stored PNG encoding."""
    import hashlib

    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    params = {"box_norm": [0, 0, 0.5, 0.5]}
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": params})
    derived = result["outputs"]["derived_ref_id"]
    derived_dir = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "derived_images"
    uuid = derived.removeprefix("image:derived:")
    png = derived_dir / f"{uuid}.png"

    recon = render_generic_derived_image(
        root / "images" / "original" / "scan.png",
        "crop",
        params,
        source_ref_id=ref_id,
    )
    default_buf = io.BytesIO()
    recon.image.save(default_buf, format="PNG")
    default_bytes = default_buf.getvalue()
    alt_bytes = None
    for compress_level, optimize in ((1, False), (9, True), (0, False), (5, True)):
        buf = io.BytesIO()
        recon.image.save(buf, format="PNG", compress_level=compress_level, optimize=optimize)
        candidate = buf.getvalue()
        if candidate != default_bytes:
            alt_bytes = candidate
            break
    assert alt_bytes is not None, "need a PNG encoding distinct from audit default encode"
    png.write_bytes(alt_bytes)
    assert hashlib.sha256(alt_bytes).hexdigest() != hashlib.sha256(default_bytes).hexdigest()
    assert compute_image_identity(path=png)["pixel_sha256"] == compute_image_identity(
        image=recon.image
    )["pixel_sha256"]

    report = run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    row = next(a for a in report["artifacts"] if a.get("ref_id") == derived)
    assert row["reconstruction_posture"] == "verified_pixel_exact"
    assert row["byte_equal_to_reconstruction"] is False


def test_parent_cycle_a_to_b_to_a(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    a = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0, 0, 0.8, 0.8]}})
    assert a["executed"] is True
    a_ref = a["outputs"]["derived_ref_id"]
    b = handler({"ref_id": a_ref, "sub_action": "crop", "params": {"box_norm": [0, 0, 0.5, 0.5]}})
    assert b["executed"] is True
    b_ref = b["outputs"]["derived_ref_id"]
    derived_dir = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "derived_images"
    a_uuid = a_ref.removeprefix("image:derived:")
    b_uuid = b_ref.removeprefix("image:derived:")
    a_desc_path = derived_dir / f"{a_uuid}.json"
    b_desc_path = derived_dir / f"{b_uuid}.json"
    a_desc = json.loads(a_desc_path.read_text(encoding="utf-8"))
    b_desc = json.loads(b_desc_path.read_text(encoding="utf-8"))
    a_desc["parent_ref_id"] = b_ref
    b_desc["parent_ref_id"] = a_ref
    a_desc_path.write_text(json.dumps(a_desc), encoding="utf-8")
    b_desc_path.write_text(json.dumps(b_desc), encoding="utf-8")

    report = run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    by_ref = {row["ref_id"]: row for row in report["artifacts"] if row.get("ref_id")}
    assert by_ref[a_ref]["reconstruction_posture"] == "not_attempted_incomplete_recipe"
    assert by_ref[b_ref]["reconstruction_posture"] == "not_attempted_incomplete_recipe"
    assert any(d.get("code") == "parent_cycle_detected" for d in report["diagnostics"])


def test_harness_shaped_structural_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0, 0, 0.5, 0.5]}})
    derived = result["outputs"]["derived_ref_id"]
    working = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "working"
    working.mkdir(parents=True, exist_ok=True)
    (working / "rev_0001.json").write_text(
        json.dumps(
            {
                "primary_evidence_ref": derived,
                "context_refs": [derived],
                "latest_refs": {"focus": derived},
                "prose": f"ignore {derived} here",
            }
        ),
        encoding="utf-8",
    )
    report = run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    row = next(a for a in report["artifacts"] if a.get("ref_id") == derived)
    assert row["reference_posture"] == "externally_referenced"


def test_descriptor_png_stem_mismatch_is_conflicting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0, 0, 0.5, 0.5]}})
    derived = result["outputs"]["derived_ref_id"]
    uuid = derived.removeprefix("image:derived:")
    di = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "derived_images"
    other_stem = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    src_png = di / f"{uuid}.png"
    moved = di / f"{other_stem}.png"
    moved.write_bytes(src_png.read_bytes())
    src_png.unlink()
    desc = json.loads((di / f"{uuid}.json").read_text(encoding="utf-8"))
    desc["absolute_path"] = str(moved.resolve())
    (di / f"{uuid}.json").write_text(json.dumps(desc), encoding="utf-8")
    report = run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    row = next(a for a in report["artifacts"] if a.get("ref_id") == derived)
    assert row["storage_posture"] == "conflicting_identity"
    assert row["reference_posture"] == "reference_ambiguous"
    assert any(
        d.get("code") == "conflicting_descriptor_image_identity" for d in report["diagnostics"]
    )


def test_chained_lineage_and_missing_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    parent = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.8, 0.8]}})
    assert parent["executed"] is True
    parent_ref = parent["outputs"]["derived_ref_id"]
    child = handler(
        {"ref_id": parent_ref, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}}
    )
    assert child["executed"] is True
    report = run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    _assert_complete_postures(report)
    by_ref = {a["ref_id"]: a for a in report["artifacts"] if a.get("ref_id")}
    assert by_ref[parent_ref]["reconstruction_posture"] == "verified_pixel_exact"
    assert by_ref[child["outputs"]["derived_ref_id"]]["reconstruction_posture"] == "verified_pixel_exact"

    derived_dir = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "derived_images"
    parent_png = derived_dir / f"{parent_ref.removeprefix('image:derived:')}.png"
    parent_png.unlink()
    report2 = run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    by_ref2 = {a["ref_id"]: a for a in report2["artifacts"] if a.get("ref_id")}
    child_row = by_ref2[child["outputs"]["derived_ref_id"]]
    assert child_row["reconstruction_posture"] in {
        "not_attempted_missing_source",
        "stored_image_unreadable",
        "render_failed",
    }


def test_point_crop_master_unsupported_crop_reconstructable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    result = handler(
        {
            "ref_id": ref_id,
            "sub_action": "point_crops",
            "params": {
                "points": [
                    {"alias": "a", "point_norm": [0.4, 0.5], "size": "medium", "shape": "wide"}
                ]
            },
        }
    )
    assert result["executed"] is True
    master = result["outputs"]["derived_ref_id"]
    report = run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    _assert_complete_postures(report)
    master_row = next(a for a in report["artifacts"] if a.get("ref_id") == master)
    assert master_row["reconstruction_posture"] == "not_attempted_unsupported_sub_action"
    assert master_row["sub_action"] == "point_crops"
    # Production point_crops_crop rows carry zoom materialization → unsupported, not guessed.
    crop_rows = [a for a in report["artifacts"] if a.get("sub_action") == "point_crops_crop"]
    assert crop_rows
    assert all(
        a["reconstruction_posture"] == "not_attempted_unsupported_sub_action" for a in crop_rows
    )

    # Mechanically reconstructable: plain box_px crop with no zoom, geometry on transform_metadata.
    derived_dir = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "derived_images"
    simple_uuid = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    simple_ref = f"image:derived:{simple_uuid}"
    src = Image.open(root / "images" / "original" / "scan.png")
    src.load()
    cropped = src.crop((10, 10, 40, 30))
    cropped.save(derived_dir / f"{simple_uuid}.png")
    (derived_dir / f"{simple_uuid}.json").write_text(
        json.dumps(
            {
                "ref_id": simple_ref,
                "parent_ref_id": ref_id,
                "sub_action": "point_crops_crop",
                "params": {"parent_point_alias": "plain"},
                "absolute_path": str((derived_dir / f"{simple_uuid}.png").resolve()),
                "transform_metadata": {
                    "box_px": [10, 10, 40, 30],
                    "zoom_factor": 1.0,
                    "output_width_height": [30, 20],
                },
            }
        ),
        encoding="utf-8",
    )
    report2 = run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    simple_row = next(a for a in report2["artifacts"] if a.get("ref_id") == simple_ref)
    assert simple_row["reconstruction_posture"] == "verified_pixel_exact"



def test_prose_reference_does_not_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0, 0, 0.5, 0.5]}})
    derived = result["outputs"]["derived_ref_id"]
    working = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "working"
    working.mkdir(parents=True, exist_ok=True)
    (working / "rev_0001.json").write_text(
        json.dumps({"note": f"uses {derived}", "near": derived.replace("derived", "derivd")}),
        encoding="utf-8",
    )
    (working / "prose.json").write_text(
        json.dumps({"text": f"mention {derived} in prose without a ref field"}),
        encoding="utf-8",
    )
    report = run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    row = next(a for a in report["artifacts"] if a.get("ref_id") == derived)
    assert row["reference_posture"] == "descriptor_only"


def test_qualified_structural_reference_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0, 0, 0.5, 0.5]}})
    derived = result["outputs"]["derived_ref_id"]
    qualified = qualify_leaf_ref(
        segment_id="seg_a", transcription_id="tx-1", leaf_ref=derived
    )
    working = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "working"
    working.mkdir(parents=True, exist_ok=True)
    (working / "rev_0001.json").write_text(
        json.dumps({"artifact_refs": [qualified], "derived_ref_id": qualified}),
        encoding="utf-8",
    )
    report = run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    row = next(a for a in report["artifacts"] if a.get("ref_id") == derived)
    assert row["reference_posture"] == "externally_referenced"
    assert row["reference_source_kind"] == "workspace_working"


def test_legacy_eight_hex_and_complete_postures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path, monkeypatch)
    original = root / "images" / "original"
    original.mkdir(parents=True)
    canon = original / "deed.png"
    canon.write_bytes(_png_bytes())
    # Production pattern: exactly 8 hex chars (not 32).
    legacy = original / "deed_derived_b034cdf9.png"
    legacy.write_bytes(_png_bytes(color=(1, 2, 3)))
    # 32-hex must NOT be treated as the legacy writer pattern.
    not_legacy = original / ("deed_derived_" + ("a" * 32) + ".png")
    not_legacy.write_bytes(_png_bytes(color=(4, 5, 6)))
    report = run_derived_image_storage_audit(dossier_id="d1", all_dossiers=False)
    _assert_complete_postures(report)
    by_name = {}
    for a in report["artifacts"]:
        rel = a.get("relative_image_path") or ""
        by_name[Path(rel).name] = a
    assert by_name["deed.png"]["storage_posture"] == "canonical_source"
    assert by_name["deed_derived_b034cdf9.png"]["storage_posture"] == "legacy_source_adjacent"
    assert by_name[not_legacy.name]["storage_posture"] == "canonical_source"
    for a in report["artifacts"]:
        assert a["reconstruction_posture"] is not None
        assert a["reference_posture"] is not None


def test_cross_workspace_descriptor_image_is_unsafe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0, 0, 0.5, 0.5]}})
    derived = result["outputs"]["derived_ref_id"]
    uuid = derived.removeprefix("image:derived:")
    di = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "derived_images"
    other = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-other" / "derived_images"
    other.mkdir(parents=True)
    png = di / f"{uuid}.png"
    moved = other / f"{uuid}.png"
    moved.write_bytes(png.read_bytes())
    desc = json.loads((di / f"{uuid}.json").read_text(encoding="utf-8"))
    desc["absolute_path"] = str(moved.resolve())
    (di / f"{uuid}.json").write_text(json.dumps(desc), encoding="utf-8")
    png.unlink()
    report = run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    row = next(a for a in report["artifacts"] if a.get("ref_id") == derived)
    assert row["storage_posture"] == "external_or_unsafe"
    _assert_complete_postures(report)


def test_report_honesty_and_bounds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0, 0, 0.5, 0.5]}})
    report = run_derived_image_storage_audit(
        dossier_id="d1",
        workspace_id="ws-1",
        max_artifacts=0,
        max_duplicate_groups=0,
        max_diagnostics=0,
    )
    assert report["summary"]["observed_image_count"] >= 1
    assert report["artifacts"] == []
    assert report["artifacts_omitted_count"] >= 1
    blob = json.dumps(report)
    assert "safe_to_delete" not in blob
    assert "deletable" not in blob
    assert "absolute_path" not in blob
    assert "b64" not in blob.lower()


def test_audit_is_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    handler({"ref_id": ref_id, "sub_action": "zoom", "params": {"factor": 1.0}})
    before = _snapshot_tree(root)
    run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    after = _snapshot_tree(root)
    assert after == before


def test_historical_recipeless_descriptor_audits_without_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-recipe descriptors remain auditable; audit must not rewrite them."""
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0, 0, 0.5, 0.5]}})
    derived = result["outputs"]["derived_ref_id"]
    uuid = derived.removeprefix("image:derived:")
    di = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "derived_images"
    desc_path = di / f"{uuid}.json"
    desc = json.loads(desc_path.read_text(encoding="utf-8"))
    desc.pop("recipe", None)
    desc.pop("recipe_fingerprint", None)
    desc_path.write_text(json.dumps(desc, ensure_ascii=False, indent=2), encoding="utf-8")
    before_bytes = desc_path.read_bytes()
    before_mtime = desc_path.stat().st_mtime_ns
    before_tree = _snapshot_tree(root)

    report = run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    row = next(a for a in report["artifacts"] if a.get("ref_id") == derived)
    assert row["recipe_source"] in {"inferred", "unavailable"}
    assert row["reconstruction_posture"] == "verified_pixel_exact"
    assert desc_path.read_bytes() == before_bytes
    assert desc_path.stat().st_mtime_ns == before_mtime
    assert _snapshot_tree(root) == before_tree


def test_malformed_persisted_recipe_emits_diagnostic_and_stays_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0, 0, 0.5, 0.5]}})
    derived = result["outputs"]["derived_ref_id"]
    uuid = derived.removeprefix("image:derived:")
    di = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "derived_images"
    desc_path = di / f"{uuid}.json"
    desc = json.loads(desc_path.read_text(encoding="utf-8"))
    desc["recipe"] = {"broken": True, "schema_version": "nope"}
    desc["recipe_fingerprint"] = "sha256:" + ("0" * 64)
    desc_path.write_text(json.dumps(desc, ensure_ascii=False, indent=2), encoding="utf-8")
    before = _snapshot_tree(root)

    report = run_derived_image_storage_audit(dossier_id="d1", workspace_id="ws-1")
    row = next(a for a in report["artifacts"] if a.get("ref_id") == derived)
    assert row["recipe_source"] == "persisted"
    assert any(
        str(d.get("code") or "").startswith("persisted_recipe_") for d in report["diagnostics"]
    )
    assert _snapshot_tree(root) == before


def test_scope_refusal_without_dossier_or_all() -> None:
    with pytest.raises(StorageAuditScopeError) as exc:
        run_derived_image_storage_audit()
    assert exc.value.code == "scope_missing"


def test_scope_refusal_dossier_and_all() -> None:
    with pytest.raises(StorageAuditScopeError) as exc:
        run_derived_image_storage_audit(dossier_id="d1", all_dossiers=True)
    assert exc.value.code == "scope_conflict"


def test_bounds_refusal_negative() -> None:
    with pytest.raises(StorageAuditScopeError) as exc:
        run_derived_image_storage_audit(dossier_id="d1", max_artifacts=-1)
    assert exc.value.code == "bounds_invalid"


def test_cli_scope_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tooling.mapping.transcript_edit.audit_derived_image_storage import main

    _root(tmp_path, monkeypatch)
    assert main([]) == 2
