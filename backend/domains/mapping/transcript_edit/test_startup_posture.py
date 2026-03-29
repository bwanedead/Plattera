"""Transcript-edit posture derivation from generic startup rows (Phase 28)."""
from __future__ import annotations

from domains.mapping.transcript_edit.startup_posture import (
    transcript_mapping_blocking_from_startup_item,
    transcript_operational_impact_from_startup_item,
)


def test_transcript_adapter_maps_explicit_mapping_blocking_bool() -> None:
    assert transcript_mapping_blocking_from_startup_item({"mapping_blocking": True}) is True
    assert transcript_mapping_blocking_from_startup_item({"mapping_blocking": False}) is False


def test_transcript_adapter_maps_generic_high_tier() -> None:
    assert transcript_mapping_blocking_from_startup_item({"title": "x", "impact_tier": "high"}) is True


def test_transcript_adapter_interprets_legacy_mission_impact_strings() -> None:
    assert transcript_mapping_blocking_from_startup_item({"mission_impact": "mapping_blocking"}) is True
    assert transcript_mapping_blocking_from_startup_item({"mission_impact": "transcript_quality_only"}) is False


def test_operational_impact_follows_mapping_gate() -> None:
    assert (
        transcript_operational_impact_from_startup_item({"impact_tier": "high"})
        == "mapping_blocking"
    )
    assert (
        transcript_operational_impact_from_startup_item({"impact_tier": "unknown"})
        == "transcript_quality_only"
    )

