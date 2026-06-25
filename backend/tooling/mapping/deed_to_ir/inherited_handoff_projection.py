"""Mechanical projection of inherited transcript-edit handoff conditions for deed-to-IR."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

MAX_PARCEL_ROWS = 12
MAX_ISSUE_ROWS = 8
MAX_HITL_ROWS = 8
MAX_EVIDENCE_REFS = 12
MAX_LANE_NOTES = 4
MAX_LANE_NOTE_CHARS = 240
MAX_TRANSCRIPT_EXCERPT_CHARS = 600

_ISSUE_COPY_KEYS = (
    "issue_id",
    "scope",
    "summary",
    "layer",
    "mapping_blocking",
    "downstream_disposition",
)
_PARCEL_COPY_KEYS = (
    "parcel_id",
    "forwardable",
    "forwardable_scope",
    "governing_range",
)
_HITL_COPY_KEYS = ("choice", "note", "prompt_id")


def build_inherited_handoff_conditions(
    *,
    source: Mapping[str, Any] | None = None,
    parcel_metadata: Mapping[str, Any] | None = None,
    issues: Sequence[Mapping[str, Any]] | None = None,
    hitl_decisions: Sequence[Mapping[str, Any]] | None = None,
    evidence_refs: Sequence[str] | None = None,
    resolution_state_ref: str | None = None,
    normalized_or_mapping_transcript: str | None = None,
    source_transcript_verbatim: str | None = None,
    excerpts: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    """Copy bounded upstream handoff lanes into a single salience block (no inference)."""
    upstream_source = _copy_upstream_source(source)
    parcels, parcels_omitted = _copy_parcel_conditions(parcel_metadata)
    issue_rows, issues_omitted = _copy_issue_rows(issues)
    hitl_rows, hitl_omitted = _copy_hitl_rows(hitl_decisions)
    evidence = _copy_evidence_refs(evidence_refs)
    transcript_lanes = _copy_transcript_lane_excerpts(
        normalized_or_mapping_transcript=normalized_or_mapping_transcript,
        source_transcript_verbatim=source_transcript_verbatim,
        excerpts=excerpts,
    )

    payload: dict[str, Any] = {
        "block_id": "inherited_handoff_conditions",
        "upstream_source": upstream_source,
        "parcels": parcels,
        "issues": issue_rows,
        "hitl_decisions": hitl_rows,
        "evidence_refs": evidence,
        "transcript_lane_excerpts": transcript_lanes,
    }
    ref = _opt_str(resolution_state_ref)
    if ref:
        payload["resolution_state_ref"] = ref

    truncation: dict[str, int] = {}
    if parcels_omitted:
        truncation["parcels_omitted"] = parcels_omitted
    if issues_omitted:
        truncation["issues_omitted"] = issues_omitted
    if hitl_omitted:
        truncation["hitl_decisions_omitted"] = hitl_omitted
    if evidence.get("omitted", 0):
        truncation["evidence_refs_omitted"] = int(evidence["omitted"])
    if truncation:
        payload["truncation"] = truncation
    return payload


def _copy_upstream_source(source: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    out: dict[str, Any] = {}
    for key in ("loaded_source_label", "source_revision_ref", "published_at"):
        value = _opt_str(source.get(key))
        if value:
            out[key] = value
    return out


def _copy_parcel_conditions(
    parcel_metadata: Mapping[str, Any] | None,
) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(parcel_metadata, Mapping):
        return [], 0
    rows_raw = parcel_metadata.get("parcels")
    if not isinstance(rows_raw, list):
        return [], 0
    rows: list[dict[str, Any]] = []
    omitted = 0
    for row in rows_raw:
        if len(rows) >= MAX_PARCEL_ROWS:
            omitted += 1
            continue
        if not isinstance(row, Mapping):
            continue
        copied = _copy_row_keys(row, _PARCEL_COPY_KEYS)
        lane_notes = row.get("lane_notes")
        if isinstance(lane_notes, list):
            copied["lane_notes"] = [
                _bound_text(str(note), MAX_LANE_NOTE_CHARS)
                for note in lane_notes[:MAX_LANE_NOTES]
                if isinstance(note, str) and note.strip()
            ]
        if copied:
            rows.append(copied)
    if len(rows_raw) > MAX_PARCEL_ROWS:
        omitted = max(omitted, len(rows_raw) - MAX_PARCEL_ROWS)
    return rows, omitted


def _copy_issue_rows(
    issues: Sequence[Mapping[str, Any]] | None,
) -> tuple[list[dict[str, Any]], int]:
    if not issues:
        return [], 0
    rows: list[dict[str, Any]] = []
    omitted = 0
    for issue in issues:
        if len(rows) >= MAX_ISSUE_ROWS:
            omitted += 1
            continue
        if not isinstance(issue, Mapping):
            continue
        copied = _copy_row_keys(issue, _ISSUE_COPY_KEYS)
        if copied:
            rows.append(copied)
    if len(issues) > MAX_ISSUE_ROWS:
        omitted = max(omitted, len(issues) - MAX_ISSUE_ROWS)
    return rows, omitted


def _copy_hitl_rows(
    hitl_decisions: Sequence[Mapping[str, Any]] | None,
) -> tuple[list[dict[str, Any]], int]:
    if not hitl_decisions:
        return [], 0
    rows: list[dict[str, Any]] = []
    omitted = 0
    for row in hitl_decisions:
        if len(rows) >= MAX_HITL_ROWS:
            omitted += 1
            continue
        if not isinstance(row, Mapping):
            continue
        copied = _copy_row_keys(row, _HITL_COPY_KEYS)
        if copied:
            rows.append(copied)
    if len(hitl_decisions) > MAX_HITL_ROWS:
        omitted = max(omitted, len(hitl_decisions) - MAX_HITL_ROWS)
    return rows, omitted


def _copy_evidence_refs(evidence_refs: Sequence[str] | None) -> dict[str, Any]:
    if not evidence_refs:
        return {"count": 0, "sample": [], "omitted": 0}
    refs = [str(ref).strip() for ref in evidence_refs if isinstance(ref, str) and str(ref).strip()]
    sample = refs[:MAX_EVIDENCE_REFS]
    omitted = max(0, len(refs) - len(sample))
    return {"count": len(refs), "sample": sample, "omitted": omitted}


def _copy_transcript_lane_excerpts(
    *,
    normalized_or_mapping_transcript: str | None,
    source_transcript_verbatim: str | None,
    excerpts: Mapping[str, str | None] | None,
) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    excerpt_map = excerpts if isinstance(excerpts, Mapping) else {}
    normalized = _opt_str(excerpt_map.get("normalized_or_mapping_transcript")) or _opt_str(
        normalized_or_mapping_transcript
    )
    verbatim = _opt_str(excerpt_map.get("source_transcript_verbatim")) or _opt_str(
        source_transcript_verbatim
    )
    if normalized:
        out["normalized_or_mapping_transcript"] = _bound_text(normalized, MAX_TRANSCRIPT_EXCERPT_CHARS)
    if verbatim:
        out["source_transcript_verbatim"] = _bound_text(verbatim, MAX_TRANSCRIPT_EXCERPT_CHARS)
    return out


def _copy_row_keys(row: Mapping[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in keys:
        if key not in row:
            continue
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
            if text:
                out[key] = text
            continue
        out[key] = value
    return out


def _opt_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _bound_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"
