"""Tests for ``run_orchestration_kernel_loop`` mechanical behavior."""

from __future__ import annotations

import json
import time
from typing import Any

from harness.execution.contracts import (
    ExecutionDashboard,
    ExecutionLatestRefs,
    ExecutionRefusal,
    ExecutionState,
    ExecutionStepRequest,
    ExecutionStepResult,
)
from harness.execution.session import ExecutionSessionManager
from harness.mission_state import new_mission_state, new_resolution_state
from harness.runtime.orchestration.contracts import (
    ActionPlan,
    OrchestrationAdapter,
    OrchestratorContext,
    SharedStateProjection,
    TerminalEvaluation,
)
from harness.runtime.composition.contracts import ComposedTurnInput, TurnBlock
from harness.runtime.memory import LoopMemoryState
from harness.runtime.memory.resume_snapshot import parse_kernel_resume_snapshot
from harness.runtime.orchestration.lifecycle import (
    KernelPromptEventTraceObserver,
    OrchestrationLifecycle,
)
from harness.runtime.orchestration.llm_turn_adapter import LlmTurnOrchestrationAdapter
from harness.runtime.orchestration.orchestrator import run_orchestration_kernel_loop
from harness.runtime.orchestration.trace_collector import KernelTraceCollector

_PACK_CJ = {"pack_continuity_stub": True}


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


class _TurnCompletionRecorder:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def observe_turn_completed(self, record: dict[str, Any]) -> None:
        self.records.append(dict(record))


class _ExplodingTurnCompletionObserver:
    def observe_turn_completed(self, record: dict[str, Any]) -> None:
        raise RuntimeError("boom")


