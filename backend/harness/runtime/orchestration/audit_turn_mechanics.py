"""Compact mechanical audit projections for human timeline (no semantic inference)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .action_batch import sequence_result_items_cap
from .subtasks.projection import project_subtask_row


def _coerce_list(value: Any, *, limit: int) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        return []
    return list(value[:limit])


def project_hydration_record_for_audit(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    out: dict[str, Any] = {
        "requested_refs": _coerce_list(record.get("requested_refs"), limit=8),
        "resolved_refs": _coerce_list(record.get("resolved_refs"), limit=8),
        "status": str(record.get("status") or ""),
        "source_turn_index": record.get("source_turn_index"),
        "surfaced_iteration": record.get("surfaced_iteration"),
    }
    reason = record.get("reason")
    if reason:
        out["reason"] = str(reason)[:400]
    errors = record.get("hydration_errors") or record.get("errors")
    if isinstance(errors, list) and errors:
        out["hydration_errors"] = [
            {
                "reason_code": str(row.get("reason_code") or row)[:128]
                if isinstance(row, Mapping)
                else str(row)[:128]
            }
            for row in errors[:5]
            if row is not None
        ]
    hydrated = record.get("hydrated_results")
    if isinstance(hydrated, list) and hydrated:
        out["hydrated_result_count"] = len(hydrated)
        out["hydrated_ref_ids"] = [
            str(row.get("ref_id") or row.get("ref") or "")[:256]
            for row in hydrated[:8]
            if isinstance(row, Mapping)
        ]
    return out


def project_pinned_hydration_for_audit(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    refs = _coerce_list(record.get("refs"), limit=8)
    if not refs:
        return None
    out: dict[str, Any] = {
        "refs": [str(ref) for ref in refs],
        "status": str(record.get("status") or ""),
        "surfaced_iteration": record.get("surfaced_iteration"),
    }
    errors = record.get("hydration_errors")
    if isinstance(errors, list) and errors:
        out["hydration_errors"] = [
            {
                "reason_code": str(row.get("reason_code") or row)[:128]
                if isinstance(row, Mapping)
                else str(row)[:128]
            }
            for row in errors[:5]
            if row is not None
        ]
    hydrated = record.get("hydrated_results")
    if isinstance(hydrated, list) and hydrated:
        out["hydrated_result_count"] = len(hydrated)
    return out


def project_action_sequence_for_audit(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    items = record.get("items")
    if not isinstance(items, (list, tuple)) or not items:
        return None
    rows: list[dict[str, Any]] = []
    for raw in items[: sequence_result_items_cap(items)]:
        if not isinstance(raw, Mapping):
            continue
        row = {
            "alias": str(raw.get("alias") or "")[:64],
            "action_type": str(raw.get("action_type") or "")[:128],
            "execution_state": str(raw.get("execution_state") or "")[:64],
            "reason_code": str(raw.get("reason_code") or "")[:128] or None,
        }
        subtask = project_subtask_row(raw)
        if subtask:
            row["delegate_subtask"] = subtask
        rows.append(row)
    if not rows:
        return None
    out: dict[str, Any] = {
        "sequence_id": str(record.get("sequence_id") or record.get("batch_id") or "")[:64],
        "source_turn_index": record.get("source_turn_index"),
        "items": rows,
    }
    if record.get("delegate_parallel") is True:
        out["delegate_parallel"] = True
    for key in (
        "delegate_count",
        "delegate_wave_started_at_epoch_seconds",
        "delegate_wave_finished_at_epoch_seconds",
        "delegate_wave_elapsed_seconds",
        "delegate_sum_subtask_seconds",
        "delegate_max_subtask_seconds",
        "delegate_wall_seconds_total",
    ):
        raw = record.get(key)
        if raw is None:
            continue
        try:
            if key == "delegate_count":
                out[key] = int(raw)
            else:
                out[key] = round(float(raw), 3)
        except (TypeError, ValueError):
            continue
    return out


def build_host_hydration_before_turn(
    *,
    pending_agent_hydration: Mapping[str, Any] | None,
    pinned_refs_hydration: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    agent_lane = project_hydration_record_for_audit(pending_agent_hydration)
    pinned_lane = project_pinned_hydration_for_audit(pinned_refs_hydration)
    if not agent_lane and not pinned_lane:
        return None
    payload: dict[str, Any] = {}
    if agent_lane:
        payload["agent_requested_hydration"] = agent_lane
    if pinned_lane:
        payload["pinned_refs_auto_hydration"] = pinned_lane
    return payload
