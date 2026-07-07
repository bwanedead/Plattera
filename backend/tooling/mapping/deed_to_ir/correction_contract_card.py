"""Bounded correction contract card for deed-to-IR upstream correction posture."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from domains.mapping.deed_to_ir.payloads.published_output import UpstreamCorrectionRow

CORRECTION_CONTRACT_REF = "deed_to_ir:correction_contract"

CORRECTION_CONTRACT_SUMMARY = (
    "Upstream correction posture is active. When final IR intentionally differs from inherited "
    "transcript-edit output, resolution state, or mapping operands, the final package must include "
    "upstream_corrections — notes are commentary only."
)

CORRECTION_REPAIR_HINT = (
    "Add one or more upstream_corrections rows, or revise the IR/package if no upstream correction "
    "was actually used."
)

def upstream_correction_row_contract_fields() -> dict[str, list[str]]:
    """Derive required/optional upstream_corrections row fields from the Pydantic contract."""
    required: list[str] = []
    optional: list[str] = []
    for name, field in UpstreamCorrectionRow.model_fields.items():
        if field.is_required():
            required.append(name)
        else:
            optional.append(name)
    return {
        "required_row_fields": required,
        "optional_row_fields": optional,
    }


_GENERIC_EXAMPLE_ROW: dict[str, Any] = {
    "correction_id": "example_call_distance_transcript_correction",
    "title": "Example call distance correction",
    "target_entity_id": "example_call2_distance",
    "target_entity_type": "resolution_unit",
    "upstream_value": "410 feet",
    "corrected_value": "438 feet",
    "posture": "confirmed_from_source",
    "resolution_used_by_ir": True,
    "recommended_action": "transcript_amendment",
    "basis_refs": [
        "transcript_edit:resolution_state:example",
        "feature_graph:ir:example",
    ],
    "rationale": "Final IR and mapping rely on the corrected distance.",
}


def build_correction_contract_card() -> dict[str, Any]:
    """Return the compact generic correction contract card (no practice-deed values)."""
    return {
        "contract_ref": CORRECTION_CONTRACT_REF,
        "summary": CORRECTION_CONTRACT_SUMMARY,
        "rules": [
            "Notes are commentary only — they are not the machine-readable correction lane.",
            "When final IR intentionally differs from inherited handoff values, include upstream_corrections.",
            "Set resolution_used_by_ir=true when final IR used the repaired value.",
            "Set resolution_used_by_ir=false only for investigated-but-not-used suspected issues.",
        ],
        **upstream_correction_row_contract_fields(),
        "example_row": dict(_GENERIC_EXAMPLE_ROW),
        "repair_hint": CORRECTION_REPAIR_HINT,
    }


def build_correction_contract_hydration_row() -> dict[str, Any]:
    """Hydration payload for deed_to_ir:correction_contract."""
    card = build_correction_contract_card()
    return {
        "ref_id": CORRECTION_CONTRACT_REF,
        "artifact_type": "deed_to_ir_correction_contract",
        **card,
    }


def render_correction_contract_card_timeline_lines(
    card: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(card, Mapping) or not card:
        return []
    lines = [f"{indent}correction_contract_card:"]
    summary = card.get("summary")
    if isinstance(summary, str) and summary.strip():
        lines.append(f"{indent}  summary: {summary.strip()}")
    example = card.get("example_row")
    if isinstance(example, Mapping):
        correction_id = example.get("correction_id")
        target = example.get("target_entity_id")
        if correction_id or target:
            lines.append(
                f"{indent}  example: correction_id={correction_id or ''} "
                f"target_entity_id={target or ''}"
            )
    repair_hint = card.get("repair_hint")
    if isinstance(repair_hint, str) and repair_hint.strip():
        lines.append(f"{indent}  repair_hint: {repair_hint.strip()}")
    return lines
