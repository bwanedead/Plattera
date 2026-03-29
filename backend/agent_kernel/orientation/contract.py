"""Generic orientation JSON contract: containers only, no domain checklist ontology."""
from __future__ import annotations

from typing import Any

from .startup_document import (
    coerce_startup_understanding,
    startup_understanding_has_minimum_viable,
)


def collect_orientation_startup_input(raw: dict[str, Any]) -> dict[str, Any]:
    """Merge nested startup_understanding with top-level orientation keys."""
    nested = raw.get("startup_understanding")
    out: dict[str, Any] = {}
    if isinstance(nested, dict):
        out.update(nested)
    for key in (
        "orientation_brief",
        "startup_rationale",
        "orientation_notes",
        "artifact_inventory",
        "initial_uncertainties",
        "initial_dependencies",
        "candidate_dependencies",
        "initial_ledger_items",
        "initial_blockers",
        "initial_focus_candidates",
        "candidate_work_items",
        "candidate_blockers",
        "candidate_focus_candidates",
    ):
        if key in raw and raw[key] is not None and key not in out:
            out[key] = raw[key]
    return out


def coerce_generic_orientation_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and coerce **generic** orientation only (no domain checklist rows).

    Use this for mission-agnostic orientation surfaces. Transcript-edit uses
    ``domains.mapping.transcript_edit.orient_checklist_adapter.coerce_transcript_edit_orient_payload``
    which may additionally accept legacy checklist-shaped rows.
    """
    startup_input = collect_orientation_startup_input(raw)
    startup_coerced = coerce_startup_understanding(startup_input)
    if not startup_understanding_has_minimum_viable(startup_coerced):
        raise ValueError("orientation_baseline_no_startup_signal")
    return {"startup_understanding": startup_coerced}

