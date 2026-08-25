"""Pre-dispatch terminal-row consistency gate tests (MAPDEP-BR-022)."""

from __future__ import annotations

import copy
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
    MAX_TERMINAL_ROW_CONFLICTS,
    REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
    ResolutionCoveredUnit,
    ResolutionItem,
    new_mission_state,
    new_resolution_state,
)
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
from harness.runtime.orchestration.orchestrator import run_orchestration_kernel_loop
from harness.runtime.orchestration.state_patch_apply import apply_state_patch
from harness.runtime.orchestration.state_patch_consistency import (
    block_contradictory_closed_resolution_before_dispatch,
    evaluate_state_patch_terminal_row_consistency,
    record_terminal_row_consistency_rejection,
)
from harness.runtime.orchestration.trace_collector import KernelTraceCollector

_PACK_CJ = {"pack_continuity_stub": True}


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
        self.write_side_effects = 0

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        self.steps.append(request)
        if request.action_id == "save_workspace_artifact":
            self.write_side_effects += 1
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


def _seed_item(
    *,
    item_id: str = "item-1",
    status: str = "open",
    next_needed_step: str | None = "verify this value",
    determination: str | None = None,
    requires_hitl: bool = False,
    no_further_progress: bool = False,
    covered_units: list[ResolutionCoveredUnit] | None = None,
) -> ResolutionItem:
    return ResolutionItem(
        item_id=item_id,
        title=f"Title {item_id}",
        kind="claim",
        status=status,
        determination=determination,
        next_needed_step=next_needed_step,
        requires_hitl=requires_hitl,
        no_further_progress=no_further_progress,
        covered_units=list(covered_units or []),
    )


def _seed_memory(items: list[ResolutionItem]) -> LoopMemoryState:
    mem = LoopMemoryState()
    rs = new_resolution_state(items=items, active_item_id=items[0].item_id if items else None)
    ms = new_mission_state(
        mission_id="m1",
        loop_family="orchestration_kernel",
        objective="t",
        resolution_state=rs,
    )
    mem.continuity.mission_state = ms
    mem.continuity.resolution_state = rs
    return mem


def _close_item_patch(item_id: str = "item-1", **fields: Any) -> dict[str, Any]:
    row = {"item_id": item_id, **fields}
    return {"resolution": {"items": [row]}}


def test_sparse_item_close_with_stale_next_step_is_blocked() -> None:
    mem = _seed_memory([_seed_item()])
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=_close_item_patch(status="closed"),
    )
    assert result is not None
    assert result.reason_code == REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK
    assert result.conflicts[0].coordinate == "resolution.items[item-1]"
    assert result.conflicts[0].fields == ("next_needed_step",)


def test_sparse_covered_unit_close_with_stale_next_step_is_blocked() -> None:
    mem = _seed_memory(
        [
            _seed_item(
                next_needed_step=None,
                covered_units=[
                    ResolutionCoveredUnit(
                        unit_id="unit-2",
                        title="Unit",
                        status="open",
                        next_needed_step="verify unit",
                    )
                ],
            )
        ]
    )
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "item-1",
                        "covered_units": [{"unit_id": "unit-2", "status": "closed"}],
                    }
                ]
            }
        },
    )
    assert result is not None
    assert result.conflicts[0].coordinate == (
        "resolution.items[item-1].covered_units[unit-2]"
    )


def test_determination_earned_with_retained_next_step_is_blocked() -> None:
    mem = _seed_memory([_seed_item(status="open", next_needed_step="still needed")])
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=_close_item_patch(determination="earned"),
    )
    assert result is not None
    assert "next_needed_step" in result.conflicts[0].fields


def test_closed_item_requires_hitl_is_blocked() -> None:
    mem = _seed_memory([_seed_item(next_needed_step=None, requires_hitl=True)])
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=_close_item_patch(status="closed"),
    )
    assert result is not None
    assert result.conflicts[0].fields == ("requires_hitl",)