class _RecordingPreChooseActionParticipant:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def before_choose_action(
        self,
        context: OrchestratorContext,
        projection: SharedStateProjection | None,
        *,
        tracer: KernelTraceCollector,
    ) -> None:
        del tracer
        self.calls.append(
            {
                "iteration": int(context.loop_memory.iterations),
                "has_projection": projection is not None,
            }
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
            continuity_journal_entry=_PACK_CJ,
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
        return ActionPlan(
            wait_for_human=True,
            hitl_request={"message": "Need operator input", "choices": [], "context": {}},
            continuity_journal_entry=_PACK_CJ,
        )


class MechanicalInheritSyncPack:
    """Mirrors LlmTurnOrchestrationAdapter: carry forward continuity + mechanical envelope."""

    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        prior_ms = context.loop_memory.continuity.mission_state
        prior_rs = context.loop_memory.continuity.resolution_state
        ts = time.time()
        mo = dict(prior_ms.opaque_payload)
        mo["turn_iteration"] = context.loop_memory.iterations
        ro = dict(prior_rs.opaque_payload)
        ro["turn_iteration"] = context.loop_memory.iterations
        rs = prior_rs.model_copy(update={"opaque_payload": ro, "updated_at_epoch_seconds": ts})
        ms = prior_ms.model_copy(
            update={
                "mission_id": context.session_id,
                "session_id": context.session_id,
                "request_id": context.request_id_prefix,
                "loop_family": "orchestration_kernel",
                "updated_at_epoch_seconds": ts,
                "opaque_payload": mo,
                "resolution_state": rs,
            }
        )
        ca = context.loop_memory.continuity.active_item_id
        return SharedStateProjection(
            mission_state=ms,
            resolution_state=rs,
            latest_refs=dict(context.loop_memory.continuity.latest_refs),
            active_item_id=ca if ca is not None else rs.active_item_id,
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        if context.loop_memory.iterations >= 3:
            return TerminalEvaluation(terminal_class="completed", reason_code="patch_persisted")
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        it = context.loop_memory.iterations
        if it == 1:
            return ActionPlan(
                action_type="noop",
                action_inputs={},
                idempotency_key="ik-patch-1",
                continuity_journal_entry=_PACK_CJ,
                state_patch={
                    "resolution": {
                        "active_item_id": "work-1",
                        "items": [
                            {
                                "item_id": "work-1",
                                "title": "Unit",
                                "kind": "work_unit",
                                "status": "open",
                            }
                        ],
                    }
                },
            )
        if it == 2:
            assert projection is not None
            assert len(projection.resolution_state.items) == 1
            assert projection.resolution_state.items[0].item_id == "work-1"
            return ActionPlan(
                action_type="noop",
                action_inputs={},
                idempotency_key="ik-patch-2",
                continuity_journal_entry=_PACK_CJ,
                state_patch={
                    "resolution": {
                        "items": [
                            {
                                "item_id": "work-1",
                                "status": "closed",
                                "determination": "earned",
                                "verification_basis": "The work item was completed against the strongest available evidence.",
                                "completion_criteria": "The unit is explicitly verified and no stronger in-run check remains.",
                            },
                        ],
                    }
                },
            )
        return ActionPlan(skip_execution=True, idempotency_key="ik-fallback", continuity_journal_entry=_PACK_CJ)


class BadTopLevelStatePatchPack:
    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return MechanicalInheritSyncPack().sync(context)

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        if context.loop_memory.iterations >= 2:
            return TerminalEvaluation(terminal_class="completed", reason_code="after_bad_patch")
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        return ActionPlan(
            action_type="noop",
            action_inputs={},
            idempotency_key="ik-bad",
            continuity_journal_entry=_PACK_CJ,
            state_patch={"domain_specific_surface": {"x": 1}},
        )


class RefuseOnceSessionManager(FakeSessionManager):
    """First ``step`` refuses; later calls behave like ``FakeSessionManager`` (no real session table)."""

    def __init__(self) -> None:
        super().__init__()
        self._calls = 0

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        self.steps.append(request)
        self._calls += 1
        if self._calls == 1:
            return ExecutionStepResult(
                session_id=request.session_id,
                idempotency_key=request.idempotency_key,
                execution_state=ExecutionState.REFUSED,
                dashboard=_dashboard(),
                refusal=ExecutionRefusal(reason_code="test_refusal", retryable=False),
            )
        return ExecutionStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=ExecutionState.EXECUTED,
            dashboard=_dashboard(refs={"step_ref": f"artifact://{request.action_id}"}),
        )


class PatchOnNoopRefusedPack:
    """Proposes a resolution patch with a noop step; used with a refusing session manager."""

    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="m-ref", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        return ActionPlan(
            action_type="noop",
            action_inputs={},
            idempotency_key="ik-ref-patch",
            continuity_journal_entry=_PACK_CJ,
            state_patch={
                "resolution": {
                    "items": [
                        {
                            "item_id": "x1",
                            "title": "T",
                            "kind": "work_unit",
                            "status": "open",
                        }
                    ],
                }
            },
        )


class _SparseNoDispatchActionPlanPack:
    """Sparse state patch without explicit skip_execution via ActionPlan."""

    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        ms = context.loop_memory.continuity.mission_state.model_copy(
            update={"mission_id": "m-sparse-ap", "loop_family": "orchestration_kernel"}
        )
        rs = context.loop_memory.continuity.resolution_state
        return SharedStateProjection(
            mission_state=ms,
            resolution_state=rs,
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        if context.loop_memory.iterations >= 2:
            return TerminalEvaluation(terminal_class="completed", reason_code="done")
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        if context.loop_memory.iterations == 1:
            return ActionPlan(
                state_patch={"mission": {"work_universe_posture": "audited"}},
                continuity_journal_entry={"step": "sparse no-dispatch action plan"},
            )
        return ActionPlan(complete_run=True, continuity_journal_entry={"step": "complete"})


class _SparseNoDispatchDictPack:
    """Sparse state patch without explicit skip_execution via dict coercion."""

    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        ms = context.loop_memory.continuity.mission_state.model_copy(
            update={"mission_id": "m-sparse-dict", "loop_family": "orchestration_kernel"}
        )
        rs = context.loop_memory.continuity.resolution_state
        return SharedStateProjection(
            mission_state=ms,
            resolution_state=rs,
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        if context.loop_memory.iterations >= 2:
            return TerminalEvaluation(terminal_class="completed", reason_code="done")
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> dict[str, Any]:
        if context.loop_memory.iterations == 1:
            return {
                "state_patch": {"mission": {"work_universe_posture": "audited"}},
                "continuity_journal_entry": {"step": "sparse no-dispatch dict"},
            }
        return {"complete_run": True, "continuity_journal_entry": {"step": "complete"}}


class _SparseHitlActionPlanPack:
    """Sparse HITL-only no-dispatch turn via ActionPlan."""

    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="m-hitl-ap", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        if context.loop_memory.iterations >= 2:
            return TerminalEvaluation(terminal_class="completed", reason_code="done")
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        return ActionPlan(
            hitl_request={"message": "Need async guidance", "choices": [], "context": {}},
            continuity_journal_entry={"step": "sparse hitl action plan"},
        )


class _SparseHitlDictPack:
    """Sparse HITL-only no-dispatch turn via dict coercion."""

    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="m-hitl-dict", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        if context.loop_memory.iterations >= 2:
            return TerminalEvaluation(terminal_class="completed", reason_code="done")
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> dict[str, Any]:
        return {
            "hitl_request": {"message": "Need async guidance", "choices": [], "context": {}},
            "continuity_journal_entry": {"step": "sparse hitl dict"},
        }


class CompleteRunWithSkippedItemRowsPack:
    """``complete_run`` with a patch containing one invalid and one valid item row."""

    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="m-skip", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        return ActionPlan(
            complete_run=True,
            rationale="done",
            idempotency_key="ik-skip-rows",
            continuity_journal_entry=_PACK_CJ,
            state_patch={
                "mission": {"work_universe_posture": "audited"},
                "resolution": {
                    "items": [
                        {"item_id": "", "title": "x", "kind": "k", "status": "s"},
                        {
                            "item_id": "ok",
                            "title": "Valid",
                            "kind": "work_unit",
                            "status": "open",
                        },
                    ],
                }
            },
        )


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
        return ActionPlan(skip_execution=True, idempotency_key="skip", continuity_journal_entry=_PACK_CJ)


def test_orchestrator_one_step_then_complete_trace() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=OneStepThenCompletePack(),
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
        orchestration_adapter=ImmediateTerminalPack(),
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
        orchestration_adapter=WaitHumanPack(),
        session_manager=sm,
        session_id="s1",
        run_artifact_ref=None,
        request_id_prefix="r3",
        max_iterations=3,
    )
    assert result.terminal_class == "waiting_human"
    assert len(sm.steps) == 0
    assert result.runtime_state.get("pending_hitl_requests_count", 0) >= 1
    assert result.runtime_state.get("blocking_prompt_id")


class AsyncHitlThenCompletePack:
    """Non-blocking HITL on turn 1, then complete_run."""

    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="m-async", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        if context.loop_memory.iterations == 1:
            return ActionPlan(
                action_type="noop",
                action_inputs={},
                idempotency_key="ik-async-hitl",
                skip_execution=True,
                wait_for_human=False,
                hitl_request={"message": "FYI only", "choices": [], "context": {}},
                continuity_journal_entry=_PACK_CJ,
            )
        return ActionPlan(
            complete_run=True,
            idempotency_key="ik-done",
            rationale="after_async_hitl",
            continuity_journal_entry=_PACK_CJ,
            state_patch={"mission": {"work_universe_posture": "audited"}},
        )


class LongRationaleCompleteRunPack:
    """complete_run with a long terminal rationale that must stay out of reason_code."""

    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="m-terminal", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        return ActionPlan(
            complete_run=True,
            idempotency_key="ik-terminal",
            rationale=(
                "The focused lower-page crop still leaves the second parcel unresolved, "
                "so the run should stop with that limitation explicit."
            ),
            continuity_journal_entry=_PACK_CJ,
            state_patch={"mission": {"work_universe_posture": "audited"}},
        )


def _closure_policy_ctx() -> dict[str, Any]:
    return {
        "domain_closure_policy": {
            "hard_enforced": True,
            "enforce_on_publish": True,
            "enforce_on_complete": True,
            "save_action_ids": ["save_workspace_artifact"],
            "publish_action_ids": ["publish_workspace_artifact"],
            "minimum_resolution_items_for_save": 0,
            "minimum_resolution_items_for_wait": 0,
            "minimum_resolution_items_for_publish": 0,
            "minimum_resolution_items_for_complete": 0,
            "required_dimension_ids": [
                "layer_1_delta_convergence",
                "layer_2_intrinsic_source_integrity",
                "layer_3_external_dependency_completeness",
                "layer_4_mapping_blocking_relevance",
            ],
            "standards": [],
        }
    }


def _resolution_items_policy_ctx(*, save: int = 0, wait: int = 0, publish: int = 0, complete: int = 0) -> dict[str, Any]:
    return {
        "domain_closure_policy": {
            "hard_enforced": True,
            "enforce_on_publish": False,
            "enforce_on_complete": False,
            "save_action_ids": ["save_workspace_artifact"],
            "publish_action_ids": ["publish_workspace_artifact"],
            "minimum_resolution_items_for_save": save,
            "minimum_resolution_items_for_wait": wait,
            "minimum_resolution_items_for_publish": publish,
            "minimum_resolution_items_for_complete": complete,
            "required_dimension_ids": [],
            "standards": [],
        }
    }


def _inherit_projection_from_context(context: OrchestratorContext) -> SharedStateProjection:
    prior_ms = context.loop_memory.continuity.mission_state
    prior_rs = context.loop_memory.continuity.resolution_state
    ts = time.time()
    rs = prior_rs.model_copy(update={"updated_at_epoch_seconds": ts})
    ms = prior_ms.model_copy(
        update={
            "mission_id": context.session_id,
            "session_id": context.session_id,
            "request_id": context.request_id_prefix,
            "loop_family": "orchestration_kernel",
            "updated_at_epoch_seconds": ts,
            "resolution_state": rs,
        }
    )
    return SharedStateProjection(
        mission_state=ms,
        resolution_state=rs,
        latest_refs=dict(context.loop_memory.continuity.latest_refs),
        active_item_id=context.loop_memory.continuity.active_item_id,
    )


class ResolutionGatedSavePack:
    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return _inherit_projection_from_context(context)

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        if context.loop_memory.iterations == 1:
            return ActionPlan(
                action_type="save_workspace_artifact",
                action_inputs={"transcript_text": "draft"},
                idempotency_key="ik-save-blocked",
                rationale="too early save",
                continuity_journal_entry=_PACK_CJ,
            )
        if context.loop_memory.iterations == 2:
            return ActionPlan(
                action_type="save_workspace_artifact",
                action_inputs={"transcript_text": "draft"},
                idempotency_key="ik-save-executed",
                rationale="save after itemization",
                continuity_journal_entry=_PACK_CJ,
                state_patch={
                    "resolution": {
                        "items": [
                            {
                                "item_id": "claim-1",
                                "title": "Bearing verification",
                                "kind": "work_unit",
                                "status": "open",
                            }
                        ],
                    }
                },
            )
        return ActionPlan(
            complete_run=True,
            idempotency_key="ik-save-done",
            rationale="done",
            continuity_journal_entry=_PACK_CJ,
            state_patch={"mission": {"work_universe_posture": "audited"}},
        )


class ResolutionGatedWaitPack:
    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return _inherit_projection_from_context(context)

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        if context.loop_memory.iterations == 1:
            return ActionPlan(
                wait_for_human=True,
                idempotency_key="ik-wait-blocked",
                hitl_request={"message": "Need human input", "choices": [], "context": {}},
                rationale="wait too early",
                continuity_journal_entry=_PACK_CJ,
            )
        return ActionPlan(
            wait_for_human=True,
            idempotency_key="ik-wait-executed",
            hitl_request={"message": "Need human input", "choices": [], "context": {}},
            rationale="wait after itemization",
            continuity_journal_entry=_PACK_CJ,
            state_patch={
                "resolution": {
                    "items": [
                        {
                            "item_id": "cutoff-1",
                            "title": "Second parcel continuation missing",
                            "kind": "work_unit",
                            "status": "open",
                        }
                    ],
                }
            },
        )


def _closure_dimensions(*, layer4_status: str = "blocking") -> list[dict[str, Any]]:
    return [
        {
            "dimension_id": "layer_1_delta_convergence",
            "title": "Layer 1",
            "status": "closed",
            "determination": "earned",
            "summary": "Transcript matches visible source",
            "verification_basis": "Direct source comparison resolved the visible transcript delta.",
        },
        {
            "dimension_id": "layer_2_intrinsic_source_integrity",
            "title": "Layer 2",
            "status": "open",
            "determination": "earned",
            "summary": "Source contradiction remains explicit",
            "verification_basis": "The visible source was reviewed closely enough to confirm the contradiction stays open.",
        },
        {
            "dimension_id": "layer_3_external_dependency_completeness",
            "title": "Layer 3",
            "status": "no_further_progress",
            "determination": "earned",
            "summary": "Current image cannot recover the missing continuation",
            "no_further_progress": True,
            "verification_basis": "The inspected evidence ends at the image boundary, so no further in-run recovery exists.",
        },
        {
            "dimension_id": "layer_4_mapping_blocking_relevance",
            "title": "Layer 4",
            "status": layer4_status,
            "determination": "earned",
            "summary": "Mapping relevance has been explicitly classified",
            "blocking": layer4_status != "non_blocking",
            "verification_basis": "The remaining uncertainty was explicitly judged for mapping relevance.",
        },
    ]


class ClosureGatedCompletePack:
    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return _inherit_projection_from_context(context)

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        if context.loop_memory.iterations == 1:
            return ActionPlan(
                complete_run=True,
                idempotency_key="ik-close-1",
                rationale="trying too early",
                continuity_journal_entry=_PACK_CJ,
                state_patch={
                    "mission": {
                        "work_universe_posture": "audited",
                        "closure_state": {
                            "overall_status": "open",
                            "ready_to_close": False,
                            "dimensions": _closure_dimensions(),
                        }
                    }
                },
            )
        return ActionPlan(
            complete_run=True,
            idempotency_key="ik-close-2",
            rationale="now explicit and ready",
            continuity_journal_entry=_PACK_CJ,
            state_patch={
                "mission": {
                    "work_universe_posture": "audited",
                    "closure_state": {
                        "overall_status": "complete_ready",
                        "ready_to_close": True,
                        "dimensions": [
                            {
                                "dimension_id": "layer_4_mapping_blocking_relevance",
                                "status": "non_blocking",
                                "summary": "Remaining caveat does not block mapping",
                                "blocking": False,
                            }
                        ],
                    }
                }
            },
        )


class ClosureGatedPublishPack:
    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return _inherit_projection_from_context(context)

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        if context.loop_memory.iterations == 1:
            return ActionPlan(
                action_type="publish_workspace_artifact",
                action_inputs={"source_revision_ref": "transcript_edit:working:rev:0001"},
                idempotency_key="ik-publish-1",
                rationale="publish before closure is ready",
                continuity_journal_entry=_PACK_CJ,
                state_patch={
                    "mission": {
                        "work_universe_posture": "audited",
                        "closure_state": {
                            "overall_status": "investigating",
                            "ready_to_publish": False,
                            "dimensions": _closure_dimensions(),
                        }
                    }
                },
            )
        if context.loop_memory.iterations == 2:
            return ActionPlan(
                action_type="publish_workspace_artifact",
                action_inputs={"source_revision_ref": "transcript_edit:working:rev:0001"},
                idempotency_key="ik-publish-2",
                rationale="publish once ledger is explicit",
                continuity_journal_entry=_PACK_CJ,
                state_patch={
                    "mission": {
                        "work_universe_posture": "audited",
                        "closure_state": {
                            "overall_status": "publish_ready",
                            "ready_to_publish": True,
                            "dimensions": [
                                {
                                    "dimension_id": "layer_4_mapping_blocking_relevance",
                                    "status": "non_blocking",
                                    "summary": "Remaining caveat is non-blocking",
                                    "blocking": False,
                                }
                            ],
                        }
                    }
                },
            )
        return ActionPlan(
            complete_run=True,
            idempotency_key="ik-publish-done",
            rationale="close after publish",
            continuity_journal_entry=_PACK_CJ,
            state_patch={
                "mission": {
                    "work_universe_posture": "audited",
                    "closure_state": {
                        "ready_to_close": True,
                        "dimensions": [
                            {
                                "dimension_id": "layer_4_mapping_blocking_relevance",
                                "status": "non_blocking",
                                "summary": "Handoff is explicit and non-blocking",
                                "blocking": False,
                            }
                        ],
                    }
                }
            },
        )


def test_non_blocking_hitl_loop_continues() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=AsyncHitlThenCompletePack(),
        session_manager=sm,
        session_id="s-async-hitl",
        run_artifact_ref=None,
        request_id_prefix="r-async-hitl",
        opaque_run_context={"loop_kind": "harness_cli"},
        max_iterations=5,
    )
    assert result.terminal_class == "completed"
    assert result.runtime_state.get("pending_hitl_requests_count", 0) >= 1


def test_complete_run_uses_short_reason_code_and_preserves_summary() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=LongRationaleCompleteRunPack(),
        session_manager=sm,
        session_id="s-long-terminal",
        run_artifact_ref=None,
        request_id_prefix="r-long-terminal",
        opaque_run_context={},
        max_iterations=3,
    )

    assert result.terminal_class == "completed"
    assert result.reason_code == "complete_run"
    assert result.terminal_summary == (
        "The focused lower-page crop still leaves the second parcel unresolved, "
        "so the run should stop with that limitation explicit."
    )
    assert len(sm.steps) == 0
    terminal_event = next(e for e in result.trace_events if e.get("event_kind") == "terminal_outcome")
    assert terminal_event["reason_code"] == "complete_run"
    assert terminal_event["payload"]["terminal_summary"] == result.terminal_summary


