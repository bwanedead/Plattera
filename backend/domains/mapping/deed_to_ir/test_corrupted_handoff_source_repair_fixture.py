"""Corrupted source-repair deed-to-IR handoff fixture integrity and launch contract tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from domains.mapping.deed_to_ir.runtime_adapter import build_deed_to_ir_runtime_adapter
from domains.mapping.deed_to_ir.test_fixtures.synthetic_transcript_edit_evidence import (
    install_synthetic_transcript_edit_derived_image,
)
from domains.mapping.deed_to_ir.test_fixtures.corrupted_handoff_fixture import (
    _CORRUPTION_UNIT_ID,
    _SOURCE_EVIDENCE_REF,
    assert_source_repair_variant_transcript_agrees_with_corrupted_operand,
    corrupted_fixture_root,
    extract_corrupted_operand_value,
    extract_target_evidence_ref,
    find_resolution_unit,
    iter_covered_units,
    load_fixture_manifest,
    load_resolution_state,
    load_transcript_edit_output,
    normal_fixture_root,
    transcript_lane_text,
    variant_fixture_root,
)
from tooling.mapping.deed_to_ir.artifact_hydration import hydrate_artifact_refs
from domains.mapping.deed_to_ir.payloads import DeedToIrScope
from domains.mapping.deed_to_ir.runtime_adapter.composition import _handoff_tool_context
from tooling.mapping.deed_to_ir.input_hydration import make_hydrate_deed_to_ir_input_handler
from tooling.mapping.deed_to_ir.startup_handoff import build_deed_to_ir_startup_handoff

_NORMAL_ROOT = normal_fixture_root()
_SOURCE_REPAIR_ROOT = variant_fixture_root("corrupted_handoff_source_repair")
_VARIANT_NAME = "corrupted_handoff_source_repair"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _launch_context(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "dossier_id": "9f5eecb6-cd7e-483c-b691-b76aa7132e8e",
        "transcription_id": "draft_legal_text_image",
        "run_id": "deed-to-ir-source-repair-test",
        "workspace_id": "deed-to-ir-source-repair-test",
        "max_iterations": 3,
        "transcript_edit_output_path": str(_SOURCE_REPAIR_ROOT / "transcript_edit_output.json"),
        "resolution_state_ref": "transcript_edit:resolution_state:practice-row-live-20260619-76",
        "resolution_state_snapshot_path": str(_SOURCE_REPAIR_ROOT / "resolution_state.json"),
    }
    base.update(overrides)
    return base


def test_source_repair_fixture_exists_with_required_files() -> None:
    for name in (
        "fixture_manifest.json",
        "transcript_edit_output.json",
        "resolution_state.json",
    ):
        assert (_SOURCE_REPAIR_ROOT / name).is_file(), name


def test_source_repair_manifest_labels_variant() -> None:
    manifest = load_fixture_manifest(_SOURCE_REPAIR_ROOT)
    assert manifest["fixture_variant"] == _VARIANT_NAME
    assert "test fixture variant" in manifest["fixture_variant_label"].lower()
    assert manifest["corruption_target"]["unit_id"] == _CORRUPTION_UNIT_ID
    assert manifest["corruption_target"]["source_evidence_ref"] == _SOURCE_EVIDENCE_REF


def test_source_repair_fixture_json_is_valid_and_manifest_hashes_match() -> None:
    manifest = load_fixture_manifest(_SOURCE_REPAIR_ROOT)
    files = manifest["files"]
    transcript = _SOURCE_REPAIR_ROOT / "transcript_edit_output.json"
    resolution = _SOURCE_REPAIR_ROOT / "resolution_state.json"
    assert _sha256(transcript) == files["transcript_edit_output.json"]["sha256"]
    assert _sha256(resolution) == files["resolution_state.json"]["sha256"]
    load_transcript_edit_output(_SOURCE_REPAIR_ROOT)
    load_resolution_state(_SOURCE_REPAIR_ROOT)


def test_normal_fixture_unchanged() -> None:
    manifest = json.loads((_NORMAL_ROOT / "fixture_manifest.json").read_text(encoding="utf-8"))
    assert _sha256(_NORMAL_ROOT / "transcript_edit_output.json") == manifest["files"]["transcript_edit_output.json"]["sha256"]
    assert _sha256(_NORMAL_ROOT / "resolution_state.json") == manifest["files"]["resolution_state.json"]["sha256"]


def test_source_repair_resolution_and_transcript_both_carry_corrupted_call2_distance() -> None:
    assert extract_corrupted_operand_value(_SOURCE_REPAIR_ROOT) == "618 feet"
    assert_source_repair_variant_transcript_agrees_with_corrupted_operand(_SOURCE_REPAIR_ROOT)
    assert "518 feet" not in transcript_lane_text(_SOURCE_REPAIR_ROOT)


def test_source_repair_differs_from_normal_only_in_intended_areas() -> None:
    normal_transcript = (_NORMAL_ROOT / "transcript_edit_output.json").read_bytes()
    variant_transcript = (_SOURCE_REPAIR_ROOT / "transcript_edit_output.json").read_bytes()
    assert normal_transcript != variant_transcript

    normal_resolution = json.loads((_NORMAL_ROOT / "resolution_state.json").read_text(encoding="utf-8"))
    variant_resolution = load_resolution_state(_SOURCE_REPAIR_ROOT)
    normal_units = dict(iter_covered_units(normal_resolution))
    variant_units = dict(iter_covered_units(variant_resolution))
    differing = [uid for uid, row in normal_units.items() if row != variant_units[uid]]
    assert differing == [_CORRUPTION_UNIT_ID]


def test_source_repair_target_evidence_ref_present() -> None:
    assert extract_target_evidence_ref(_SOURCE_REPAIR_ROOT) == _SOURCE_EVIDENCE_REF
    unit = find_resolution_unit(load_resolution_state(_SOURCE_REPAIR_ROOT), _CORRUPTION_UNIT_ID)
    assert unit is not None
    assert _SOURCE_EVIDENCE_REF in unit.get("evidence_refs", [])


def test_source_repair_mapping_operands_show_corrupted_value() -> None:
    handoff = build_deed_to_ir_startup_handoff(
        scope=DeedToIrScope(
            dossier_id="9f5eecb6-cd7e-483c-b691-b76aa7132e8e",
            transcription_id="draft_legal_text_image",
            run_id="deed-to-ir-source-repair-test",
            workspace_id="deed-to-ir-source-repair-test",
        ),
        transcript_edit_output_path=str(_SOURCE_REPAIR_ROOT / "transcript_edit_output.json"),
        resolution_state_ref="transcript_edit:resolution_state:practice-row-live-20260619-76",
        resolution_state_snapshot=load_resolution_state(_SOURCE_REPAIR_ROOT),
    )
    handler = make_hydrate_deed_to_ir_input_handler(handoff_context=_handoff_tool_context(handoff))
    hydrated = handler({"sections": ["mapping_operands"]})
    operands = hydrated["outputs"]["mapping_operands"]
    rows = operands.get("operands") if isinstance(operands.get("operands"), list) else []
    call2 = next(row for row in rows if row.get("operand_id") == _CORRUPTION_UNIT_ID)
    assert call2.get("distance_raw") == "618 feet"


def test_source_repair_startup_prompt_and_wire_payload_are_path_and_answer_key_free() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_launch_context())
    prompt_text = "\n".join(block.content for block in surface.blocks)
    wire = json.dumps(surface.payload["deed_to_ir_startup_handoff"])
    for forbidden in (
        str(_SOURCE_REPAIR_ROOT),
        "variants\\corrupted_handoff_source_repair",
        "variants/corrupted_handoff_source_repair",
        "corruption_target",
        "source_supported_value",
        "fixture_variant",
        "518 feet",
        "resolution_state_snapshot_path",
        "transcript_edit_output_path",
    ):
        assert forbidden not in prompt_text
        assert forbidden not in wire


def test_source_repair_upstream_evidence_ref_hydrates_when_descriptor_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dossier_id = "d-source-repair-test"
    transcription_id = "tx-source-repair"
    workspace_id = "practice-row-live-20260619-76"

    install_synthetic_transcript_edit_derived_image(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        ref_id=_SOURCE_EVIDENCE_REF,
    )

    handoff_context = {
        "resolution_state_ref": f"transcript_edit:resolution_state:{workspace_id}",
    }
    hydrated = hydrate_artifact_refs(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        ref_ids=[_SOURCE_EVIDENCE_REF, "image:derived:missing-ref"],
        handoff_context=handoff_context,
    )
    assert hydrated["executed"] is True
    assert hydrated["outputs"]["hydrated_count"] == 1
    assert len(hydrated["outputs"]["errors"]) == 1
    row = hydrated["outputs"]["results"][0]
    assert row["ref_id"] == _SOURCE_EVIDENCE_REF
    assert row["kind"] == "upstream_derived_image"
    dumped = json.dumps(hydrated)
    assert "absolute_path" not in dumped
    assert str(tmp_path) not in dumped
    assert isinstance(hydrated.get("image_evidence"), list)
    assert hydrated["image_evidence"][0]["ref_id"] == _SOURCE_EVIDENCE_REF
