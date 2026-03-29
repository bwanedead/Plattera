from __future__ import annotations

from typing import Any

_ALL_CONVENTIONS = {"plss", "metes_and_bounds", "lot_block", "hybrid", "unknown"}

BLOCKER_ARCHETYPE_CATALOG: list[dict[str, Any]] = [
    {
        "archetype_id": "conflicting_location_token",
        "label": "Conflicting Location Token",
        "description": "Location-identifying tokens conflict across transcript or evidence.",
        "applies_to_conventions": ["plss", "metes_and_bounds", "lot_block", "hybrid", "unknown"],
        "default_blocking_class": "mapping_blocking",
        "typical_resolution_condition": "One location token is selected with supporting evidence.",
        "typical_next_actions": ["gather_image_evidence", "request_hitl", "apply_edit_plan"],
    },
    {
        "archetype_id": "ambiguous_boundary_call",
        "label": "Ambiguous Boundary Call",
        "description": "A boundary distance/bearing/call is ambiguous or contradictory.",
        "applies_to_conventions": ["metes_and_bounds", "hybrid", "plss", "unknown"],
        "default_blocking_class": "mapping_blocking",
        "typical_resolution_condition": "Boundary call text is disambiguated and verified.",
        "typical_next_actions": ["open_spans", "image_verify", "request_hitl"],
    },
    {
        "archetype_id": "missing_anchor_reference",
        "label": "Missing Anchor Reference",
        "description": "Expected anchor (POB/POC/monument/reference) is missing or unclear.",
        "applies_to_conventions": ["metes_and_bounds", "hybrid", "plss", "unknown"],
        "default_blocking_class": "closure_blocking",
        "typical_resolution_condition": "Anchor reference is recovered or explicitly unresolved with scope impact.",
        "typical_next_actions": ["open_spans", "gather_image_evidence", "request_hitl"],
    },
    {
        "archetype_id": "source_occlusion",
        "label": "Source Occlusion",
        "description": "Source has occlusion (smudge, overwrite, stain) blocking confident extraction.",
        "applies_to_conventions": ["plss", "metes_and_bounds", "lot_block", "hybrid", "unknown"],
        "default_blocking_class": "source_blocking",
        "typical_resolution_condition": "Alternate evidence or explicit operator decision resolves occluded region.",
        "typical_next_actions": ["gather_image_evidence", "request_hitl"],
    },
    {
        "archetype_id": "source_truncation",
        "label": "Source Truncation",
        "description": "Document/scan appears truncated and missing relevant content.",
        "applies_to_conventions": ["plss", "metes_and_bounds", "lot_block", "hybrid", "unknown"],
        "default_blocking_class": "source_blocking",
        "typical_resolution_condition": "Additional pages/context are provided or scoped closure is justified.",
        "typical_next_actions": ["mark_blocked_by_incomplete_source", "request_hitl"],
    },
    {
        "archetype_id": "unknown_notation_system",
        "label": "Unknown Notation System",
        "description": "Notation format cannot be confidently interpreted with current context.",
        "applies_to_conventions": ["unknown", "hybrid", "metes_and_bounds", "plss", "lot_block"],
        "default_blocking_class": "mapping_blocking",
        "typical_resolution_condition": "Notation is decoded or mapped to supported semantic fields.",
        "typical_next_actions": ["open_spans", "request_hitl"],
    },
    {
        "archetype_id": "transcript_anchor_missing",
        "label": "Transcript Anchor Missing",
        "description": "Expected transcript anchor is absent in normalized text despite source evidence.",
        "applies_to_conventions": ["plss", "metes_and_bounds", "lot_block", "hybrid", "unknown"],
        "default_blocking_class": "closure_blocking",
        "typical_resolution_condition": "Transcript anchor is reintroduced or closure requirement adjusted with evidence.",
        "typical_next_actions": ["apply_edit_plan", "open_spans", "request_hitl"],
    },
]


def menu_for_candidates(menu_family_candidates: list[str] | None) -> list[dict[str, Any]]:
    families = {
        str(value or "").strip().lower()
        for value in (menu_family_candidates or [])
        if str(value or "").strip()
    }
    if not families:
        families = {"unknown"}
    selected: list[dict[str, Any]] = []
    for row in BLOCKER_ARCHETYPE_CATALOG:
        if not isinstance(row, dict):
            continue
        applies = {
            str(value or "").strip().lower()
            for value in list(row.get("applies_to_conventions") or [])
            if str(value or "").strip()
        }
        if not applies:
            applies = set(_ALL_CONVENTIONS)
        if not families.intersection(applies):
            continue
        selected.append(dict(row))
    return selected
