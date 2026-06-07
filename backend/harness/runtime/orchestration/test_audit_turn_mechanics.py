"""Tests for mechanical audit projections."""

from __future__ import annotations

from harness.runtime.orchestration.audit_turn_mechanics import project_action_sequence_for_audit
from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE


def _delegate_item(alias: str) -> dict:
    return {
        "alias": alias,
        "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
        "execution_state": "executed",
        "delegate_subtask": {
            "subtask_id": alias,
            "profile": "harness.observation",
            "status": "completed",
            "result": {"reading": "A"},
        },
    }


def test_project_action_sequence_for_audit_preserves_delegate_parallel_metadata() -> None:
    items = [_delegate_item(f"read_{index}") for index in range(12)]
    projected = project_action_sequence_for_audit(
        {
            "batch_id": "req:iter:7:batch",
            "source_turn_index": 7,
            "items": items,
            "delegate_parallel": True,
            "delegate_count": 12,
            "delegate_wave_elapsed_seconds": 4.512,
            "delegate_sum_subtask_seconds": 10.0,
            "delegate_max_subtask_seconds": 1.5,
            "delegate_wall_seconds_total": 4.512,
        }
    )
    assert projected is not None
    assert projected["delegate_parallel"] is True
    assert projected["delegate_count"] == 12
    assert projected["delegate_wave_elapsed_seconds"] == 4.512
    assert projected["delegate_sum_subtask_seconds"] == 10.0
    assert projected["delegate_max_subtask_seconds"] == 1.5
    assert projected["delegate_wall_seconds_total"] == 4.512
    assert len(projected["items"]) == 12


def test_project_action_sequence_for_audit_omits_delegate_metadata_when_absent() -> None:
    projected = project_action_sequence_for_audit(
        {
            "batch_id": "req:iter:1:batch",
            "source_turn_index": 1,
            "items": [_delegate_item("read_a")],
        }
    )
    assert projected is not None
    assert "delegate_parallel" not in projected
    assert "delegate_count" not in projected
    assert "delegate_wall_seconds_total" not in projected
