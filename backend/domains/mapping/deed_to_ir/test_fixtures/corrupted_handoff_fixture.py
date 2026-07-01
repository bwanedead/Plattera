"""Test-only helpers for the corrupted deed-to-IR handoff fixture variant."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[5]
_NORMAL_FIXTURE_ROOT = _REPO_ROOT / "practice_deeds" / "right_of_way" / "deed_to_ir"
_CORRUPTED_FIXTURE_ROOT = (
    _NORMAL_FIXTURE_ROOT / "variants" / "corrupted_handoff_call_distance"
)
_CORRUPTION_UNIT_ID = "p1_call2_distance"
_SOURCE_DISTANCE_PATTERN = re.compile(r"\b518\s+feet\b", re.IGNORECASE)


def normal_fixture_root() -> Path:
    return _NORMAL_FIXTURE_ROOT


def corrupted_fixture_root() -> Path:
    return _CORRUPTED_FIXTURE_ROOT


def load_fixture_manifest(root: Path | None = None) -> dict[str, Any]:
    fixture_root = root or corrupted_fixture_root()
    return json.loads((fixture_root / "fixture_manifest.json").read_text(encoding="utf-8"))


def load_resolution_state(root: Path | None = None) -> dict[str, Any]:
    fixture_root = root or corrupted_fixture_root()
    return json.loads((fixture_root / "resolution_state.json").read_text(encoding="utf-8"))


def load_transcript_edit_output(root: Path | None = None) -> dict[str, Any]:
    fixture_root = root or corrupted_fixture_root()
    return json.loads((fixture_root / "transcript_edit_output.json").read_text(encoding="utf-8"))


def find_resolution_unit(resolution: dict[str, Any], unit_id: str) -> dict[str, Any] | None:
    for item in resolution.get("items", []):
        if not isinstance(item, dict):
            continue
        for unit in item.get("covered_units", []):
            if isinstance(unit, dict) and unit.get("unit_id") == unit_id:
                return unit
    return None


def extract_corrupted_operand_value(root: Path | None = None) -> str:
    unit = find_resolution_unit(load_resolution_state(root), _CORRUPTION_UNIT_ID)
    if unit is None:
        raise AssertionError(f"missing resolution unit {_CORRUPTION_UNIT_ID}")
    value = unit.get("determined_value")
    if not isinstance(value, str) or not value.strip():
        raise AssertionError(f"{_CORRUPTION_UNIT_ID} missing determined_value")
    return value


def extract_source_lane_distance_text(root: Path | None = None) -> str:
    transcript = load_transcript_edit_output(root)
    payload = transcript.get("revision_snapshot", {}).get("payload", {})
    if not isinstance(payload, dict):
        raise AssertionError("transcript_edit_output missing revision_snapshot.payload")
    for lane in ("source_transcript_verbatim", "normalized_or_mapping_transcript"):
        text = payload.get(lane)
        if isinstance(text, str) and _SOURCE_DISTANCE_PATTERN.search(text):
            return text
    raise AssertionError("source-supported 518 feet not found in transcript lanes")


def assert_corrupted_operand_differs_from_source_lanes(root: Path | None = None) -> None:
    operand = extract_corrupted_operand_value(root)
    source_text = extract_source_lane_distance_text(root)
    assert operand != _SOURCE_DISTANCE_PATTERN.search(source_text).group(0)  # type: ignore[union-attr]
    assert _SOURCE_DISTANCE_PATTERN.search(source_text) is not None


def iter_covered_units(resolution: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for item in resolution.get("items", []):
        if not isinstance(item, dict):
            continue
        for unit in item.get("covered_units", []):
            if isinstance(unit, dict) and isinstance(unit.get("unit_id"), str):
                rows.append((unit["unit_id"], unit))
    return rows
