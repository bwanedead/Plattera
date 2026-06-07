"""Tests for delegate wave timing aggregates."""

from __future__ import annotations

from harness.runtime.orchestration.delegate_wave_trace import (
    DelegateWaveTiming,
    attach_delegate_wave_metadata,
)
from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE


def _delegate_item(*, wall_seconds: float, alias: str = "read_a") -> dict:
    return {
        "alias": alias,
        "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
        "execution_state": "executed",
        "delegate_subtask": {
            "subtask_trace": {
                "wall_seconds": wall_seconds,
                "model_call_seconds": wall_seconds - 0.1,
                "retry_count": 0,
            }
        },
    }


def test_parallel_wave_metadata_records_elapsed_sum_and_max() -> None:
    sequence_result: dict = {}
    attach_delegate_wave_metadata(
        sequence_result,
        item_rows=[_delegate_item(wall_seconds=2.0), _delegate_item(wall_seconds=3.5, alias="read_b")],
        delegate_parallel=True,
        wave_timing=DelegateWaveTiming(
            wall_elapsed_seconds=3.6,
            started_at_epoch_seconds=1_700_000_000.0,
            finished_at_epoch_seconds=1_700_000_003.6,
        ),
    )
    assert sequence_result["delegate_parallel"] is True
    assert sequence_result["delegate_count"] == 2
    assert sequence_result["delegate_wave_elapsed_seconds"] == 3.6
    assert sequence_result["delegate_sum_subtask_seconds"] == 5.5
    assert sequence_result["delegate_max_subtask_seconds"] == 3.5
    assert sequence_result["delegate_wall_seconds_total"] == 3.6


def test_parallel_wave_elapsed_lte_sum_in_mocked_concurrent_path() -> None:
    sequence_result: dict = {}
    attach_delegate_wave_metadata(
        sequence_result,
        item_rows=[_delegate_item(wall_seconds=1.2), _delegate_item(wall_seconds=1.1, alias="read_b")],
        delegate_parallel=True,
        wave_timing=DelegateWaveTiming(
            wall_elapsed_seconds=1.25,
            started_at_epoch_seconds=10.0,
            finished_at_epoch_seconds=11.25,
        ),
    )
    assert sequence_result["delegate_wave_elapsed_seconds"] <= sequence_result["delegate_sum_subtask_seconds"]
