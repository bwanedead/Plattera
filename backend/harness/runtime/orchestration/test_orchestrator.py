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
from harness.runtime.memory.resume_snapshot import parse_kernel_resume_snapshot
from harness.runtime.orchestration.llm_turn_adapter import LlmTurnOrchestrationAdapter
from harness.runtime.orchestration.orchestrator import run_orchestration_kernel_loop

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
                            {"item_id": "work-1", "status": "closed"},
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
    patch_events = [e for e in result.trace_events if e.get("event_kind") == "state_patch_outcome"]
    assert patch_events
    assert patch_events[-1]["payload"].get("detail", {}).get("skipped_resolution_rows") is True


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
            "rationale": None,
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
            assert context.loop_memory.continuity.continuity_journal_entries[0]["author_payload"].get("mark") == "t1"
            assert context.loop_memory.continuity.operator_progress_message == "hello op"
            return ActionPlan(
                complete_run=True,
                idempotency_key="ik2",
                rationale="done",
                continuity_journal_entry={"close_out": True},
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


# ---------------------------------------------------------------------------
# image_evidence propagated through on_turn_completed
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
        return ActionPlan(complete_run=True, continuity_journal_entry={"done": True})

    def on_turn_completed(self, turn_index: int, **kwargs: Any) -> None:
        self._last_turn_result = {"turn_index": turn_index, **kwargs}


def test_image_evidence_in_tool_result_raw_via_on_turn_completed() -> None:
    """image_evidence from the execution result must appear in on_turn_completed tool_result_raw."""
    pack = _OneStepImagePack()
    sm = _ImageEvidenceSessionManager()
    sm.start_session(
        __import__("harness.execution.contracts", fromlist=["ExecutionSessionStartRequest"])
        .ExecutionSessionStartRequest(run_id="r-img", session_id="sess-img")
    )
    run_orchestration_kernel_loop(
        orchestration_adapter=pack,
        session_manager=sm,
        session_id="sess-img",
        run_artifact_ref=None,
        request_id_prefix="req-img",
        opaque_run_context={},
        max_iterations=3,
    )
    # The image step is turn 1; _last_turn_result should be from the complete_run turn.
    # For the tool execution turn, we need to check via a recorder.
    # Re-run with a recording adapter that captures all on_turn_completed calls.
    results: list[dict[str, Any]] = []

    class _RecordingPack(_OneStepImagePack):
        def on_turn_completed(self, turn_index: int, **kwargs: Any) -> None:  # type: ignore[override]
            results.append({"turn_index": turn_index, **kwargs})

    pack2 = _RecordingPack()
    sm2 = _ImageEvidenceSessionManager()
    sm2.start_session(
        __import__("harness.execution.contracts", fromlist=["ExecutionSessionStartRequest"])
        .ExecutionSessionStartRequest(run_id="r-img2", session_id="sess-img2")
    )
    run_orchestration_kernel_loop(
        orchestration_adapter=pack2,
        session_manager=sm2,
        session_id="sess-img2",
        run_artifact_ref=None,
        request_id_prefix="req-img2",
        opaque_run_context={},
        max_iterations=3,
    )

    # Turn 1 is the tool execution turn.
    tool_turn = next(r for r in results if r["turn_index"] == 1)
    tool_result = tool_turn["tool_result_raw"]
    assert tool_result is not None
    evidence = tool_result["image_evidence"]
    assert len(evidence) == 2
    assert evidence[0]["ref_id"] == "image:assoc:tx1:original"
    assert evidence[1]["ref_id"] == "image:assoc:tx1:processed"


def test_image_evidence_empty_list_when_no_evidence() -> None:
    """When image_evidence is empty, tool_result_raw.image_evidence should be []."""
    results: list[dict[str, Any]] = []

    class _NoEvidencePack(OneStepThenCompletePack):
        def on_turn_completed(self, turn_index: int, **kwargs: Any) -> None:  # type: ignore[override]
            results.append({"turn_index": turn_index, **kwargs})

    sm = FakeSessionManager()
    sm.start_session(
        __import__("harness.execution.contracts", fromlist=["ExecutionSessionStartRequest"])
        .ExecutionSessionStartRequest(run_id="r-ne", session_id="sess-ne")
    )
    run_orchestration_kernel_loop(
        orchestration_adapter=_NoEvidencePack(),
        session_manager=sm,
        session_id="sess-ne",
        run_artifact_ref=None,
        request_id_prefix="req-ne",
        opaque_run_context={},
        max_iterations=3,
    )

    tool_turn = next((r for r in results if r.get("tool_request") is not None), None)
    assert tool_turn is not None
    assert tool_turn["tool_result_raw"]["image_evidence"] == []