def test_closed_unit_requires_hitl_is_blocked() -> None:
    mem = _seed_memory(
        [
            _seed_item(
                next_needed_step=None,
                covered_units=[
                    ResolutionCoveredUnit(
                        unit_id="unit-2",
                        title="Unit",
                        status="open",
                        requires_hitl=True,
                    )
                ],
            )
        ]
    )
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "item-1",
                        "covered_units": [{"unit_id": "unit-2", "status": "earned"}],
                    }
                ]
            }
        },
    )
    assert result is not None
    assert result.conflicts[0].fields == ("requires_hitl",)


def test_closed_item_and_unit_no_further_progress_are_blocked() -> None:
    mem = _seed_memory(
        [
            _seed_item(
                next_needed_step=None,
                no_further_progress=True,
                covered_units=[
                    ResolutionCoveredUnit(
                        unit_id="unit-2",
                        title="Unit",
                        status="open",
                        no_further_progress=True,
                    )
                ],
            )
        ]
    )
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "item-1",
                        "status": "closed",
                        "covered_units": [{"unit_id": "unit-2", "status": "closed"}],
                    }
                ]
            }
        },
    )
    assert result is not None
    coords = {c.coordinate for c in result.conflicts}
    assert "resolution.items[item-1]" in coords
    assert "resolution.items[item-1].covered_units[unit-2]" in coords


def test_close_and_clear_stale_fields_is_accepted() -> None:
    mem = _seed_memory([_seed_item()])
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=_close_item_patch(
            status="closed",
            next_needed_step=None,
            requires_hitl=False,
            no_further_progress=False,
        ),
    )
    assert result is None


def test_reopen_while_retaining_next_step_is_accepted() -> None:
    mem = _seed_memory([_seed_item(status="closed", next_needed_step="verify")])
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=_close_item_patch(status="open"),
    )
    assert result is None


def test_open_in_review_blocked_may_retain_next_step() -> None:
    for status in ("open", "in_review", "blocked", "no_further_progress"):
        mem = _seed_memory([_seed_item(status="unassessed", next_needed_step="x")])
        result = evaluate_state_patch_terminal_row_consistency(
            mission_state=mem.continuity.mission_state,
            resolution_state=mem.continuity.resolution_state,
            state_patch=_close_item_patch(status=status),
        )
        assert result is None, status


def test_untouched_legacy_contradiction_does_not_block_other_coordinate() -> None:
    mem = _seed_memory(
        [
            _seed_item(
                item_id="legacy",
                status="closed",
                next_needed_step="stale legacy",
            ),
            _seed_item(item_id="target", status="open", next_needed_step="ok"),
        ]
    )
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=_close_item_patch("target", status="in_review"),
    )
    assert result is None


def test_plans_without_state_patch_remain_unchanged() -> None:
    mem = _seed_memory([_seed_item(status="closed", next_needed_step="stale")])
    assert (
        evaluate_state_patch_terminal_row_consistency(
            mission_state=mem.continuity.mission_state,
            resolution_state=mem.continuity.resolution_state,
            state_patch=None,
        )
        is None
    )


def test_rejection_leaves_mission_resolution_refs_and_deliveries_unchanged() -> None:
    mem = _seed_memory([_seed_item()])
    mem.continuity.latest_refs = {"working": "artifact://w"}
    mem.continuity.pending_result_deliveries = [{"delivery_id": "d1"}]
    before_ms = mem.continuity.mission_state.model_copy(deep=True)
    before_rs = mem.continuity.resolution_state.model_copy(deep=True)
    before_refs = copy.deepcopy(mem.continuity.latest_refs)
    before_deliveries = copy.deepcopy(mem.continuity.pending_result_deliveries)

    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=_close_item_patch(status="closed"),
    )
    assert result is not None
    record_terminal_row_consistency_rejection(
        loop_memory=mem,
        tracer=KernelTraceCollector(session_id="s", request_id="r"),
        iteration=1,
        result=result,
    )

    assert mem.continuity.mission_state == before_ms
    assert mem.continuity.resolution_state == before_rs
    assert mem.continuity.latest_refs == before_refs
    assert mem.continuity.pending_result_deliveries == before_deliveries
    fb = mem.continuity.state_patch_feedback
    assert fb["outcome"] == "rejected"
    assert fb["reason_code"] == REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK
    assert fb["conflicts"][0]["coordinate"] == "resolution.items[item-1]"
    assert "genuinely earned" in fb["repair_hint"]
    assert "reopen/reclassify" in fb["repair_hint"]


