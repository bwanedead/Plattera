"""Test-only helpers for corrupted deed-to-IR handoff fixture variants."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[5]
_NORMAL_FIXTURE_ROOT = _REPO_ROOT / "practice_deeds" / "right_of_way" / "deed_to_ir"
_VARIANTS_ROOT = _NORMAL_FIXTURE_ROOT / "variants"
_CORRUPTION_UNIT_ID = "p1_call2_distance"
_SOURCE_DISTANCE_PATTERN = re.compile(r"\b518\s+feet\b", re.IGNORECASE)
_CORRUPTED_DISTANCE_PATTERN = re.compile(r"\b618\s+feet\b", re.IGNORECASE)
_SOURCE_EVIDENCE_REF = "image:derived:fba6f159e40d4010896245d6525d4acf"
_CALL3_CORRUPTION_UNIT_ID = "p1_call3_distance"
_CALL3_SOURCE_DISTANCE_PATTERN = re.compile(r"\b180\s+feet\b", re.IGNORECASE)
_CALL3_CORRUPTED_DISTANCE_PATTERN = re.compile(r"\b280\s+feet\b", re.IGNORECASE)
_CALL3_SOURCE_EVIDENCE_REF = _SOURCE_EVIDENCE_REF

FIXTURE_VARIANTS: dict[str, Path] = {
    "corrupted_handoff_call_distance": _VARIANTS_ROOT / "corrupted_handoff_call_distance",
    "corrupted_handoff_source_repair": _VARIANTS_ROOT / "corrupted_handoff_source_repair",
    "corrupted_handoff_source_repair_call3_distance": (
        _VARIANTS_ROOT / "corrupted_handoff_source_repair_call3_distance"
    ),
}


def normal_fixture_root() -> Path:
    return _NORMAL_FIXTURE_ROOT


def variant_fixture_root(name: str) -> Path:
    if name not in FIXTURE_VARIANTS:
        raise KeyError(name)
    return FIXTURE_VARIANTS[name]


def corrupted_fixture_root(variant: str = "corrupted_handoff_call_distance") -> Path:
    return variant_fixture_root(variant)


def load_fixture_manifest(root: Path | None = None) -> dict[str, Any]:
    fixture_root = root or corrupted_fixture_root()
    return json.loads((fixture_root / "fixture_manifest.json").read_text(encoding="utf-8"))


def load_resolution_state(root: Path | None = None) -> dict[str, Any]:
    fixture_root = root or corrupted_fixture_root()
    return json.loads((fixture_root / "resolution_state.json").read_text(encoding="utf-8"))


def load_transcript_edit_output(root: Path | None = None) -> dict[str, Any]:
    fixture_root = root or corrupted_fixture_root()
    return json.loads((fixture_root / "transcript_edit_output.json").read_text(encoding="utf-8"))


def transcript_payload(root: Path | None = None) -> dict[str, Any]:
    transcript = load_transcript_edit_output(root)
    payload = transcript.get("revision_snapshot", {}).get("payload", {})
    if not isinstance(payload, dict):
        raise AssertionError("transcript_edit_output missing revision_snapshot.payload")
    return payload


def find_resolution_unit(resolution: dict[str, Any], unit_id: str) -> dict[str, Any] | None:
    for item in resolution.get("items", []):
        if not isinstance(item, dict):
            continue
        for unit in item.get("covered_units", []):
            if isinstance(unit, dict) and unit.get("unit_id") == unit_id:
                return unit
    return None


def extract_corrupted_operand_value(
    root: Path | None = None,
    *,
    unit_id: str = _CORRUPTION_UNIT_ID,
) -> str:
    unit = find_resolution_unit(load_resolution_state(root), unit_id)
    if unit is None:
        raise AssertionError(f"missing resolution unit {unit_id}")
    value = unit.get("determined_value")
    if not isinstance(value, str) or not value.strip():
        raise AssertionError(f"{unit_id} missing determined_value")
    return value


def extract_target_evidence_ref(
    root: Path | None = None,
    *,
    unit_id: str = _CORRUPTION_UNIT_ID,
) -> str:
    unit = find_resolution_unit(load_resolution_state(root), unit_id)
    if unit is None:
        raise AssertionError(f"missing resolution unit {unit_id}")
    refs = unit.get("evidence_refs")
    if not isinstance(refs, list):
        raise AssertionError(f"{unit_id} missing evidence_refs")
    for ref in refs:
        if isinstance(ref, str) and ref.strip():
            return ref.strip()
    raise AssertionError(f"{unit_id} has no evidence refs")


def transcript_lane_text(root: Path | None = None) -> str:
    payload = transcript_payload(root)
    parts: list[str] = []
    for lane in ("source_transcript_verbatim", "normalized_or_mapping_transcript"):
        text = payload.get(lane)
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)


def assert_contradiction_variant_operand_differs_from_source_lanes(root: Path | None = None) -> None:
    operand = extract_corrupted_operand_value(root)
    payload = transcript_payload(root)
    for lane in ("source_transcript_verbatim", "normalized_or_mapping_transcript"):
        text = payload.get(lane)
        assert isinstance(text, str)
        match = _SOURCE_DISTANCE_PATTERN.search(text)
        assert match is not None, f"source-supported distance missing in {lane}"
        assert operand != match.group(0)


def assert_source_repair_variant_transcript_agrees_with_corrupted_operand(root: Path | None = None) -> None:
    operand = extract_corrupted_operand_value(root)
    lanes = transcript_lane_text(root)
    assert _CORRUPTED_DISTANCE_PATTERN.search(lanes) is not None
    assert _SOURCE_DISTANCE_PATTERN.search(lanes) is None
    assert operand == "618 feet"


def assert_call3_source_repair_variant_transcript_agrees_with_corrupted_operand(
    root: Path | None = None,
) -> None:
    operand = extract_corrupted_operand_value(root, unit_id=_CALL3_CORRUPTION_UNIT_ID)
    lanes = transcript_lane_text(root)
    assert _CALL3_CORRUPTED_DISTANCE_PATTERN.search(lanes) is not None
    assert _CALL3_SOURCE_DISTANCE_PATTERN.search(lanes) is None
    assert operand == "280 feet"


def iter_covered_units(resolution: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for item in resolution.get("items", []):
        if not isinstance(item, dict):
            continue
        for unit in item.get("covered_units", []):
            if isinstance(unit, dict) and isinstance(unit.get("unit_id"), str):
                rows.append((unit["unit_id"], unit))
    return rows