def test_complete_run_is_blocked_until_closure_state_is_ready() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=ClosureGatedCompletePack(),
        session_manager=sm,
        session_id="s-close-gated",
        run_artifact_ref=None,
        request_id_prefix="r-close-gated",
        opaque_run_context=_closure_policy_ctx(),
        max_iterations=3,
    )

    assert result.terminal_class == "completed"
    assert result.reason_code == "complete_run"
    assert len(sm.steps) == 0
    closure = result.runtime_state["mission_state"].closure_state
    assert closure.ready_to_close is True
    blocked_event = next(
        e
        for e in result.trace_events
        if e.get("event_kind") == "tool_execution" and e.get("reason_code") == "closure_complete_not_ready"
    )
    assert blocked_event["payload"]["execution_state"] == "refused"


def test_publish_is_blocked_until_closure_state_is_publish_ready() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=ClosureGatedPublishPack(),
        session_manager=sm,
        session_id="s-publish-gated",
        run_artifact_ref=None,
        request_id_prefix="r-publish-gated",
        opaque_run_context=_closure_policy_ctx(),
        max_iterations=4,
    )

    assert result.terminal_class == "completed"
    assert result.reason_code == "complete_run"
    assert len(sm.steps) == 1
    assert sm.steps[0].action_id == "publish_workspace_artifact"
    closure = result.runtime_state["mission_state"].closure_state
    assert closure.ready_to_publish is True
    blocked_event = next(
        e
        for e in result.trace_events
        if e.get("event_kind") == "tool_execution" and e.get("reason_code") == "closure_publish_not_ready"
    )
    assert blocked_event["payload"]["execution_state"] == "refused"


def test_save_is_blocked_until_resolution_items_exist() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=ResolutionGatedSavePack(),
        session_manager=sm,
        session_id="s-save-gated",
        run_artifact_ref=None,
        request_id_prefix="r-save-gated",
        opaque_run_context=_resolution_items_policy_ctx(save=1),
        max_iterations=4,
    )

    assert result.terminal_class == "completed"
    assert result.reason_code == "complete_run"
    assert len(sm.steps) == 1
    assert sm.steps[0].action_id == "save_workspace_artifact"
    assert len(result.runtime_state["resolution_state"].items) == 1
    blocked_event = next(
        e
        for e in result.trace_events
        if e.get("event_kind") == "tool_execution" and e.get("reason_code") == "resolution_items_save_required"
    )
    assert blocked_event["payload"]["execution_state"] == "refused"


def test_wait_for_human_is_blocked_until_resolution_items_exist() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=ResolutionGatedWaitPack(),
        session_manager=sm,
        session_id="s-wait-gated",
        run_artifact_ref=None,
        request_id_prefix="r-wait-gated",
        opaque_run_context=_resolution_items_policy_ctx(wait=1),
        max_iterations=3,
    )

    assert result.terminal_class == "waiting_human"
    assert result.reason_code == "waiting_human_feedback"
    assert len(result.runtime_state["resolution_state"].items) == 1
    blocked_event = next(
        e
        for e in result.trace_events
        if e.get("event_kind") == "tool_execution" and e.get("reason_code") == "resolution_items_wait_required"
    )
    assert blocked_event["payload"]["execution_state"] == "refused"
    assert result.runtime_state.get("pending_hitl_requests_count", 0) >= 1


