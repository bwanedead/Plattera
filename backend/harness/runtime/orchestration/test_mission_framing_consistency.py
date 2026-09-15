"""Pre-dispatch mission-framing consistency tests (MAPDEP-BR-035)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from harness.execution.contracts import (
    ExecutionDashboard,
    ExecutionLatestRefs,
    ExecutionState,
    ExecutionStepRequest,
    ExecutionStepResult,
)
from harness.execution.session import ExecutionSessionManager
from harness.mission_state import (
    REASON_MISSION_FRAMING_REQUIRED,
    ResolutionItem,
    new_mission_state,
    new_resolution_state,
)
from harness.runtime.control import CONTROL_SCHEMA_VERSION, RunControlRequest
from harness.runtime.memory import LoopMemoryState
from harness.runtime.memory.resume_snapshot import parse_kernel_resume_snapshot
from harness.runtime.orchestration.action_sequence import ActionPlanAction
from harness.runtime.orchestration.contracts import (
    ActionPlan,
    OrchestratorContext,
    SharedStateProjection,
    TerminalEvaluation,
)
from harness.runtime.orchestration.lifecycle import OrchestrationLifecycle
from harness.runtime.orchestration.mission_framing_consistency import (
    REASON_MISSION_FRAMING_CONSISTENCY_REPAIR_BUDGET_EXHAUSTED,
    _next_same_conflict_streak,
    block_incomplete_mission_framing_before_dispatch,
    evaluate_plan_mission_framing_consistency,
    record_mission_framing_consistency_rejection,
)
from harness.runtime.orchestration.orchestrator import run_orchestration_kernel_loop
from harness.runtime.orchestration.state_patch_consistency import (
    MAX_IDENTICAL_TERMINAL_ROW_CONFLICT_REJECTIONS,
    evaluate_state_patch_terminal_row_consistency,
    record_terminal_row_consistency_rejection,
)
from harness.runtime.orchestration.trace_collector import KernelTraceCollector

_PACK_CJ = {"pack_continuity_stub": True}
_OBJECTIVE = "Finish the assigned mission"
_SUCCESS = {
    "condition_id": "sc-1",
    "title": "Named success condition",
    "status": "open",
}


def _dashboard() -> ExecutionDashboard:
    return ExecutionDashboard(
        latest_refs=ExecutionLatestRefs(refs={}),
        budgets_remaining={},
        last_refusal=None,
    )


class RecordingSessionManager(ExecutionSessionManager):
    def __init__(self) -> None:
        super().__init__()
        self.steps: list[ExecutionStepRequest] = []

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        self.steps.append(request)
        return ExecutionStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=ExecutionState.EXECUTED,
            dashboard=_dashboard(),
        )


class _InheritSyncMixin:
    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        prior_ms = context.loop_memory.continuity.mission_state
        prior_rs = context.loop_memory.continuity.resolution_state
        return SharedStateProjection(
            mission_state=prior_ms,
            resolution_state=prior_rs,
            latest_refs=dict(context.loop_memory.continuity.latest_refs),
            active_item_id=prior_rs.active_item_id,
        )


def _item(item_id: str) -> ResolutionItem:
    return ResolutionItem(
        item_id=item_id,
        title=f"Work item {item_id}",
        kind="claim",
        status="open",
    )


def _seed_memory(
    *,
    items: list[ResolutionItem] | None = None,
    objective: str | None = None,
    success_conditions: list[dict[str, Any]] | None = None,
    work_universe_posture: str = "initial",
    motion_posture: str = "inventory",
) -> LoopMemoryState:
    mem = LoopMemoryState()
    seeded = list(items or [])
    rs = new_resolution_state(
        items=seeded,
        active_item_id=seeded[0].item_id if seeded else None,
    )
    ms = new_mission_state(
        mission_id="m1",
        loop_family="orchestration_kernel",
        objective=objective,
        success_conditions=success_conditions,
        work_universe_posture=work_universe_posture,  # type: ignore[arg-type]
        motion_posture=motion_posture,  # type: ignore[arg-type]
        resolution_state=rs,
    )
    mem.continuity.mission_state = ms
    mem.continuity.resolution_state = rs
    return mem


def _tool_plan(*, state_patch: dict[str, Any] | None = None, complete_run: bool = False) -> ActionPlan:
    return ActionPlan(
        actions=(
            ActionPlanAction(
                action_type="hydrate_artifact_refs",
                action_inputs={"refs": ["artifact://example"]},
                alias="hydrate",
            ),
        ),
        state_patch=state_patch,
        complete_run=complete_run,
        continuity_journal_entry=_PACK_CJ,
    )


def _run_one_plan(mem: LoopMemoryState, plan: ActionPlan, *, max_iterations: int = 3):
    class _Pack(_InheritSyncMixin):
        def evaluate_terminal(self, context, projection):
            if context.loop_memory.iterations >= 2:
                return TerminalEvaluation(terminal_class="completed", reason_code="done")
            return None

        def choose_action(self, context, projection):
            if context.loop_memory.iterations == 1:
                return plan
            return ActionPlan(skip_execution=True, continuity_journal_entry=_PACK_CJ)

    sm = RecordingSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=_Pack(),
        session_manager=sm,
        session_id="sess-framing",
        run_artifact_ref=None,
        request_id_prefix="req-framing",
        opaque_run_context={},
        max_iterations=max_iterations,
        initial_loop_memory=mem,
    )
    return result, sm


def test_initial_inventory_empty_framing_allows_orientation() -> None:
    mem = _seed_memory(work_universe_posture="initial", motion_posture="inventory")
    result, sm = _run_one_plan(mem, _tool_plan())
    assert result.terminal_class == "completed"
    assert len(sm.steps) == 1


def test_partial_inventory_empty_framing_allows_orientation() -> None:
    mem = _seed_memory(work_universe_posture="partial", motion_posture="inventory")
    result, sm = _run_one_plan(mem, _tool_plan())
    assert result.terminal_class == "completed"
    assert len(sm.steps) == 1


def test_transition_to_believed_adequate_without_framing_refuses() -> None:
    mem = _seed_memory()
    result, sm = _run_one_plan(
        mem,
        ActionPlan(
            skip_execution=True,
            state_patch={"mission": {"work_universe_posture": "believed_adequate"}},
            continuity_journal_entry=_PACK_CJ,
        ),
    )
    assert sm.steps == []
    fb = result.runtime_state["state_patch_feedback"]
    assert fb["reason_code"] == REASON_MISSION_FRAMING_REQUIRED
    assert fb["missing_fields"] == ["objective", "success_conditions"]
    assert fb["effective_work_universe_posture"] == "believed_adequate"
    assert mem.continuity.mission_state.work_universe_posture == "initial"


def test_transition_to_resolution_while_partial_refuses() -> None:
    mem = _seed_memory(work_universe_posture="partial")
    result, sm = _run_one_plan(
        mem,
        ActionPlan(
            skip_execution=True,
            state_patch={"mission": {"motion_posture": "resolution"}},
            continuity_journal_entry=_PACK_CJ,
        ),
    )
    assert sm.steps == []
    fb = result.runtime_state["state_patch_feedback"]
    assert fb["reason_code"] == REASON_MISSION_FRAMING_REQUIRED
    assert fb["effective_motion_posture"] == "resolution"
    assert fb["effective_work_universe_posture"] == "partial"


def test_objective_without_success_condition_refuses() -> None:
    mem = _seed_memory()
    result, sm = _run_one_plan(
        mem,
        _tool_plan(
            state_patch={
                "mission": {
                    "objective": _OBJECTIVE,
                    "work_universe_posture": "believed_adequate",
                    "motion_posture": "resolution",
                }
            }
        ),
    )
    assert sm.steps == []
    fb = result.runtime_state["state_patch_feedback"]
    assert fb["missing_fields"] == ["success_conditions"]


def test_success_condition_without_objective_refuses() -> None:
    mem = _seed_memory()
    result, sm = _run_one_plan(
        mem,
        _tool_plan(
            state_patch={
                "mission": {
                    "success_conditions": [_SUCCESS],
                    "work_universe_posture": "believed_adequate",
                    "motion_posture": "resolution",
                }
            }
        ),
    )
    assert sm.steps == []
    fb = result.runtime_state["state_patch_feedback"]
    assert fb["missing_fields"] == ["objective"]


def test_same_plan_framing_and_action_dispatches_once() -> None:
    mem = _seed_memory()
    result, sm = _run_one_plan(
        mem,
        _tool_plan(
            state_patch={
                "mission": {
                    "objective": _OBJECTIVE,
                    "success_conditions": [_SUCCESS],
                    "work_universe_posture": "believed_adequate",
                    "motion_posture": "resolution",
                }
            }
        ),
    )
    assert result.terminal_class == "completed"
    assert len(sm.steps) == 1
    assert mem.continuity.mission_state.objective == _OBJECTIVE
    assert mem.continuity.mission_state.motion_posture == "resolution"


def test_existing_framing_is_inherited_from_sparse_patch() -> None:
    mem = _seed_memory(
        objective=_OBJECTIVE,
        success_conditions=[_SUCCESS],
        work_universe_posture="partial",
        motion_posture="inventory",
    )
    result, sm = _run_one_plan(
        mem,
        _tool_plan(
            state_patch={
                "mission": {
                    "work_universe_posture": "believed_adequate",
                    "motion_posture": "resolution",
                }
            }
        ),
    )
    assert result.terminal_class == "completed"
    assert len(sm.steps) == 1
    assert mem.continuity.mission_state.objective == _OBJECTIVE
    assert len(mem.continuity.mission_state.success_conditions) == 1


def test_invalid_resolution_state_self_heals_and_dispatches() -> None:
    mem = _seed_memory(
        work_universe_posture="believed_adequate",
        motion_posture="resolution",
    )
    result, sm = _run_one_plan(
        mem,
        _tool_plan(
            state_patch={
                "mission": {
                    "objective": _OBJECTIVE,
                    "success_conditions": [_SUCCESS],
                }
            }
        ),
    )
    assert result.terminal_class == "completed"
    assert len(sm.steps) == 1


def test_invalid_state_may_downgrade_to_inventory() -> None:
    mem = _seed_memory(
        work_universe_posture="believed_adequate",
        motion_posture="resolution",
    )
    result, sm = _run_one_plan(
        mem,
        ActionPlan(
            skip_execution=True,
            state_patch={
                "mission": {
                    "work_universe_posture": "partial",
                    "motion_posture": "inventory",
                }
            },
            continuity_journal_entry=_PACK_CJ,
        ),
    )
    assert result.terminal_class == "completed"
    assert sm.steps == []
    assert mem.continuity.mission_state.work_universe_posture == "partial"
    assert mem.continuity.mission_state.motion_posture == "inventory"
    assert mem.continuity.mission_state.objective is None


def test_rejected_plan_leaves_pre_dispatch_surfaces_unchanged() -> None:
    mem = _seed_memory()
    mem.continuity.latest_refs = {"working": "artifact://w"}
    mem.continuity.pending_result_deliveries = [{"delivery_id": "d1"}]
    mem.hitl.answered_hitl_responses = [
        {"prompt_id": "hitl-pending-1", "feedback": {"answer": "keep"}}
    ]
    mem.continuity.user_message_ledger = [
        {
            "message_id": "user-msg-1",
            "created_at_epoch_seconds": 1.0,
            "source": "operator",
            "text": "note",
            "metadata": {},
            "status": "pending",
            "received_at_iteration": 0,
            "consumed_iteration": None,
            "defer_reason": None,
            "deferred_iteration": None,
        }
    ]
    before = {
        "pins": copy.deepcopy(mem.continuity.pinned_refs),
        "answered": copy.deepcopy(mem.hitl.answered_hitl_responses),
        "ledger": copy.deepcopy(mem.continuity.user_message_ledger),
        "ms": mem.continuity.mission_state.model_copy(deep=True),
        "rs": mem.continuity.resolution_state.model_copy(deep=True),
        "refs": copy.deepcopy(mem.continuity.latest_refs),
        "deliveries": copy.deepcopy(mem.continuity.pending_result_deliveries),
        "single": mem.continuity.single_action_turn_count,
        "multi": mem.continuity.multi_action_turn_count,
    }
    result, sm = _run_one_plan(
        mem,
        ActionPlan(
            actions=(
                ActionPlanAction(
                    action_type="hydrate_artifact_refs",
                    action_inputs={"refs": ["artifact://example"]},
                    alias="hydrate",
                ),
            ),
            state_patch={"mission": {"work_universe_posture": "believed_adequate"}},
            pin_refs=("artifact://should-not-pin",),
            hitl_consumed_prompt_ids=("hitl-pending-1",),
            user_message_consumed_ids=("user-msg-1",),
            continuity_journal_entry=_PACK_CJ,
        ),
    )
    assert result.runtime_state["state_patch_feedback"]["reason_code"] == REASON_MISSION_FRAMING_REQUIRED
    assert sm.steps == []
    assert mem.continuity.pinned_refs == before["pins"]
    assert mem.hitl.answered_hitl_responses == before["answered"]
    assert mem.continuity.user_message_ledger == before["ledger"]
    assert mem.continuity.mission_state == before["ms"]
    assert mem.continuity.resolution_state == before["rs"]
    assert mem.continuity.latest_refs == before["refs"]
    assert mem.continuity.pending_result_deliveries == before["deliveries"]
    assert mem.continuity.single_action_turn_count == before["single"]
    assert mem.continuity.multi_action_turn_count == before["multi"]


def test_repeated_identical_rejection_is_bounded() -> None:
    assert MAX_IDENTICAL_TERMINAL_ROW_CONFLICT_REJECTIONS == 4

    class _RepeatPack(_InheritSyncMixin):
        def evaluate_terminal(self, context, projection):
            return None

        def choose_action(self, context, projection):
            return _tool_plan(
                state_patch={"mission": {"work_universe_posture": "believed_adequate"}}
            )

    mem = _seed_memory()
    sm = RecordingSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=_RepeatPack(),
        session_manager=sm,
        session_id="sess-framing-budget",
        run_artifact_ref=None,
        request_id_prefix="req-framing-budget",
        opaque_run_context={},
        max_iterations=8,
        initial_loop_memory=mem,
    )
    assert result.terminal_class == "failed"
    assert result.reason_code == REASON_MISSION_FRAMING_CONSISTENCY_REPAIR_BUDGET_EXHAUSTED
    assert sm.steps == []
    fb = result.runtime_state["state_patch_feedback"]
    assert fb["same_conflict_streak"] == 4
    assert fb["reason_code"] == REASON_MISSION_FRAMING_REQUIRED


def test_changed_missing_field_identity_resets_streak() -> None:
    class _ShiftPack(_InheritSyncMixin):
        def evaluate_terminal(self, context, projection):
            if context.loop_memory.iterations >= 3:
                return TerminalEvaluation(terminal_class="completed", reason_code="done")
            return None

        def choose_action(self, context, projection):
            if context.loop_memory.iterations == 1:
                return _tool_plan(
                    state_patch={"mission": {"work_universe_posture": "believed_adequate"}}
                )
            return _tool_plan(
                state_patch={
                    "mission": {
                        "objective": _OBJECTIVE,
                        "work_universe_posture": "believed_adequate",
                    }
                }
            )

    mem = _seed_memory()
    sm = RecordingSessionManager()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=_ShiftPack(),
        session_manager=sm,
        session_id="sess-framing-reset",
        run_artifact_ref=None,
        request_id_prefix="req-framing-reset",
        opaque_run_context={},
        max_iterations=4,
        initial_loop_memory=mem,
    )
    assert result.terminal_class == "completed"
    fb = result.runtime_state["state_patch_feedback"]
    assert fb["reason_code"] == REASON_MISSION_FRAMING_REQUIRED
    assert fb["missing_fields"] == ["success_conditions"]
    assert fb["same_conflict_streak"] == 1
    assert sm.steps == []


def test_resume_parity_for_repair_and_exhaustion() -> None:
    mem = _seed_memory(
        work_universe_posture="believed_adequate",
        motion_posture="resolution",
    )
    plan = _tool_plan()
    tracer = KernelTraceCollector(session_id="sess-framing-resume", request_id="req-framing-resume")
    snapshots: list[dict[str, Any]] = []

    def _writer(snap: dict[str, Any]) -> None:
        snapshots.append(dict(snap))

    lifecycle = OrchestrationLifecycle(resume_checkpoint_writer=_writer)
    blocked = block_incomplete_mission_framing_before_dispatch(
        loop_memory=mem,
        action_plan=plan,
        tracer=tracer,
        iteration=1,
        lifecycle=lifecycle,
        session_manager=RecordingSessionManager(),
        session_id="sess-framing-resume",
        turn_completion_observer=None,
    )
    assert blocked is not None
    assert blocked.repair_budget_exhausted is False
    fb1 = copy.deepcopy(mem.continuity.state_patch_feedback)
    restored, _next_it, err = parse_kernel_resume_snapshot(snapshots[0])
    assert err is None
    result2 = evaluate_plan_mission_framing_consistency(
        mission_state=restored.continuity.mission_state,
        resolution_state=restored.continuity.resolution_state,
        action_plan=plan,
    )
    assert result2 is not None
    assert result2.reason_code == fb1["reason_code"]
    assert result2.as_dict()["missing_fields"] == fb1["missing_fields"]

    repair = _tool_plan(
        state_patch={
            "mission": {
                "objective": _OBJECTIVE,
                "success_conditions": [_SUCCESS],
            }
        }
    )
    repaired = evaluate_plan_mission_framing_consistency(
        mission_state=restored.continuity.mission_state,
        resolution_state=restored.continuity.resolution_state,
        action_plan=repair,
    )
    assert repaired is None

    mem.continuity.state_patch_feedback = {
        "reason_code": REASON_MISSION_FRAMING_REQUIRED,
        "conflict_identity": result2.framing_identity(),
        "same_conflict_streak": 3,
        "outcome": "rejected",
    }
    blocked_last = block_incomplete_mission_framing_before_dispatch(
        loop_memory=mem,
        action_plan=plan,
        tracer=tracer,
        iteration=4,
        lifecycle=lifecycle,
        session_manager=RecordingSessionManager(),
        session_id="sess-framing-resume",
        turn_completion_observer=None,
    )
    assert blocked_last is not None
    assert blocked_last.repair_budget_exhausted is True


def test_hitl_and_operator_controls_remain_available() -> None:
    mem = _seed_memory(
        work_universe_posture="believed_adequate",
        motion_posture="resolution",
    )
    hitl_plan = ActionPlan(
        wait_for_human=True,
        hitl_request={"prompt_id": "hitl-1", "question": "Need a human decision."},
        continuity_journal_entry=_PACK_CJ,
    )
    result = evaluate_plan_mission_framing_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        action_plan=hitl_plan,
    )
    assert result is None

    class _StopPack(_InheritSyncMixin):
        def evaluate_terminal(self, context, projection):
            return None

        def choose_action(self, context, projection):
            return _tool_plan()

    reader_calls = {"n": 0}

    def _reader() -> RunControlRequest | None:
        reader_calls["n"] += 1
        if reader_calls["n"] >= 2:
            return RunControlRequest(
                schema_version=CONTROL_SCHEMA_VERSION,
                request_id="req-stop-1",
                command="stop",
                requested_at_epoch_seconds=1.0,
                reason="operator stop",
                requested_by="cli",
            )
        return None

    sm = RecordingSessionManager()
    stopped = run_orchestration_kernel_loop(
        orchestration_adapter=_StopPack(),
        session_manager=sm,
        session_id="sess-framing-stop",
        run_artifact_ref=None,
        request_id_prefix="req-framing-stop",
        opaque_run_context={},
        max_iterations=4,
        initial_loop_memory=mem,
        lifecycle=OrchestrationLifecycle(run_control_reader=_reader),
    )
    assert stopped.terminal_class == "stopped"
    assert stopped.reason_code == "stopped_by_operator"
    assert sm.steps == []


def test_gate_modules_have_no_domain_imports() -> None:
    roots = (
        Path(__file__).resolve().parents[2] / "mission_state" / "mission_framing_consistency.py",
        Path(__file__).resolve().with_name("mission_framing_consistency.py"),
    )
    for path in roots:
        text = path.read_text(encoding="utf-8").lower()
        for banned in ("transcript_edit", "deed_to_ir", "domains.mapping", "range 7", "curve station"):
            assert banned not in text, f"{path.name} contains {banned!r}"


def test_production_shaped_three_items_without_framing_refuses() -> None:
    mem = _seed_memory(
        items=[_item("item-1"), _item("item-2"), _item("item-3")],
        work_universe_posture="initial",
        motion_posture="inventory",
    )
    result, sm = _run_one_plan(
        mem,
        _tool_plan(
            state_patch={
                "mission": {
                    "work_universe_posture": "believed_adequate",
                    "motion_posture": "resolution",
                }
            }
        ),
    )
    assert sm.steps == []
    fb = result.runtime_state["state_patch_feedback"]
    assert list(fb.keys())  # JSON-native mapping
    assert fb["reason_code"] == REASON_MISSION_FRAMING_REQUIRED
    assert fb["missing_fields"] == ["objective", "success_conditions"]
    assert fb["effective_work_universe_posture"] == "believed_adequate"
    assert fb["effective_motion_posture"] == "resolution"
    assert mem.continuity.mission_state.work_universe_posture == "initial"
    assert mem.continuity.resolution_state.items[0].status == "open"


def test_framing_rejection_omits_prior_terminal_row_repair_bundle() -> None:
    mem = _seed_memory(
        items=[
            ResolutionItem(
                item_id="item-1",
                title="Work item item-1",
                kind="claim",
                status="open",
                next_needed_step="verify this value",
            )
        ]
    )
    mem.continuity.state_patch_feedback = {
        "pending_hitl_integration_prompt_ids": ["hitl-prior"],
        "semantic_repair_debt": ["determined_value"],
    }
    close_patch = {"resolution": {"items": [{"item_id": "item-1", "status": "closed"}]}}
    terminal = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=close_patch,
    )
    assert terminal is not None
    record_terminal_row_consistency_rejection(
        loop_memory=mem,
        tracer=KernelTraceCollector(session_id="sess-bundle", request_id="req-bundle"),
        iteration=1,
        result=terminal,
        state_patch=close_patch,
    )
    prior_fb = mem.continuity.state_patch_feedback
    assert "state_patch_repair_bundle" in prior_fb
    assert prior_fb["pending_hitl_integration_prompt_ids"] == ["hitl-prior"]
    assert prior_fb["semantic_repair_debt"] == ["determined_value"]

    framing_plan = ActionPlan(
        skip_execution=True,
        state_patch={"mission": {"work_universe_posture": "believed_adequate"}},
        continuity_journal_entry=_PACK_CJ,
    )
    blocked = block_incomplete_mission_framing_before_dispatch(
        loop_memory=mem,
        action_plan=framing_plan,
        tracer=KernelTraceCollector(session_id="sess-bundle", request_id="req-bundle-2"),
        iteration=2,
        lifecycle=OrchestrationLifecycle(),
        session_manager=RecordingSessionManager(),
        session_id="sess-bundle",
        turn_completion_observer=None,
    )
    assert blocked is not None
    fb = mem.continuity.state_patch_feedback
    assert fb["reason_code"] == REASON_MISSION_FRAMING_REQUIRED
    assert "state_patch_repair_bundle" not in fb
    assert fb["pending_hitl_integration_prompt_ids"] == ["hitl-prior"]
    assert fb["semantic_repair_debt"] == ["determined_value"]


class _LooksLikeMarker:
    def __init__(self, text: str) -> None:
        self._text = text

    def __str__(self) -> str:
        return self._text


def test_framing_streak_identity_requires_exact_string_equality() -> None:
    identity = "objective,success_conditions|believed_adequate|inventory"
    exact_previous = {
        "reason_code": REASON_MISSION_FRAMING_REQUIRED,
        "conflict_identity": identity,
        "same_conflict_streak": 2,
    }
    assert _next_same_conflict_streak(exact_previous, framing_identity=identity) == 3

    malformed = (
        {"reason_code": f" {REASON_MISSION_FRAMING_REQUIRED}", "conflict_identity": identity},
        {"reason_code": f"{REASON_MISSION_FRAMING_REQUIRED} ", "conflict_identity": identity},
        {"reason_code": REASON_MISSION_FRAMING_REQUIRED.upper(), "conflict_identity": identity},
        {"reason_code": True, "conflict_identity": identity},
        {"reason_code": {"code": REASON_MISSION_FRAMING_REQUIRED}, "conflict_identity": identity},
        {
            "reason_code": _LooksLikeMarker(REASON_MISSION_FRAMING_REQUIRED),
            "conflict_identity": identity,
        },
        {
            "reason_code": REASON_MISSION_FRAMING_REQUIRED,
            "conflict_identity": f" {identity}",
        },
        {
            "reason_code": REASON_MISSION_FRAMING_REQUIRED,
            "conflict_identity": identity.upper(),
        },
        {"reason_code": REASON_MISSION_FRAMING_REQUIRED, "conflict_identity": True},
        {
            "reason_code": REASON_MISSION_FRAMING_REQUIRED,
            "conflict_identity": {"id": identity},
        },
        {
            "reason_code": REASON_MISSION_FRAMING_REQUIRED,
            "conflict_identity": _LooksLikeMarker(identity),
        },
    )
    for previous in malformed:
        previous = {**previous, "same_conflict_streak": 3}
        assert _next_same_conflict_streak(previous, framing_identity=identity) == 1


def test_malformed_prior_streak_identity_resets_on_production_record_path() -> None:
    mem = _seed_memory()
    plan = ActionPlan(
        skip_execution=True,
        state_patch={"mission": {"work_universe_posture": "believed_adequate"}},
        continuity_journal_entry=_PACK_CJ,
    )
    result = evaluate_plan_mission_framing_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        action_plan=plan,
    )
    assert result is not None
    identity = result.framing_identity()
    mem.continuity.state_patch_feedback = {
        "reason_code": _LooksLikeMarker(REASON_MISSION_FRAMING_REQUIRED),
        "conflict_identity": _LooksLikeMarker(identity),
        "same_conflict_streak": 3,
        "outcome": "rejected",
    }
    streak = record_mission_framing_consistency_rejection(
        loop_memory=mem,
        tracer=None,
        iteration=2,
        result=result,
    )
    assert streak == 1
    assert mem.continuity.state_patch_feedback["same_conflict_streak"] == 1
