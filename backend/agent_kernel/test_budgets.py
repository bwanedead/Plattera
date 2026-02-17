"""Tests for deterministic budget tracking helpers."""

from pathlib import Path
import sys

# Ensure repo root is importable when pytest is invoked from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.budgets import BudgetTracker
from backend.agent_kernel.models import KernelBudgets, StopReason


def _build_budgets(max_wall_time_seconds: int = 10) -> KernelBudgets:
    return KernelBudgets(
        max_steps=2,
        max_wall_time_seconds=max_wall_time_seconds,
        max_retrieval_calls=2,
        max_semantic_calls=1,
        max_patch_calls=1,
    )


def test_budget_tracker_snapshots_usage_across_budget_types() -> None:
    tracker = BudgetTracker(_build_budgets(), start_monotonic_seconds=100.0)

    tracker.record_step()
    tracker.record_retrieval_call()
    tracker.record_retrieval_call(semantic=True)
    tracker.record_patch_call()

    snapshot = tracker.snapshot(now_monotonic_seconds=104.0)

    assert snapshot.steps_used == 1
    assert snapshot.wall_time_seconds == 4
    assert snapshot.retrieval_calls_used == 2
    assert snapshot.semantic_calls_used == 1
    assert snapshot.patch_calls_used == 1


def test_over_budget_steps_returns_budget_exceeded_stop_reason() -> None:
    tracker = BudgetTracker(_build_budgets(), start_monotonic_seconds=0.0)
    tracker.record_step(count=2)

    status = tracker.record_step()

    assert status.exceeded is True
    assert status.stop_reason == StopReason.BUDGET_EXCEEDED
    assert status.reason_code == "budget_steps_exceeded"


def test_over_budget_wall_time_returns_budget_exceeded_stop_reason() -> None:
    tracker = BudgetTracker(_build_budgets(), start_monotonic_seconds=100.0)

    status = tracker.check(now_monotonic_seconds=111.1)

    assert status.exceeded is True
    assert status.stop_reason == StopReason.BUDGET_EXCEEDED
    assert status.reason_code == "budget_wall_time_exceeded"


def test_over_budget_retrieval_returns_budget_exceeded_stop_reason() -> None:
    tracker = BudgetTracker(
        _build_budgets(max_wall_time_seconds=1_000_000),
        start_monotonic_seconds=0.0,
    )

    tracker.record_retrieval_call(count=2)
    status = tracker.record_retrieval_call()

    assert status.exceeded is True
    assert status.stop_reason == StopReason.BUDGET_EXCEEDED
    assert status.reason_code == "budget_retrieval_calls_exceeded"


def test_over_budget_semantic_returns_budget_exceeded_stop_reason() -> None:
    tracker = BudgetTracker(
        _build_budgets(max_wall_time_seconds=1_000_000),
        start_monotonic_seconds=0.0,
    )

    tracker.record_retrieval_call(semantic=True)
    status = tracker.record_semantic_call()

    assert status.exceeded is True
    assert status.stop_reason == StopReason.BUDGET_EXCEEDED
    assert status.reason_code == "budget_semantic_calls_exceeded"


def test_over_budget_patch_returns_budget_exceeded_stop_reason() -> None:
    tracker = BudgetTracker(
        _build_budgets(max_wall_time_seconds=1_000_000),
        start_monotonic_seconds=0.0,
    )

    tracker.record_patch_call()
    status = tracker.record_patch_call()

    assert status.exceeded is True
    assert status.stop_reason == StopReason.BUDGET_EXCEEDED
    assert status.reason_code == "budget_patch_calls_exceeded"