def test_skip_execution_no_session_step() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=SkipExecutionPack(),
        session_manager=sm,
        session_id="s1",
        run_artifact_ref=None,
        request_id_prefix="r4",
        max_iterations=5,
    )
    assert result.terminal_class == "completed"
    assert len(sm.steps) == 0


def test_orchestration_adapter_protocol_typing() -> None:
    p: OrchestrationAdapter = OneStepThenCompletePack()
    assert hasattr(p, "initialize")


def test_explicit_pre_choose_action_participant_runs_before_choose_action() -> None:
    participant = _RecordingPreChooseActionParticipant()
    sm = FakeSessionManager()

    result = run_orchestration_kernel_loop(
        orchestration_adapter=SkipExecutionPack(),
        session_manager=sm,
        session_id="sess-lifecycle-pre",
        run_artifact_ref=None,
        request_id_prefix="req-lifecycle-pre",
        opaque_run_context={},
        max_iterations=2,
        lifecycle=OrchestrationLifecycle(pre_choose_action_participant=participant),
    )

    assert result.terminal_class == "completed"
    assert participant.calls
    assert participant.calls[0]["iteration"] == 1
    assert participant.calls[0]["has_projection"] is True


def test_turn_completion_observer_exception_does_not_break_loop() -> None:
    sm = FakeSessionManager()

    result = run_orchestration_kernel_loop(
        orchestration_adapter=SkipExecutionPack(),
        session_manager=sm,
        session_id="sess-turn-observer",
        run_artifact_ref=None,
        request_id_prefix="req-turn-observer",
        opaque_run_context={},
        max_iterations=2,
        lifecycle=OrchestrationLifecycle(
            turn_completion_observer=_ExplodingTurnCompletionObserver(),
        ),
    )

    assert result.terminal_class == "completed"


def test_state_patch_persists_across_sync_iterations() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=MechanicalInheritSyncPack(),
        session_manager=sm,
        session_id="sess-patch",
        run_artifact_ref=None,
        request_id_prefix="req-patch",
        opaque_run_context={},
        max_iterations=6,
    )
    assert result.terminal_class == "completed"
    assert result.reason_code == "patch_persisted"
    assert len(sm.steps) == 2
    rs = result.runtime_state["resolution_state"]
    assert len(rs.items) == 1
    assert rs.items[0].status == "closed"


def test_complete_run_patch_surfaces_skipped_item_rows_in_feedback_and_trace() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=CompleteRunWithSkippedItemRowsPack(),
        session_manager=sm,
        session_id="sess-skip-rows",
        run_artifact_ref=None,
        request_id_prefix="req-skip-rows",
        opaque_run_context={},
        max_iterations=3,
    )
    assert result.terminal_class == "completed"
    assert len(result.runtime_state["resolution_state"].items) == 1
    fb = result.runtime_state["state_patch_feedback"]
    assert fb.get("outcome") == "applied"
    assert fb.get("skipped_resolution_rows") is True
    assert fb.get("row_skips") == {"resolution": {"items": {"missing_item_id": 1}, "relations": {}}}
    assert "item_id" in str(fb.get("repair_hint"))
    patch_events = [e for e in result.trace_events if e.get("event_kind") == "state_patch_outcome"]
    assert patch_events
    assert patch_events[-1]["payload"].get("detail", {}).get("skipped_resolution_rows") is True
    assert "item_id" in str(patch_events[-1]["payload"].get("detail", {}).get("repair_hint"))


def test_invalid_state_patch_is_dropped_without_terminating_loop() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=BadTopLevelStatePatchPack(),
        session_manager=sm,
        session_id="sess-bad",
        run_artifact_ref=None,
        request_id_prefix="req-bad",
        max_iterations=5,
    )
    assert result.terminal_class == "completed"
    assert result.reason_code == "after_bad_patch"
    assert len(sm.steps) == 1
    assert len(result.runtime_state["resolution_state"].items) == 0
    fb = result.runtime_state["state_patch_feedback"]
    assert fb.get("outcome") == "rejected"
    assert fb.get("reason_code") == "state_patch_unknown_keys"
    kinds = [e.get("event_kind") for e in result.trace_events]
    assert "state_patch_outcome" in kinds


def _fake_llm_action_json(ik_suffix: str) -> str:
    return json.dumps(
        {
            "action_type": "noop",
            "action_inputs": {},
            "idempotency_key": f"ik-{ik_suffix}",
            "skip_execution": False,
            "wait_for_human": False,
            "complete_run": False,
            "rationale": f"stub rationale {ik_suffix}",
            "state_patch": None,
            "continuity_journal_entry": {"llm_stub_turn": ik_suffix},
            "operator_progress_message": None,
        }
    )


def test_kernel_loop_llm_adapter_prompt_telemetry_and_trace_match_turns() -> None:
    """Two iterations => two prompt_event traces; llm_contact_count and prompt_event_count both == 2."""
    call_n = {"i": 0}

    def fake_caller(prompt: str, model: str, **_kwargs: Any) -> str:
        call_n["i"] += 1
        return _fake_llm_action_json(str(call_n["i"]))

    composed = ComposedTurnInput(
        blocks=(TurnBlock(content="hi"),),
        surface_payloads={},
        tool_handlers={"noop": lambda x: x},
    )
    tracer = KernelTraceCollector(session_id="sess-telemetry", request_id="req-tel")
    lifecycle = OrchestrationLifecycle(
        prompt_event_observer=KernelPromptEventTraceObserver(tracer=tracer),
    )
    adapter = LlmTurnOrchestrationAdapter(
        composed_input=composed,
        text_model_caller=fake_caller,
        model_name="stub-model",
    )

    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=adapter,
        session_manager=sm,
        session_id="sess-telemetry",
        run_artifact_ref=None,
        request_id_prefix="req-tel",
        opaque_run_context={},
        max_iterations=2,
        lifecycle=lifecycle,
        tracer=tracer,
    )

    assert result.terminal_class == "exhausted"
    assert call_n["i"] == 2
    assert result.runtime_state["llm_contact_count"] == 2
    assert result.runtime_state["prompt_event_count"] == 2
    assert result.runtime_state["last_prompt_event_surface"] == "orchestration_kernel_llm_turn"
    assert result.runtime_state["last_prompt_event_id"] == "req-tel:iter2:kernel_llm"

    pe_events = [e for e in result.trace_events if e.get("phase") == "prompt_event"]
    assert len(pe_events) == 2
    assert pe_events[0]["iteration_index"] == 1
    assert pe_events[1]["iteration_index"] == 2
    for ev in pe_events:
        payload = ev.get("payload") or {}
        assert payload.get("model") == "stub-model"
        pe = payload.get("prompt_event")
        assert isinstance(pe, dict)
        assert pe.get("outcome_kind") == "kernel_action_plan_parsed"

    snap = result.kernel_resume_snapshot
    assert snap["telemetry"]["prompt_event_count"] == 2
    assert snap["telemetry"]["llm_contact_count"] == 2
    assert snap["telemetry"]["last_prompt_event_id"] == "req-tel:iter2:kernel_llm"

    restored, next_it, err = parse_kernel_resume_snapshot(snap)
    assert err is None
    assert next_it == 3
    assert restored.telemetry.prompt_event_count == 2
    assert restored.telemetry.llm_contact_count == 2


class ContinuityJournalTwoTurnPack:
    """First turn writes journal + progress; second turn asserts they are loop-carried, then completes."""

    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="mj", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        it = context.loop_memory.iterations
        if it == 2:
            assert len(context.loop_memory.continuity.continuity_journal_entries) == 1
            first_payload = context.loop_memory.continuity.continuity_journal_entries[0]["author_payload"]
            assert first_payload["author_addendum"].get("mark") == "t1"
            assert first_payload["host_derived"]["kernel_turn_index"] == 1
            assert context.loop_memory.continuity.operator_progress_message == "hello op"
            return ActionPlan(
                complete_run=True,
                idempotency_key="ik2",
                rationale="done",
                continuity_journal_entry={"close_out": True},
                state_patch={"mission": {"work_universe_posture": "audited"}},
            )
        return ActionPlan(
            action_type="noop",
            action_inputs={},
            idempotency_key="ik1",
            skip_execution=True,
            continuity_journal_entry={"mark": "t1"},
            operator_progress_message="hello op",
        )


