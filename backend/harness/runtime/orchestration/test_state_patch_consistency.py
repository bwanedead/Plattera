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
    MAX_IDENTICAL_TERMINAL_ROW_CONFLICT_REJECTIONS,
    REASON_STATE_PATCH_CONSISTENCY_REPAIR_BUDGET_EXHAUSTED,
    block_contradictory_closed_resolution_before_dispatch,
    evaluate_state_patch_terminal_row_consistency,
    record_terminal_row_consistency_rejection,
)
from harness.runtime.orchestration.state_patch_repair_bundle import (
    REASON_TERMINAL_ROW_LIVE_WORK,
    build_terminal_row_consistency_repair_bundle,
    project_state_patch_repair_bundle_for_prompt,
)
from harness.runtime.orchestration.repair_lane import should_use_state_repair_lane
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
        state_patch=_close_item_patch(status="closed"),
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
    assert "Omitting a field preserves" in fb["repair_hint"]
    assert fb["same_conflict_streak"] == 1
    bundle = fb["state_patch_repair_bundle"]
    assert bundle["reason"] == REASON_TERMINAL_ROW_LIVE_WORK
    assert bundle["fragments"][0]["required_clear_delta"] == {"next_needed_step": None}
    assert should_use_state_repair_lane(fb) is True


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
    assert blocked is not None
    assert blocked.blocked is True
    assert blocked.repair_budget_exhausted is False
    assert snapshots
    fb1 = copy.deepcopy(mem.continuity.state_patch_feedback)
    assert fb1["same_conflict_streak"] == 1
    assert "state_patch_repair_bundle" in fb1

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
    assert restored.continuity.state_patch_feedback["same_conflict_streak"] == 1
    assert restored.continuity.state_patch_feedback["conflict_identity"] == fb1["conflict_identity"]


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


# --- MAPDEP-BR-023: sparse-clear bundle, streak, identical-conflict budget ---


def test_sparse_omit_remains_conflicting_and_bundle_carries_null_clear() -> None:
    mem = _seed_memory([_seed_item(next_needed_step="verify unit chain")])
    patch = _close_item_patch(status="closed")
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=patch,
    )
    assert result is not None
    assert result.conflicts[0].fields == ("next_needed_step",)
    bundle = build_terminal_row_consistency_repair_bundle(state_patch=patch, result=result)
    assert bundle is not None
    assert bundle["reason"] == REASON_TERMINAL_ROW_LIVE_WORK
    assert "Omitting a field preserves" in bundle["instruction"]
    frag = bundle["fragments"][0]
    assert frag["path"] == "resolution.items[item-1]"
    assert frag["conflicting_fields"] == ["next_needed_step"]
    assert frag["required_clear_delta"] == {"next_needed_step": None}
    assert frag["fragment"]["status"] == "closed"
    assert "next_needed_step" not in frag["fragment"]


def test_requires_hitl_and_no_further_progress_clear_deltas() -> None:
    mem = _seed_memory(
        [_seed_item(next_needed_step=None, requires_hitl=True, no_further_progress=True)]
    )
    patch = _close_item_patch(status="closed")
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=patch,
    )
    assert result is not None
    assert set(result.conflicts[0].fields) == {"requires_hitl", "no_further_progress"}
    bundle = build_terminal_row_consistency_repair_bundle(state_patch=patch, result=result)
    assert bundle is not None
    assert bundle["fragments"][0]["required_clear_delta"] == {
        "requires_hitl": False,
        "no_further_progress": False,
    }


def test_only_conflicting_fields_appear_in_required_clear_delta() -> None:
    mem = _seed_memory([_seed_item(requires_hitl=True)])
    patch = _close_item_patch(status="closed")
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=patch,
    )
    assert result is not None
    assert result.conflicts[0].fields == ("next_needed_step", "requires_hitl")
    bundle = build_terminal_row_consistency_repair_bundle(state_patch=patch, result=result)
    assert bundle is not None
    assert bundle["fragments"][0]["required_clear_delta"] == {
        "next_needed_step": None,
        "requires_hitl": False,
    }
    assert "no_further_progress" not in bundle["fragments"][0]["required_clear_delta"]


