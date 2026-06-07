"""Audit timeline rendering for delegate observation worklist observability."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from harness.audit.artifact_ref_links import (
    ArtifactLinkContext,
    format_ref_with_link,
    resolve_artifact_image_link,
)

_MAX_ROWS = 12


def render_delegate_observation_worklist_timeline(
    turn: Mapping[str, Any],
    *,
    link_context: ArtifactLinkContext | None = None,
) -> list[str]:
    summary = _coerce_mapping(turn.get("prompt_observability_summary"))
    worklist = _coerce_mapping(summary.get("delegate_observation_worklist"))
    if not worklist:
        return []

    rows = worklist.get("rows")
    if not isinstance(rows, list) or not rows:
        return []

    lines = ["Delegate observation worklist:"]
    counts = _coerce_mapping(worklist.get("counts"))
    unintegrated = counts.get("unintegrated_completed")
    if unintegrated is not None:
        lines.append(f"- unintegrated_completed: {unintegrated}")

    reminder = str(worklist.get("reminder") or "").strip()
    if reminder:
        lines.append(f"- reminder: {reminder}")

    for row in rows[:_MAX_ROWS]:
        if not isinstance(row, Mapping):
            continue
        lines.extend(_format_row(row, link_context=link_context))

    lines.append("")
    return lines


def _format_row(
    row: Mapping[str, Any],
    *,
    link_context: ArtifactLinkContext | None,
) -> list[str]:
    ref_id = str(row.get("ref_id") or "?")
    status = str(row.get("status") or "completed")
    rendered_ref = _render_ref(ref_id, link_context, label="subtask")
    lines = [f"- {rendered_ref} ({status})"]

    context_refs = row.get("context_refs")
    if isinstance(context_refs, list) and context_refs:
        rendered_refs = ", ".join(
            _render_ref(str(ref), link_context, label="context") for ref in context_refs[:4]
        )
        lines.append(f"  - context_refs: {rendered_refs}")

    for label, key in (
        ("task_response", "task_response_preview"),
        ("source_visible_text", "source_visible_text_preview"),
        ("ambiguity", "ambiguity_preview"),
        ("limits", "limits_preview"),
        ("task", "task_preview"),
    ):
        preview = str(row.get(key) or "").strip()
        if preview:
            lines.append(f"  - {label}: {preview}")

    trace = _coerce_mapping(row.get("subtask_trace"))
    if trace:
        parts: list[str] = []
        if trace.get("total_seconds") is not None:
            parts.append(f"total={trace['total_seconds']}s")
        if trace.get("model_call_seconds") is not None:
            parts.append(f"model={trace['model_call_seconds']}s")
        if trace.get("retry_count") is not None:
            parts.append(f"retries={trace['retry_count']}")
        if trace.get("prompt_char_count") is not None:
            parts.append(f"prompt_chars={trace['prompt_char_count']}")
        if trace.get("image_attachment_count") is not None:
            parts.append(f"images={trace['image_attachment_count']}")
        if parts:
            lines.append(f"  - timing: {' '.join(parts)}")

    return lines


def _render_ref(
    ref_id: str,
    link_context: ArtifactLinkContext | None,
    *,
    label: str,
) -> str:
    if not ref_id:
        return "none"
    if link_context is None:
        return f"`{ref_id}`"
    link = resolve_artifact_image_link(ref_id, link_context, link_label=label)
    return format_ref_with_link(ref_id, link, link_label=label)


def _coerce_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
