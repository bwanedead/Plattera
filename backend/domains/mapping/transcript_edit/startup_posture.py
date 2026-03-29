"""Transcript-edit domain: map generic startup work rows to native ledger posture.

Shared ``agent_kernel.orientation`` emits only generic ``impact_tier`` and preserves model fields;
transcript-specific ``mapping_blocking`` / ``operational_impact`` strings are interpreted here only.
"""
from __future__ import annotations

from typing import Any

_GENERIC_TIERS = frozenset({"high", "medium", "low", "unknown"})


def transcript_mapping_blocking_from_startup_item(row: dict[str, Any]) -> bool:
    """Whether this work item is mapping-closure-critical for transcript-edit (domain semantics).

    Prefer explicit model-authored ``mapping_blocking`` when present. Otherwise interpret
    generic ``impact_tier`` and legacy ``mission_impact`` strings that transcript-edit prompts may emit.
    """
    if "mapping_blocking" in row:
        return bool(row.get("mapping_blocking"))
    tier = str(row.get("impact_tier") or "").strip().lower()
    if tier == "high":
        return True
    if tier in ("medium", "low", "unknown"):
        return False
    mi = str(row.get("mission_impact") or "").strip().lower()
    if mi in ("mapping_blocking", "mapping_critical", "critical", "high"):
        return True
    if mi in ("transcript_quality_only", "quality", "low", "none"):
        return False
    return False


def transcript_operational_impact_from_startup_item(row: dict[str, Any]) -> str:
    """Native ledger ``operational_impact`` for transcript-edit discovery rows."""
    if transcript_mapping_blocking_from_startup_item(row):
        return "mapping_blocking"
    return "transcript_quality_only"


def transcript_layer_tag_from_startup_item(row: dict[str, Any]) -> str:
    """Native ``layer_tag`` for transcript-edit shaped rows."""
    if transcript_mapping_blocking_from_startup_item(row):
        return "layer1_canonical_recovery"
    return "layer4_transcript_quality_optional"