def test_resubmit_with_explicit_clears_passes_and_merges() -> None:
    mem = _seed_memory([_seed_item()])
    corrected = _close_item_patch(
        status="closed",
        next_needed_step=None,
        requires_hitl=False,
        no_further_progress=False,
    )
    assert (
        evaluate_state_patch_terminal_row_consistency(
            mission_state=mem.continuity.mission_state,
            resolution_state=mem.continuity.resolution_state,
            state_patch=corrected,
        )
        is None
    )
    _ms, rs, _ = apply_state_patch(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=corrected,
    )
    assert rs.items[0].status == "closed"
    assert rs.items[0].next_needed_step is None


def test_covered_unit_coordinate_fragment_and_parent_item_fragment() -> None:
    mem = _seed_memory(
        [
            _seed_item(
                next_needed_step="parent step",
                covered_units=[
                    ResolutionCoveredUnit(
                        unit_id="unit-2",
                        title="Unit",
                        status="open",
                        next_needed_step="unit step",
                    )
                ],
            )
        ]
    )
    patch = {
        "resolution": {
            "items": [
                {
                    "item_id": "item-1",
                    "status": "closed",
                    "covered_units": [{"unit_id": "unit-2", "status": "closed"}],
                }
            ]
        }
    }
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=patch,
    )
    assert result is not None
    bundle = build_terminal_row_consistency_repair_bundle(state_patch=patch, result=result)
    assert bundle is not None
    paths = {row["path"] for row in bundle["fragments"]}
    assert "resolution.items[item-1]" in paths
    assert "resolution.items[item-1].covered_units[unit-2]" in paths
    unit_frag = next(
        row for row in bundle["fragments"] if "covered_units" in row["path"]
    )
    assert unit_frag["fragment"]["unit_id"] == "unit-2"
    assert unit_frag["required_clear_delta"] == {"next_needed_step": None}


def test_terminal_bundle_bounds_large_summary_and_strips_raw_payloads() -> None:
    from harness.mission_state import TerminalRowConflict, TerminalRowConsistencyResult

    patch = {
        "resolution": {
            "items": [
                {
                    "item_id": "item-1",
                    "status": "closed",
                    "summary": "S" * 5000,
                    "raw_prompt_text": "SECRET_PROMPT",
                    "prompt_text": "SECRET_PROMPT",
                    "image_bytes": b"raw",
                }
            ]
        }
    }
    result = TerminalRowConsistencyResult(
        reason_code=REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
        conflicts=(
            TerminalRowConflict(
                coordinate="resolution.items[item-1]",
                fields=("next_needed_step",),
            ),
        ),
        conflicts_omitted_count=0,
    )
    bundle = build_terminal_row_consistency_repair_bundle(state_patch=patch, result=result)
    assert bundle is not None
    frag = bundle["fragments"][0]["fragment"]
    assert "raw_prompt_text" not in frag
    assert "prompt_text" not in frag
    assert "image_bytes" not in frag
    serialized = str(bundle)
    assert "SECRET_PROMPT" not in serialized
    assert len(serialized) < 8000


def test_terminal_bundle_reports_omission_beyond_fragment_capacity() -> None:
    from harness.mission_state import TerminalRowConflict, TerminalRowConsistencyResult
    from harness.runtime.orchestration.state_patch_repair_bundle import MAX_FRAGMENTS

    conflicts = tuple(
        TerminalRowConflict(
            coordinate=f"resolution.items[item-{i}]",
            fields=("next_needed_step",),
        )
        for i in range(MAX_FRAGMENTS + 4)
    )
    patch = {
        "resolution": {
            "items": [
                {"item_id": f"item-{i}", "status": "closed"} for i in range(len(conflicts))
            ]
        }
    }
    result = TerminalRowConsistencyResult(
        reason_code=REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
        conflicts=conflicts,
        conflicts_omitted_count=2,
    )
    bundle = build_terminal_row_consistency_repair_bundle(state_patch=patch, result=result)
    assert bundle is not None
    assert len(bundle["fragments"]) == MAX_FRAGMENTS
    assert bundle["conflicts_omitted_count"] == 4 + 2


