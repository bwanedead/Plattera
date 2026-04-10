"""Closure and resolution policy evaluation helpers for the orchestration kernel.

Extracted from ``orchestrator`` to keep the main loop focused on mechanics.
All functions here are pure evaluation: no side effects, no state mutation.
"""

from __future__ import annotations

from typing import Any

from ..memory import LoopMemoryState
from .contracts import ActionPlan
from .state_patch_apply import StatePatchError, apply_state_patch

_PUBLISH_ACTION_IDS = frozenset({"publish_workspace_artifact"})
_SAVE_ACTION_IDS = frozenset({"save_workspace_artifact"})


def closure_policy(run_ctx: dict[str, Any]) -> dict[str, Any] | None:
    raw = run_ctx.get("domain_closure_policy")
    return dict(raw) if isinstance(raw, dict) else None


def effective_resolution_state(
    *,
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
) -> Any:
    if not action_plan.state_patch:
        return loop_memory.continuity.resolution_state
    try:
        _, resolution_state, _ = apply_state_patch(
            mission_state=loop_memory.continuity.mission_state,
            resolution_state=loop_memory.continuity.resolution_state,
            state_patch=action_plan.state_patch,
        )
        return resolution_state
    except StatePatchError:
        return loop_memory.continuity.resolution_state


def effective_closure_state(
    *,
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
) -> Any:
    if not action_plan.state_patch:
        return loop_memory.continuity.mission_state.closure_state
    try:
        mission_state, _, _ = apply_state_patch(
            mission_state=loop_memory.continuity.mission_state,
            resolution_state=loop_memory.continuity.resolution_state,
            state_patch=action_plan.state_patch,
        )
        return mission_state.closure_state
    except StatePatchError:
        return loop_memory.continuity.mission_state.closure_state


def minimum_resolution_items_required(
    *,
    policy: dict[str, Any],
    action_plan: ActionPlan,
) -> tuple[int, str | None]:
    is_publish = str(action_plan.action_type or "").strip() in _PUBLISH_ACTION_IDS
    is_save = str(action_plan.action_type or "").strip() in _SAVE_ACTION_IDS
    is_complete = bool(action_plan.complete_run)
    is_hitl = bool(action_plan.wait_for_human) or action_plan.hitl_request is not None

    if is_complete:
        return int(policy.get("minimum_resolution_items_for_complete") or 0), "complete"
    if is_publish:
        return int(policy.get("minimum_resolution_items_for_publish") or 0), "publish"
    if is_hitl:
        return int(policy.get("minimum_resolution_items_for_wait") or 0), "wait"
    if is_save:
        return int(policy.get("minimum_resolution_items_for_save") or 0), "save"
    return 0, None


def resolution_inventory_enforcement_failure(
    *,
    run_ctx: dict[str, Any],
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
) -> tuple[str, str] | None:
    policy = closure_policy(run_ctx)
    if not policy or not bool(policy.get("hard_enforced")):
        return None

    minimum_items, target = minimum_resolution_items_required(
        policy=policy,
        action_plan=action_plan,
    )
    if minimum_items <= 0 or target is None:
        return None

    resolution_state = effective_resolution_state(
        loop_memory=loop_memory,
        action_plan=action_plan,
    )
    item_count = len(getattr(resolution_state, "items", ()) or ())
    if item_count >= minimum_items:
        return None

    return (
        f"resolution_items_{target}_required",
        (
            f"domain policy requires at least {minimum_items} resolution items before {target}; "
            f"current item count is {item_count}"
        ),
    )


def closure_enforcement_failure(
    *,
    run_ctx: dict[str, Any],
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
) -> tuple[str, str] | None:
    policy = closure_policy(run_ctx)
    if not policy or not bool(policy.get("hard_enforced")):
        return None

    is_publish = str(action_plan.action_type or "").strip() in _PUBLISH_ACTION_IDS
    is_complete = bool(action_plan.complete_run)
    if not ((is_publish and bool(policy.get("enforce_on_publish"))) or (is_complete and bool(policy.get("enforce_on_complete")))):
        return None

    cs = effective_closure_state(loop_memory=loop_memory, action_plan=action_plan)
    required_dimension_ids = tuple(
        str(value).strip()
        for value in (policy.get("required_dimension_ids") or ())
        if str(value).strip()
    )
    dimensions = {
        str(getattr(dim, "dimension_id", "") or ""): dim
        for dim in getattr(cs, "dimensions", ()) or ()
        if str(getattr(dim, "dimension_id", "") or "")
    }
    missing = [
        dim_id
        for dim_id in required_dimension_ids
        if dim_id not in dimensions or not str(getattr(dimensions[dim_id], "status", "") or "").strip()
    ]
    if missing:
        target = "publish" if is_publish else "complete"
        return (
            f"closure_{target}_dimensions_missing",
            f"closure enforcement missing required dimensions: {missing}",
        )

    if bool(getattr(cs, "requires_hitl", False)) or any(
        bool(getattr(dimensions[dim_id], "requires_hitl", False))
        for dim_id in required_dimension_ids
        if dim_id in dimensions
    ):
        target = "publish" if is_publish else "complete"
        return (
            f"closure_{target}_requires_hitl",
            "closure enforcement requires HITL before this action",
        )

    if is_publish and not bool(getattr(cs, "ready_to_publish", False)):
        return (
            "closure_publish_not_ready",
            "closure enforcement requires ready_to_publish before publish_workspace_artifact",
        )

    if is_complete and not bool(getattr(cs, "ready_to_close", False)):
        return (
            "closure_complete_not_ready",
            "closure enforcement requires ready_to_close before complete_run",
        )

    return None