def test_kernel_step_result_record_after_executed_step_roundtrips_resume() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=OneStepThenCompletePack(),
        session_manager=sm,
        session_id="sess-sr",
        run_artifact_ref=None,
        request_id_prefix="req-sr",
        opaque_run_context={},
        max_iterations=4,
    )
    assert result.terminal_class == "completed"
    assert len(sm.steps) == 1
    snap = result.kernel_resume_snapshot
    assert snap is not None
    mem, _, err = parse_kernel_resume_snapshot(snap)
    assert err is None
    assert len(mem.continuity.kernel_step_result_records) == 1
    row = mem.continuity.kernel_step_result_records[0]
    assert row["kernel_turn_index"] == 1
    assert row["execution_state"] == "executed"


def test_kernel_continuity_journal_carried_across_turns() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=ContinuityJournalTwoTurnPack(),
        session_manager=sm,
        session_id="sess-cj",
        run_artifact_ref=None,
        request_id_prefix="req-cj",
        opaque_run_context={},
        max_iterations=6,
    )
    assert result.terminal_class == "completed"
    assert result.runtime_state["operator_progress_message"] == "hello op"
    assert result.runtime_state["continuity_journal_entry_count"] == 2
    snap = result.kernel_resume_snapshot
    assert snap is not None
    mem, _, err = parse_kernel_resume_snapshot(snap)
    assert err is None
    assert len(mem.continuity.continuity_journal_entries) == 2
    assert len(mem.continuity.kernel_step_records) == 2


def test_state_patch_not_applied_when_step_refused() -> None:
    sm = RefuseOnceSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=PatchOnNoopRefusedPack(),
        session_manager=sm,
        session_id="sess-np",
        run_artifact_ref=None,
        request_id_prefix="req-np",
        opaque_run_context={},
        max_iterations=3,
    )
    assert result.terminal_class == "failed"
    assert result.reason_code == "test_refusal"
    assert len(sm.steps) == 1
    assert len(result.runtime_state["resolution_state"].items) == 0
    fb = result.runtime_state["state_patch_feedback"]
    assert fb.get("outcome") == "not_applied"
    assert fb.get("execution_reason_code") == "test_refusal"
    assert any(e.get("event_kind") == "state_patch_outcome" for e in result.trace_events)


def test_sparse_no_dispatch_action_plan_commits_patch_without_explicit_skip_execution() -> None:
    result = run_orchestration_kernel_loop(
        orchestration_adapter=_SparseNoDispatchActionPlanPack(),
        session_manager=FakeSessionManager(),
        session_id="sess-sparse-ap",
        run_artifact_ref=None,
        request_id_prefix="req-sparse-ap",
        opaque_run_context={},
        max_iterations=3,
    )

    assert result.terminal_class == "completed"
    assert result.runtime_state["mission_state"].work_universe_posture == "audited"
    fb = result.runtime_state["state_patch_feedback"]
    assert fb.get("outcome") == "applied"


def test_sparse_no_dispatch_dict_plan_commits_patch_without_explicit_skip_execution() -> None:
    result = run_orchestration_kernel_loop(
        orchestration_adapter=_SparseNoDispatchDictPack(),
        session_manager=FakeSessionManager(),
        session_id="sess-sparse-dict",
        run_artifact_ref=None,
        request_id_prefix="req-sparse-dict",
        opaque_run_context={},
        max_iterations=3,
    )

    assert result.terminal_class == "completed"
    assert result.runtime_state["mission_state"].work_universe_posture == "audited"
    fb = result.runtime_state["state_patch_feedback"]
    assert fb.get("outcome") == "applied"


def test_sparse_hitl_action_plan_emits_async_request_without_explicit_skip_execution() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=_SparseHitlActionPlanPack(),
        session_manager=sm,
        session_id="sess-hitl-ap",
        run_artifact_ref=None,
        request_id_prefix="req-hitl-ap",
        opaque_run_context={},
        max_iterations=3,
    )

    assert result.terminal_class == "completed"
    assert len(sm.steps) == 0
    assert result.runtime_state["pending_hitl_requests_count"] == 1
    assert result.runtime_state["hitl_state"] == "async_prompts_pending"
    fb = result.runtime_state["state_patch_feedback"]
    assert fb.get("outcome") == "no_patch"


def test_sparse_hitl_dict_plan_emits_async_request_without_explicit_skip_execution() -> None:
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=_SparseHitlDictPack(),
        session_manager=sm,
        session_id="sess-hitl-dict",
        run_artifact_ref=None,
        request_id_prefix="req-hitl-dict",
        opaque_run_context={},
        max_iterations=3,
    )

    assert result.terminal_class == "completed"
    assert len(sm.steps) == 0
    assert result.runtime_state["pending_hitl_requests_count"] == 1
    assert result.runtime_state["hitl_state"] == "async_prompts_pending"
    fb = result.runtime_state["state_patch_feedback"]
    assert fb.get("outcome") == "no_patch"


# ---------------------------------------------------------------------------
# image_evidence propagated through explicit turn-completion observation
# ---------------------------------------------------------------------------


class _ImageEvidenceSessionManager(ExecutionSessionManager):
    """Returns a step result whose ActionDispatchResult carries image_evidence."""

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        from harness.execution.contracts import ActionDispatchResult, SessionExecutionRecord

        result = ActionDispatchResult(
            action_id=request.action_id,
            executed=True,
            outputs={"hydrated": True},
            artifact_refs=("image:assoc:tx1:original",),
            image_evidence=(
                {"ref_id": "image:assoc:tx1:original", "media_type": "image/jpeg", "data": "b64=="},
                {"ref_id": "image:assoc:tx1:processed", "media_type": "image/jpeg", "data": "b64proc=="},
            ),
        )
        rec = SessionExecutionRecord(
            session_id=request.session_id,
            run_id=request.run_id or "",
            request=request,
            result=result,
        )
        return ExecutionStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=ExecutionState.EXECUTED,
            dashboard=_dashboard(),
            record=rec,
        )


class _OneStepImagePack:
    """One step with image evidence, then complete."""

    def initialize(self, context: OrchestratorContext) -> None: ...
    def evaluate_terminal(self, context: OrchestratorContext, projection: Any) -> None: ...

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="m-img", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
            latest_refs={},
        )

    def choose_action(self, context: OrchestratorContext, projection: Any) -> ActionPlan:
        if context.loop_memory.iterations == 1:
            return ActionPlan(
                action_type="hydrate_tool",
                action_inputs={"ref_ids": ["image:assoc:tx1:original"]},
                idempotency_key="ik-img",
                continuity_journal_entry={"img_turn": True},
            )
        return ActionPlan(
            complete_run=True,
            continuity_journal_entry={"done": True},
            state_patch={"mission": {"work_universe_posture": "audited"}},
        )


def test_image_evidence_in_tool_result_raw_via_turn_completion_observer() -> None:
    """image_evidence from the execution result must appear in turn-completion records."""
    observer = _TurnCompletionRecorder()
    sm = _ImageEvidenceSessionManager()
    sm.start_session(
        __import__("harness.execution.contracts", fromlist=["ExecutionSessionStartRequest"])
        .ExecutionSessionStartRequest(run_id="r-img", session_id="sess-img")
    )
    run_orchestration_kernel_loop(
        orchestration_adapter=_OneStepImagePack(),
        session_manager=sm,
        session_id="sess-img",
        run_artifact_ref=None,
        request_id_prefix="req-img",
        opaque_run_context={},
        max_iterations=3,
        lifecycle=OrchestrationLifecycle(turn_completion_observer=observer),
    )

    tool_turn = next(r for r in observer.records if r["turn_index"] == 1)
    tool_result = tool_turn["tool_result_raw"]
    assert tool_result is not None
    summary = tool_result["image_evidence_summary"]
    assert summary is not None
    assert summary["count"] == 2
    assert summary["ref_ids"] == [
        "image:assoc:tx1:original",
        "image:assoc:tx1:processed",
    ]
    assert "b64" not in str(tool_result)


def test_turn_completion_observer_receives_normalized_state_records() -> None:
    observer = _TurnCompletionRecorder()
    sm = FakeSessionManager()
    sm.start_session(
        __import__("harness.execution.contracts", fromlist=["ExecutionSessionStartRequest"])
        .ExecutionSessionStartRequest(run_id="r-state", session_id="sess-state")
    )
    run_orchestration_kernel_loop(
        orchestration_adapter=OneStepThenCompletePack(),
        session_manager=sm,
        session_id="sess-state",
        run_artifact_ref=None,
        request_id_prefix="req-state",
        opaque_run_context={},
        max_iterations=3,
        lifecycle=OrchestrationLifecycle(turn_completion_observer=observer),
    )

    tool_turn = next(r for r in observer.records if r["turn_index"] == 1)
    assert isinstance(tool_turn["mission_state_after"], dict)
    assert isinstance(tool_turn["resolution_state_after"], dict)
    assert tool_turn["mission_state_after"]["loop_family"] == "orchestration_kernel"
    assert tool_turn["resolution_state_after"]["items"] == []


