"""Mechanical delegate wave timing aggregates for action-sequence results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE


@dataclass(frozen=True)
class DelegateWaveTiming:
    wall_elapsed_seconds: float
    started_at_epoch_seconds: float
    finished_at_epoch_seconds: float


def is_homogeneous_delegate_batch(actions: Sequence[Mapping[str, Any]] | Sequence[Any]) -> bool:
    if not actions:
        return False
    for item in actions:
        action_type = str(getattr(item, "action_type", None) or (item.get("action_type") if isinstance(item, Mapping) else "") or "")
        if action_type != DELEGATE_SUBTASK_ACTION_TYPE:
            return False
    return True


def attach_delegate_wave_metadata(
    sequence_result: dict[str, Any],
    *,
    item_rows: Sequence[Mapping[str, Any]],
    delegate_parallel: bool,
    wave_timing: DelegateWaveTiming,
) -> None:
    """Persist wave-level delegate timing on a sequence result record."""
    delegate_count = sum(
        1
        for row in item_rows
        if str(row.get("action_type") or "") == DELEGATE_SUBTASK_ACTION_TYPE
    )
    if delegate_count < 1:
        return

    subtask_walls = _collect_subtask_wall_seconds(item_rows)
    sum_seconds = round(sum(subtask_walls), 3) if subtask_walls else 0.0
    max_seconds = round(max(subtask_walls), 3) if subtask_walls else 0.0
    wave_elapsed = round(float(wave_timing.wall_elapsed_seconds), 3)

    sequence_result["delegate_count"] = delegate_count
    sequence_result["delegate_parallel"] = bool(delegate_parallel)
    sequence_result["delegate_wave_started_at_epoch_seconds"] = round(
        float(wave_timing.started_at_epoch_seconds),
        3,
    )
    sequence_result["delegate_wave_finished_at_epoch_seconds"] = round(
        float(wave_timing.finished_at_epoch_seconds),
        3,
    )
    sequence_result["delegate_wave_elapsed_seconds"] = wave_elapsed
    sequence_result["delegate_sum_subtask_seconds"] = sum_seconds
    sequence_result["delegate_max_subtask_seconds"] = max_seconds
    # Compatibility alias: wave wall clock for parallel batches; serial uses loop span.
    sequence_result["delegate_wall_seconds_total"] = wave_elapsed


def _collect_subtask_wall_seconds(item_rows: Sequence[Mapping[str, Any]]) -> list[float]:
    walls: list[float] = []
    for row in item_rows:
        trace = _trace_from_item_row(row)
        if not isinstance(trace, Mapping):
            continue
        raw = trace.get("wall_seconds")
        if raw is None:
            raw = trace.get("total_seconds")
        if raw is None:
            continue
        try:
            walls.append(float(raw))
        except (TypeError, ValueError):
            continue
    return walls


def _trace_from_item_row(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for key in ("delegate_subtask", "outputs_excerpt"):
        block = row.get(key)
        if isinstance(block, Mapping):
            trace = block.get("subtask_trace")
            if isinstance(trace, Mapping):
                return trace
    return None
