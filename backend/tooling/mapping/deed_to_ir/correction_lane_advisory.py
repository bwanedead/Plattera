"""Mechanical non-blocking advisory when upstream_corrections may be missing."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MAX_MATCHED_TERMS = 8

CORRECTION_LANGUAGE_TERMS: tuple[str, ...] = (
    "upstream defect",
    "upstream correction",
    "transcript defect",
    "corrected ir",
    "source-grounded correction",
    "inherited value",
    "handoff value",
    "differs from inherited",
    "source reads",
    "corrected value",
    "corrected distance",
    "corrected course",
)

CORRECTION_HINT = (
    "If the final IR intentionally differs from inherited transcript/resolution/mapping operands, "
    "add an upstream_corrections row. Do not put upstream deltas only in notes."
)


def _row_text_fields(row: Mapping[str, Any]) -> list[str]:
    fields: list[str] = []
    for key in ("summary", "title", "description", "rationale", "note_id", "scope_id"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            fields.append(value.strip())
    return fields


def _collect_package_text(
    *,
    scope_results: list[Any] | None,
    external_dependencies: list[Any] | None,
    closure_dimensions: list[Any] | None,
    notes: list[Any] | None,
) -> str:
    chunks: list[str] = []
    for section in (scope_results, external_dependencies, closure_dimensions, notes):
        if not isinstance(section, list):
            continue
        for row in section:
            if not isinstance(row, Mapping):
                continue
            chunks.extend(_row_text_fields(row))
    return "\n".join(chunks).lower()


def _collect_basis_refs(
    *,
    scope_results: list[Any] | None,
    closure_dimensions: list[Any] | None,
    notes: list[Any] | None,
) -> list[str]:
    refs: list[str] = []
    for section in (scope_results, closure_dimensions, notes):
        if not isinstance(section, list):
            continue
        for row in section:
            if not isinstance(row, Mapping):
                continue
            basis = row.get("basis_refs")
            if not isinstance(basis, list):
                continue
            for ref in basis:
                if isinstance(ref, str) and ref.strip():
                    refs.append(ref.strip())
    return refs


def detect_correction_lane_advisory(
    *,
    upstream_corrections: list[Any] | None,
    scope_results: list[Any] | None = None,
    external_dependencies: list[Any] | None = None,
    closure_dimensions: list[Any] | None = None,
    notes: list[Any] | None = None,
) -> dict[str, Any] | None:
    """Return advisory metadata when corrections are empty but text suggests correction reporting."""
    if isinstance(upstream_corrections, list) and upstream_corrections:
        return None

    combined = _collect_package_text(
        scope_results=scope_results,
        external_dependencies=external_dependencies,
        closure_dimensions=closure_dimensions,
        notes=notes,
    )
    matched_terms: list[str] = []
    for term in CORRECTION_LANGUAGE_TERMS:
        if term in combined:
            matched_terms.append(term)
        if len(matched_terms) >= MAX_MATCHED_TERMS:
            break

    basis_refs = _collect_basis_refs(
        scope_results=scope_results,
        closure_dimensions=closure_dimensions,
        notes=notes,
    )
    has_image_derived = any(ref.startswith("image:derived:") for ref in basis_refs)
    image_derived_with_correction_language = has_image_derived and bool(matched_terms)

    possible = bool(matched_terms) or image_derived_with_correction_language
    if not possible:
        return None

    advisory: dict[str, Any] = {
        "upstream_corrections_empty": True,
        "possible_correction_language_found": True,
        "matched_terms": matched_terms[:MAX_MATCHED_TERMS],
        "repair_hint": CORRECTION_HINT,
    }
    if image_derived_with_correction_language:
        advisory["image_derived_basis_with_correction_language"] = True
    return advisory


def render_correction_lane_advisory_timeline_lines(
    advisory: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(advisory, Mapping) or not advisory:
        return []
    lines = [f"{indent}correction_lane_advisory:"]
    lines.append(
        "{indent}  upstream_corrections_empty={empty} matched_terms={terms}".format(
            indent=indent,
            empty=advisory.get("upstream_corrections_empty"),
            terms=", ".join(advisory.get("matched_terms") or []) or "none",
        )
    )
    hint = advisory.get("repair_hint")
    if isinstance(hint, str) and hint.strip():
        lines.append(f"{indent}  hint={hint.strip()}")
    return lines
