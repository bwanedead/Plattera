"""Bounded hydration of deed-to-IR upstream input lanes (mechanical projection only)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .inherited_handoff_projection import build_inherited_handoff_conditions
from .operand_suite import build_operand_suite_payload
from .resolution_state_projection import (
    build_resolution_state_index,
    build_resolution_state_selected_rows,
)

MAX_TRANSCRIPT_CHARS = 12000
MAX_LIST_ROWS = 32
MAX_RESOLUTION_ITEMS = 64
MAX_RESOLUTION_UNIT_IDS = 64
MAX_EVIDENCE_REFS = 48

VALID_SECTIONS = frozenset(
    {
        "inherited_handoff_conditions",
        "normalized_transcript",
        "verbatim_transcript",
        "parcel_metadata",
        "issues",
        "hitl_decisions",
        "evidence_refs",
        "resolution_state",
        "mapping_operands",
    }
)


def make_hydrate_deed_to_ir_input_handler(
    *,
    handoff_context: Mapping[str, Any],
) -> Callable[[Any], Any]:
    """Return a handler closed over the mechanical startup handoff context."""

    def handler(request: Any) -> dict[str, Any]:
        inputs = _extract_inputs(request)
        sections = _parse_sections(inputs.get("sections"))
        if not sections:
            return _refusal("sections_required", "sections must be a non-empty list of known section names.")
        unknown = sorted(set(sections) - VALID_SECTIONS)
        if unknown:
            return _refusal(
                "unknown_sections",
                f"Unknown sections: {', '.join(unknown)}.",
            )
        unit_ids, unit_ids_omitted = _parse_unit_ids(inputs.get("resolution_unit_ids"))
        results: dict[str, Any] = {}
        errors: list[dict[str, str]] = []
        if unit_ids_omitted:
            errors.append(
                {
                    "section": "resolution_state",
                    "reason": "resolution_unit_ids_truncated",
                    "omitted_count": unit_ids_omitted,
                }
            )
        for section in sections:
            payload, section_errors = _hydrate_section(
                section=section,
                handoff=handoff_context,
                resolution_unit_ids=unit_ids,
                unit_ids_omitted=unit_ids_omitted,
            )
            if payload is not None:
                results[section] = payload
            errors.extend(section_errors)
        inherited = _inherited_handoff_conditions(handoff_context)
        return {
            "executed": True,
            "outputs": {
                "inherited_handoff_conditions": inherited,
                "sections": sections,
                "results": results,
                "errors": errors,
                "hydrated_section_count": len(results),
            },
        }

    return handler


def _hydrate_section(
    *,
    section: str,
    handoff: Mapping[str, Any],
    resolution_unit_ids: list[str] | None,
    unit_ids_omitted: int = 0,
) -> tuple[Any | None, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    if section == "inherited_handoff_conditions":
        return _inherited_handoff_conditions(handoff), errors
    if section == "normalized_transcript":
        text = handoff.get("normalized_or_mapping_transcript")
        if not isinstance(text, str) or not text.strip():
            errors.append(_section_error(section, "unavailable"))
            return None, errors
        return {"text": _bound_text(text)}, errors
    if section == "verbatim_transcript":
        text = handoff.get("source_transcript_verbatim")
        if not isinstance(text, str) or not text.strip():
            errors.append(_section_error(section, "unavailable"))
            return None, errors
        return {"text": _bound_text(text)}, errors
    if section == "parcel_metadata":
        meta = handoff.get("parcel_metadata")
        if not isinstance(meta, Mapping) or not meta:
            errors.append(_section_error(section, "unavailable"))
            return None, errors
        return {"parcel_metadata": dict(meta)}, errors
    if section == "issues":
        rows = handoff.get("issues")
        if not isinstance(rows, list):
            errors.append(_section_error(section, "unavailable"))
            return None, errors
        return {"issues": rows[:MAX_LIST_ROWS]}, errors
    if section == "hitl_decisions":
        rows = handoff.get("hitl_decisions")
        if not isinstance(rows, list):
            errors.append(_section_error(section, "unavailable"))
            return None, errors
        return {"hitl_decisions": rows[:MAX_LIST_ROWS]}, errors
    if section == "evidence_refs":
        refs = handoff.get("evidence_refs")
        if not isinstance(refs, list):
            errors.append(_section_error(section, "unavailable"))
            return None, errors
        return {"evidence_refs": [str(r) for r in refs[:MAX_EVIDENCE_REFS]]}, errors
    if section == "resolution_state":
        return _hydrate_resolution_state(
            handoff,
            resolution_unit_ids,
            unit_ids_omitted=unit_ids_omitted,
        )
    if section == "mapping_operands":
        return _hydrate_mapping_operands(handoff)
    return None, [_section_error(section, "unsupported")]


def _hydrate_mapping_operands(
    handoff: Mapping[str, Any],
) -> tuple[Any | None, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    payload = build_operand_suite_payload(handoff)
    if payload is None:
        errors.append(_section_error("mapping_operands", "unavailable"))
        return None, errors
    return payload, errors


def _hydrate_resolution_state(
    handoff: Mapping[str, Any],
    resolution_unit_ids: list[str] | None,
    *,
    unit_ids_omitted: int = 0,
) -> tuple[Any | None, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    ref = handoff.get("resolution_state_ref")
    snapshot = handoff.get("resolution_state_snapshot")
    if not isinstance(snapshot, Mapping):
        errors.append(_section_error("resolution_state", "unavailable"))
        return None, errors
    if resolution_unit_ids:
        rows, not_found, truncation = build_resolution_state_selected_rows(
            snapshot,
            resolution_unit_ids,
            resolution_state_ref=str(ref) if ref is not None else None,
        )
        filter_payload: dict[str, Any] = {"resolution_unit_ids": resolution_unit_ids}
        if unit_ids_omitted:
            filter_payload["resolution_unit_ids_omitted"] = unit_ids_omitted
        payload: dict[str, Any] = {
            "projection_mode": "selected_rows",
            "resolution_state_ref": ref,
            "items": rows,
            "filter": filter_payload,
        }
        if truncation:
            payload["truncation"] = truncation
        if not_found:
            errors.extend(
                {"section": "resolution_state", "resolution_unit_id": uid, "reason": "not_found"}
                for uid in not_found
            )
        if not rows and not_found:
            return None, errors
        return payload, errors
    payload = build_resolution_state_index(
        snapshot,
        resolution_state_ref=str(ref) if ref is not None else None,
    )
    return payload, errors


def _inherited_handoff_conditions(handoff: Mapping[str, Any]) -> dict[str, Any]:
    source = handoff.get("source") if isinstance(handoff.get("source"), Mapping) else {}
    parcel_metadata = handoff.get("parcel_metadata") if isinstance(handoff.get("parcel_metadata"), Mapping) else {}
    issues = handoff.get("issues") if isinstance(handoff.get("issues"), list) else []
    hitl = handoff.get("hitl_decisions") if isinstance(handoff.get("hitl_decisions"), list) else []
    evidence = handoff.get("evidence_refs") if isinstance(handoff.get("evidence_refs"), list) else []
    excerpts = handoff.get("excerpts") if isinstance(handoff.get("excerpts"), Mapping) else {}
    prebuilt = handoff.get("inherited_handoff_conditions")
    if isinstance(prebuilt, Mapping) and prebuilt:
        return dict(prebuilt)
    return build_inherited_handoff_conditions(
        source=source,
        parcel_metadata=parcel_metadata,
        issues=[row for row in issues if isinstance(row, Mapping)],
        hitl_decisions=[row for row in hitl if isinstance(row, Mapping)],
        evidence_refs=[str(ref) for ref in evidence if isinstance(ref, str)],
        resolution_state_ref=str(handoff.get("resolution_state_ref") or "") or None,
        normalized_or_mapping_transcript=(
            str(handoff.get("normalized_or_mapping_transcript"))
            if isinstance(handoff.get("normalized_or_mapping_transcript"), str)
            else None
        ),
        source_transcript_verbatim=(
            str(handoff.get("source_transcript_verbatim"))
            if isinstance(handoff.get("source_transcript_verbatim"), str)
            else None
        ),
        excerpts=excerpts,
    )


def _bound_text(text: str) -> str:
    if len(text) <= MAX_TRANSCRIPT_CHARS:
        return text
    return text[: MAX_TRANSCRIPT_CHARS - 1].rstrip() + "…"


def _parse_sections(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for entry in value:
        if isinstance(entry, str) and entry.strip() and entry.strip() not in out:
            out.append(entry.strip())
    return out


def _parse_unit_ids(value: Any) -> tuple[list[str] | None, int]:
    if value is None:
        return None, 0
    if not isinstance(value, list):
        return None, 0
    out: list[str] = []
    for entry in value:
        if isinstance(entry, str) and entry.strip() and entry.strip() not in out:
            out.append(entry.strip())
    if not out:
        return None, 0
    if len(out) <= MAX_RESOLUTION_UNIT_IDS:
        return out, 0
    return out[:MAX_RESOLUTION_UNIT_IDS], len(out) - MAX_RESOLUTION_UNIT_IDS


def _section_error(section: str, reason: str) -> dict[str, str]:
    return {"section": section, "reason": reason}


def _extract_inputs(request: Any) -> dict[str, Any]:
    if hasattr(request, "inputs"):
        raw = request.inputs
        return dict(raw) if isinstance(raw, Mapping) else {}
    if isinstance(request, Mapping):
        return dict(request)
    return {}


def _refusal(code: str, message: str) -> dict[str, Any]:
    return {
        "executed": False,
        "refusal": {
            "reason_code": code,
            "retryable": False,
            "blocked_by_invariant": True,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {"error": {"code": code, "message": message}},
    }
