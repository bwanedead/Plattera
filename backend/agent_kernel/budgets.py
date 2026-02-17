"""Deterministic budget tracking helpers for Agent Kernel v0."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Optional

from .models import KernelBudgets, StopReason


@dataclass(frozen=True)
class BudgetStatus:
    """Current budget check result."""

    exceeded: bool
    stop_reason: Optional[StopReason] = None
    reason_code: Optional[str] = None


@dataclass(frozen=True)
class BudgetSnapshot:
    """Snapshot of current usage counts and elapsed wall time."""

    steps_used: int
    wall_time_seconds: int
    retrieval_calls_used: int
    semantic_calls_used: int
    patch_calls_used: int


class BudgetTracker:
    """Tracks kernel budget usage and returns deterministic over-budget reasons."""

    def __init__(
        self,
        budgets: KernelBudgets,
        start_monotonic_seconds: Optional[float] = None,
    ) -> None:
        self._budgets = budgets
        self._start = monotonic() if start_monotonic_seconds is None else start_monotonic_seconds
        self._steps_used = 0
        self._retrieval_calls_used = 0
        self._semantic_calls_used = 0
        self._patch_calls_used = 0

    def record_step(self, count: int = 1) -> BudgetStatus:
        self._steps_used += _validate_count(count)
        return self.check()

    def record_retrieval_call(self, *, semantic: bool = False, count: int = 1) -> BudgetStatus:
        amount = _validate_count(count)
        self._retrieval_calls_used += amount
        if semantic:
            self._semantic_calls_used += amount
        return self.check()

    def record_semantic_call(self, count: int = 1) -> BudgetStatus:
        self._semantic_calls_used += _validate_count(count)
        return self.check()

    def record_patch_call(self, count: int = 1) -> BudgetStatus:
        self._patch_calls_used += _validate_count(count)
        return self.check()

    def snapshot(self, now_monotonic_seconds: Optional[float] = None) -> BudgetSnapshot:
        return BudgetSnapshot(
            steps_used=self._steps_used,
            wall_time_seconds=self._elapsed_wall_time_seconds(now_monotonic_seconds),
            retrieval_calls_used=self._retrieval_calls_used,
            semantic_calls_used=self._semantic_calls_used,
            patch_calls_used=self._patch_calls_used,
        )

    def check(self, now_monotonic_seconds: Optional[float] = None) -> BudgetStatus:
        if self._steps_used > self._budgets.max_steps:
            return BudgetStatus(True, StopReason.BUDGET_EXCEEDED, "budget_steps_exceeded")
        if self._elapsed_wall_time_seconds(now_monotonic_seconds) > self._budgets.max_wall_time_seconds:
            return BudgetStatus(True, StopReason.BUDGET_EXCEEDED, "budget_wall_time_exceeded")
        if self._retrieval_calls_used > self._budgets.max_retrieval_calls:
            return BudgetStatus(True, StopReason.BUDGET_EXCEEDED, "budget_retrieval_calls_exceeded")
        if self._semantic_calls_used > self._budgets.max_semantic_calls:
            return BudgetStatus(True, StopReason.BUDGET_EXCEEDED, "budget_semantic_calls_exceeded")
        if self._patch_calls_used > self._budgets.max_patch_calls:
            return BudgetStatus(True, StopReason.BUDGET_EXCEEDED, "budget_patch_calls_exceeded")
        return BudgetStatus(False, None, None)

    def _elapsed_wall_time_seconds(self, now_monotonic_seconds: Optional[float] = None) -> int:
        now = monotonic() if now_monotonic_seconds is None else now_monotonic_seconds
        elapsed = max(0.0, now - self._start)
        return int(elapsed)


def _validate_count(count: int) -> int:
    if count < 0:
        raise ValueError("count must be >= 0")
    return count