def test_same_conflict_streak_increments_and_resets_on_coordinate_change() -> None:
    mem = _seed_memory(
        [
            _seed_item(item_id="a", next_needed_step="stale-a"),
            _seed_item(item_id="b", next_needed_step="stale-b"),
        ]
    )
    tracer = KernelTraceCollector(session_id="s", request_id="r")
    patch_a = _close_item_patch("a", status="closed")
    result_a = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=patch_a,
    )
    assert result_a is not None
    streak1 = record_terminal_row_consistency_rejection(
        loop_memory=mem, tracer=tracer, iteration=1, result=result_a, state_patch=patch_a
    )
    assert streak1 == 1
    assert mem.continuity.state_patch_feedback["same_conflict_streak"] == 1

    streak2 = record_terminal_row_consistency_rejection(
        loop_memory=mem, tracer=tracer, iteration=2, result=result_a, state_patch=patch_a
    )
    assert streak2 == 2

    patch_b = _close_item_patch("b", status="closed")
    result_b = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=patch_b,
    )
    assert result_b is not None
    streak_reset = record_terminal_row_consistency_rejection(
        loop_memory=mem, tracer=tracer, iteration=3, result=result_b, state_patch=patch_b
    )
    assert streak_reset == 1
    assert mem.continuity.state_patch_feedback["same_conflict_streak"] == 1


def test_accepted_patch_clears_prior_rejection_streak() -> None:
    from harness.runtime.orchestration.state_patch_apply import (
        apply_action_plan_state_patch_to_loop_memory,
    )

    mem = _seed_memory([_seed_item()])
    tracer = KernelTraceCollector(session_id="s", request_id="r")
    bad = _close_item_patch(status="closed")
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=bad,
    )
    assert result is not None
    record_terminal_row_consistency_rejection(
        loop_memory=mem, tracer=tracer, iteration=1, result=result, state_patch=bad
    )
    assert mem.continuity.state_patch_feedback["same_conflict_streak"] == 1

    good = ActionPlan(
        skip_execution=True,
        state_patch=_close_item_patch(
            status="closed",
            next_needed_step=None,
            requires_hitl=False,
            no_further_progress=False,
        ),
        continuity_journal_entry=_PACK_CJ,
    )
    apply_action_plan_state_patch_to_loop_memory(
        loop_memory=mem,
        action_plan=good,
        tracer=tracer,
        iteration=2,
    )
    fb = mem.continuity.state_patch_feedback
    assert fb["outcome"] == "applied"
    assert "same_conflict_streak" not in fb


class _RepeatOmitPack(_InheritSyncMixin):
    """Repeatedly omit next_needed_step on a terminal covered-unit close."""

    def __init__(self, *, max_omits: int) -> None:
        self.max_omits = max_omits
        self.omits = 0

    def evaluate_terminal(self, context, projection):
        return None

    def choose_action(self, context, projection):
        self.omits += 1
        if self.omits <= self.max_omits:
            return ActionPlan(
                actions=(
                    ActionPlanAction(
                        action_type="save_workspace_artifact",
                        action_inputs={"draft_payload": {"n": self.omits}},
                        alias=f"save-{self.omits}",
                    ),
                ),
                state_patch={
                    "resolution": {
                        "items": [
                            {
                                "item_id": "item-1",
                                "covered_units": [
                                    {"unit_id": "unit-2", "status": "closed"}
                                ],
                            }
                        ]
                    }
                },
                continuity_journal_entry=_PACK_CJ,
            )
        return ActionPlan(
            skip_execution=True,
            state_patch={
                "resolution": {
                    "items": [
                        {
                            "item_id": "item-1",
                            "covered_units": [
                                {
                                    "unit_id": "unit-2",
                                    "status": "closed",
                                    "next_needed_step": None,
                                }
                            ],
                        }
                    ]
                }
            },
            continuity_journal_entry=_PACK_CJ,
        )


