"""Tests for ``run_orchestration_kernel_loop`` mechanical behavior."""

from __future__ import annotations

from typing import Any

import pytest

from agent_kernel.models import (
    KernelClaimabilityStatus,
    KernelDashboard,
    KernelFailureClassification,
    KernelGapSummary,
    KernelLatestRefs,
    KernelNoProgressRisk,
    KernelStepRequest,
    KernelStepResult,
    StepExecutionState,
)

from harness.mission_state import new_mission_state, new_resolution_state
from harness.runtime.run.contracts import (
    ActionPlan,
    OrchestrationPack,
    OrchestratorContext,
    SharedStateProjection,
    TerminalEvaluation,
)
from harness.runtime.run.orchestrator import run_orchestration_kernel_loop

from agent_kernel.session import KernelSessionManager


def _dashboard(*, refs: dict | None = None) -> KernelDashboard:
    artifact_refs: dict[str, dict[str, object]] = {}
    if refs:
        for k, v in refs.items():
            artifact_refs[k] = {"ref": v, "kind": "test"}
    return KernelDashboard(
        latest_refs=KernelLatestRefs(artifact_refs=artifact_refs),
        gap_summary=KernelGapSummary(),
        claimability=KernelClaimabilityStatus(claimable_ready=True, missing_claimability=[]),
        semantic_ready=True,
        budgets_remaining={
            "steps_remaining": 9,
            "wall_time_seconds_remaining": 3600,
            "retrieval_calls_remaining": 10,
            "semantic_calls_remaining": 10,
            "patch_calls_remaining": 10,
        },
        failure_classification=KernelFailureClassification(),
        no_progress_risk=KernelNoProgressRisk(risk_score=0.0, basis="test"),
        last_refusal=None,
    )


class FakeSessionManager(KernelSessionManager):
    """Session manager that records steps and returns EXECUTED with optional refs."""

    def __init__(self) -> None:
        super().__init__()
        self.steps: list[KernelStepRequest] = []

    def step(self, request: KernelStepRequest) -> KernelStepResult:  # type: ignore[override]
        self.steps.append(request)
        return KernelStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=StepExecutionState.EXECUTED,
            dashboard=_dashboard(refs={"step_ref": f"artifact://{request.action_type}"}),
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
    # Runtime check: pack satisfies structural protocol used by the loop driver.
    p: OrchestrationPack = OneStepThenCompletePack()
    assert hasattr(p, "initialize")