def test_feedback_bounds_beyond_32_conflicts() -> None:
    items = [
        _seed_item(item_id=f"item-{i}", status="open", next_needed_step="stale")
        for i in range(MAX_TERMINAL_ROW_CONFLICTS + 3)
    ]
    mem = _seed_memory(items)
    patch = {
        "resolution": {
            "items": [{"item_id": f"item-{i}", "status": "closed"} for i in range(len(items))]
        }
    }
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=patch,
    )
    assert result is not None
    assert len(result.conflicts) == MAX_TERMINAL_ROW_CONFLICTS
    assert result.conflicts_omitted_count == 3
    payload = result.as_dict()
    assert "transcript" not in str(payload).lower()


class ConflictingSaveThenCorrectPack(_InheritSyncMixin):
    """Turn 1: contradictory close + save. Turn 2: corrected close + save. Turn 3: done."""

    def __init__(self) -> None:
        self.plans: list[ActionPlan] = []

    def evaluate_terminal(
        self, context: OrchestratorContext, projection: SharedStateProjection | None
    ) -> TerminalEvaluation | None:
        if context.loop_memory.iterations >= 3:
            return TerminalEvaluation(terminal_class="completed", reason_code="done")
        return None

    def choose_action(
        self, context: OrchestratorContext, projection: SharedStateProjection | None
    ) -> ActionPlan:
        it = context.loop_memory.iterations
        if it == 1:
            plan = ActionPlan(
                actions=(
                    ActionPlanAction(
                        action_type="save_workspace_artifact",
                        action_inputs={"draft_payload": {"x": 1}},
                        alias="save",
                    ),
                ),
                state_patch=_close_item_patch(status="closed"),
                continuity_journal_entry=_PACK_CJ,
            )
        elif it == 2:
            plan = ActionPlan(
                actions=(
                    ActionPlanAction(
                        action_type="save_workspace_artifact",
                        action_inputs={"draft_payload": {"x": 2}},
                        alias="save2",
                    ),
                ),
                state_patch=_close_item_patch(
                    status="closed",
                    next_needed_step=None,
                    requires_hitl=False,
                    no_further_progress=False,
                ),
                continuity_journal_entry=_PACK_CJ,
            )
        else:
            plan = ActionPlan(
                skip_execution=True,
                continuity_journal_entry=_PACK_CJ,
            )
        self.plans.append(plan)
        return plan


def test_conflicting_save_is_not_dispatched_and_corrected_turn_dispatches() -> None:
    sm = RecordingSessionManager()
    mem = _seed_memory([_seed_item()])
    pack = ConflictingSaveThenCorrectPack()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=pack,
        session_manager=sm,
        session_id="sess-br022",
        run_artifact_ref=None,
        request_id_prefix="req-br022",
        opaque_run_context={},
        max_iterations=6,
        initial_loop_memory=mem,
    )
    assert result.terminal_class == "completed"
    assert sm.write_side_effects == 1
    assert len(sm.steps) == 1
    assert sm.steps[0].action_id == "save_workspace_artifact"
    assert sm.steps[0].inputs.get("draft_payload") == {"x": 2}
    rs = result.runtime_state["resolution_state"]
    item = next(i for i in rs.items if i.item_id == "item-1")
    assert item.status == "closed"
    assert item.next_needed_step is None
    fb_events = [
        e for e in result.trace_events if e.get("event_kind") == "state_patch_outcome"
    ]
    assert any(
        e.get("reason_code") == REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK
        for e in fb_events
    )