# ---------------------------------------------------------------------------
# Retryable transform-param refusal: loop continues, next-turn recovery
# ---------------------------------------------------------------------------


class _RetryableRefuseOnceSessionManager(ExecutionSessionManager):
    """First ``step`` returns a retryable param refusal; subsequent steps execute normally."""

    def __init__(self) -> None:
        super().__init__()
        self.steps: list[ExecutionStepRequest] = []
        self._calls = 0

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        self.steps.append(request)
        self._calls += 1
        if self._calls == 1:
            from harness.execution.contracts import ActionDispatchResult, SessionExecutionRecord

            dispatch_result = ActionDispatchResult(
                action_id=request.action_id,
                executed=False,
                outputs={
                    "error": {
                        "code": "invalid_transform_params",
                        "message": "crop requires params.box or params.box_norm",
                        "repair_hint": "Use params.box = [x1, y1, x2, y2] with pixel coordinates.",
                    }
                },
                refusal=ExecutionRefusal(
                    reason_code="invalid_transform_params",
                    retryable=True,
                    blocked_by_invariant=False,
                    blocked_by_budget=False,
                ),
            )
            rec = SessionExecutionRecord(
                session_id=request.session_id,
                run_id=request.run_id or "",
                request=request,
                result=dispatch_result,
            )
            return ExecutionStepResult(
                session_id=request.session_id,
                idempotency_key=request.idempotency_key,
                execution_state=ExecutionState.REFUSED,
                dashboard=_dashboard(),
                refusal=dispatch_result.refusal,
                record=rec,
            )
        return ExecutionStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=ExecutionState.EXECUTED,
            dashboard=_dashboard(refs={"transform_ref": "image:derived:abc123"}),
        )


class _TransformRetryRecoverPack:
    """
    Turn 1: dispatch transform_artifact with bad params → gets retryable refusal.
    Turn 2: sees the refusal in step records, dispatches corrected call → executes.
    Turn 3: complete_run.
    """

    def __init__(self) -> None:
        self._turn2_saw_refusal = False
        self._turn2_saw_repair_hint = False

    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="m-transform-retry", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        it = context.loop_memory.iterations
        if it == 1:
            # Turn 1: bad crop params (no box / box_norm)
            return ActionPlan(
                action_type="transform_artifact",
                action_inputs={"ref_id": "image:assoc:tx-1:original", "sub_action": "crop", "params": {}},
                idempotency_key="ik-transform-bad",
                continuity_journal_entry={"step": "crop attempt with missing params"},
            )
        if it == 2:
            # Turn 2: verify the refusal is visible in step result records
            step_records = context.loop_memory.continuity.kernel_step_result_records
            if step_records:
                last = step_records[-1]
                self._turn2_saw_refusal = last.get("execution_state") == "refused"
                self._turn2_saw_repair_hint = (
                    "repair_hint" in str(last.get("outputs_for_continuity", {}))
                )
            # Dispatch corrected request
            return ActionPlan(
                action_type="transform_artifact",
                action_inputs={"ref_id": "image:assoc:tx-1:original", "sub_action": "crop", "params": {"box": [0, 0, 400, 200]}},
                idempotency_key="ik-transform-good",
                continuity_journal_entry={"step": "corrected crop with explicit box"},
            )
        return ActionPlan(
            complete_run=True,
            idempotency_key="ik-done",
            rationale="transform recovered",
            continuity_journal_entry={"step": "done"},
            state_patch={"mission": {"work_universe_posture": "audited"}},
        )


def test_retryable_transform_param_refusal_does_not_terminate_loop() -> None:
    """A retryable crop-param refusal must NOT kill the run; loop continues to next turn."""
    sm = _RetryableRefuseOnceSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=_TransformRetryRecoverPack(),
        session_manager=sm,
        session_id="sess-transform-retry",
        run_artifact_ref=None,
        request_id_prefix="req-transform-retry",
        opaque_run_context={},
        max_iterations=5,
    )

    # Run must complete normally, not fail with transform param error
    assert result.terminal_class == "completed", (
        f"Expected completed, got terminal_class={result.terminal_class!r} reason_code={result.reason_code!r}"
    )
    assert result.reason_code == "complete_run"

    # Both steps must have been dispatched (bad params on turn 1, corrected on turn 2)
    assert len(sm.steps) == 2
    assert sm.steps[0].action_id == "transform_artifact"
    assert sm.steps[1].action_id == "transform_artifact"

    # Trace must record the refused turn (not skip it)
    refused_events = [
        e for e in result.trace_events
        if e.get("event_kind") == "tool_execution" and e.get("reason_code") == "invalid_transform_params"
    ]
    assert refused_events, "Expected a trace event for the retryable transform param refusal"
    assert refused_events[0]["payload"]["execution_state"] == "refused"

    # The second dispatch must have executed
    executed_events = [
        e for e in result.trace_events
        if e.get("event_kind") == "tool_execution"
        and (e.get("payload") or {}).get("execution_state") == "executed"
    ]
    assert executed_events, "Expected at least one executed transform step"


def test_retryable_refusal_info_is_visible_in_next_turn_step_records() -> None:
    """After a retryable refusal, the prior step record and repair_hint are visible to the adapter on the next turn."""
    pack = _TransformRetryRecoverPack()
    sm = _RetryableRefuseOnceSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=pack,
        session_manager=sm,
        session_id="sess-repair-visible",
        run_artifact_ref=None,
        request_id_prefix="req-repair-visible",
        opaque_run_context={},
        max_iterations=5,
    )

    assert result.terminal_class == "completed"
    # Pack.choose_action at turn 2 should have seen the refused step record
    assert pack._turn2_saw_refusal, "Turn 2 did not see the prior refused step in kernel_step_result_records"
    assert pack._turn2_saw_repair_hint, "Turn 2 did not see the repair_hint in the prior refused step outputs"


def test_image_evidence_empty_list_when_no_evidence() -> None:
    """When image_evidence is empty, tool_result_raw.image_evidence_summary should be None."""
    observer = _TurnCompletionRecorder()

    sm = FakeSessionManager()
    sm.start_session(
        __import__("harness.execution.contracts", fromlist=["ExecutionSessionStartRequest"])
        .ExecutionSessionStartRequest(run_id="r-ne", session_id="sess-ne")
    )
    run_orchestration_kernel_loop(
        orchestration_adapter=OneStepThenCompletePack(),
        session_manager=sm,
        session_id="sess-ne",
        run_artifact_ref=None,
        request_id_prefix="req-ne",
        opaque_run_context={},
        max_iterations=3,
        lifecycle=OrchestrationLifecycle(turn_completion_observer=observer),
    )

    tool_turn = next((r for r in observer.records if r.get("tool_request") is not None), None)
    assert tool_turn is not None
    assert tool_turn["tool_result_raw"]["image_evidence_summary"] is None


class _MissingIdempotencyDispatchPack:
    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="m-idem", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        if context.loop_memory.iterations >= 2:
            return TerminalEvaluation(terminal_class="completed", reason_code="done")
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        if context.loop_memory.iterations == 1:
            return ActionPlan(
                action_type="noop",
                action_inputs={"kind": "dispatch"},
                continuity_journal_entry={"step": "dispatch without model-authored idempotency"},
            )
        return ActionPlan(complete_run=True, continuity_journal_entry={"step": "complete"})


def test_orchestrator_host_fills_missing_dispatch_idempotency_consistently() -> None:
    observer = _TurnCompletionRecorder()
    sm = FakeSessionManager()
    sm.start_session(
        __import__("harness.execution.contracts", fromlist=["ExecutionSessionStartRequest"])
        .ExecutionSessionStartRequest(run_id="r-idem", session_id="sess-idem")
    )
    mem = LoopMemoryState()

    run_orchestration_kernel_loop(
        orchestration_adapter=_MissingIdempotencyDispatchPack(),
        session_manager=sm,
        session_id="sess-idem",
        run_artifact_ref=None,
        request_id_prefix="req-idem",
        opaque_run_context={},
        max_iterations=3,
        lifecycle=OrchestrationLifecycle(turn_completion_observer=observer),
        initial_loop_memory=mem,
    )

    assert len(sm.steps) == 1
    generated = sm.steps[0].idempotency_key
    assert generated == "req-idem:iter:1:dispatch:noop"
    assert mem.continuity.kernel_step_records[0]["idempotency_key"] == generated
    tool_turn = next(r for r in observer.records if r.get("tool_request") is not None)
    assert tool_turn["tool_request"]["idempotency_key"] == generated


