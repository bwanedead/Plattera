"""Round-trip and resume behavior for ``session_wire`` (mechanical only)."""

from __future__ import annotations

from harness.execution.contracts import (
    ActionDispatchResult,
    ExecutionSessionStartRequest,
    ExecutionState,
    ExecutionStepRequest,
)
from harness.execution.executor import ExecutionExecutor
from harness.execution.session import ExecutionSessionManager
from harness.execution.session_wire import execution_session_from_wire, execution_session_to_wire


def test_hydrated_session_preserves_idempotency_dedupe() -> None:
    executor = ExecutionExecutor()

    def _noop(request: ExecutionStepRequest) -> ActionDispatchResult:
        return ActionDispatchResult(
            action_id=request.action_id,
            executed=True,
            outputs={},
            idempotency_key=request.idempotency_key,
        )

    executor.register("noop", _noop)
    mgr = ExecutionSessionManager(executor=executor)
    start = mgr.start_session(ExecutionSessionStartRequest(run_id="r1", session_id="s-dedupe"))
    sid = start.session_id
    r1 = mgr.step(
        ExecutionStepRequest(session_id=sid, action_id="noop", inputs={}, idempotency_key="ik-one"),
    )
    assert r1.execution_state == ExecutionState.EXECUTED
    r2 = mgr.step(
        ExecutionStepRequest(session_id=sid, action_id="noop", inputs={}, idempotency_key="ik-one"),
    )
    assert r2.execution_state == ExecutionState.DEDUPED

    wire = execution_session_to_wire(mgr.sessions[sid])
    session, err = execution_session_from_wire(wire)
    assert err is None
    assert session is not None

    mgr2 = ExecutionSessionManager(executor=executor)
    mgr2.hydrate_session(session)
    r3 = mgr2.step(
        ExecutionStepRequest(session_id=sid, action_id="noop", inputs={}, idempotency_key="ik-one"),
    )
    assert r3.execution_state == ExecutionState.DEDUPED