def _seed_unit_live_work_memory() -> LoopMemoryState:
    return _seed_memory(
        [
            _seed_item(
                next_needed_step=None,
                covered_units=[
                    ResolutionCoveredUnit(
                        unit_id="unit-2",
                        title="Curve station",
                        status="open",
                        next_needed_step="verify station chain",
                    )
                ],
            )
        ]
    )


def test_three_identical_rejections_remain_retryable_fourth_exhausts() -> None:
    assert MAX_IDENTICAL_TERMINAL_ROW_CONFLICT_REJECTIONS == 4
    sm = RecordingSessionManager()
    mem = _seed_unit_live_work_memory()
    pack = _RepeatOmitPack(max_omits=10)
    result = run_orchestration_kernel_loop(
        orchestration_adapter=pack,
        session_manager=sm,
        session_id="sess-budget",
        run_artifact_ref=None,
        request_id_prefix="req-budget",
        opaque_run_context={},
        max_iterations=8,
        initial_loop_memory=mem,
    )
    assert result.terminal_class == "failed"
    assert result.reason_code == REASON_STATE_PATCH_CONSISTENCY_REPAIR_BUDGET_EXHAUSTED
    assert sm.steps == []
    assert sm.write_side_effects == 0
    fb = result.runtime_state["state_patch_feedback"]
    assert fb["same_conflict_streak"] == 4
    assert fb["outcome"] == "rejected"
    assert "state_patch_repair_bundle" in fb
    assert result.terminal_summary is not None
    assert "identical" in result.terminal_summary.lower()


def test_corrected_patch_after_retries_succeeds_within_budget() -> None:
    sm = RecordingSessionManager()
    mem = _seed_unit_live_work_memory()
    pack = _RepeatOmitPack(max_omits=2)

    class _RecoverPack(_RepeatOmitPack):
        def evaluate_terminal(self, context, projection):
            if context.loop_memory.iterations >= 4:
                return TerminalEvaluation(terminal_class="completed", reason_code="done")
            return None

    result = run_orchestration_kernel_loop(
        orchestration_adapter=_RecoverPack(max_omits=2),
        session_manager=sm,
        session_id="sess-recover",
        run_artifact_ref=None,
        request_id_prefix="req-recover",
        opaque_run_context={},
        max_iterations=8,
        initial_loop_memory=mem,
    )
    assert result.terminal_class == "completed"
    unit = result.runtime_state["resolution_state"].items[0].covered_units[0]
    assert unit.status == "closed"
    assert unit.next_needed_step is None
    assert sm.steps == []


