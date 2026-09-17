"""Durable, provider-agnostic budget for logical harness LLM calls.

One logical call is reserved before the shared model caller reaches a provider.
Provider transport retries remain inside that one reservation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from .instrumented_caller import TextModelCaller

REASON_LOGICAL_LLM_CALL_BUDGET_EXHAUSTED = "logical_llm_call_budget_exhausted"


class LogicalLlmCallBudgetError(RuntimeError):
    """Raised before an invocation when the configured logical-call cap is spent."""

    reason_code = REASON_LOGICAL_LLM_CALL_BUDGET_EXHAUSTED


@dataclass
class LogicalLlmCallBudget:
    """Run-local mechanical counter; ``max_calls=None`` preserves legacy behavior."""

    max_calls: int | None = None
    calls_used: int = 0
    _reservation_lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.max_calls is not None and (type(self.max_calls) is not int or self.max_calls < 0):
            raise ValueError("logical_llm_call_budget_invalid")
        if type(self.calls_used) is not int or self.calls_used < 0:
            raise ValueError("logical_llm_call_budget_invalid")
        if self.max_calls is not None and self.calls_used > self.max_calls:
            raise ValueError("logical_llm_call_budget_invalid")

    def reserve(self) -> int:
        """Consume one logical call before provider work begins, or fail closed."""
        with self._reservation_lock:
            if self.max_calls is not None and self.calls_used >= self.max_calls:
                raise LogicalLlmCallBudgetError(REASON_LOGICAL_LLM_CALL_BUDGET_EXHAUSTED)
            self.calls_used += 1
            return self.calls_used

    def to_wire(self) -> dict[str, int | None]:
        return {"max_calls": self.max_calls, "calls_used": self.calls_used}


def parse_launch_max_llm_calls(value: Any) -> tuple[int | None, str | None]:
    """Accept an optional exact nonnegative integer launch value; never coerce."""
    if value is None:
        return None, None
    if type(value) is int and value >= 0:
        return value, None
    return None, "logical_llm_call_budget_invalid"


def parse_env_max_llm_calls(value: str | None) -> tuple[int | None, str | None]:
    """Parse the CLI environment transport form without accepting aliases/coercions."""
    if value is None or value == "":
        return None, None
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        return None, "logical_llm_call_budget_invalid"
    return int(value), None


def budget_from_wire(value: Any) -> tuple[LogicalLlmCallBudget | None, str | None]:
    """Strictly restore a persisted budget. Missing remains backward-compatible."""
    if value is None:
        return LogicalLlmCallBudget(), None
    if not isinstance(value, Mapping):
        return None, "resume_snapshot_logical_llm_call_budget_invalid"
    if set(value) != {"max_calls", "calls_used"}:
        return None, "resume_snapshot_logical_llm_call_budget_invalid"
    max_calls = value.get("max_calls")
    calls_used = value.get("calls_used")
    if max_calls is not None and (type(max_calls) is not int or max_calls < 0):
        return None, "resume_snapshot_logical_llm_call_budget_invalid"
    if type(calls_used) is not int or calls_used < 0:
        return None, "resume_snapshot_logical_llm_call_budget_invalid"
    try:
        return LogicalLlmCallBudget(max_calls=max_calls, calls_used=calls_used), None
    except ValueError:
        return None, "resume_snapshot_logical_llm_call_budget_invalid"


def configure_logical_llm_call_budget(
    *,
    restored: LogicalLlmCallBudget,
    configured_max_calls: int | None,
    reset_for_fork: bool = False,
) -> tuple[LogicalLlmCallBudget | None, str | None]:
    """Reconcile launch config with persisted run-local state.

    A same-run resume inherits the saved effective cap and count; it refuses any
    attempt to raise or replace that cap. A fork is a new logical run, so it
    takes the currently configured effective ceiling and starts its own count.
    """
    if reset_for_fork:
        return LogicalLlmCallBudget(
            max_calls=(configured_max_calls if configured_max_calls is not None else restored.max_calls)
        ), None
    if configured_max_calls is None:
        return restored, None
    if restored.max_calls is None:
        return LogicalLlmCallBudget(max_calls=configured_max_calls), None
    if restored.max_calls != configured_max_calls:
        return None, "logical_llm_call_budget_resume_config_mismatch"
    return restored, None


def budget_model_caller(caller: TextModelCaller, *, budget: LogicalLlmCallBudget) -> TextModelCaller:
    """Wrap the sole runtime caller so every parent/delegate/repair call is counted."""

    def _budgeted(prompt: str, model: str, **kwargs: Any) -> Mapping[str, Any] | str:
        call_number = budget.reserve()
        try:
            result = caller(prompt, model, **kwargs)
        except Exception as exc:
            _attach_budget_trace(getattr(exc, "llm_call_trace", None), budget=budget, call_number=call_number)
            raise
        if not isinstance(result, Mapping):
            return result
        merged = dict(result)
        trace = merged.get("llm_call_trace")
        if isinstance(trace, Mapping):
            annotated = dict(trace)
            _attach_budget_trace(annotated, budget=budget, call_number=call_number)
            merged["llm_call_trace"] = annotated
        return merged

    return _budgeted


def _attach_budget_trace(trace: Any, *, budget: LogicalLlmCallBudget, call_number: int) -> None:
    if not isinstance(trace, dict):
        return
    trace["logical_llm_call_number"] = call_number
    trace["logical_llm_call_max"] = budget.max_calls
