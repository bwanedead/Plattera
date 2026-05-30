"""Audit timeline rendering for state_patch repair bundles."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def render_state_patch_repair_bundle_timeline(turn: Mapping[str, Any]) -> list[str]:
    feedback = _coerce_mapping(turn.get("state_patch_feedback"))
    bundle = _coerce_mapping(feedback.get("state_patch_repair_bundle"))
    fragments = bundle.get("fragments")
    if not isinstance(fragments, list) or not fragments:
        return []

    lines = ["State patch repair bundle:"]
    reason = bundle.get("reason")
    if reason:
        lines.append(f"- reason: {reason}")
    lines.append(f"- fragments: {len(fragments)}")
    for row in fragments[:5]:
        if not isinstance(row, Mapping):
            continue
        path = str(row.get("path") or "?")
        lines.append(f"- {path}")
        errors = row.get("validation_errors") or []
        if isinstance(errors, list) and errors:
            lines.append(f"  - errors: {'; '.join(str(e) for e in errors[:3])}")
        fragment = _coerce_mapping(row.get("fragment"))
        if fragment:
            summary = _compact_fragment_summary(fragment)
            if summary:
                lines.append(f"  - fragment: {summary}")
        if row.get("truncated"):
            lines.append("  - truncated: true")
    lines.append("")
    return lines


def _compact_fragment_summary(fragment: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "status",
        "determination",
        "determined_value",
        "item_id",
        "unit_id",
    ):
        value = fragment.get(key)
        if value not in (None, ""):
            text = str(value).replace("\n", " ").strip()
            if len(text) > 120:
                text = text[:117] + "..."
            parts.append(f"{key}={text}")
    if fragment.get("evidence_refs"):
        refs = fragment.get("evidence_refs")
        if isinstance(refs, list) and refs:
            parts.append(f"evidence_refs={refs[0]}")
    return " ".join(parts)


def _coerce_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
