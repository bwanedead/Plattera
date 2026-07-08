"""Bounded correction contract card for deed-to-IR upstream correction posture."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from domains.mapping.deed_to_ir.payloads.published_output import UpstreamCorrectionRow

CORRECTION_CONTRACT_REF = "deed_to_ir:correction_contract"

FORBIDDEN_UPSTREAM_CORRECTION_FIELDS: tuple[str, ...] = (
    "summary",
    "affected_scope",
    "value_kind",
    "inherited_value",
    "ir_value",
)

UPSTREAM_CORRECTION_FIELD_MAPPING_HINTS: dict[str, str] = {
    "summary": "rationale",
    "inherited_value": "upstream_value",
    "ir_value": "corrected_value",
    "confirmed": "confirmed_from_source",
    "resolved": "confirmed_from_source",
}

VALID_UPSTREAM_CORRECTION_POSTURES: tuple[str, ...] = (
    "suspected",
    "confirmed_from_source",
    "needs_hitl",
)

RECOMMENDED_UPSTREAM_CORRECTION_ACTION = "transcript_amendment"

CORRECTION_CONTRACT_SUMMARY = (
    "Upstream correction posture is active. When final IR intentionally differs from inherited "
    "transcript-edit output, resolution state, or mapping operands, the final package must include "
    "upstream_corrections — notes are commentary only."
)

CORRECTION_REPAIR_HINT = (
    "Copy retry_package_shell, add upstream_corrections from upstream_corrections_template "
    "(exact schema field names), then retry prepare_deed_to_ir_final_package."
)

_GENERIC_TEMPLATE_BASIS_REFS: list[str] = [
    "image:derived:example_source_crop_ref",
    "feature_graph:ir:example_ir_ref",
]

_GENERIC_EXAMPLE_ROW: dict[str, Any] = {
    "correction_id": "example_call_2_distance_source_repair",
    "posture": "confirmed_from_source",
    "resolution_used_by_ir": True,
    "recommended_action": RECOMMENDED_UPSTREAM_CORRECTION_ACTION,
    "basis_refs": list(_GENERIC_TEMPLATE_BASIS_REFS),
    "rationale": "Source evidence supports the corrected value used by the final IR.",
    "target_entity_id": "example_call_2_distance",
    "target_entity_type": "resolution_unit",
    "upstream_value": "430 feet",
    "corrected_value": "410 feet",
}

_PRACTICE_DEED_AGENT_FACING_TOKENS: tuple[str, ...] = (
    "518",
    "542",
    "618",
    "right_of_way",
    "parcel_1",
    "p1_call2_distance",
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
            "Use exact schema field names only — do not invent summary, inherited_value, or ir_value.",
        ],
        **upstream_correction_row_contract_fields(),
        "forbidden_fields": list(FORBIDDEN_UPSTREAM_CORRECTION_FIELDS),
        "field_mapping_hints": dict(UPSTREAM_CORRECTION_FIELD_MAPPING_HINTS),
        "valid_postures": list(VALID_UPSTREAM_CORRECTION_POSTURES),
        "example_row": dict(_GENERIC_EXAMPLE_ROW),
        "repair_hint": CORRECTION_REPAIR_HINT,
    }


def build_upstream_correction_row_template_from_delta(delta: Mapping[str, Any]) -> dict[str, Any]:
    """Build a copyable upstream_corrections row template from a mechanical candidate delta."""
    row = dict(_GENERIC_EXAMPLE_ROW)
    row["correction_id"] = "agent_must_fill_unique_id"
    target_entity_id = str(delta.get("target_entity_id") or "").strip()
    if target_entity_id:
        row["target_entity_id"] = target_entity_id
    upstream = str(delta.get("inherited_value") or "").strip()
    corrected = str(delta.get("ir_value") or "").strip()
    if upstream:
        row["upstream_value"] = upstream
    if corrected:
        row["corrected_value"] = corrected
    basis_refs = delta.get("basis_refs")
    if isinstance(basis_refs, list):
        refs = [str(item or "").strip() for item in basis_refs if str(item or "").strip()]
        if refs:
            row["basis_refs"] = refs
    return row


def build_upstream_corrections_template(
    *,
    candidate_deltas: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Return one copyable template row per candidate delta (advisory only)."""
    if not isinstance(candidate_deltas, Sequence):
        return []
    templates: list[dict[str, Any]] = []
    for delta in candidate_deltas:
        if isinstance(delta, Mapping):
            templates.append(build_upstream_correction_row_template_from_delta(delta))
    return templates


def agent_facing_example_contains_practice_deed_tokens(payload: Mapping[str, Any] | None) -> list[str]:
    """Return practice-deed tokens found in an agent-facing example/template payload."""
    if not isinstance(payload, Mapping):
        return []
    text = str(payload).lower()
    return [token for token in _PRACTICE_DEED_AGENT_FACING_TOKENS if token in text]


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
    required = card.get("required_row_fields")
    if isinstance(required, list) and required:
        lines.append(f"{indent}  required_fields: {', '.join(str(f) for f in required)}")
    forbidden = card.get("forbidden_fields")
    if isinstance(forbidden, list) and forbidden:
        lines.append(f"{indent}  forbidden_fields: {', '.join(str(f) for f in forbidden)}")
    mapping_hints = card.get("field_mapping_hints")
    if isinstance(mapping_hints, Mapping):
        for src, dst in mapping_hints.items():
            lines.append(f"{indent}  field_mapping: {src} -> {dst}")
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
