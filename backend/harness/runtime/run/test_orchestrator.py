"""Tests for ``run_orchestration_kernel_loop`` mechanical behavior."""

from __future__ import annotations

from harness.execution.contracts import (
    ExecutionDashboard,
    ExecutionLatestRefs,
    ExecutionState,
    ExecutionStepRequest,
    ExecutionStepResult,
)
from harness.execution.session import ExecutionSessionManager
from harness.mission_state import new_mission_state, new_resolution_state
from harness.runtime.run.contracts import (
    ActionPlan,
    OrchestrationPack,
    OrchestratorContext,
    SharedStateProjection,
    TerminalEvaluation,
)
from harness.runtime.run.orchestrator import run_orchestration_kernel_loop


def _dashboard(*, refs: dict | None = None) -> ExecutionDashboard:
    return ExecutionDashboard(
        latest_refs=ExecutionLatestRefs(refs=dict(refs or {})),
        budgets_remaining={},
        last_refusal=None,
    )


class FakeSessionManager(ExecutionSessionManager):
    """Session manager that records steps and returns EXECUTED with optional refs."""

    def __init__(self) -> None:
        super().__init__()
        self.steps: list[ExecutionStepRequest] = []

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        self.steps.append(request)
        return ExecutionStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=ExecutionState.EXECUTED,
            dashboard=_dashboard(refs={"step_ref": f"artifact://{request.action_id}"}),
        )


class OneStepThenCompletePack:
    """Executes one kernel step then completes on next iteration."""

    implements = True

    def initialize(self, context: OrchestratorContext) -> None:
        self._initialized = True

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        ms = new_mission_state(
            mission_id="m-orch",
            loop_family="orchestration_kernel",
            objective="t",
        )
        rs = new_resolution_state()
        refs = dict(context.loop_memory.continuity.latest_refs)
        return SharedStateProjection(
            mission_state=ms,
            resolution_state=rs,
            latest_refs=refs,
            active_item_id="item-1" if refs else None,
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        if context.loop_memory.iterations >= 2:
            return TerminalEvaluation(terminal_class="completed", reason_code="test_done")
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        return ActionPlan(
            action_type="noop",
            action_inputs={},
            idempotency_key=f"ik-{context.loop_memory.iterations}",
        )


class ImmediateTerminalPack:
    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="m2", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        return TerminalEvaluation(terminal_class="blocked", reason_code="immediate")

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        raise AssertionError("choose_action should not run when terminal fires first")


class WaitHumanPack:
    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="m3", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        return ActionPlan(wait_for_human=True)


class SkipExecutionPack:
    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="m4", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        if context.loop_memory.iterations >= 2:
            return TerminalEvaluation(terminal_class="completed", reason_code="after_skip")
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        return ActionPlan(skip_execution=True, idempotency_key="skip")


def test_orchestrator_one_step_then_complete_trace() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_pack=OneStepThenCompletePack(),
        session_manager=sm,
        session_id="s1",
        run_artifact_ref=None,
        request_id_prefix="req-orch",
        opaque_run_context={"product": "ctx"},
        max_iterations=5,
    )
    assert result.terminal_class == "completed"
    assert result.reason_code == "test_done"
    assert len(sm.steps) == 1
    kinds = [e.get("event_kind") for e in result.trace_events]
    assert "request_start" in kinds
    assert "tool_execution" in kinds or any(k == "iteration" for k in kinds)
    start_payload = next(e["payload"] for e in result.trace_events if e.get("event_kind") == "request_start")
    assert start_payload.get("opaque_run_context") == {"product": "ctx"}


def test_terminal_before_action_no_step() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_pack=ImmediateTerminalPack(),
        session_manager=sm,
        session_id="s1",
        run_artifact_ref=None,
        request_id_prefix="r2",
        max_iterations=3,
    )
    assert result.terminal_class == "blocked"
    assert len(sm.steps) == 0


def test_wait_for_human_no_step() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_pack=WaitHumanPack(),
        session_manager=sm,
        session_id="s1",
        run_artifact_ref=None,
        request_id_prefix="r3",
        max_iterations=3,
    )
    assert result.terminal_class == "waiting_human"
    assert len(sm.steps) == 0


def test_skip_execution_no_session_step() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_pack=SkipExecutionPack(),
        session_manager=sm,
        session_id="s1",
        run_artifact_ref=None,
        request_id_prefix="r4",
        max_iterations=5,
    )
    assert result.terminal_class == "completed"
    assert len(sm.steps) == 0


def test_orchestration_pack_protocol_typing() -> None:
    p: OrchestrationPack = OneStepThenCompletePack()
    assert hasattr(p, "initialize")
