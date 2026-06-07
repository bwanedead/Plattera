"""Parallel mechanical dispatch for homogeneous delegate_subtask action batches."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import time
from time import perf_counter
from ...execution.contracts import (
    ActionDispatchResult,
    ExecutionRefusal,
    ExecutionStepRequest,
    ExecutionStepResult,
)
from ...execution.session import ExecutionSessionManager
from .action_sequence import ActionPlanAction
from .delegate_wave_trace import DelegateWaveTiming
from .subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE
from .tool_batch_policy import ToolBatchPolicy

_LOG = logging.getLogger(__name__)
_MAX_PARALLEL_DELEGATES = 16


@dataclass(frozen=True)
class DelegateParallelOutcome:
    normalized_request: ExecutionStepRequest | None = None
    deduped_result: ExecutionStepResult | None = None
    dispatch_result: ActionDispatchResult | None = None


def can_run_delegate_batch_parallel(
    actions: tuple[ActionPlanAction, ...],
    tool_batch_policies: Mapping[str, ToolBatchPolicy],
    *,
    multi_action: bool,
) -> bool:
    if not multi_action or len(actions) < 2:
        return False
    if any(item.action_type != DELEGATE_SUBTASK_ACTION_TYPE for item in actions):
        return False
    policy = tool_batch_policies.get(DELEGATE_SUBTASK_ACTION_TYPE)
    return bool(policy and policy.allowed and policy.can_run_parallel)


def execute_delegate_batch_parallel(
    *,
    session_manager: ExecutionSessionManager,
    session_id: str,
    prepared: list[tuple[ActionPlanAction, ExecutionStepRequest]],
) -> tuple[list[DelegateParallelOutcome], DelegateWaveTiming]:
    """Run delegate handlers concurrently after idempotency preflight; record stays serial upstream."""

    del session_id  # session identity is carried on each request
    if not prepared:
        now = round(time.time(), 3)
        return [], DelegateWaveTiming(
            wall_elapsed_seconds=0.0,
            started_at_epoch_seconds=now,
            finished_at_epoch_seconds=now,
        )

    outcomes: list[DelegateParallelOutcome | None] = [None] * len(prepared)
    pending: list[tuple[int, ExecutionStepRequest]] = []

    for index, (_, request) in enumerate(prepared):
        normalized_request, deduped = session_manager.preflight_step(request)
        if deduped is not None:
            outcomes[index] = DelegateParallelOutcome(deduped_result=deduped)
            continue
        assert normalized_request is not None
        pending.append((index, normalized_request))

    def _dispatch(request: ExecutionStepRequest) -> ActionDispatchResult:
        try:
            return session_manager.executor.execute(request)
        except Exception:  # noqa: BLE001
            _LOG.warning("delegate_parallel_dispatch_failed", exc_info=True)
            return ActionDispatchResult(
                action_id=DELEGATE_SUBTASK_ACTION_TYPE,
                executed=False,
                reason_codes=("sequence_dispatch_exception",),
                refusal=ExecutionRefusal(
                    reason_code="sequence_dispatch_exception",
                    retryable=True,
                ),
                idempotency_key=request.idempotency_key,
            )

    wave_started_at_epoch = time.time()
    wall_start = perf_counter()
    if pending:
        max_workers = min(len(pending), _MAX_PARALLEL_DELEGATES)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            dispatch_results = list(pool.map(_dispatch, [req for _, req in pending]))
        for (index, normalized_request), dispatch_result in zip(
            pending,
            dispatch_results,
            strict=True,
        ):
            outcomes[index] = DelegateParallelOutcome(
                normalized_request=normalized_request,
                dispatch_result=dispatch_result,
            )
    wall_elapsed = round(max(0.0, perf_counter() - wall_start), 3)
    if any(row is None for row in outcomes):
        raise RuntimeError("delegate_parallel_outcome_incomplete")
    return outcomes, DelegateWaveTiming(
        wall_elapsed_seconds=wall_elapsed,
        started_at_epoch_seconds=round(wave_started_at_epoch, 3),
        finished_at_epoch_seconds=round(time.time(), 3),
    )


def record_delegate_dispatch(
    *,
    session_manager: ExecutionSessionManager,
    session_id: str,
    request: ExecutionStepRequest,
    dispatch_result: ActionDispatchResult,
) -> ExecutionStepResult | None:
    """Record one delegate dispatch into the session without re-executing the handler."""

    del session_id
    if dispatch_result is None:
        return None
    return session_manager.record_dispatch_result(request, dispatch_result)
