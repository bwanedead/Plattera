"""STORAGE-BR-009: read-only derived-image cache reclamation planning."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

import config.paths as paths_mod
import tooling.mapping.transcript_edit.derived_image_descriptor as descriptor_mod
import tooling.mapping.transcript_edit.paths as te_paths_mod
from tooling.mapping.transcript_edit.artifact_transform import make_transform_artifact_handler
from tooling.mapping.transcript_edit.derived_image_reclamation_plan import (
    RECLAMATION_POSTURE,
    SCHEMA_VERSION,
    build_derived_image_reclamation_plan,
    run_derived_image_reclamation_plan,
)
from tooling.mapping.transcript_edit.derived_image_storage_audit import (
    StorageAuditScopeError,
    run_derived_image_storage_audit,
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


def _crop(handler, ref_id: str) -> str:
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0, 0, 0.5, 0.5]}})
    assert result["executed"] is True
    return result["outputs"]["derived_ref_id"]


def _assert_plan_accounting(plan: dict[str, Any]) -> None:
    examined = plan["examined_count"]
    candidates = plan["candidate_count"]
    retained = plan["retained_count"]
    assert examined == candidates + retained
    assert sum(plan["reason_counts"].values()) == retained
    assert plan["retained_run_owned_count"] <= retained


def _assert_no_absolute_paths(payload: dict[str, Any]) -> None:
    blob = json.dumps(payload)
    assert "absolute_path" not in blob
    assert ":\\" not in blob
    assert ":/" not in blob or "transcript_edit" in blob  # relative posix only


def test_verified_generic_run_owned_becomes_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    derived = _crop(handler, ref_id)
    plan = run_derived_image_reclamation_plan(dossier_id="d1", workspace_id="ws-1")
    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["authorization_posture"] == "planning_only"
    assert plan["apply_supported"] is False
    assert plan["candidate_count"] >= 1
    refs = {c["ref_id"] for c in plan["candidates"]}
    assert derived in refs
    row = next(c for c in plan["candidates"] if c["ref_id"] == derived)
    assert row["reclamation_posture"] == RECLAMATION_POSTURE
    assert row["relative_image_path"]
    assert row["relative_descriptor_path"]
    assert row["size_bytes"] > 0
    _assert_plan_accounting(plan)
    _assert_no_absolute_paths(plan)


def test_referenced_verified_generic_remains_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    derived = _crop(handler, ref_id)
    working = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "working"
    working.mkdir(parents=True, exist_ok=True)
    (working / "rev_0001.json").write_text(
        json.dumps({"primary_evidence_ref": derived, "context_refs": [derived]}),
        encoding="utf-8",
    )
    plan = run_derived_image_reclamation_plan(dossier_id="d1", workspace_id="ws-1")
    row = next((c for c in plan["candidates"] if c["ref_id"] == derived), None)
    assert row is not None
    assert row["reference_posture"] == "externally_referenced"
    assert row["reclamation_posture"] == RECLAMATION_POSTURE


def test_canonical_and_legacy_images_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path, monkeypatch)
    original = root / "images" / "original"
    original.mkdir(parents=True)
    (original / "deed.png").write_bytes(_png_bytes())
    (original / "deed_derived_b034cdf9.png").write_bytes(_png_bytes(color=(1, 2, 3)))
    plan = run_derived_image_reclamation_plan(dossier_id="d1", all_dossiers=False)
    candidate_paths = {c.get("relative_image_path") for c in plan["candidates"]}
    assert not any(p and "deed.png" in p for p in candidate_paths)
    assert not any(p and "deed_derived_b034cdf9.png" in p for p in candidate_paths)
    assert plan["reason_counts"].get("canonical_or_legacy_source", 0) >= 2


def test_point_crop_family_excluded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    result = handler(
        {
            "ref_id": ref_id,
            "sub_action": "point_crops",
            "params": {
                "points": [{"alias": "a", "point_norm": [0.4, 0.5], "size": "medium", "shape": "wide"}]
            },
        }
    )
    assert result["executed"] is True
    master = result["outputs"]["derived_ref_id"]
    plan = run_derived_image_reclamation_plan(dossier_id="d1", workspace_id="ws-1")
    assert master not in {c["ref_id"] for c in plan["candidates"]}
    assert plan["reason_counts"].get("point_crop_family", 0) >= 1


def test_orphan_and_conflicting_identities_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    derived = _crop(handler, ref_id)
    uuid = derived.removeprefix("image:derived:")
    di = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "derived_images"
    orphan = di / ("b" * 32 + ".png")
    orphan.write_bytes(_png_bytes(color=(5, 6, 7)))
    other_stem = "c" * 32
    src_png = di / f"{uuid}.png"
    moved = di / f"{other_stem}.png"
    moved.write_bytes(src_png.read_bytes())
    src_png.unlink()
    desc = json.loads((di / f"{uuid}.json").read_text(encoding="utf-8"))
    desc["absolute_path"] = str(moved.resolve())
    (di / f"{uuid}.json").write_text(json.dumps(desc), encoding="utf-8")

    plan = run_derived_image_reclamation_plan(dossier_id="d1", workspace_id="ws-1")
    assert derived not in {c["ref_id"] for c in plan["candidates"]}
    assert plan["reason_counts"].get("missing_descriptor_or_orphan", 0) >= 1
    assert plan["reason_counts"].get("conflicting_or_ambiguous_identity", 0) >= 1


def test_missing_unsafe_symlink_corrupt_pngs_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    d_missing = _crop(handler, ref_id)
    d_corrupt = _crop(handler, ref_id)
    d_symlink = _crop(handler, ref_id)
    d_unsafe = _crop(handler, ref_id)
    di = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "derived_images"

    (di / f"{d_missing.removeprefix('image:derived:')}.png").unlink()
    corrupt_png = di / f"{d_corrupt.removeprefix('image:derived:')}.png"
    corrupt_png.write_bytes(b"not-a-png")

    symlink_png = di / f"{d_symlink.removeprefix('image:derived:')}.png"
    _install_png_symlink_mocks(monkeypatch, symlink_png)

    unsafe_uuid = d_unsafe.removeprefix("image:derived:")
    other = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-other" / "derived_images"
    other.mkdir(parents=True)
    moved = other / f"{unsafe_uuid}.png"
    moved.write_bytes((di / f"{unsafe_uuid}.png").read_bytes())
    desc = json.loads((di / f"{unsafe_uuid}.json").read_text(encoding="utf-8"))
    desc["absolute_path"] = str(moved.resolve())
    (di / f"{unsafe_uuid}.json").write_text(json.dumps(desc), encoding="utf-8")
    (di / f"{unsafe_uuid}.png").unlink()

    plan = run_derived_image_reclamation_plan(dossier_id="d1", workspace_id="ws-1")
    refs = {c["ref_id"] for c in plan["candidates"]}
    assert d_missing not in refs
    assert d_corrupt not in refs
    assert d_symlink not in refs
    assert d_unsafe not in refs
    reasons = plan["reason_counts"]
    assert reasons.get("missing_png", 0) >= 1
    unsafe_reasons = {
        "unsafe_or_unreadable_png",
        "missing_or_invalid_pixel_sha256",
        "missing_or_invalid_physical_size",
        "resolver_verification_failed",
        "reconstruction_not_verified_pixel_exact",
    }
    assert any(reasons.get(r, 0) >= 1 for r in unsafe_reasons)
    assert reasons.get("external_or_unsafe_path", 0) >= 1


def _install_png_symlink_mocks(monkeypatch: pytest.MonkeyPatch, png: Path) -> None:
    """Windows-safe: mock symlink at *png* without creating a real link."""
    PathCls = type(png)
    orig_lexists = os.path.lexists
    orig_islink = os.path.islink
    orig_is_symlink = PathCls.is_symlink
    target = os.fspath(png)

    def fake_lexists(path: Any) -> bool:
        if os.fspath(path) == target:
            return True
        return orig_lexists(path)

    def fake_islink(path: Any) -> bool:
        if os.fspath(path) == target:
            return True
        return orig_islink(path)

    def fake_is_symlink(self: PathCls) -> bool:
        if os.fspath(self) == target:
            return True
        return orig_is_symlink(self)

    monkeypatch.setattr(os.path, "lexists", fake_lexists)
    monkeypatch.setattr(os.path, "islink", fake_islink)
    monkeypatch.setattr(PathCls, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(descriptor_mod.os.path, "islink", fake_islink)


def test_invalid_recipe_and_pixel_mismatch_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    d_recipeless = _crop(handler, ref_id)
    d_bad_recipe = _crop(handler, ref_id)
    d_mismatch = _crop(handler, ref_id)
    di = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "derived_images"

    recipeless_path = di / f"{d_recipeless.removeprefix('image:derived:')}.json"
    recipeless = json.loads(recipeless_path.read_text(encoding="utf-8"))
    recipeless.pop("recipe", None)
    recipeless.pop("recipe_fingerprint", None)
    recipeless_path.write_text(json.dumps(recipeless), encoding="utf-8")

    bad_path = di / f"{d_bad_recipe.removeprefix('image:derived:')}.json"
    bad = json.loads(bad_path.read_text(encoding="utf-8"))
    bad["recipe"] = {"broken": True}
    bad["recipe_fingerprint"] = "sha256:" + ("0" * 64)
    bad_path.write_text(json.dumps(bad), encoding="utf-8")

    mismatch_png = di / f"{d_mismatch.removeprefix('image:derived:')}.png"
    img = Image.open(mismatch_png)
    img.load()
    corrupted = Image.new("RGB", img.size, color=(1, 1, 1))
    buf = io.BytesIO()
    corrupted.save(buf, format="PNG")
    mismatch_png.write_bytes(buf.getvalue())

    plan = run_derived_image_reclamation_plan(dossier_id="d1", workspace_id="ws-1")
    refs = {c["ref_id"] for c in plan["candidates"]}
    assert d_recipeless not in refs
    assert d_bad_recipe not in refs
    assert d_mismatch not in refs
    reasons = plan["reason_counts"]
    assert reasons.get("recipe_not_persisted", 0) >= 1
    assert reasons.get("pixel_mismatch", 0) >= 1


def test_descriptor_missing_durable_content_sha256_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    derived = _crop(handler, ref_id)
    desc_path = (
        root
        / "artifacts"
        / "transcript_edit"
        / "d1"
        / "tx-1"
        / "ws-1"
        / "derived_images"
        / f"{derived.removeprefix('image:derived:')}.json"
    )
    desc = json.loads(desc_path.read_text(encoding="utf-8"))
    desc.pop("content_sha256", None)
    desc_path.write_text(json.dumps(desc), encoding="utf-8")

    plan = run_derived_image_reclamation_plan(dossier_id="d1", workspace_id="ws-1")
    assert derived not in {c["ref_id"] for c in plan["candidates"]}
    assert plan["reason_counts"].get("descriptor_missing_durable_content_sha256", 0) >= 1


def test_candidate_bytes_equal_physical_png_bytes_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    derived = _crop(handler, ref_id)
    di = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "derived_images"
    png_path = di / f"{derived.removeprefix('image:derived:')}.png"
    physical = png_path.stat().st_size

    plan = run_derived_image_reclamation_plan(dossier_id="d1", workspace_id="ws-1")
    row = next(c for c in plan["candidates"] if c["ref_id"] == derived)
    assert row["size_bytes"] == physical
    assert plan["candidate_count"] == 1
    assert plan["candidate_bytes"] == physical
    _assert_plan_accounting(plan)


def test_detail_caps_do_not_change_totals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    for _ in range(3):
        _crop(handler, ref_id)
    full = run_derived_image_reclamation_plan(dossier_id="d1", workspace_id="ws-1", max_candidates=500)
    capped = run_derived_image_reclamation_plan(dossier_id="d1", workspace_id="ws-1", max_candidates=1)
    assert capped["candidate_count"] == full["candidate_count"]
    assert capped["candidate_bytes"] == full["candidate_bytes"]
    assert len(capped["candidates"]) == 1
    assert capped["candidates_omitted_count"] == full["candidate_count"] - 1


def test_plan_and_cli_are_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    _crop(handler, ref_id)
    before = _snapshot_tree(root)
    run_derived_image_reclamation_plan(dossier_id="d1", workspace_id="ws-1")
    from tooling.mapping.transcript_edit.plan_derived_image_reclamation import main as plan_main

    assert plan_main(["--dossier-id", "d1", "--workspace-id", "ws-1"]) == 0
    assert _snapshot_tree(root) == before


def test_cli_scope_refusal_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tooling.mapping.transcript_edit.plan_derived_image_reclamation import main

    _root(tmp_path, monkeypatch)
    assert main([]) == 2
    assert main(["--dossier-id", "d1", "--all-dossiers"]) == 2
    assert main(["--dossier-id", "d1", "--max-candidates", "-1"]) == 2


def test_audit_may_embed_reclamation_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    _crop(handler, ref_id)
    report = run_derived_image_storage_audit(
        dossier_id="d1",
        workspace_id="ws-1",
        include_reclamation_plan=True,
        max_reclamation_candidates=10,
    )
    plan = report["reclamation_plan"]
    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["candidate_count"] >= 1
    blob = json.dumps(report)
    assert "safe_to_delete" not in blob
    assert "deletable" not in blob


def test_build_plan_from_records_unit_exclusions() -> None:
    """Synthetic rows: totals and reason_counts without filesystem resolver."""
    base = {
        "storage_posture": "run_owned",
        "reconstruction_posture": "verified_pixel_exact",
        "recipe_source": "persisted",
        "sub_action": "crop",
        "size_bytes": 100,
        "content_sha256": "a" * 64,
        "pixel_sha256": "b" * 64,
        "ref_id": "image:derived:" + ("1" * 32),
        "relative_image_path": "x.png",
        "relative_descriptor_path": "x.json",
        "_dossier_id": "d1",
        "_tx_id": "tx-1",
        "_ws_id": "ws-1",
        "_obj": {"content_sha256": "a" * 64},
    }
    records = [
        dict(base),
        {**base, "storage_posture": "canonical_source", "ref_id": None},
        {**base, "storage_posture": "missing_descriptor", "ref_id": None},
    ]
    plan = build_derived_image_reclamation_plan(records, max_candidates=0)
    assert plan["examined_count"] == 3
    assert plan["candidate_count"] == 0  # resolver fails without real paths
    assert plan["retained_count"] == 3
    assert plan["reason_counts"].get("canonical_or_legacy_source") == 1
    assert plan["reason_counts"].get("missing_descriptor_or_orphan") == 1
    assert plan["reason_counts"].get("descriptor_unsafe_or_absent") == 1
    assert plan["retained_run_owned_count"] == 1
    _assert_plan_accounting(plan)


def test_scope_error_propagates() -> None:
    with pytest.raises(StorageAuditScopeError) as exc:
        run_derived_image_reclamation_plan()
    assert exc.value.code == "scope_missing"


def test_plan_accounting_invariants_mixed_record_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    candidate = _crop(handler, ref_id)
    point_crop = handler(
        {
            "ref_id": ref_id,
            "sub_action": "point_crops",
            "params": {
                "points": [{"alias": "a", "point_norm": [0.4, 0.5], "size": "medium", "shape": "wide"}]
            },
        }
    )["outputs"]["derived_ref_id"]
    original = root / "images" / "original"
    (original / "deed.png").write_bytes(_png_bytes())
    (original / "deed_derived_b034cdf9.png").write_bytes(_png_bytes(color=(1, 2, 3)))
    di = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "derived_images"
    (di / ("d" * 32 + ".png")).write_bytes(_png_bytes(color=(9, 9, 9)))

    plan = run_derived_image_reclamation_plan(dossier_id="d1", workspace_id="ws-1")
    _assert_plan_accounting(plan)
    assert plan["candidate_count"] >= 1
    assert candidate in {c["ref_id"] for c in plan["candidates"]}
    assert point_crop not in {c["ref_id"] for c in plan["candidates"]}
    assert plan["reason_counts"].get("canonical_or_legacy_source", 0) >= 2
    assert plan["reason_counts"].get("missing_descriptor_or_orphan", 0) >= 1
    assert plan["reason_counts"].get("point_crop_family", 0) >= 1
    assert plan["retained_run_owned_count"] >= 1


def test_audit_ignores_reclamation_bounds_when_plan_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, ref_id, root, _src = _make_transform(tmp_path, monkeypatch)
    _crop(handler, ref_id)
    report = run_derived_image_storage_audit(
        dossier_id="d1",
        workspace_id="ws-1",
        include_reclamation_plan=False,
        max_reclamation_candidates=-1,
    )
    assert "reclamation_plan" not in report

    with pytest.raises(StorageAuditScopeError) as exc:
        run_derived_image_storage_audit(
            dossier_id="d1",
            workspace_id="ws-1",
            include_reclamation_plan=True,
            max_reclamation_candidates=-1,
        )
    assert exc.value.code == "bounds_invalid"
