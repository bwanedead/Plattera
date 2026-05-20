"""Execution hook tests for action_batch."""

from __future__ import annotations

from harness.execution.contracts import (
    ActionDispatchResult,
    ExecutionDashboard,
    ExecutionLatestRefs,
    ExecutionRefusal,
    ExecutionState,
    ExecutionStepRequest,
    ExecutionStepResult,
    SessionExecutionRecord,
)
from harness.execution.session import ExecutionSessionManager
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.action_batch_hooks import execute_action_batch
from harness.runtime.orchestration.contracts import ActionPlan
from harness.runtime.orchestration.action_batch import ActionBatchItem
from harness.runtime.orchestration.tool_batch_policy import ToolBatchPolicy


class _BatchFakeSessionManager(ExecutionSessionManager):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[ExecutionStepRequest] = []

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        self.requests.append(request)
        if request.action_id == "fail_once":
            result = ActionDispatchResult(
                action_id=request.action_id,
                executed=False,
                refusal=ExecutionRefusal(reason_code="retryable_fail", retryable=True),
            )
        elif request.action_id == "transform_artifact":
            alias = request.idempotency_key.rsplit(":", 1)[-1]
            derived = f"image:derived:{alias}"
            result = ActionDispatchResult(
                action_id=request.action_id,
                executed=True,
                outputs={"derived_ref_id": derived},
                artifact_refs=(derived,),
            )
        else:
            result = ActionDispatchResult(
                action_id=request.action_id,
                executed=True,
                outputs={"results": []},
                artifact_refs=(),
            )
        record = SessionExecutionRecord(
            session_id=request.session_id,
            run_id="r",
            request=request,
            result=result,
        )
        return ExecutionStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=ExecutionState.EXECUTED if result.executed else ExecutionState.REFUSED,
            dashboard=ExecutionDashboard(
                latest_refs=ExecutionLatestRefs(refs={}),
                budgets_remaining={},
                last_refusal=result.refusal,
            ),
            refusal=result.refusal,
            record=record,
        )


def _policies() -> dict[str, ToolBatchPolicy]:
    return {
        "hydrate_artifact_refs": ToolBatchPolicy(
            tool_id="hydrate_artifact_refs",
            allowed=True,
            max_calls_per_batch=3,
            side_effect_class="read_only",
        ),
        "transform_artifact": ToolBatchPolicy(
            tool_id="transform_artifact",
            allowed=True,
            max_calls_per_batch=4,
            side_effect_class="derived_artifact",
        ),
        "fail_once": ToolBatchPolicy(
            tool_id="fail_once",
            allowed=True,
            max_calls_per_batch=2,
            side_effect_class="read_only",
        ),
    }


def test_executes_two_read_only_items() -> None:
    sm = _BatchFakeSessionManager()
    lm = LoopMemoryState()
    plan = ActionPlan(
        action_batch=(
            ActionBatchItem("h1", "hydrate_artifact_refs", {"ref_ids": ["a"]}),
            ActionBatchItem("h2", "hydrate_artifact_refs", {"ref_ids": ["b"]}),
        ),
        rationale="batch hydrate",
    )
    outcome = execute_action_batch(
        loop_memory=lm,
        session_manager=sm,
        session_id="s",
        action_plan=plan,
        iteration=2,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_policies(),
    )
    assert len(sm.requests) == 2
    assert all(r.action_id == "hydrate_artifact_refs" for r in sm.requests)
    assert len(outcome.batch_result["items"]) == 2


def test_transform_batch_collects_refs_and_idempotency_keys() -> None:
    sm = _BatchFakeSessionManager()
    lm = LoopMemoryState()
    plan = ActionPlan(
        action_batch=(
            ActionBatchItem("p1", "transform_artifact", {}),
            ActionBatchItem("p2", "transform_artifact", {}),
        ),
        rationale="batch crops",
    )
    outcome = execute_action_batch(
        loop_memory=lm,
        session_manager=sm,
        session_id="s",
        action_plan=plan,
        iteration=3,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_policies(),
    )
    assert sm.requests[0].idempotency_key == "req:iter:3:batch:p1"
    assert sm.requests[1].idempotency_key == "req:iter:3:batch:p2"
    items = outcome.batch_result["items"]
    assert items[0]["artifact_refs"] == ["image:derived:p1"]
    assert items[1]["artifact_refs"] == ["image:derived:p2"]


def test_partial_failure_per_alias() -> None:
    sm = _BatchFakeSessionManager()
    lm = LoopMemoryState()
    plan = ActionPlan(
        action_batch=(
            ActionBatchItem("ok", "hydrate_artifact_refs", {}),
            ActionBatchItem("bad", "fail_once", {}),
        ),
        rationale="partial",
    )
    outcome = execute_action_batch(
        loop_memory=lm,
        session_manager=sm,
        session_id="s",
        action_plan=plan,
        iteration=1,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_policies(),
    )
    by_alias = {row["alias"]: row for row in outcome.batch_result["items"]}
    assert by_alias["ok"]["execution_state"] == "executed"
    assert by_alias["bad"]["execution_state"] == "retryable_error"
