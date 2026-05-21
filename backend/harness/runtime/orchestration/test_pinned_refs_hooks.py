"""Tests for pinned-ref auto-hydration hooks."""

from __future__ import annotations

from unittest.mock import MagicMock

from harness.execution.contracts import (
    ActionDispatchResult,
    ExecutionDashboard,
    ExecutionLatestRefs,
    ExecutionState,
    ExecutionStepRequest,
    ExecutionStepResult,
    SessionExecutionRecord,
)
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.pinned_refs_hooks import (
    _refs_already_scheduled_for_hydration,
    surface_active_pinned_refs_before_choose_action,
)


def _executed_hydrate_result(*, ref_id: str = "pin-b") -> ExecutionStepResult:
    request = ExecutionStepRequest(session_id="s1", action_id="hydrate_artifact_refs")
    result = ActionDispatchResult(
        action_id="hydrate_artifact_refs",
        executed=True,
        outputs={"results": [{"ref_id": ref_id}]},
        artifact_refs=(),
    )
    record = SessionExecutionRecord(session_id="s1", run_id="r", request=request, result=result)
    return ExecutionStepResult(
        session_id="s1",
        idempotency_key="",
        execution_state=ExecutionState.EXECUTED,
        dashboard=ExecutionDashboard(
            latest_refs=ExecutionLatestRefs(refs={}),
            budgets_remaining={},
            last_refusal=None,
        ),
        record=record,
    )


def test_pinned_hydration_skips_refs_already_in_pending_agent_hydration() -> None:
    mem = LoopMemoryState()
    mem.continuity.pinned_refs = [
        {
            "ref": "pin-a",
            "pinned_at_turn": 1,
            "last_refreshed_turn": 1,
            "ttl_turns": 8,
        }
    ]
    mem.continuity.pending_agent_hydration = {
        "status": "pending",
        "resolved_refs": ["pin-a"],
        "requested_refs": ["pin-a"],
    }
    scheduled = _refs_already_scheduled_for_hydration(mem)
    assert "pin-a" in scheduled

    manager = MagicMock()
    surface_active_pinned_refs_before_choose_action(
        loop_memory=mem,
        session_manager=manager,
        session_id="s1",
        request_id_prefix="pfx",
        run_id="run",
        iteration=2,
    )
    manager.step.assert_not_called()
    assert mem.continuity.pinned_refs_hydration is None


def test_pinned_hydration_dispatches_unscheduled_active_refs() -> None:
    mem = LoopMemoryState()
    mem.continuity.pinned_refs = [
        {
            "ref": "pin-b",
            "pinned_at_turn": 1,
            "last_refreshed_turn": 1,
            "ttl_turns": 8,
        }
    ]
    manager = MagicMock()
    manager.step.return_value = _executed_hydrate_result()
    surface_active_pinned_refs_before_choose_action(
        loop_memory=mem,
        session_manager=manager,
        session_id="s1",
        request_id_prefix="pfx",
        run_id="run",
        iteration=2,
    )
    manager.step.assert_called_once()
    record = mem.continuity.pinned_refs_hydration
    assert record is not None
    assert record.get("refs") == ["pin-b"]
    assert record.get("hydrated_results")
