"""Integrity tests for stable upstream transcript-edit lineage fixture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from domains.mapping.deed_to_ir.test_fixtures.corrupted_handoff_fixture import (
    _SOURCE_EVIDENCE_REF,
    extract_target_evidence_ref,
    normal_fixture_root,
    variant_fixture_root,
)
from domains.mapping.deed_to_ir.test_fixtures.transcript_edit_lineage_fixture import (
    _EXPECTED_CROP_WIDTH_HEIGHT,
    _MIN_REAL_PNG_BYTES,
    critical_descriptor_path,
    critical_evidence_ref,
    critical_png_path,
    is_fake_test_png,
    load_critical_descriptor,
    load_lineage_manifest,
    restore_critical_evidence_to_destination,
    sha256_file,
    source_image_path,
    transcript_edit_lineage_fixture_root,
)

_FIXTURE_ROOT = transcript_edit_lineage_fixture_root()
_MANIFEST = _FIXTURE_ROOT / "fixture_manifest.json"
_NORMAL_DEED_IR = normal_fixture_root()
_SOURCE_REPAIR = variant_fixture_root("corrupted_handoff_source_repair")

pytestmark = pytest.mark.skipif(
    not _MANIFEST.is_file(),
    reason="local transcript-edit lineage backup fixture is intentionally git-ignored",
)


def test_lineage_fixture_directory_and_required_files_exist() -> None:
    assert _FIXTURE_ROOT.is_dir()
    for rel in (
        "fixture_manifest.json",
        "transcript_edit_output.json",
        "resolution_state.json",
        "source/draft_legal_text_image_original.jpg",
        "evidence/derived_images/fba6f159e40d4010896245d6525d4acf.json",
        "evidence/derived_images/fba6f159e40d4010896245d6525d4acf.png",
    ):
        assert (_FIXTURE_ROOT / rel).is_file(), rel


def test_lineage_manifest_hashes_and_counts_match_files() -> None:
    manifest = load_lineage_manifest()
    files = manifest["files"]

    assert manifest["schema_version"] == "transcript_edit_upstream_lineage_fixture.v1"
    assert manifest["source_upstream_run_id"] == "practice-row-live-20260619-76"
    assert manifest["dossier_id"] == "9f5eecb6-cd7e-483c-b691-b76aa7132e8e"
    assert manifest["transcription_id"] == "draft_legal_text_image"
    assert manifest["critical_evidence_refs"][0]["ref_id"] == critical_evidence_ref()

    for rel, meta in files.items():
        path = _FIXTURE_ROOT / rel
        assert sha256_file(path) == meta["sha256"]
        assert path.stat().st_size == meta["byte_length"]

    resolution = json.loads((_FIXTURE_ROOT / "resolution_state.json").read_text(encoding="utf-8"))
    items = resolution.get("items", [])
    relations = resolution.get("relations", [])
    covered = sum(len(i.get("covered_units", [])) for i in items if isinstance(i, dict))
    res_meta = files["resolution_state.json"]
    assert len(items) == res_meta["item_count"]
    assert len(relations) == res_meta["relation_count"]
    assert covered == res_meta["covered_unit_count"]


def test_lineage_source_image_has_expected_dimensions_when_pil_available() -> None:
    pytest.importorskip("PIL")
    from PIL import Image

    with Image.open(source_image_path()) as im:
        assert im.width >= 1000
        assert im.height >= 1000


def test_lineage_critical_crop_is_real_not_fake_test_png() -> None:
    png = critical_png_path()
    assert png.stat().st_size >= _MIN_REAL_PNG_BYTES
    assert not is_fake_test_png(png)

    desc = load_critical_descriptor()
    assert desc["ref_id"] == critical_evidence_ref()
    assert desc["params"]["parent_point_alias"] == "p1_call2_distance"
    assert tuple(desc["width_height"]) == _EXPECTED_CROP_WIDTH_HEIGHT
    assert desc["transform_metadata"]["alias"] == "p1_call2_distance"

    pytest.importorskip("PIL")
    from PIL import Image

    with Image.open(png) as im:
        assert (im.width, im.height) == _EXPECTED_CROP_WIDTH_HEIGHT


def test_normal_deed_to_ir_fixture_still_loads_separately() -> None:
    deed_manifest = json.loads((_NORMAL_DEED_IR / "fixture_manifest.json").read_text(encoding="utf-8"))
    assert deed_manifest["source_upstream_run_id"] == "practice-row-live-20260619-76"
    assert (_NORMAL_DEED_IR / "transcript_edit_output.json").is_file()
    assert sha256_file(_NORMAL_DEED_IR / "transcript_edit_output.json") == deed_manifest["files"][
        "transcript_edit_output.json"
    ]["sha256"]


def test_corrupted_source_repair_references_same_critical_evidence_ref() -> None:
    assert extract_target_evidence_ref(_SOURCE_REPAIR) == _SOURCE_EVIDENCE_REF
    assert _SOURCE_EVIDENCE_REF == critical_evidence_ref()


def test_restore_helper_copies_critical_evidence_to_temp_destination(tmp_path: Path) -> None:
    dest = tmp_path / "derived_images"
    result = restore_critical_evidence_to_destination(destination_derived_dir=dest)
    assert result["restored"] is True
    assert (dest / "fba6f159e40d4010896245d6525d4acf.png").is_file()
    desc = json.loads((dest / "fba6f159e40d4010896245d6525d4acf.json").read_text(encoding="utf-8"))
    assert desc["absolute_path"] == str((dest / "fba6f159e40d4010896245d6525d4acf.png").resolve())
    assert desc["size_bytes"] >= _MIN_REAL_PNG_BYTES


def test_live_restore_requires_explicit_flag() -> None:
    from domains.mapping.deed_to_ir.test_fixtures.transcript_edit_lineage_fixture import (
        restore_critical_evidence_to_live_artifacts,
    )

    with pytest.raises(ValueError, match="allow_live_restore_required"):
        restore_critical_evidence_to_live_artifacts(
            dossier_id="9f5eecb6-cd7e-483c-b691-b76aa7132e8e",
            transcription_id="draft_legal_text_image",
            workspace_id="practice-row-live-20260619-76",
        )
