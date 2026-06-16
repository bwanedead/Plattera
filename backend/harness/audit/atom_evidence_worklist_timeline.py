"""Audit timeline rendering for atom evidence worklist observability."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from harness.audit.artifact_ref_links import (
    ArtifactLinkContext,
    format_ref_with_link,
    resolve_artifact_image_link,
)

_UTIL_OPEN_PACKET_READY = "open_packet_ready_unused"
_UTIL_OPEN_PACKET_USED = "open_packet_used_not_determined"
_UTIL_OPEN_EVIDENCE_REF = "open_evidence_referenced_not_determined"


def render_atom_evidence_worklist_timeline(
    turn: Mapping[str, Any],
    *,
    link_context: ArtifactLinkContext | None = None,
) -> list[str]:
    """Render a compact worklist section from prompt observability on a turn."""
    summary = _coerce_mapping(turn.get("prompt_observability_summary"))
    worklist = _coerce_mapping(summary.get("atom_evidence_worklist"))
    if not worklist:
        return []

    lines = ["Atom Evidence Worklist:"]
    counts = _coerce_mapping(worklist.get("counts"))
    if counts:
        lines.append(_format_counts_line(counts))

    priority_rows = worklist.get("priority_rows")
    if isinstance(priority_rows, list):
        grouped = _group_priority_rows(priority_rows)
        for utilization_status, label in (
            (_UTIL_OPEN_PACKET_READY, "open packet ready unused"),
            (_UTIL_OPEN_PACKET_USED, "open packet used not determined"),
            (_UTIL_OPEN_EVIDENCE_REF, "open evidence referenced not determined"),
        ):
            rows = grouped.get(utilization_status) or []
            if not rows:
                continue
            lines.append(f"- {label}:")
            for row in rows:
                if isinstance(row, Mapping):
                    lines.extend(
                        _format_priority_row(row, link_context=link_context, indent="  ")
                    )

    unmatched = worklist.get("unmatched_packet_refs")
    if isinstance(unmatched, list) and unmatched:
        lines.append("- unmatched packet refs:")
        for row in unmatched:
            if isinstance(row, Mapping):
                lines.extend(
                    _format_unmatched_row(row, link_context=link_context, indent="  ")
                )

    lines.append("")
    return lines


def _group_priority_rows(rows: list[Any]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        status = str(row.get("utilization_status") or "")
        grouped.setdefault(status, []).append(row)
    return grouped


def _format_counts_line(counts: Mapping[str, Any]) -> str:
    parts = []
    total = counts.get("atoms_total")
    if total is not None:
        parts.append(f"{total} atoms")
    closed = counts.get("closed")
    if closed is not None:
        parts.append(f"{closed} closed")
    open_count = counts.get("open")
    if open_count is not None:
        parts.append(f"{open_count} open")
    blocked = counts.get("blocked")
    if blocked is not None:
        parts.append(f"{blocked} blocked")
    ready = counts.get("packet_ready_unused")
    if ready is not None:
        parts.append(f"{ready} packet-ready-unused")
    used = counts.get("packet_used_not_determined")
    if used is not None:
        parts.append(f"{used} packet-used-not-determined")
    unmatched = counts.get("unmatched_packet_refs")
    if unmatched is not None:
        parts.append(f"{unmatched} unmatched-packet-refs")
    return f"- counts: {' · '.join(parts)}"


def _format_priority_row(
    row: Mapping[str, Any],
    *,
    link_context: ArtifactLinkContext | None,
    indent: str,
) -> list[str]:
    atom_id = str(row.get("atom_id") or "?")
    packet_refs = row.get("packet_refs")
    if not isinstance(packet_refs, list) or not packet_refs:
        return [f"{indent}- {atom_id} (no packet refs in projection)"]

    lines: list[str] = []
    for pref in packet_refs[:4]:
        if not isinstance(pref, Mapping):
            continue
        lines.append(
            f"{indent}- {_format_atom_packet_line(atom_id, pref, link_context=link_context)}"
        )
    delegate_refs = row.get("delegate_refs")
    if isinstance(delegate_refs, list):
        for delegate in delegate_refs[:2]:
            if isinstance(delegate, Mapping):
                lines.append(f"{indent}  delegate {_format_delegate_tail(delegate, link_context)}")
    return lines


def _format_unmatched_row(
    row: Mapping[str, Any],
    *,
    link_context: ArtifactLinkContext | None,
    indent: str,
) -> list[str]:
    alias = str(row.get("source_alias") or "?")
    crop_ref = str(row.get("crop_ref") or "")
    crop = _render_ref(crop_ref, link_context, label="crop")
    line = f"{indent}- {alias} -> crop {crop}"
    target_atom_id = str(row.get("target_atom_id") or "").strip()
    if target_atom_id:
        line += f" target_atom_id {target_atom_id}"
    target_hint = str(row.get("target_hint") or "").strip()
    if target_hint:
        line += f' hint="{target_hint}"'
    overlay_ref = str(row.get("overlay_ref") or "")
    if overlay_ref:
        line += f" overlay {_render_ref(overlay_ref, link_context, label='overlay')}"
    turn = row.get("created_turn")
    if turn is not None:
        line += f" created T{turn}"
    lines = [line]
    delegate_refs = row.get("delegate_refs")
    if isinstance(delegate_refs, list):
        for delegate in delegate_refs[:2]:
            if isinstance(delegate, Mapping):
                lines.append(f"{indent}  delegate {_format_delegate_tail(delegate, link_context)}")
    return lines


def _format_atom_packet_line(
    atom_id: str,
    pref: Mapping[str, Any],
    *,
    link_context: ArtifactLinkContext | None,
) -> str:
    crop_ref = str(pref.get("crop_ref") or "")
    overlay_ref = str(pref.get("overlay_ref") or "")
    source_alias = str(pref.get("source_alias") or "")
    match_kind = str(pref.get("match_kind") or "")
    turn = pref.get("created_turn")

    if match_kind == "shared_evidence_ref":
        label = atom_id
        detail = f"shared/cited crop {_render_ref(crop_ref, link_context, label='crop')}"
        if source_alias and source_alias != atom_id:
            detail += f" alias {source_alias}"
    elif match_kind == _MATCH_TARGET_ATOM_ID:
        label = atom_id
        detail = (
            f"target_atom_id crop {_render_ref(crop_ref, link_context, label='crop')}"
        )
        if source_alias and source_alias != atom_id:
            detail += f" alias {source_alias}"
    elif match_kind and match_kind != "direct_alias_match":
        label = atom_id
        detail = (
            f"{match_kind.replace('_', ' ')} crop {_render_ref(crop_ref, link_context, label='crop')}"
        )
    else:
        label = atom_id
        detail = f"crop {_render_ref(crop_ref, link_context, label='crop')}"

    if overlay_ref:
        detail += f" overlay {_render_ref(overlay_ref, link_context, label='overlay')}"
    if source_alias and match_kind != "shared_evidence_ref":
        detail += f" alias {source_alias}"
    target_atom_id = str(pref.get("target_atom_id") or "").strip()
    if target_atom_id and target_atom_id != atom_id:
        detail += f" target_atom_id {target_atom_id}"
    target_hint = str(pref.get("target_hint") or "").strip()
    if target_hint:
        detail += f' hint="{target_hint}"'
    if turn is not None:
        detail += f" created T{turn}"

    nested = pref.get("delegate_refs")
    if isinstance(nested, list) and nested:
        delegate = nested[0]
        if isinstance(delegate, Mapping):
            detail += f" delegate {_format_delegate_tail(delegate, link_context)}"
    return f"{label} -> {detail}"


def _format_delegate_tail(
    delegate: Mapping[str, Any],
    link_context: ArtifactLinkContext | None,
) -> str:
    ref = str(delegate.get("delegate_ref") or "")
    status = str(delegate.get("delegate_status") or "")
    rendered = _render_ref(ref, link_context, label="delegate")
    if status:
        return f"{rendered} status {status}"
    return rendered


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