def test_checkpoint_at_streak_3_then_same_rejection_exhausts() -> None:
    mem = _seed_unit_live_work_memory()
    plan = ActionPlan(
        actions=(
            ActionPlanAction(
                action_type="save_workspace_artifact",
                action_inputs={"draft_payload": {"x": 1}},
                alias="save",
            ),
        ),
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
    snapshots: list[dict[str, Any]] = []

    def _writer(snap: dict[str, Any]) -> None:
        snapshots.append(dict(snap))

    lifecycle = OrchestrationLifecycle(resume_checkpoint_writer=_writer)
    sm = RecordingSessionManager()
    for it in (1, 2, 3):
        outcome = block_contradictory_closed_resolution_before_dispatch(
            loop_memory=mem,
            action_plan=plan,
            tracer=KernelTraceCollector(session_id="s", request_id=f"r{it}"),
            iteration=it,
            lifecycle=lifecycle,
            session_manager=sm,
            session_id="sess-streak3",
            turn_completion_observer=None,
        )
        assert outcome is not None
        assert outcome.repair_budget_exhausted is False
    assert mem.continuity.state_patch_feedback["same_conflict_streak"] == 3
    assert snapshots

    restored, _next_it, err = parse_kernel_resume_snapshot(snapshots[-1])
    assert err is None
    assert restored.continuity.state_patch_feedback["same_conflict_streak"] == 3

    class _ResumeExhaust(_InheritSyncMixin):
        def evaluate_terminal(self, context, projection):
            return None

        def choose_action(self, context, projection):
            return plan

    result = run_orchestration_kernel_loop(
        orchestration_adapter=_ResumeExhaust(),
        session_manager=RecordingSessionManager(),
        session_id="sess-streak3-resume",
        run_artifact_ref=None,
        request_id_prefix="req-streak3-resume",
        opaque_run_context={},
        max_iterations=2,
        initial_loop_memory=restored,
    )
    assert result.terminal_class == "failed"
    assert result.reason_code == REASON_STATE_PATCH_CONSISTENCY_REPAIR_BUDGET_EXHAUSTED
    assert result.runtime_state["state_patch_feedback"]["same_conflict_streak"] == 4


def test_different_conflict_sets_do_not_prematurely_exhaust() -> None:
    mem = _seed_memory(
        [
            _seed_item(item_id="a", next_needed_step="a"),
            _seed_item(item_id="b", next_needed_step="b"),
            _seed_item(item_id="c", next_needed_step="c"),
            _seed_item(item_id="d", next_needed_step="d"),
        ]
    )
    lifecycle = OrchestrationLifecycle()
    sm = RecordingSessionManager()
    for idx, item_id in enumerate(("a", "b", "c", "d"), start=1):
        plan = ActionPlan(
            actions=(
                ActionPlanAction(
                    action_type="save_workspace_artifact",
                    action_inputs={"draft_payload": {"i": idx}},
                    alias=f"s{idx}",
                ),
            ),
            state_patch=_close_item_patch(item_id, status="closed"),
        )
        outcome = block_contradictory_closed_resolution_before_dispatch(
            loop_memory=mem,
            action_plan=plan,
            tracer=KernelTraceCollector(session_id="s", request_id=f"r{idx}"),
            iteration=idx,
            lifecycle=lifecycle,
            session_manager=sm,
            session_id="sess-diff",
            turn_completion_observer=None,
        )
        assert outcome is not None
        assert outcome.repair_budget_exhausted is False
        assert mem.continuity.state_patch_feedback["same_conflict_streak"] == 1


def test_state_repair_prompt_receives_bundle_without_new_lane() -> None:
    from harness.runtime.orchestration.repair_instruction import STATE_REPAIR_INSTRUCTION

    mem = _seed_memory([_seed_item()])
    patch = _close_item_patch(status="closed")
    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mem.continuity.mission_state,
        resolution_state=mem.continuity.resolution_state,
        state_patch=patch,
    )
    assert result is not None
    record_terminal_row_consistency_rejection(
        loop_memory=mem,
        tracer=None,
        iteration=1,
        result=result,
        state_patch=patch,
    )
    fb = mem.continuity.state_patch_feedback
    assert should_use_state_repair_lane(fb) is True
    projected = project_state_patch_repair_bundle_for_prompt(fb)
    assert projected is not None
    assert projected["reason"] == REASON_TERMINAL_ROW_LIVE_WORK
    assert projected["fragments"][0]["required_clear_delta"] == {"next_needed_step": None}
    assert "Omitting a field preserves" in STATE_REPAIR_INSTRUCTION
    assert "state_patch_repair_bundle" in STATE_REPAIR_INSTRUCTION
    assert "required_clear_delta" in STATE_REPAIR_INSTRUCTION
