"""Unit tests for closure and resolution policy evaluation helpers (orchestrator_policy.py).

These test the pure, side-effect-free evaluation functions directly.
The full orchestrator integration tests (test_orchestrator.py) verify these
paths end-to-end; these unit tests pin the specific blocking invariants.
"""
from __future__ import annotations

from harness.mission_state import (
    ClosureDimension,
    ClosureState,
    new_mission_state,
    new_resolution_state,
    ResolutionItem,
)
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.contracts import ActionPlan
from harness.runtime.orchestration.orchestrator_policy import (
    closure_enforcement_failure,
    resolution_inventory_enforcement_failure,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _loop_memory_with_closure(
    *,
    dimensions: list[ClosureDimension] | None = None,
    ready_to_close: bool = False,
    ready_to_publish: bool = False,
    requires_hitl: bool = False,
    resolution_items: list[ResolutionItem] | None = None,
    work_universe_posture: str = "audited",
) -> LoopMemoryState:
    ms = new_mission_state(mission_id="m-policy", loop_family="orchestration_kernel")
    ms = ms.model_copy(
        update={
            "work_universe_posture": work_universe_posture,
            "closure_state": ClosureState(
                dimensions=list(dimensions or []),
                ready_to_close=ready_to_close,
                ready_to_publish=ready_to_publish,
                requires_hitl=requires_hitl,
            )
        }
    )
    rs = new_resolution_state()
    if resolution_items:
        rs = rs.model_copy(update={"items": list(resolution_items)})
    ms = ms.model_copy(update={"resolution_state": rs})
    mem = LoopMemoryState()
    mem.continuity.mission_state = ms
    mem.continuity.resolution_state = rs
    return mem


def _dim(dimension_id: str, status: str = "closed", *, requires_hitl: bool = False) -> ClosureDimension:
    return ClosureDimension(dimension_id=dimension_id, title=dimension_id, status=status, requires_hitl=requires_hitl)


def _item(item_id: str, *, requires_hitl: bool = False) -> ResolutionItem:
    return ResolutionItem(
        item_id=item_id,
        title=item_id,
        kind="work_unit",
        status="closed",
        requires_hitl=requires_hitl,
    )


def _hard_enforced_policy(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "hard_enforced": True,
        "enforce_on_complete": True,
        "enforce_on_publish": True,
        "save_action_ids": ["save_workspace_artifact"],
        "publish_action_ids": ["publish_workspace_artifact"],
        "required_dimension_ids": ["layer_a"],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# closure_enforcement_failure — no policy / policy not hard_enforced
# ---------------------------------------------------------------------------


def test_closure_enforcement_returns_none_without_policy() -> None:
    mem = _loop_memory_with_closure()
    plan = ActionPlan(complete_run=True)
    assert closure_enforcement_failure(run_ctx={}, loop_memory=mem, action_plan=plan) is None


def test_closure_enforcement_returns_none_when_not_hard_enforced() -> None:
    mem = _loop_memory_with_closure()
    plan = ActionPlan(complete_run=True)
    ctx = {"domain_closure_policy": {"hard_enforced": False, "enforce_on_complete": True}}
    assert closure_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan) is None


def test_closure_enforcement_returns_none_when_enforce_on_complete_false() -> None:
    mem = _loop_memory_with_closure(
        dimensions=[_dim("layer_a")], ready_to_close=True
    )
    plan = ActionPlan(complete_run=True)
    ctx = {"domain_closure_policy": {"hard_enforced": True, "enforce_on_complete": False}}
    assert closure_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan) is None


# ---------------------------------------------------------------------------
# closure_enforcement_failure — blocking paths
# ---------------------------------------------------------------------------


def test_closure_enforcement_blocks_complete_when_dimension_missing() -> None:
    """complete_run without required dimension present → blocking."""
    mem = _loop_memory_with_closure(dimensions=[])  # layer_a not present
    plan = ActionPlan(complete_run=True)
    ctx = {"domain_closure_policy": _hard_enforced_policy()}
    result = closure_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan)
    assert result is not None
    reason_code, message = result
    assert reason_code == "closure_complete_dimensions_missing"
    assert "layer_a" in message


def test_closure_enforcement_blocks_complete_when_requires_hitl() -> None:
    """Dimension has requires_hitl=True → blocking."""
    mem = _loop_memory_with_closure(dimensions=[_dim("layer_a", requires_hitl=True)])
    plan = ActionPlan(complete_run=True)
    ctx = {"domain_closure_policy": _hard_enforced_policy()}
    result = closure_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan)
    assert result is not None
    reason_code, _ = result
    assert reason_code == "closure_complete_requires_hitl"


