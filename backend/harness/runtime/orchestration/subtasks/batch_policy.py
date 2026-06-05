"""Mechanical batching policy for harness-native ``delegate_subtask``."""

from __future__ import annotations

from typing import Any

from ..tool_batch_policy import ToolBatchPolicy
from .contracts import DELEGATE_SUBTASK_ACTION_TYPE

DELEGATE_SUBTASK_MAX_CALLS_PER_BATCH = 4
DELEGATE_SUBTASK_SIDE_EFFECT_CLASS = "model_observation"


def delegate_subtask_tool_batch_spec(*, max_calls_per_batch: int | None = None) -> dict[str, Any]:
    """Return the ``tool_specs[].batching`` object for ``delegate_subtask``."""

    max_calls = DELEGATE_SUBTASK_MAX_CALLS_PER_BATCH
    if max_calls_per_batch is not None:
        max_calls = max(1, int(max_calls_per_batch))
    return {
        "allowed": True,
        "max_calls_per_batch": max_calls,
        "side_effect_class": DELEGATE_SUBTASK_SIDE_EFFECT_CLASS,
        "can_run_parallel": True,
    }


def delegate_subtask_tool_batch_policy() -> ToolBatchPolicy:
    """Resolved batch policy for parser/executor tests and tooling."""

    return ToolBatchPolicy(
        tool_id=DELEGATE_SUBTASK_ACTION_TYPE,
        allowed=True,
        max_calls_per_batch=DELEGATE_SUBTASK_MAX_CALLS_PER_BATCH,
        side_effect_class=DELEGATE_SUBTASK_SIDE_EFFECT_CLASS,
        can_run_parallel=True,
    )