# ---------------------------------------------------------------------------
# Run control (pause / stop) boundary checks
# ---------------------------------------------------------------------------


class _ControlRecordingSessionManager(FakeSessionManager):
    pass


class _ControlChooseActionPack:
    """Exposes whether ``choose_action`` ran; never returns a terminal."""

    def __init__(self) -> None:
        self.choose_action_calls = 0

    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="m-ctl", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        self.choose_action_calls += 1
        return ActionPlan(
            action_type="noop",
            action_inputs={},
            idempotency_key=f"ik-{context.loop_memory.iterations}",
            continuity_journal_entry=_PACK_CJ,
        )


def _control_request(command: str, *, reason: str | None = None):
    from harness.runtime.control import CONTROL_SCHEMA_VERSION, RunControlRequest
    return RunControlRequest(
        schema_version=CONTROL_SCHEMA_VERSION,
        request_id="req-test-1",
        command=command,
        requested_at_epoch_seconds=1.0,
        reason=reason,
        requested_by="cli",
    )


def test_run_control_pause_before_choose_action_exits_without_model_call() -> None:
    from harness.runtime.control import RunControlRequest
    pack = _ControlChooseActionPack()
    sm = _ControlRecordingSessionManager()
    checkpoints: list[dict] = []

    def _writer(snap):  # capture resume snapshots
        checkpoints.append(dict(snap))

    reader_request: RunControlRequest | None = _control_request("pause", reason="tea break")

    def _reader():
        return reader_request

    result = run_orchestration_kernel_loop(
        orchestration_adapter=pack,
        session_manager=sm,
        session_id="s-ctl-pause",
        run_artifact_ref=None,
        request_id_prefix="r-ctl-pause",
        max_iterations=5,
        lifecycle=OrchestrationLifecycle(
            resume_checkpoint_writer=_writer,
            run_control_reader=_reader,
        ),
    )
    assert result.terminal_class == "paused"
    assert result.reason_code == "paused_by_operator"
    assert pack.choose_action_calls == 0
    assert len(sm.steps) == 0
    # Checkpoint was written before exit.
    assert checkpoints, "expected a resume checkpoint before paused exit"
    assert result.kernel_resume_snapshot is not None
    # Control request metadata propagated into runtime_state.
    ctl = result.runtime_state.get("control_request")
    assert isinstance(ctl, dict)
    assert ctl.get("command") == "pause"
    assert ctl.get("reason") == "tea break"
    assert result.runtime_state.get("resumable") is True


def test_run_control_stop_after_choose_action_exits_without_tool_dispatch() -> None:
    from harness.runtime.control import RunControlRequest
    pack = _ControlChooseActionPack()
    sm = _ControlRecordingSessionManager()

    # Fire on the second call so choose_action runs once first (post-choose boundary).
    reader_calls = {"n": 0}

    def _reader() -> RunControlRequest | None:
        reader_calls["n"] += 1
        # n==1: pre-choose on iter 1 ► no control (let choose_action run).
        # n==2: post-choose on iter 1 ► fire stop.
        if reader_calls["n"] >= 2:
            return _control_request("stop")
        return None

    result = run_orchestration_kernel_loop(
        orchestration_adapter=pack,
        session_manager=sm,
        session_id="s-ctl-stop",
        run_artifact_ref=None,
        request_id_prefix="r-ctl-stop",
        max_iterations=5,
        lifecycle=OrchestrationLifecycle(run_control_reader=_reader),
    )
    assert result.terminal_class == "stopped"
    assert result.reason_code == "stopped_by_operator"
    assert pack.choose_action_calls == 1
    # No tool dispatch should have occurred at the post-choose boundary.
    assert len(sm.steps) == 0


def test_run_control_reader_errors_do_not_crash_loop() -> None:
    pack = _ControlChooseActionPack()
    sm = _ControlRecordingSessionManager()

    def _boom():
        raise RuntimeError("io_error")

    # Cap iterations so the loop exits via exhaustion rather than running forever.
    result = run_orchestration_kernel_loop(
        orchestration_adapter=pack,
        session_manager=sm,
        session_id="s-ctl-err",
        run_artifact_ref=None,
        request_id_prefix="r-ctl-err",
        max_iterations=2,
        lifecycle=OrchestrationLifecycle(run_control_reader=_boom),
    )
    # Reader errors are swallowed; loop exhausts normally.
    assert result.terminal_class == "exhausted"
    assert result.reason_code == "max_iterations_reached"


# ---------------------------------------------------------------------------
# Recoverable model-output failures
# ---------------------------------------------------------------------------


def _llm_turn_adapter_for_recovery_test(caller) -> LlmTurnOrchestrationAdapter:
    return LlmTurnOrchestrationAdapter(
        composed_input=ComposedTurnInput(
            blocks=(TurnBlock(content="test prompt block"),),
            surface_payloads={},
            tool_handlers={"noop": lambda payload: payload},
        ),
        text_model_caller=caller,
        model_name="fake-model",
    )


def test_orchestrator_recovers_from_length_failure_with_turn_recovery_prompt() -> None:
    calls: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **kwargs: Any) -> Any:
        call_options = kwargs.get("call_options")
        calls.append({"prompt": prompt, "phase": getattr(call_options, "phase", None)})
        if len(calls) == 1:
            return {
                "success": False,
                "error": "OpenAI returned truncated response (finish_reason: length)",
                "text": None,
                "model": model,
                "finish_reason": "length",
                "usage": {"prompt_tokens": 25966, "completion_tokens": 16000, "total_tokens": 41966},
                "char_count": 0,
            }
        return json.dumps(
            {
                "complete_run": True,
                "rationale": "recovered with a bounded action",
                "state_patch": {"mission": {"work_universe_posture": "audited"}},
                "continuity_journal_entry": {"recovered": True},
            }
        )

    result = run_orchestration_kernel_loop(
        orchestration_adapter=_llm_turn_adapter_for_recovery_test(caller),
        session_manager=FakeSessionManager(),
        session_id="s-recovery",
        run_artifact_ref=None,
        request_id_prefix="r-recovery",
        opaque_run_context={"recoverable_turn_failure_budget": 1},
        max_iterations=3,
        lifecycle=OrchestrationLifecycle(resume_checkpoint_writer=lambda snap: checkpoints.append(dict(snap))),
    )

    assert result.terminal_class == "completed"
    assert result.reason_code == "complete_run"
    assert [call["phase"] for call in calls] == ["choose_action", "choose_action_turn_recovery"]
    assert '"prompt_mode": "turn_recovery"' in calls[1]["prompt"]
    assert checkpoints[0]["turn_recovery"]["last_failure"]["provider_finish_reason"] == "length"
    assert result.kernel_resume_snapshot is not None
    assert result.kernel_resume_snapshot["turn_recovery"]["last_failure"] == {}


def test_orchestrator_fails_only_after_recoverable_turn_failure_budget_exhausted() -> None:
    calls: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
        call_options = kwargs.get("call_options")
        calls.append({"prompt": prompt, "phase": getattr(call_options, "phase", None)})
        return {
            "success": False,
            "error": "OpenAI returned truncated response (finish_reason: length)",
            "text": None,
            "model": model,
            "finish_reason": "length",
            "usage": {"prompt_tokens": 100, "completion_tokens": 16000, "total_tokens": 16100},
            "char_count": 0,
        }

    result = run_orchestration_kernel_loop(
        orchestration_adapter=_llm_turn_adapter_for_recovery_test(caller),
        session_manager=FakeSessionManager(),
        session_id="s-recovery-fail",
        run_artifact_ref=None,
        request_id_prefix="r-recovery-fail",
        opaque_run_context={"recoverable_turn_failure_budget": 1},
        max_iterations=4,
    )

    assert result.terminal_class == "failed"
    assert result.reason_code == "recoverable_turn_failure_budget_exhausted"
    assert [call["phase"] for call in calls] == ["choose_action", "choose_action_turn_recovery"]
    assert result.kernel_resume_snapshot is not None
    assert result.kernel_resume_snapshot["turn_recovery"]["consecutive_failures"] == 2


