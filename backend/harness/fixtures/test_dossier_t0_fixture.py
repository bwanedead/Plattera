"""Focused tests for generic dossier T0 fixture freeze tooling."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from harness.fixtures.dossier_t0_fixture import (
    CONFLICT_REASON,
    DossierT0FixtureError,
    FreezePlan,
    SegmentSpec,
    file_fingerprint,
    freeze_dossier_t0_fixture,
    sha256_file,
    validate_fixture_integrity,
    write_fixture_set_manifest,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _tree_fingerprint(root: Path) -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        fp = file_fingerprint(path)
        out[rel] = (fp["sha256"], fp["byte_length"])
    return out


def _build_synthetic_dossier(tmp_path: Path, *, with_head_part1: bool = True) -> tuple[Path, Path, Path, FreezePlan]:
    dossiers_root = tmp_path / "dossiers_data"
    destination_root = tmp_path / "fixtures"
    dossier_id = "11111111-2222-3333-4444-555555555555"
    images = tmp_path / "images"
    images.mkdir(parents=True)

    img1 = images / "page1.jpg"
    img2 = images / "page2.jpg"
    img1.write_bytes(b"synthetic-page-1-bytes")
    img2.write_bytes(b"synthetic-page-2-bytes-xx")
    hash1 = sha256_file(img1)
    hash2 = sha256_file(img2)

    assoc = {
        "dossier_id": dossier_id,
        "associations": [
            {
                "transcription_id": "draft_page1",
                "position": 1,
                "metadata": {
                    "processing_params": {
                        "model": "gpt-o4-mini",
                        "extraction_mode": "legal_document_json",
                        "redundancy_count": 3,
                    },
                    "provenance": {"source": {"file_hash": hash1}},
                },
            },
            {
                "transcription_id": "draft_page2",
                "position": 2,
                "metadata": {
                    "processing_params": {
                        "model": "gpt-o4-mini",
                        "extraction_mode": "legal_document_json",
                        "redundancy_count": 3,
                    },
                    "provenance": {"source": {"file_hash": hash2}},
                },
            },
        ],
    }
    _write_json(dossiers_root / "associations" / f"assoc_{dossier_id}.json", assoc)

    tx1 = dossiers_root / "views" / "transcriptions" / dossier_id / "draft_page1"
    tx2 = dossiers_root / "views" / "transcriptions" / dossier_id / "draft_page2"
    for tx, stem in ((tx1, "draft_page1"), (tx2, "draft_page2")):
        _write_json(
            tx / "run.json",
            {
                "status": "completed",
                "processing_params": {
                    "model": "gpt-o4-mini",
                    "extraction_mode": "legal_document_json",
                    "redundancy_count": 3,
                },
            },
        )
        _write_json(tx / "raw" / f"{stem}_v1.json", {"text": f"{stem}-v1"})
        _write_json(tx / "raw" / f"{stem}_v2.json", {"text": f"{stem}-v2"})
        # Downstream artifacts that must never be copied.
        _write_json(tx / "consensus" / f"llm_{stem}.json", {"consensus": True})
        _write_json(tx / "alignment" / "draft_1.json", {"alignment": True})
        (tx / "final").mkdir(parents=True, exist_ok=True)
        _write_json(tx / "final" / "selected.json", {"final": True})

    if with_head_part1:
        _write_json(tx1 / "head.json", {"raw": {"head": "v1"}})
    # tx2 intentionally has no head.json

    plan = FreezePlan(
        dossiers_root=dossiers_root,
        destination_root=destination_root,
        fixture_id="synthetic_two_segment",
        dossier_id=dossier_id,
        segments=(
            SegmentSpec(
                position=1,
                transcription_id="draft_page1",
                source_image_path=img1,
                source_sha256=hash1,
                source_fixture_name="page1.jpg",
            ),
            SegmentSpec(
                position=2,
                transcription_id="draft_page2",
                source_image_path=img2,
                source_sha256=hash2,
                source_fixture_name="page2.jpg",
            ),
        ),
    )
    return dossiers_root, destination_root, img1, plan


def test_freeze_synthetic_two_segment_preserves_order_and_allowlist(tmp_path: Path) -> None:
    dossiers_root, destination_root, _img1, plan = _build_synthetic_dossier(tmp_path)
    before = _tree_fingerprint(dossiers_root)

    result = freeze_dossier_t0_fixture(plan)
    assert result.outcome == "created"
    assert result.segment_count == 2
    assert result.fixture_dir == destination_root / "synthetic_two_segment"

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "dossier_t0_fixture.v1"
    assert [s["transcription_id"] for s in manifest["segments"]] == [
        "draft_page1",
        "draft_page2",
    ]
    assert [s["position"] for s in manifest["segments"]] == [1, 2]
    assert manifest["segments"][0]["t0_head_ref"] == "t0/draft_page1/head.json"
    assert manifest["segments"][1]["t0_head_ref"] is None
    assert manifest["segments"][0]["model"] == "gpt-o4-mini"
    assert manifest["segments"][0]["extraction_mode"] == "legal_document_json"
    assert manifest["segments"][0]["redundancy_count"] == 3

    fixture_dir = result.fixture_dir
    assert (fixture_dir / "source" / "page1.jpg").is_file()
    assert (fixture_dir / "t0" / "draft_page1" / "run.json").is_file()
    assert (fixture_dir / "t0" / "draft_page1" / "head.json").is_file()
    assert (fixture_dir / "t0" / "draft_page1" / "raw" / "draft_page1_v1.json").is_file()
    assert not (fixture_dir / "t0" / "draft_page2" / "head.json").exists()
    assert not (fixture_dir / "t0" / "draft_page1" / "consensus").exists()
    assert not (fixture_dir / "t0" / "draft_page1" / "alignment").exists()
    assert not (fixture_dir / "t0" / "draft_page1" / "final").exists()
    assert not (fixture_dir / "t0" / "draft_page2" / "consensus").exists()

    assert _tree_fingerprint(dossiers_root) == before


def test_exact_source_hash_validation(tmp_path: Path) -> None:
    _dossiers_root, _destination_root, _img1, plan = _build_synthetic_dossier(tmp_path)
    bad = SegmentSpec(
        position=plan.segments[0].position,
        transcription_id=plan.segments[0].transcription_id,
        source_image_path=plan.segments[0].source_image_path,
        source_sha256="0" * 64,
        source_fixture_name=plan.segments[0].source_fixture_name,
    )
    bad_plan = FreezePlan(
        dossiers_root=plan.dossiers_root,
        destination_root=plan.destination_root,
        fixture_id=plan.fixture_id,
        dossier_id=plan.dossier_id,
        segments=(bad, plan.segments[1]),
    )
    with pytest.raises(DossierT0FixtureError) as exc:
        freeze_dossier_t0_fixture(bad_plan)
    assert exc.value.reason == "dossier_t0_fixture_source_hash_mismatch"


def test_optional_missing_head_without_synthesis(tmp_path: Path) -> None:
    _dossiers_root, _destination_root, _img1, plan = _build_synthetic_dossier(
        tmp_path, with_head_part1=False
    )
    result = freeze_dossier_t0_fixture(plan)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert all(segment["t0_head_ref"] is None for segment in manifest["segments"])
    assert not (result.fixture_dir / "t0" / "draft_page1" / "head.json").exists()
    assert not (result.fixture_dir / "t0" / "draft_page2" / "head.json").exists()


def test_manifest_relative_path_containment_and_hash_coverage(tmp_path: Path) -> None:
    _dossiers_root, _destination_root, _img1, plan = _build_synthetic_dossier(tmp_path)
    result = freeze_dossier_t0_fixture(plan)
    manifest = validate_fixture_integrity(result.fixture_dir)
    refs = {entry["ref"] for entry in manifest["files"]}
    for entry in manifest["files"]:
        assert ".." not in entry["ref"]
        assert not entry["ref"].startswith("/")
        assert ":\\" not in entry["ref"]
        path = result.fixture_dir.joinpath(*entry["ref"].split("/"))
        fp = file_fingerprint(path)
        assert fp["sha256"] == entry["sha256"]
        assert fp["byte_length"] == entry["byte_length"]
    for segment in manifest["segments"]:
        assert segment["source_ref"] in refs
        assert segment["t0_run_ref"] in refs
        if segment["t0_head_ref"] is not None:
            assert segment["t0_head_ref"] in refs
        for raw_ref in segment["t0_raw_refs"]:
            assert raw_ref in refs


def test_reject_absolute_and_traversal_refs_on_validate(tmp_path: Path) -> None:
    _dossiers_root, destination_root, _img1, plan = _build_synthetic_dossier(tmp_path)
    result = freeze_dossier_t0_fixture(plan)
    manifest_path = result.manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["segments"][0]["source_ref"] = "C:/tmp/evil.jpg"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DossierT0FixtureError) as exc:
        validate_fixture_integrity(result.fixture_dir)
    assert exc.value.reason in {
        "dossier_t0_fixture_absolute_path",
        "dossier_t0_fixture_invalid_ref",
        "dossier_t0_fixture_ref_set_mismatch",
        "dossier_t0_fixture_missing_file",
    }

    # Restore a traversal case on a fresh freeze destination.
    shutil.rmtree(result.fixture_dir)
    result2 = freeze_dossier_t0_fixture(
        FreezePlan(
            dossiers_root=plan.dossiers_root,
            destination_root=destination_root / "alt",
            fixture_id=plan.fixture_id,
            dossier_id=plan.dossier_id,
            segments=plan.segments,
        )
    )
    manifest2 = json.loads(result2.manifest_path.read_text(encoding="utf-8"))
    manifest2["segments"][0]["source_ref"] = "../outside.jpg"
    result2.manifest_path.write_text(json.dumps(manifest2), encoding="utf-8")
    with pytest.raises(DossierT0FixtureError) as exc2:
        validate_fixture_integrity(result2.fixture_dir)
    assert exc2.value.reason in {
        "dossier_t0_fixture_path_traversal",
        "dossier_t0_fixture_invalid_ref",
        "dossier_t0_fixture_ref_set_mismatch",
        "dossier_t0_fixture_missing_file",
    }


def test_identical_replay_is_noop(tmp_path: Path) -> None:
    dossiers_root, _destination_root, _img1, plan = _build_synthetic_dossier(tmp_path)
    first = freeze_dossier_t0_fixture(plan)
    before_fixture = _tree_fingerprint(first.fixture_dir)
    before_source = _tree_fingerprint(dossiers_root)
    second = freeze_dossier_t0_fixture(plan)
    assert second.outcome == "idempotent_replay"
    assert _tree_fingerprint(first.fixture_dir) == before_fixture
    assert _tree_fingerprint(dossiers_root) == before_source


def test_conflicting_existing_fixture_refused(tmp_path: Path) -> None:
    _dossiers_root, _destination_root, img1, plan = _build_synthetic_dossier(tmp_path)
    freeze_dossier_t0_fixture(plan)
    other_img = tmp_path / "images" / "other.jpg"
    other_img.write_bytes(b"different-bytes-for-conflict")
    conflict_plan = FreezePlan(
        dossiers_root=plan.dossiers_root,
        destination_root=plan.destination_root,
        fixture_id=plan.fixture_id,
        dossier_id="99999999-9999-9999-9999-999999999999",
        segments=(
            SegmentSpec(
                position=1,
                transcription_id="draft_page1",
                source_image_path=img1,
                source_sha256=sha256_file(img1),
                source_fixture_name="page1.jpg",
            ),
            plan.segments[1],
        ),
    )
    with pytest.raises(DossierT0FixtureError) as exc:
        freeze_dossier_t0_fixture(conflict_plan)
    assert exc.value.reason == CONFLICT_REASON


def test_malformed_association_refused(tmp_path: Path) -> None:
    dossiers_root, destination_root, _img1, plan = _build_synthetic_dossier(tmp_path)
    bad_assoc = dossiers_root / "associations" / f"assoc_{plan.dossier_id}.json"
    _write_json(bad_assoc, {"dossier_id": plan.dossier_id, "associations": "nope"})
    with pytest.raises(DossierT0FixtureError) as exc:
        freeze_dossier_t0_fixture(plan)
    assert exc.value.reason == "dossier_t0_fixture_malformed_associations"


def test_duplicate_positions_and_transcription_ids_refused(tmp_path: Path) -> None:
    _dossiers_root, _destination_root, img1, plan = _build_synthetic_dossier(tmp_path)
    dup_pos = FreezePlan(
        dossiers_root=plan.dossiers_root,
        destination_root=plan.destination_root,
        fixture_id="dup_pos",
        dossier_id=plan.dossier_id,
        segments=(
            plan.segments[0],
            SegmentSpec(
                position=1,
                transcription_id="draft_page2",
                source_image_path=plan.segments[1].source_image_path,
                source_sha256=plan.segments[1].source_sha256,
                source_fixture_name="page2.jpg",
            ),
        ),
    )
    with pytest.raises(DossierT0FixtureError) as exc:
        freeze_dossier_t0_fixture(dup_pos)
    assert exc.value.reason == "dossier_t0_fixture_duplicate_position"

    dup_tid = FreezePlan(
        dossiers_root=plan.dossiers_root,
        destination_root=plan.destination_root,
        fixture_id="dup_tid",
        dossier_id=plan.dossier_id,
        segments=(
            plan.segments[0],
            SegmentSpec(
                position=2,
                transcription_id="draft_page1",
                source_image_path=plan.segments[1].source_image_path,
                source_sha256=plan.segments[1].source_sha256,
                source_fixture_name="page2.jpg",
            ),
        ),
    )
    with pytest.raises(DossierT0FixtureError) as exc2:
        freeze_dossier_t0_fixture(dup_tid)
    assert exc2.value.reason == "dossier_t0_fixture_duplicate_transcription_id"


def test_segment_order_mismatch_refused(tmp_path: Path) -> None:
    _dossiers_root, _destination_root, _img1, plan = _build_synthetic_dossier(tmp_path)
    swapped = FreezePlan(
        dossiers_root=plan.dossiers_root,
        destination_root=plan.destination_root,
        fixture_id="swapped",
        dossier_id=plan.dossier_id,
        segments=(
            SegmentSpec(
                position=1,
                transcription_id="draft_page2",
                source_image_path=plan.segments[1].source_image_path,
                source_sha256=plan.segments[1].source_sha256,
                source_fixture_name="page2.jpg",
            ),
            SegmentSpec(
                position=2,
                transcription_id="draft_page1",
                source_image_path=plan.segments[0].source_image_path,
                source_sha256=plan.segments[0].source_sha256,
                source_fixture_name="page1.jpg",
            ),
        ),
    )
    with pytest.raises(DossierT0FixtureError) as exc:
        freeze_dossier_t0_fixture(swapped)
    assert exc.value.reason == "dossier_t0_fixture_segment_order_mismatch"


def test_fixture_set_manifest_lists_without_dependency_claim(tmp_path: Path) -> None:
    _dossiers_root, destination_root, _img1, plan = _build_synthetic_dossier(tmp_path)
    freeze_dossier_t0_fixture(plan)
    # Second synthetic fixture by copying destination under another id via second freeze root.
    plan_b = FreezePlan(
        dossiers_root=plan.dossiers_root,
        destination_root=destination_root,
        fixture_id="synthetic_b",
        dossier_id=plan.dossier_id,
        segments=plan.segments,
    )
    # Reuse same source dossier under a different fixture id (allowed for set listing test).
    freeze_dossier_t0_fixture(plan_b)
    path = write_fixture_set_manifest(
        destination_root=destination_root,
        fixture_ids=["synthetic_two_segment", "synthetic_b"],
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "dossier_t0_fixture_set.v1"
    assert [f["fixture_id"] for f in payload["fixtures"]] == [
        "synthetic_two_segment",
        "synthetic_b",
    ]
    blob = json.dumps(payload)
    assert "depend" not in blob.lower()
    assert "parent" not in blob.lower()
    assert "child" not in blob.lower()


def test_partial_staging_not_left_as_valid_fixture(tmp_path: Path) -> None:
    dossiers_root, destination_root, _img1, plan = _build_synthetic_dossier(tmp_path)
    # Remove run.json so materialize fails after staging starts.
    run_path = (
        dossiers_root
        / "views"
        / "transcriptions"
        / plan.dossier_id
        / "draft_page2"
        / "run.json"
    )
    run_path.unlink()
    with pytest.raises(DossierT0FixtureError):
        freeze_dossier_t0_fixture(plan)
    assert not (destination_root / plan.fixture_id).exists()
    leftovers = list(destination_root.glob(".__building__*")) + list(
        destination_root.glob(".synthetic_two_segment.__building__*")
    )
    assert leftovers == []


def _assoc_path(plan: FreezePlan) -> Path:
    return plan.dossiers_root / "associations" / f"assoc_{plan.dossier_id}.json"


def test_provenance_hash_missing_malformed_and_mismatched(tmp_path: Path) -> None:
    dossiers_root, _destination_root, _img1, plan = _build_synthetic_dossier(tmp_path)
    assoc_path = _assoc_path(plan)

    payload = json.loads(assoc_path.read_text(encoding="utf-8"))
    del payload["associations"][0]["metadata"]["provenance"]
    _write_json(assoc_path, payload)
    with pytest.raises(DossierT0FixtureError) as missing:
        freeze_dossier_t0_fixture(plan)
    assert missing.value.reason == "dossier_t0_fixture_missing_provenance_hash"

    dossiers_root, _destination_root, _img1, plan = _build_synthetic_dossier(tmp_path / "malformed")
    assoc_path = _assoc_path(plan)
    payload = json.loads(assoc_path.read_text(encoding="utf-8"))
    payload["associations"][0]["metadata"]["provenance"]["source"]["file_hash"] = "not-a-hash"
    _write_json(assoc_path, payload)
    with pytest.raises(DossierT0FixtureError) as malformed:
        freeze_dossier_t0_fixture(plan)
    assert malformed.value.reason == "dossier_t0_fixture_malformed_provenance_hash"

    dossiers_root, _destination_root, _img1, plan = _build_synthetic_dossier(tmp_path / "mismatch")
    assoc_path = _assoc_path(plan)
    payload = json.loads(assoc_path.read_text(encoding="utf-8"))
    payload["associations"][0]["metadata"]["provenance"]["source"]["file_hash"] = "ab" * 32
    _write_json(assoc_path, payload)
    with pytest.raises(DossierT0FixtureError) as mismatched:
        freeze_dossier_t0_fixture(plan)
    assert mismatched.value.reason == "dossier_t0_fixture_provenance_hash_mismatch"


def test_undeclared_extra_files_rejected(tmp_path: Path) -> None:
    _dossiers_root, _destination_root, _img1, plan = _build_synthetic_dossier(tmp_path)
    result = freeze_dossier_t0_fixture(plan)
    extra = result.fixture_dir / "t0" / "draft_page1" / "consensus.json"
    extra.write_text("{}", encoding="utf-8")
    with pytest.raises(DossierT0FixtureError) as exc:
        validate_fixture_integrity(result.fixture_dir)
    assert exc.value.reason in {
        "dossier_t0_fixture_undeclared_files",
        "dossier_t0_fixture_allowlist_violation",
    }


def test_manifest_rejects_coerced_and_unexpected_types(tmp_path: Path) -> None:
    _dossiers_root, _destination_root, _img1, plan = _build_synthetic_dossier(tmp_path)
    result = freeze_dossier_t0_fixture(plan)
    manifest_path = result.manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    bad = json.loads(json.dumps(manifest))
    bad["segments"][0]["position"] = True
    manifest_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(DossierT0FixtureError) as exc:
        validate_fixture_integrity(result.fixture_dir)
    assert exc.value.reason == "dossier_t0_fixture_malformed_manifest"

    bad = json.loads(json.dumps(manifest))
    bad["files"][0]["byte_length"] = "123"
    manifest_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(DossierT0FixtureError):
        validate_fixture_integrity(result.fixture_dir)

    bad = json.loads(json.dumps(manifest))
    bad["segments"][0]["source_sha256"] = "zz" * 32
    manifest_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(DossierT0FixtureError):
        validate_fixture_integrity(result.fixture_dir)

    bad = json.loads(json.dumps(manifest))
    bad["segments"][0]["model"] = ""
    manifest_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(DossierT0FixtureError):
        validate_fixture_integrity(result.fixture_dir)

    bad = json.loads(json.dumps(manifest))
    bad["segments"][0]["redundancy_count"] = 0
    manifest_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(DossierT0FixtureError):
        validate_fixture_integrity(result.fixture_dir)

    bad = json.loads(json.dumps(manifest))
    bad["segments"] = list(reversed(bad["segments"]))
    # keep positions swapped relative to list order
    manifest_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(DossierT0FixtureError) as order_exc:
        validate_fixture_integrity(result.fixture_dir)
    assert order_exc.value.reason == "dossier_t0_fixture_invalid_segment_order"

    bad = json.loads(json.dumps(manifest))
    bad["extra_field"] = True
    manifest_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(DossierT0FixtureError) as unexpected:
        validate_fixture_integrity(result.fixture_dir)
    assert unexpected.value.reason == "dossier_t0_fixture_unexpected_manifest_field"


def test_set_manifest_replay_is_no_write(tmp_path: Path) -> None:
    _dossiers_root, destination_root, _img1, plan = _build_synthetic_dossier(tmp_path)
    freeze_dossier_t0_fixture(plan)
    path = write_fixture_set_manifest(
        destination_root=destination_root,
        fixture_ids=["synthetic_two_segment"],
    )
    before = path.read_bytes()
    mtime = path.stat().st_mtime_ns
    path2 = write_fixture_set_manifest(
        destination_root=destination_root,
        fixture_ids=["synthetic_two_segment"],
    )
    assert path2 == path
    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == mtime


def test_segment_source_hash_must_match_files_entry(tmp_path: Path) -> None:
    _dossiers_root, _destination_root, _img1, plan = _build_synthetic_dossier(tmp_path)
    result = freeze_dossier_t0_fixture(plan)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    other = "ab" * 32
    manifest["segments"][0]["source_sha256"] = other
    # Keep files[].sha256 unchanged so both remain valid hex independently.
    result.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DossierT0FixtureError) as exc:
        validate_fixture_integrity(result.fixture_dir)
    assert exc.value.reason == "dossier_t0_fixture_source_hash_mismatch"


def test_duplicate_declared_refs_rejected(tmp_path: Path) -> None:
    _dossiers_root, _destination_root, _img1, plan = _build_synthetic_dossier(tmp_path)
    result = freeze_dossier_t0_fixture(plan)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    raw_ref = manifest["segments"][0]["t0_raw_refs"][0]
    manifest["segments"][0]["t0_raw_refs"].append(raw_ref)
    result.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DossierT0FixtureError) as exc:
        validate_fixture_integrity(result.fixture_dir)
    assert exc.value.reason == "dossier_t0_fixture_duplicate_ref"

    result2 = freeze_dossier_t0_fixture(
        FreezePlan(
            dossiers_root=plan.dossiers_root,
            destination_root=plan.destination_root / "dup_source",
            fixture_id=plan.fixture_id,
            dossier_id=plan.dossier_id,
            segments=plan.segments,
        )
    )
    manifest2 = json.loads(result2.manifest_path.read_text(encoding="utf-8"))
    manifest2["segments"][1]["source_ref"] = manifest2["segments"][0]["source_ref"]
    result2.manifest_path.write_text(json.dumps(manifest2), encoding="utf-8")
    with pytest.raises(DossierT0FixtureError) as exc2:
        validate_fixture_integrity(result2.fixture_dir)
    assert exc2.value.reason == "dossier_t0_fixture_duplicate_ref"


def test_set_manifest_rejects_traversal_absolute_duplicate_and_bad_ref(
    tmp_path: Path,
) -> None:
    _dossiers_root, destination_root, _img1, plan = _build_synthetic_dossier(tmp_path)
    freeze_dossier_t0_fixture(plan)

    with pytest.raises(DossierT0FixtureError) as trav:
        write_fixture_set_manifest(
            destination_root=destination_root,
            fixture_ids=["../outside"],
        )
    assert trav.value.reason == "dossier_t0_fixture_invalid_plan"

    absolute = str((tmp_path / "abs_id").resolve())
    with pytest.raises(DossierT0FixtureError) as abs_exc:
        write_fixture_set_manifest(
            destination_root=destination_root,
            fixture_ids=[absolute],
        )
    assert abs_exc.value.reason == "dossier_t0_fixture_invalid_plan"

    with pytest.raises(DossierT0FixtureError) as dup:
        write_fixture_set_manifest(
            destination_root=destination_root,
            fixture_ids=["synthetic_two_segment", "synthetic_two_segment"],
        )
    assert dup.value.reason == "dossier_t0_fixture_duplicate_fixture_id"

    # Mismatched member ref: mutate via validate_set_manifest_payload surface.
    from harness.fixtures.dossier_t0_fixture_manifest import (
        build_set_manifest_payload,
        validate_set_manifest_payload,
    )

    payload = build_set_manifest_payload(["synthetic_two_segment"])
    payload["fixtures"][0]["manifest_ref"] = "other/fixture_manifest.json"
    with pytest.raises(DossierT0FixtureError) as mismatch:
        validate_set_manifest_payload(payload)
    assert mismatch.value.reason == "dossier_t0_fixture_set_member_ref_mismatch"
