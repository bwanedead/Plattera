"""Execution hook tests for canonical ``actions`` sequences."""

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
from harness.runtime.orchestration.action_sequence import (
    ActionPlanAction,
    action_plan_with_canonical_actions,
)
from harness.runtime.orchestration.action_sequence_hooks import (
    _execute_sequence_items,
    capture_hydrate_after_sequence,
)
from harness.runtime.orchestration.hydrate_next import MAX_HYDRATE_NEXT_REFS
from harness.runtime.orchestration.tool_batch_policy import ToolBatchPolicy


class _SequenceFakeSessionManager(ExecutionSessionManager):
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
    sm = _SequenceFakeSessionManager()
    lm = LoopMemoryState()
    actions = (
        ActionPlanAction("h1", "hydrate_artifact_refs", {"ref_ids": ["a"]}),
        ActionPlanAction("h2", "hydrate_artifact_refs", {"ref_ids": ["b"]}),
    )
    sequence_result, _ = _execute_sequence_items(
        loop_memory=lm,
        session_manager=sm,
        session_id="s",
        actions=actions,
        iteration=2,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_policies(),
        multi_action=True,
    )
    assert len(sm.requests) == 2
    assert all(r.action_id == "hydrate_artifact_refs" for r in sm.requests)
    assert len(sequence_result["items"]) == 2


def test_transform_sequence_collects_refs_and_idempotency_keys() -> None:
    sm = _SequenceFakeSessionManager()
    lm = LoopMemoryState()
    actions = (
        ActionPlanAction("p1", "transform_artifact", {}),
        ActionPlanAction("p2", "transform_artifact", {}),
    )
    sequence_result, _ = _execute_sequence_items(
        loop_memory=lm,
        session_manager=sm,
        session_id="s",
        actions=actions,
        iteration=3,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_policies(),
        multi_action=True,
    )
    assert sm.requests[0].idempotency_key == "req:iter:3:batch:p1"
    assert sm.requests[1].idempotency_key == "req:iter:3:batch:p2"
    items = sequence_result["items"]
    assert items[0]["artifact_refs"] == ["image:derived:p1"]
    assert items[1]["artifact_refs"] == ["image:derived:p2"]


def test_partial_failure_per_alias() -> None:
    sm = _SequenceFakeSessionManager()
    lm = LoopMemoryState()
    actions = (
        ActionPlanAction("ok", "hydrate_artifact_refs", {}),
        ActionPlanAction("bad", "fail_once", {}),
    )
    sequence_result, _ = _execute_sequence_items(
        loop_memory=lm,
        session_manager=sm,
        session_id="s",
        actions=actions,
        iteration=1,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_policies(),
        multi_action=True,
    )
    by_alias = {row["alias"]: row for row in sequence_result["items"]}
    assert by_alias["ok"]["execution_state"] == "executed"
    assert by_alias["bad"]["execution_state"] == "retryable_error"


def test_capture_hydrate_after_sequence_caps_aggregate_resolved_refs() -> None:
    lm = LoopMemoryState()
    count = MAX_HYDRATE_NEXT_REFS + 3
    actions = tuple(
        ActionPlanAction(
            f"a{i}",
            "transform_artifact",
            {},
            hydrate_next=(f"image:derived:a{i}",),
        )
        for i in range(count)
    )
    plan = action_plan_with_canonical_actions(actions=actions, rationale="many hydrates")
    sequence_result = {
        "batch_id": "req:iter:1:actions",
        "source_turn_index": 1,
        "items": [
            {
                "alias": f"a{i}",
                "action_type": "transform_artifact",
                "execution_state": "executed",
                "outputs_excerpt": {"derived_ref_id": f"image:derived:a{i}"},
            }
            for i in range(count)
        ],
    }
    capture_hydrate_after_sequence(
        loop_memory=lm,
        action_plan=plan,
        sequence_result=sequence_result,
        iteration=1,
    )
    pending = lm.continuity.pending_agent_hydration
    assert pending is not None
    assert len(pending["resolved_refs"]) == MAX_HYDRATE_NEXT_REFS
    assert any(
        e.get("reason_code") == "aggregate_hydrate_next_cap_exceeded"
        for e in pending.get("errors") or []
    )