def test_closure_enforcement_blocks_complete_when_not_ready_to_close() -> None:
    """Dimension present but ready_to_close=False → blocking."""
    mem = _loop_memory_with_closure(
        dimensions=[_dim("layer_a")], ready_to_close=False
    )
    plan = ActionPlan(complete_run=True)
    ctx = {"domain_closure_policy": _hard_enforced_policy()}
    result = closure_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan)
    assert result is not None
    reason_code, _ = result
    assert reason_code == "closure_complete_not_ready"


def test_closure_enforcement_blocks_complete_when_resolution_item_requires_hitl() -> None:
    """An item-level outstanding HITL requirement is a complete_run blocker."""
    mem = _loop_memory_with_closure(
        dimensions=[_dim("layer_a")],
        ready_to_close=True,
        work_universe_posture="audited",
        resolution_items=[_item("i1", requires_hitl=True)],
    )
    plan = ActionPlan(complete_run=True)
    ctx = {"domain_closure_policy": _hard_enforced_policy()}
    result = closure_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan)
    assert result is not None
    reason_code, message = result
    assert reason_code == "closure_complete_items_require_hitl"
    assert "i1" in message


def test_closure_enforcement_allows_complete_when_all_conditions_met() -> None:
    """All required dimensions closed, ready_to_close=True → allowed."""
    mem = _loop_memory_with_closure(
        dimensions=[_dim("layer_a")], ready_to_close=True
    )
    plan = ActionPlan(complete_run=True)
    ctx = {"domain_closure_policy": _hard_enforced_policy()}
    assert closure_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan) is None


def test_closure_enforcement_blocks_publish_when_not_publish_ready() -> None:
    """publish_workspace_artifact with ready_to_publish=False → blocking."""
    mem = _loop_memory_with_closure(
        dimensions=[_dim("layer_a")], ready_to_publish=False
    )
    plan = ActionPlan(action_type="publish_workspace_artifact")
    ctx = {
        "domain_closure_policy": _hard_enforced_policy(enforce_on_complete=False, enforce_on_publish=True)
    }
    result = closure_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan)
    assert result is not None
    reason_code, _ = result
    assert reason_code == "closure_publish_not_ready"


def test_closure_enforcement_allows_publish_when_ready_to_publish() -> None:
    """publish_workspace_artifact with ready_to_publish=True → allowed."""
    mem = _loop_memory_with_closure(
        dimensions=[_dim("layer_a")], ready_to_publish=True
    )
    plan = ActionPlan(action_type="publish_workspace_artifact")
    ctx = {
        "domain_closure_policy": _hard_enforced_policy(enforce_on_complete=False, enforce_on_publish=True)
    }
    assert closure_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan) is None


def test_closure_enforcement_blocks_publish_when_resolution_item_requires_hitl() -> None:
    """An item-level outstanding HITL requirement is a publish blocker."""
    mem = _loop_memory_with_closure(
        dimensions=[_dim("layer_a")],
        ready_to_publish=True,
        work_universe_posture="audited",
        resolution_items=[_item("i1", requires_hitl=True)],
    )
    plan = ActionPlan(action_type="publish_workspace_artifact")
    ctx = {
        "domain_closure_policy": _hard_enforced_policy(
            enforce_on_complete=False,
            enforce_on_publish=True,
        )
    }
    result = closure_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan)
    assert result is not None
    reason_code, message = result
    assert reason_code == "closure_publish_items_require_hitl"
    assert "i1" in message


def test_closure_enforcement_allows_publish_when_resolution_items_do_not_require_hitl() -> None:
    """False or absent item-level HITL flags do not block publish on their own."""
    mem = _loop_memory_with_closure(
        dimensions=[_dim("layer_a")],
        ready_to_publish=True,
        work_universe_posture="audited",
        resolution_items=[_item("i1"), _item("i2", requires_hitl=False)],
    )
    plan = ActionPlan(action_type="publish_workspace_artifact")
    ctx = {
        "domain_closure_policy": _hard_enforced_policy(
            enforce_on_complete=False,
            enforce_on_publish=True,
        )
    }
    assert closure_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan) is None


def test_closure_enforcement_does_not_guess_publish_role_without_declared_action_ids() -> None:
    mem = _loop_memory_with_closure(
        dimensions=[_dim("layer_a")],
        ready_to_publish=False,
        work_universe_posture="partial",
    )
    plan = ActionPlan(action_type="publish_workspace_artifact")
    ctx = {
        "domain_closure_policy": _hard_enforced_policy(
            publish_action_ids=[],
            enforce_on_complete=False,
            enforce_on_publish=True,
        )
    }
    assert closure_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan) is None


