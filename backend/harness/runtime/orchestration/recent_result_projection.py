"""Prompt-only TTL compaction for recent tool/action result lanes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_STALE_TURN_AGE = 2
_HOT_TURN_AGE = 1


def _turn_index(row: Mapping[str, Any]) -> int | None:
    for key in ("kernel_turn_index", "source_turn_index"):
        try:
            return int(row.get(key))
        except (TypeError, ValueError):
            continue
    return None


def _refs_from_slice(row: Mapping[str, Any]) -> frozenset[str]:
    refs: set[str] = set()
    for key in ("latest_artifact_ref",):
        raw = row.get(key)
        if isinstance(raw, str) and raw.strip():
            refs.add(raw.strip())
    artifact_refs = row.get("artifact_refs") or []
    if isinstance(artifact_refs, list):
        for entry in artifact_refs:
            if isinstance(entry, str) and entry.strip():
                refs.add(entry.strip())
    delegate_ref = row.get("delegate_result_ref")
    if isinstance(delegate_ref, str) and delegate_ref.strip():
        refs.add(delegate_ref.strip())
    summary = row.get("evidence_artifact_summary")
    if isinstance(summary, Mapping):
        for key in ("derived_ref", "source_ref"):
            raw = summary.get(key)
            if isinstance(raw, str) and raw.strip():
                refs.add(raw.strip())
        rendered = summary.get("rendered_evidence_refs") or []
        if isinstance(rendered, list):
            for entry in rendered:
                if isinstance(entry, str) and entry.strip():
                    refs.add(entry.strip())
    crop_summary = row.get("point_crop_set_summary")
    if isinstance(crop_summary, Mapping):
        master = crop_summary.get("master_overlay_ref")
        if isinstance(master, str) and master.strip():
            refs.add(master.strip())
        points = crop_summary.get("points") or []
        if isinstance(points, list):
            for pt in points:
                if isinstance(pt, Mapping):
                    crop_ref = pt.get("crop_ref")
                    if isinstance(crop_ref, str) and crop_ref.strip():
                        refs.add(crop_ref.strip())
    return frozenset(refs)


def project_recent_tool_result_slices_for_prompt(
    slices: Sequence[Mapping[str, Any]],
    *,
    current_turn: int,
    hot_refs: frozenset[str],
) -> list[dict[str, Any]]:
    """Apply turn-age TTL without changing durable step-result records."""
    projected: list[dict[str, Any]] = []
    for row in slices:
        if not isinstance(row, Mapping):
            continue
        turn = _turn_index(row)
        age = (current_turn - turn) if turn is not None else _STALE_TURN_AGE
        row_refs = _refs_from_slice(row)
        keep_hot = age <= _HOT_TURN_AGE or bool(row_refs & hot_refs)
        projected.append(
            project_recent_result_for_prompt(dict(row), age=age, keep_hot=keep_hot)
        )
    return projected


def project_recent_action_sequence_for_prompt(
    record: Mapping[str, Any] | None,
    *,
    current_turn: int,
    hot_refs: frozenset[str],
) -> dict[str, Any] | None:
    from .action_sequence import project_sequence_item_row

    if not record:
        return None
    try:
        source_turn = int(record.get("source_turn_index", 0))
    except (TypeError, ValueError):
        source_turn = 0
    age = max(0, current_turn - source_turn)
    items = record.get("items") or []
    if not isinstance(items, (list, tuple)) or not items:
        return None
    projected_items = []
    for row in items[:5]:
        if not isinstance(row, Mapping):
            continue
        sanitized = project_sequence_item_row(row)
        row_refs = _refs_from_slice(sanitized)
        keep_hot = age <= _HOT_TURN_AGE or bool(row_refs & hot_refs)
        projected_items.append(
            project_recent_result_for_prompt(sanitized, age=age, keep_hot=keep_hot)
        )
    return {
        "sequence_id": str(record.get("batch_id") or record.get("sequence_id") or ""),
        "source_turn_index": source_turn,
        "items": projected_items,
    }


def project_recent_result_for_prompt(
    row: dict[str, Any],
    *,
    age: int,
    keep_hot: bool,
) -> dict[str, Any]:
    """Drop excerpt/detail for stale rows; preserve refs and mechanical status."""
    if keep_hot or age <= _HOT_TURN_AGE:
        return compact_stale_result_slice(row, stale=False)
    return compact_stale_result_slice(row, stale=True)


def compact_stale_result_slice(row: dict[str, Any], *, stale: bool) -> dict[str, Any]:
    if not stale:
        return {key: value for key, value in row.items() if value is not None}

    compact: dict[str, Any] = {}
    for key in (
        "kernel_turn_index",
        "source_turn_index",
        "action_type",
        "execution_state",
        "execution_reason_code",
        "alias",
        "status",
        "result_truncated",
        "latest_artifact_ref",
        "artifact_refs",
        "delegate_result_ref",
        "artifact_count",
        "output_shape",
        "outputs_structural_metadata",
        "outputs",
        "read_action_summary",
    ):
        if key in row and row[key] not in (None, "", [], {}):
            compact[key] = row[key]

    if "artifact_refs" in row and "artifact_count" not in compact:
        refs = row.get("artifact_refs") or []
        if isinstance(refs, list):
            compact["artifact_count"] = len(refs)

    summary = row.get("evidence_artifact_summary")
    if isinstance(summary, Mapping):
        compact["evidence_artifact_summary"] = {
            key: summary[key]
            for key in ("derived_ref", "source_ref", "rendered_evidence_refs")
            if key in summary and summary[key] not in (None, "", [], {})
        }

    crop_summary = row.get("point_crop_set_summary")
    if isinstance(crop_summary, Mapping):
        compact["point_crop_set_summary"] = {
            key: crop_summary[key]
            for key in (
                "kind",
                "sub_action",
                "overlay_role",
                "master_overlay_ref",
                "source_ref",
                "placement_surface_ref",
                "source_unwrapped_from_ref",
                "source_lineage_line",
                "legacy_source_repaired",
                "legacy_source_repair_warning",
                "previous_crop_set_overlay_ref",
                "view_of_crop_set_overlay_ref",
                "point_count",
                "points",
                "delegation_lines",
                "grid",
                "legend",
                "coordinate_lattice",
                "point_key_lines",
                "review_lines",
            )
            if key in crop_summary and crop_summary[key] not in (None, "", [], {})
        }

    source_window = row.get("source_window")
    if isinstance(source_window, Mapping):
        compact["source_window"] = {
            key: source_window[key]
            for key in (
                "root_box_norm",
                "local_box_norm",
                "touches_source_edge",
                "touches_root_source_edge",
                "room_to_source_edge_norm",
                "room_to_root_source_edge_norm",
                "can_expand",
                "can_expand_root",
                "position_label",
                "root_position_label",
                "edge_summary",
                "projection_available",
            )
            if key in source_window and source_window[key] not in (None, "", [], {})
        }

    excerpt = row.get("outputs_excerpt")
    if isinstance(excerpt, Mapping):
        compact["output_shape"] = {
            "top_level_keys": sorted(str(k) for k in excerpt.keys())[:12],
            "excerpt_omitted": True,
        }
    elif excerpt is not None:
        compact["output_shape"] = {"excerpt_omitted": True}

    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}
