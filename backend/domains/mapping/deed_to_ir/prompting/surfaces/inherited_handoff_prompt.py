"""Agent-facing prompt rendering for inherited handoff conditions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_PROMPT_LANE_NOTES = 4
_PROMPT_EVIDENCE_REFS = 12


def format_inherited_handoff_conditions_markdown(block: Mapping[str, Any]) -> str:
    """Render inherited handoff conditions for startup prompts (copy-only labels)."""
    lines: list[str] = [
        "### Inherited handoff conditions (upstream — not agent conclusions)",
        "",
        "Mechanical copy of transcript-edit output lanes deed-to-IR inherits. "
        "Treat these as starting inputs and provenance — not local work inventory to recreate.",
        "",
    ]

    upstream = block.get("upstream_source")
    if isinstance(upstream, Mapping) and upstream:
        lines.append("**Upstream output identity**")
        label = upstream.get("loaded_source_label")
        if label:
            lines.append(f"- loaded_from: `{label}`")
        ref = upstream.get("source_revision_ref")
        if ref:
            lines.append(f"- source_revision_ref: `{ref}`")
        published = upstream.get("published_at")
        if published:
            lines.append(f"- published_at: {published}")
        rs_ref = block.get("resolution_state_ref")
        if rs_ref:
            lines.append(f"- resolution_state_ref: `{rs_ref}`")
        lines.append("")

    parcels = block.get("parcels")
    if isinstance(parcels, list) and parcels:
        lines.append("**Parcel forwardability (copied from parcel_metadata)**")
        for row in parcels:
            if not isinstance(row, Mapping):
                continue
            pid = row.get("parcel_id", "?")
            fwd = row.get("forwardable")
            scope = row.get("forwardable_scope")
            governing = row.get("governing_range")
            lines.append(f"- `{pid}` forwardable={fwd} scope={scope!r} governing_range={governing!r}")
            notes = row.get("lane_notes")
            if isinstance(notes, list):
                for note in notes[:_PROMPT_LANE_NOTES]:
                    if isinstance(note, str) and note.strip():
                        lines.append(f"  - lane_note: {note.strip()}")
        lines.append("")

    issues = block.get("issues")
    if isinstance(issues, list) and issues:
        lines.append("**Upstream issues / dependency signals (copied from issues)**")
        for issue in issues:
            if not isinstance(issue, Mapping):
                continue
            iid = issue.get("issue_id", "?")
            summary = issue.get("summary", "")
            disposition = issue.get("downstream_disposition")
            blocking = issue.get("mapping_blocking")
            parts = [f"- `{iid}`: {summary}"]
            if disposition:
                parts.append(f" downstream_disposition={disposition!r}")
            if blocking is not None:
                parts.append(f" mapping_blocking={blocking}")
            lines.append("".join(parts))
        lines.append("")

    hitl = block.get("hitl_decisions")
    if isinstance(hitl, list) and hitl:
        lines.append("**HITL decisions (copied from hitl_decisions)**")
        for row in hitl:
            if not isinstance(row, Mapping):
                continue
            choice = row.get("choice", "")
            note = row.get("note")
            lines.append(f"- choice: {choice}")
            if isinstance(note, str) and note.strip():
                lines.append(f"  note: {note.strip()}")
        lines.append("")

    evidence = block.get("evidence_refs")
    if isinstance(evidence, Mapping):
        count = evidence.get("count", 0)
        sample = evidence.get("sample")
        if count:
            lines.append(f"**Evidence refs:** count={count}")
            if isinstance(sample, list):
                for ref in sample[:_PROMPT_EVIDENCE_REFS]:
                    lines.append(f"- `{ref}`")
            lines.append("")

    lanes = block.get("transcript_lane_excerpts")
    if isinstance(lanes, Mapping):
        for label, key in (
            ("Normalized / mapping lane excerpt", "normalized_or_mapping_transcript"),
            ("Source verbatim lane excerpt", "source_transcript_verbatim"),
        ):
            excerpt = lanes.get(key)
            if isinstance(excerpt, str) and excerpt.strip():
                lines.append(f"**{label}**")
                lines.append(excerpt)
                lines.append("")

    return "\n".join(lines).rstrip()