def test_kernel_resume_snapshot_preserves_turn_recovery_state() -> None:
    mem = LoopMemoryState()
    mem.turn_recovery.record_failure(
        {
            "iteration": 18,
            "prompt_mode": "resume",
            "reason_code": "model_call_failed",
            "provider_finish_reason": "length",
        }
    )

    from harness.runtime.memory.resume_snapshot import build_kernel_resume_snapshot

    snapshot = build_kernel_resume_snapshot(
        loop_memory=mem,
        session_id="s-recovery-snapshot",
        session_manager=FakeSessionManager(),
        next_iteration=19,
    )
    restored, next_iteration, err = parse_kernel_resume_snapshot(snapshot)

    assert err is None
    assert next_iteration == 19
    assert restored.turn_recovery.consecutive_failures == 1
    assert restored.turn_recovery.last_failure["provider_finish_reason"] == "length"


# ---------------------------------------------------------------------------
# Agent-authored ``hydrate_next`` — end-to-end regression
# ---------------------------------------------------------------------------

class _SaveThenInspectPack:
    """Iter 1: save workspace artifact + hydrate_next on its revision_ref.
    Iter 2: terminal.  Used to verify that the next turn sees the saved
    revision without an intermediate hydrate_artifact_refs LLM turn.
    """

    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="m-hn", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        if context.loop_memory.iterations == 1:
            return ActionPlan(
                action_type="save_workspace_artifact",
                action_inputs={},
                rationale="save and request next-turn inspection of the saved revision",
                hydrate_next=("@result.revision_ref",),
                hydrate_next_reason="inspect saved payload before publish",
            )
        return ActionPlan(
            complete_run=True,
            state_patch={"mission": {"work_universe_posture": "audited"}},
            rationale="inspected; done",
        )


class _SaveAndHydrateFakeSessionManager(ExecutionSessionManager):
    """Returns a save-style payload for ``save_workspace_artifact`` and
    a results/errors payload for ``hydrate_artifact_refs``."""

    def __init__(self) -> None:
        super().__init__()
        self.steps: list[ExecutionStepRequest] = []

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        from harness.execution.contracts import (
            ActionDispatchResult,
            SessionExecutionRecord,
        )
        self.steps.append(request)
        if request.action_id == "save_workspace_artifact":
            outputs = {"revision_ref": "transcript_edit:working:rev:0001"}
            artifact_refs: tuple[str, ...] = ("transcript_edit:working:rev:0001",)
        elif request.action_id == "hydrate_artifact_refs":
            outputs = {
                "results": [
                    {"ref_id": rid, "kind": "transcript_edit_draft", "payload": {"body": "saved"}}
                    for rid in (request.inputs.get("ref_ids") or [])
                ],
                "errors": [],
            }
            artifact_refs = ()
        else:
            outputs = {}
            artifact_refs = ()
        result = ActionDispatchResult(
            action_id=request.action_id, executed=True,
            outputs=outputs, artifact_refs=artifact_refs,
        )
        record = SessionExecutionRecord(
            session_id=request.session_id, run_id="r", request=request, result=result,
        )
        return ExecutionStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=ExecutionState.EXECUTED,
            dashboard=_dashboard(refs={"latest": f"artifact://{request.action_id}"}),
            record=record,
        )


def test_hydrate_next_dispatches_hydration_on_next_iteration_without_agent_call() -> None:
    """Regression: a save with ``hydrate_next: ['@result.revision_ref']`` causes
    the harness to dispatch ``hydrate_artifact_refs`` on the next iteration
    automatically — no extra agent turn is spent only hydrating."""
    sm = _SaveAndHydrateFakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=_SaveThenInspectPack(),
        session_manager=sm,
        session_id="s-hn",
        run_artifact_ref=None,
        request_id_prefix="req-hn",
        max_iterations=4,
    )
    assert result.terminal_class == "completed"
    # Two dispatched steps: the agent's save, then the harness-driven hydrate.
    action_ids = [s.action_id for s in sm.steps]
    assert action_ids == ["save_workspace_artifact", "hydrate_artifact_refs"]
    hydrate_step = sm.steps[1]
    assert hydrate_step.inputs == {"ref_ids": ["transcript_edit:working:rev:0001"]}
    # The pack only authored ONE choose_action plan that dispatched (iter 1);
    # iter 2 terminated before any second authored hydrate plan was needed.


class _BatchTransformThenCompletePack:
    """Iter 1: two transform batch items + hydrate_next batch placeholders.
    Iter 2: complete after harness hydrates both derived refs on next iteration.
    """

    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="m-batch", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
        )

    def evaluate_terminal(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> TerminalEvaluation | None:
        return None

    def choose_action(self, context: OrchestratorContext, projection: SharedStateProjection | None) -> ActionPlan:
        from harness.runtime.orchestration.action_batch import ActionBatchItem

        if context.loop_memory.iterations == 1:
            return ActionPlan(
                action_batch=(
                    ActionBatchItem("p1", "transform_artifact", {}),
                    ActionBatchItem("p2", "transform_artifact", {}),
                ),
                hydrate_next=(
                    "@batch.p1.result.derived_ref_id",
                    "@batch.p2.result.derived_ref_id",
                ),
                hydrate_next_reason="inspect both crops",
                rationale="batch two crops and request next-turn hydration",
            )
        return ActionPlan(
            complete_run=True,
            state_patch={"mission": {"work_universe_posture": "audited"}},
            rationale="inspected both hydrated crops; done",
        )


class _BatchTransformFakeSessionManager(_SaveAndHydrateFakeSessionManager):
    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        from harness.execution.contracts import (
            ActionDispatchResult,
            SessionExecutionRecord,
        )

        self.steps.append(request)
        if request.action_id == "hydrate_artifact_refs":
            outputs = {
                "results": [
                    {"ref_id": rid, "kind": "image", "payload": {}}
                    for rid in (request.inputs.get("ref_ids") or [])
                ],
                "errors": [],
            }
            artifact_refs: tuple[str, ...] = ()
        elif request.action_id == "transform_artifact":
            alias = request.idempotency_key.rsplit(":", 1)[-1]
            derived = f"image:derived:{alias}"
            outputs = {"derived_ref_id": derived}
            artifact_refs = (derived,)
        else:
            outputs = {}
            artifact_refs = ()

        result = ActionDispatchResult(
            action_id=request.action_id,
            executed=True,
            outputs=outputs,
            artifact_refs=artifact_refs,
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
            execution_state=ExecutionState.EXECUTED,
            dashboard=_dashboard(refs={"latest": "artifact://batch"}),
            record=record,
        )


def test_action_batch_hydrate_next_surfaces_both_refs_without_intermediate_hydrate_turn() -> None:
    """Regression: batch transforms + batch hydrate_next placeholders → next iteration
    dispatches hydrate_artifact_refs for both derived refs without an agent hydrate turn."""
    sm = _BatchTransformFakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=_BatchTransformThenCompletePack(),
        session_manager=sm,
        session_id="s-batch-hn",
        run_artifact_ref=None,
        request_id_prefix="req-batch-hn",
        max_iterations=4,
        opaque_run_context={
            "__tool_batch_policies": {
                "transform_artifact": {
                    "allowed": True,
                    "max_calls_per_batch": 4,
                    "side_effect_class": "derived_artifact",
                    "can_run_parallel": False,
                    "conflict_key": None,
                },
            },
        },
    )
    assert result.terminal_class == "completed"
    transform_steps = [s for s in sm.steps if s.action_id == "transform_artifact"]
    assert len(transform_steps) == 2
    hydrate_step = next(s for s in sm.steps if s.action_id == "hydrate_artifact_refs")
    assert set(hydrate_step.inputs.get("ref_ids") or []) == {
        "image:derived:p1",
        "image:derived:p2",
    }


def test_hydrate_next_with_no_request_leaves_orchestrator_unchanged() -> None:
    """A normal plan without hydrate_next must not trigger any extra dispatch."""
    sm = FakeSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=OneStepThenCompletePack(),
        session_manager=sm,
        session_id="s-hn-baseline",
        run_artifact_ref=None,
        request_id_prefix="req-hn-baseline",
        max_iterations=4,
    )
    assert result.terminal_class == "completed"
    # No extra ``hydrate_artifact_refs`` step beyond what the pack itself authored.
    assert all(s.action_id != "hydrate_artifact_refs" for s in sm.steps)
