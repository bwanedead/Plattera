"""Corrupted deed-to-IR handoff fixture variant integrity and launch contract tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from domains.mapping.deed_to_ir.runtime_adapter import build_deed_to_ir_runtime_adapter
from domains.mapping.deed_to_ir.test_fixtures.corrupted_handoff_fixture import (
    _CORRUPTION_UNIT_ID,
    assert_contradiction_variant_operand_differs_from_source_lanes,
    corrupted_fixture_root,
    extract_corrupted_operand_value,
    find_resolution_unit,
    iter_covered_units,
    load_fixture_manifest,
    load_resolution_state,
    load_transcript_edit_output,
    normal_fixture_root,
)

_NORMAL_MANIFEST = normal_fixture_root() / "fixture_manifest.json"
_NORMAL_TRANSCRIPT = normal_fixture_root() / "transcript_edit_output.json"
_NORMAL_RESOLUTION = normal_fixture_root() / "resolution_state.json"
_CORRUPTED_ROOT = corrupted_fixture_root()
_CORRUPTED_MANIFEST = _CORRUPTED_ROOT / "fixture_manifest.json"
_CORRUPTED_TRANSCRIPT = _CORRUPTED_ROOT / "transcript_edit_output.json"
_CORRUPTED_RESOLUTION = _CORRUPTED_ROOT / "resolution_state.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _corrupted_launch_context(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "dossier_id": "9f5eecb6-cd7e-483c-b691-b76aa7132e8e",
        "transcription_id": "draft_legal_text_image",
        "run_id": "deed-to-ir-corrupted-test",
        "workspace_id": "deed-to-ir-corrupted-test",
        "max_iterations": 3,
        "transcript_edit_output_path": str(_CORRUPTED_TRANSCRIPT),
        "resolution_state_ref": "transcript_edit:resolution_state:practice-row-live-20260619-76",
        "resolution_state_snapshot_path": str(_CORRUPTED_RESOLUTION),
    }
    base.update(overrides)
    return base


def test_normal_frozen_fixture_still_exists_and_unchanged() -> None:
    assert _NORMAL_MANIFEST.is_file()
    assert _NORMAL_TRANSCRIPT.is_file()
    assert _NORMAL_RESOLUTION.is_file()

    manifest = json.loads(_NORMAL_MANIFEST.read_text(encoding="utf-8"))
    files = manifest["files"]
    assert _sha256(_NORMAL_TRANSCRIPT) == files["transcript_edit_output.json"]["sha256"]
    assert _sha256(_NORMAL_RESOLUTION) == files["resolution_state.json"]["sha256"]
    assert "fixture_variant" not in manifest


def test_corrupted_fixture_exists_with_required_files() -> None:
    for name in (
        "fixture_manifest.json",
        "transcript_edit_output.json",
        "resolution_state.json",
    ):
        assert (_CORRUPTED_ROOT / name).is_file(), name


def test_corrupted_manifest_labels_fixture_variant() -> None:
    manifest = load_fixture_manifest()
    assert manifest["fixture_variant"] == "corrupted_handoff_call_distance"
    assert "test fixture variant" in manifest["fixture_variant_label"].lower()
    assert manifest["derived_from_fixture"] == "practice_deeds/right_of_way/deed_to_ir"
    assert manifest["corruption_target"]["unit_id"] == _CORRUPTION_UNIT_ID


def test_corrupted_fixture_json_is_valid() -> None:
    load_fixture_manifest()
    load_transcript_edit_output()
    load_resolution_state()


def test_corrupted_manifest_hashes_and_counts_match_files() -> None:
    manifest = load_fixture_manifest()
    files = manifest["files"]

    assert _sha256(_CORRUPTED_TRANSCRIPT) == files["transcript_edit_output.json"]["sha256"]
    assert _CORRUPTED_TRANSCRIPT.stat().st_size == files["transcript_edit_output.json"]["byte_length"]

    assert _sha256(_CORRUPTED_RESOLUTION) == files["resolution_state.json"]["sha256"]
    assert _CORRUPTED_RESOLUTION.stat().st_size == files["resolution_state.json"]["byte_length"]

    resolution = load_resolution_state()
    items = resolution.get("items") if isinstance(resolution.get("items"), list) else []
    relations = resolution.get("relations") if isinstance(resolution.get("relations"), list) else []
    covered_units = sum(
        len(item.get("covered_units"))
        for item in items
        if isinstance(item, dict) and isinstance(item.get("covered_units"), list)
    )
    assert len(items) == files["resolution_state.json"]["item_count"]
    assert len(relations) == files["resolution_state.json"]["relation_count"]
    assert covered_units == files["resolution_state.json"]["covered_unit_count"]


def test_corrupted_fixture_differs_only_in_intended_bounded_areas() -> None:
    assert _CORRUPTED_TRANSCRIPT.read_bytes() == _NORMAL_TRANSCRIPT.read_bytes()

    normal_resolution = json.loads(_NORMAL_RESOLUTION.read_text(encoding="utf-8"))
    corrupted_resolution = load_resolution_state()
    normal_units = dict(iter_covered_units(normal_resolution))
    corrupted_units = dict(iter_covered_units(corrupted_resolution))
    assert normal_units.keys() == corrupted_units.keys()

    differing_unit_ids: list[str] = []
    for unit_id, normal_unit in normal_units.items():
        if normal_unit != corrupted_units[unit_id]:
            differing_unit_ids.append(unit_id)

    assert differing_unit_ids == [_CORRUPTION_UNIT_ID]
    assert normal_units[_CORRUPTION_UNIT_ID]["determined_value"] == "518 feet"
    assert corrupted_units[_CORRUPTION_UNIT_ID]["determined_value"] == "618 feet"


def test_corrupted_resolution_operand_changed_and_source_lane_preserves_correct_value() -> None:
    assert extract_corrupted_operand_value() == "618 feet"
    assert_contradiction_variant_operand_differs_from_source_lanes()


def test_runtime_adapter_launches_with_corrupted_fixture_paths() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_corrupted_launch_context())

    handoff = surface.payload["deed_to_ir_startup_handoff"]
    assert handoff["resolution_state_ref"] == "transcript_edit:resolution_state:practice-row-live-20260619-76"
    assert handoff["resolution_state_counts"]["items"] == 5
    assert handoff["resolution_state_counts"]["covered_units"] == 15

    corrupted_unit = find_resolution_unit(load_resolution_state(), _CORRUPTION_UNIT_ID)
    assert corrupted_unit is not None
    assert corrupted_unit["determined_value"] == "618 feet"


def test_corrupted_handoff_startup_prompt_and_wire_payload_are_path_free() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_corrupted_launch_context())

    prompt_text = "\n".join(block.content for block in surface.blocks)
    wire = json.dumps(surface.payload["deed_to_ir_startup_handoff"])
    assert "Inherited handoff conditions" in prompt_text
    for forbidden in (
        str(_CORRUPTED_TRANSCRIPT),
        str(_CORRUPTED_RESOLUTION),
        "resolution_state_snapshot_path",
        "transcript_edit_output_path",
        "variants\\corrupted_handoff_call_distance",
        "variants/corrupted_handoff_call_distance",
        "618 feet",
    ):
        assert forbidden not in prompt_text
        assert forbidden not in wire


def test_corrupted_fixture_helper_rejects_missing_unit(tmp_path: Path) -> None:
    resolution = load_resolution_state()
    for item in resolution["items"]:
        item["covered_units"] = [
            unit for unit in item.get("covered_units", []) if unit.get("unit_id") != _CORRUPTION_UNIT_ID
        ]
    bad_root = tmp_path / "bad"
    bad_root.mkdir()
    (bad_root / "resolution_state.json").write_text(json.dumps(resolution), encoding="utf-8")
    (bad_root / "transcript_edit_output.json").write_text(
        _CORRUPTED_TRANSCRIPT.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match=_CORRUPTION_UNIT_ID):
        extract_corrupted_operand_value(bad_root)
