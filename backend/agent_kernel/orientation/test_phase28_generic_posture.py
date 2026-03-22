"""Phase 28: shared orientation startup document stays mission-agnostic."""
from __future__ import annotations

import re

import pytest

from agent_kernel.orientation.startup_document import work_item_impact_tier


def test_vague_mission_impact_without_mapping_blocking_is_unknown_tier() -> None:
    tier = work_item_impact_tier(
        {
            "title": "Toast darkness calibration",
            "summary": "User did not specify urgency; mission_impact is vague.",
            "mission_impact": "mapping_blocking",
        }
    )
    assert tier == "unknown"


def test_no_mapping_blocking_inference_in_generic_module_source() -> None:
    from pathlib import Path

    src = Path(__file__).resolve().parent / "startup_document.py"
    text = src.read_text(encoding="utf-8")
    assert "mapping_blocking" not in text
    assert "work_item_mapping_blocking" not in text


def test_toaster_style_work_item_uses_generic_impact_tier_only() -> None:
    assert (
        work_item_impact_tier(
            {"title": "Preheat sequence", "summary": "Need to verify slot timing", "impact_tier": "high"}
        )
        == "high"
    )
    assert work_item_impact_tier({"title": "UFO hull sketch", "mission_impact": "low"}) == "low"


def test_numeric_importance_maps_to_tier() -> None:
    assert work_item_impact_tier({"title": "x", "importance": 90}) == "high"
    assert work_item_impact_tier({"title": "x", "importance": 50}) == "medium"
    assert work_item_impact_tier({"title": "x", "importance": 10}) == "low"