def test_closure_enforcement_blocks_complete_when_work_universe_not_audited() -> None:
    mem = _loop_memory_with_closure(
        dimensions=[_dim("layer_a")],
        ready_to_close=True,
        work_universe_posture="partial",
    )
    plan = ActionPlan(complete_run=True)
    result = closure_enforcement_failure(
        run_ctx={"domain_closure_policy": _hard_enforced_policy()},
        loop_memory=mem,
        action_plan=plan,
    )
    assert result == (
        "work_universe_complete_not_audited",
        "work-universe posture must be audited before complete; current posture is partial",
    )


def test_closure_enforcement_blocks_publish_when_work_universe_not_audited() -> None:
    mem = _loop_memory_with_closure(
        dimensions=[_dim("layer_a")],
        ready_to_publish=True,
        work_universe_posture="believed_adequate",
    )
    plan = ActionPlan(action_type="publish_workspace_artifact")
    result = closure_enforcement_failure(
        run_ctx={
            "domain_closure_policy": _hard_enforced_policy(
                enforce_on_complete=False,
                enforce_on_publish=True,
            )
        },
        loop_memory=mem,
        action_plan=plan,
    )
    assert result == (
        "work_universe_publish_not_audited",
        "work-universe posture must be audited before publish; current posture is believed_adequate",
    )


def test_closure_enforcement_allows_complete_when_same_turn_patch_sets_audited() -> None:
    mem = _loop_memory_with_closure(
        dimensions=[_dim("layer_a")],
        ready_to_close=True,
        work_universe_posture="partial",
    )
    plan = ActionPlan(
        complete_run=True,
        state_patch={"mission": {"work_universe_posture": "audited"}},
    )
    assert (
        closure_enforcement_failure(
            run_ctx={"domain_closure_policy": _hard_enforced_policy()},
            loop_memory=mem,
            action_plan=plan,
        )
        is None
    )


# ---------------------------------------------------------------------------
# resolution_inventory_enforcement_failure
# ---------------------------------------------------------------------------


def test_resolution_inventory_returns_none_without_policy() -> None:
    mem = _loop_memory_with_closure()
    plan = ActionPlan(complete_run=True)
    assert resolution_inventory_enforcement_failure(run_ctx={}, loop_memory=mem, action_plan=plan) is None


def test_resolution_inventory_returns_none_when_not_hard_enforced() -> None:
    mem = _loop_memory_with_closure()
    plan = ActionPlan(complete_run=True)
    ctx = {"domain_closure_policy": {"hard_enforced": False, "minimum_resolution_items_for_complete": 1}}
    assert resolution_inventory_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan) is None


def test_resolution_inventory_blocks_complete_when_below_minimum() -> None:
    """complete_run with 0 items when minimum is 1 → blocked."""
    mem = _loop_memory_with_closure(resolution_items=[])
    plan = ActionPlan(complete_run=True)
    ctx = {
        "domain_closure_policy": {
            "hard_enforced": True,
            "minimum_resolution_items_for_complete": 1,
        }
    }
    result = resolution_inventory_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan)
    assert result is not None
    reason_code, message = result
    assert reason_code == "resolution_items_complete_required"
    assert "1" in message


def test_resolution_inventory_allows_complete_when_minimum_met() -> None:
    """complete_run with 1 item when minimum is 1 → allowed."""
    mem = _loop_memory_with_closure(resolution_items=[_item("i1")])
    plan = ActionPlan(complete_run=True)
    ctx = {
        "domain_closure_policy": {
            "hard_enforced": True,
            "minimum_resolution_items_for_complete": 1,
        }
    }
    assert resolution_inventory_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan) is None


def test_resolution_inventory_does_not_apply_to_non_gated_actions() -> None:
    """A plain tool action is not subject to the resolution-inventory gate."""
    mem = _loop_memory_with_closure(resolution_items=[])
    plan = ActionPlan(action_type="some_tool", skip_execution=False)
    ctx = {
        "domain_closure_policy": {
            "hard_enforced": True,
            "minimum_resolution_items_for_complete": 1,
        }
    }
    # minimum only applies to complete/publish/wait/save; a generic tool returns 0 minimum.
    assert resolution_inventory_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan) is None


def test_resolution_inventory_does_not_guess_save_role_without_declared_action_ids() -> None:
    mem = _loop_memory_with_closure(resolution_items=[])
    plan = ActionPlan(action_type="save_workspace_artifact", skip_execution=False)
    ctx = {
        "domain_closure_policy": {
            "hard_enforced": True,
            "save_action_ids": [],
            "minimum_resolution_items_for_save": 1,
        }
    }
    assert resolution_inventory_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan) is None
