"""Audit timeline rendering for stable_context orientation memory."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from harness.audit.artifact_ref_links import (
    ArtifactLinkContext,
    format_ref_with_link,
    resolve_artifact_image_link,
)


def render_stable_context_timeline(
    turn: Mapping[str, Any],
    *,
    link_context: ArtifactLinkContext | None = None,
) -> list[str]:
    feedback = _coerce_mapping(turn.get("state_patch_feedback"))
    turn_delta = _coerce_mapping(feedback.get("stable_context"))
    if not turn_delta:
        turn_delta = _coerce_mapping(_coerce_mapping(feedback.get("detail")).get("stable_context"))
    snapshot = _coerce_mapping(turn.get("stable_context"))
    if not turn_delta and not snapshot:
        return []

    lines = ["Stable Context"]
    upserted = turn_delta.get("upserted") if turn_delta else None
    retired = turn_delta.get("retired") if turn_delta else None
    skipped = turn_delta.get("skipped_rows") if turn_delta else None
    if isinstance(upserted, list) and upserted:
        lines.append("  upserted_this_turn:")
        for context_id in upserted[:16]:
            lines.append(f"    - {context_id}")
    if isinstance(retired, list) and retired:
        lines.append("  retired_this_turn:")
        for context_id in retired[:16]:
            lines.append(f"    - {context_id}")
    if isinstance(skipped, list) and skipped:
        lines.append("  skipped_rows:")
        for row in skipped[:8]:
            if isinstance(row, Mapping):
                lines.append(f"    - {row.get('reason') or row}")

    for section, label in (
        ("active", "active_index"),
        ("retired", "retired_index"),
        ("expired", "expired_index"),
    ):
        rows = snapshot.get(section) if snapshot else None
        if not isinstance(rows, list) or not rows:
            continue
        lines.append(f"  {label}:")
        for row in rows[:12]:
            if not isinstance(row, Mapping):
                continue
            context_id = str(row.get("context_id") or "").strip()
            if not context_id:
                continue
            title = str(row.get("title") or "").strip()
            role = str(row.get("role") or "").strip()
            header = context_id
            if title:
                header = f"{header} | {title}"
            if role:
                header = f"{header} | role={role}"
            remaining = row.get("expires_in_turns")
            if remaining is not None:
                header = f"{header} | expires_in_turns={remaining}"
            lines.append(f"    - {header}")
            basis_refs = row.get("basis_refs")
            if isinstance(basis_refs, list) and basis_refs:
                lines.append("      basis_refs:")
                for ref in basis_refs[:8]:
                    lines.append(f"        - {_render_ref(str(ref), link_context)}")
            attached = row.get("attached_entity_ids")
            if isinstance(attached, list) and attached:
                lines.append("      attached_entity_ids:")
                for entity_id in attached[:12]:
                    lines.append(f"        - {entity_id}")
            excerpt = row.get("body_excerpt")
            if isinstance(excerpt, str) and excerpt.strip():
                lines.append(f"      body_excerpt: {excerpt.strip()}")

    lines.append("")
    return lines


def _coerce_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _render_ref(ref_id: str, link_context: ArtifactLinkContext | None) -> str:
    if not ref_id:
        return "none"
    if link_context is None:
        return f"`{ref_id}`"
    link = resolve_artifact_image_link(ref_id, link_context, link_label="basis_ref")
    return format_ref_with_link(ref_id, link, link_label="basis_ref")