def test_checkpoint_resume_parity_for_pre_dispatch_verdict() -> None:
    mem = _seed_memory([_seed_item()])
    plan = ActionPlan(
        actions=(
            ActionPlanAction(
                action_type="save_workspace_artifact",
                action_inputs={"draft_payload": {"x": 1}},
                alias="save",
            ),
        ),
        state_patch=_close_item_patch(status="closed"),
    )
    tracer = KernelTraceCollector(session_id="sess-resume", request_id="req-resume")
    snapshots: list[dict[str, Any]] = []

    def _writer(snap: dict[str, Any]) -> None:
        snapshots.append(dict(snap))

    lifecycle = OrchestrationLifecycle(resume_checkpoint_writer=_writer)
    blocked = block_contradictory_closed_resolution_before_dispatch(
        loop_memory=mem,
        action_plan=plan,
        tracer=tracer,
        iteration=1,
        lifecycle=lifecycle,
        session_manager=RecordingSessionManager(),
        session_id="sess-resume",
        turn_completion_observer=None,
    )
    assert blocked is True
    assert snapshots
    fb1 = copy.deepcopy(mem.continuity.state_patch_feedback)

    restored, _next_it, err = parse_kernel_resume_snapshot(snapshots[0])
    assert err is None
    # Re-evaluate the same plan against restored continuity state.
    result2 = evaluate_state_patch_terminal_row_consistency(
        mission_state=restored.continuity.mission_state,
        resolution_state=restored.continuity.resolution_state,
        state_patch=plan.state_patch,
    )
    assert result2 is not None
    assert result2.reason_code == fb1["reason_code"]
    assert result2.as_dict()["conflicts"] == fb1["conflicts"]
    assert result2.conflicts_omitted_count == fb1["conflicts_omitted_count"]


def test_accepted_patch_still_merges_with_live_apply_semantics() -> None:
    mem = _seed_memory([_seed_item(next_needed_step="verify")])
    patch = _close_item_patch(
        status="closed",
        next_needed_step=None,
        requires_hitl=False,
        no_further_progress=False,
    )
    assert (
        evaluate_state_patch_terminal_row_consistency(
            mission_state=mem.continuity.mission_state,
            resolution_state=mem.continuity.resolution_state,
            state_patch=patch,
        )
        is None
    )
    _ms, rs, _ = apply_state_patch(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=patch,
    )
    assert rs.items[0].status == "closed"
    assert rs.items[0].next_needed_step is None


def test_identity_only_covered_unit_row_does_not_activate_legacy_contradiction() -> None:
    mem = _seed_memory(
        [
            _seed_item(
                next_needed_step=None,
                covered_units=[
                    ResolutionCoveredUnit(
                        unit_id="unit-2",
                        title="Unit",
                        status="closed",
                        next_needed_step="stale unit work",
                    )
                ],
            )
        ]
    )
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "item-1",
                        "covered_units": [{"unit_id": "unit-2"}],
                    }
                ]
            }
        },
    )
    assert result is None


def test_covered_unit_row_with_changed_field_still_validates_effective_state() -> None:
    mem = _seed_memory(
        [
            _seed_item(
                next_needed_step=None,
                covered_units=[
                    ResolutionCoveredUnit(
                        unit_id="unit-2",
                        title="Unit",
                        status="open",
                        next_needed_step="verify unit",
                    )
                ],
            )
        ]
    )
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "item-1",
                        "covered_units": [{"unit_id": "unit-2", "status": "closed"}],
                    }
                ]
            }
        },
    )
    assert result is not None
    assert result.conflicts[0].coordinate == (
        "resolution.items[item-1].covered_units[unit-2]"
    )
    assert result.conflicts[0].fields == ("next_needed_step",)


class InventoryAndContradictionPack(_InheritSyncMixin):
    """One turn: contradictory close + save under inventory minimum that would also fire."""

    def evaluate_terminal(
        self, context: OrchestratorContext, projection: SharedStateProjection | None
    ) -> TerminalEvaluation | None:
        if context.loop_memory.iterations >= 2:
            return TerminalEvaluation(terminal_class="completed", reason_code="done")
        return None

    def choose_action(
        self, context: OrchestratorContext, projection: SharedStateProjection | None
    ) -> ActionPlan:
        if context.loop_memory.iterations == 1:
            return ActionPlan(
                actions=(
                    ActionPlanAction(
                        action_type="save_workspace_artifact",
                        action_inputs={"draft_payload": {"x": 1}},
                        alias="save",
                    ),
                ),
                state_patch=_close_item_patch(status="closed"),
                pin_refs=("artifact://should-not-pin",),
                hitl_consumed_prompt_ids=("hitl-pending-1",),
                user_message_consumed_ids=("user-msg-1",),
                continuity_journal_entry=_PACK_CJ,
            )
        return ActionPlan(skip_execution=True, continuity_journal_entry=_PACK_CJ)


def _inventory_save_policy_ctx(*, minimum_save: int = 2) -> dict[str, Any]:
    return {
        "domain_closure_policy": {
            "hard_enforced": True,
            "enforce_on_publish": False,
            "enforce_on_complete": False,
            "save_action_ids": ["save_workspace_artifact"],
            "publish_action_ids": ["publish_workspace_artifact"],
            "minimum_resolution_items_for_save": minimum_save,
            "minimum_resolution_items_for_wait": 0,
            "minimum_resolution_items_for_publish": 0,
            "minimum_resolution_items_for_complete": 0,
            "required_dimension_ids": [],
            "standards": [],
        }
    }


def test_contradictory_plan_beats_resolution_inventory_and_does_not_commit() -> None:
    sm = RecordingSessionManager()
    mem = _seed_memory([_seed_item()])  # 1 item; inventory requires 2 for save
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
    before_pins = list(mem.continuity.pinned_refs)
    before_answered = copy.deepcopy(mem.hitl.answered_hitl_responses)
    before_ledger = copy.deepcopy(mem.continuity.user_message_ledger)
    before_item_status = mem.continuity.resolution_state.items[0].status
    before_single = mem.continuity.single_action_turn_count

    result = run_orchestration_kernel_loop(
        orchestration_adapter=InventoryAndContradictionPack(),
        session_manager=sm,
        session_id="sess-inv-contra",
        run_artifact_ref=None,
        request_id_prefix="req-inv-contra",
        opaque_run_context=_inventory_save_policy_ctx(minimum_save=2),
        max_iterations=4,
        initial_loop_memory=mem,
    )

    assert result.terminal_class == "completed"
    assert sm.write_side_effects == 0
    assert len(sm.steps) == 0
    fb = result.runtime_state["state_patch_feedback"]
    assert fb.get("reason_code") == REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK
    assert fb.get("outcome") == "rejected"
    # Must not have fallen through to inventory policy-block commit.
    inventory_events = [
        e
        for e in result.trace_events
        if e.get("reason_code") == "resolution_items_save_required"
    ]
    assert inventory_events == []
    rs = result.runtime_state["resolution_state"]
    assert rs.items[0].status == before_item_status
    assert rs.items[0].next_needed_step == "verify this value"
    # Continuity pins / HITL / user-message / observability must be untouched.
    assert mem.continuity.pinned_refs == before_pins
    assert mem.hitl.answered_hitl_responses == before_answered
    assert mem.continuity.user_message_ledger == before_ledger
    assert mem.continuity.user_message_ledger[0]["status"] == "pending"
    assert mem.continuity.single_action_turn_count == before_single


def test_rejected_plan_does_not_mutate_pins_hitl_user_messages_or_refs() -> None:
    sm = RecordingSessionManager()
    mem = _seed_memory([_seed_item()])
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

    class _OneShotReject(_InheritSyncMixin):
        def evaluate_terminal(self, context, projection):
            if context.loop_memory.iterations >= 2:
                return TerminalEvaluation(terminal_class="completed", reason_code="done")
            return None

        def choose_action(self, context, projection):
            if context.loop_memory.iterations == 1:
                return ActionPlan(
                    actions=(
                        ActionPlanAction(
                            action_type="save_workspace_artifact",
                            action_inputs={"draft_payload": {"x": 1}},
                            alias="save",
                        ),
                    ),
                    state_patch=_close_item_patch(status="closed"),
                    pin_refs=("artifact://should-not-pin",),
                    hitl_consumed_prompt_ids=("hitl-pending-1",),
                    user_message_consumed_ids=("user-msg-1",),
                    continuity_journal_entry=_PACK_CJ,
                )
            return ActionPlan(skip_execution=True, continuity_journal_entry=_PACK_CJ)

    result = run_orchestration_kernel_loop(
        orchestration_adapter=_OneShotReject(),
        session_manager=sm,
        session_id="sess-no-mutate",
        run_artifact_ref=None,
        request_id_prefix="req-no-mutate",
        opaque_run_context={},
        max_iterations=4,
        initial_loop_memory=mem,
    )
    assert result.terminal_class == "completed"
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
    assert (
        result.runtime_state["state_patch_feedback"]["reason_code"]
        == REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK
    )