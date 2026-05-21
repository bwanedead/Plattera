"""Closure and resolution policy evaluation helpers for the orchestration kernel.

Extracted from ``orchestrator`` to keep the main loop focused on mechanics.
All functions here are pure evaluation: no side effects, no state mutation.
"""

from __future__ import annotations

from typing import Any

from ..memory import LoopMemoryState
from .action_sequence import effective_actions
from .contracts import ActionPlan
from .required_output_gate import required_output_artifact_enforcement_failure
from .state_patch_apply import StatePatchError, apply_state_patch

def closure_policy(run_ctx: dict[str, Any]) -> dict[str, Any] | None:
    raw = run_ctx.get("domain_closure_policy")
    return dict(raw) if isinstance(raw, dict) else None


def _normalize_action_id(value: Any) -> str:
    return str(value or "").strip()


def _policy_action_ids(policy: dict[str, Any], key: str) -> frozenset[str]:
    raw_values = policy.get(key) or ()
    if isinstance(raw_values, str):
        raw_values = (raw_values,)
    if not isinstance(raw_values, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(
        normalized
        for normalized in (_normalize_action_id(value) for value in raw_values)
        if normalized
    )


def _action_has_policy_role(
    *,
    policy: dict[str, Any],
    action_plan: ActionPlan,
    role_action_ids_key: str,
) -> bool:
    actions = effective_actions(action_plan)
    role_ids = _policy_action_ids(policy, role_action_ids_key)
    if not actions:
        action_id = _normalize_action_id(action_plan.action_type)
        return bool(action_id) and action_id in role_ids
    return any(_normalize_action_id(item.action_type) in role_ids for item in actions)


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


def effective_mission_state(
    *,
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
) -> Any:
    if not action_plan.state_patch:
        return loop_memory.continuity.mission_state
    try:
        mission_state, _, _ = apply_state_patch(
            mission_state=loop_memory.continuity.mission_state,
            resolution_state=loop_memory.continuity.resolution_state,
            state_patch=action_plan.state_patch,
        )
        return mission_state
    except StatePatchError:
        return loop_memory.continuity.mission_state


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
    is_publish = _action_has_policy_role(
        policy=policy,
        action_plan=action_plan,
        role_action_ids_key="publish_action_ids",
    )
    is_save = _action_has_policy_role(
        policy=policy,
        action_plan=action_plan,
        role_action_ids_key="save_action_ids",
    )
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
    is_publish = bool(policy) and _action_has_policy_role(
        policy=policy,
        action_plan=action_plan,
        role_action_ids_key="publish_action_ids",
    )
    is_complete = bool(action_plan.complete_run)
    if not (is_publish or is_complete):
        return None

    mission_state = effective_mission_state(loop_memory=loop_memory, action_plan=action_plan)
    posture = str(getattr(mission_state, "work_universe_posture", "") or "").strip() or "initial"
    if posture != "audited":
        target = "publish" if is_publish else "complete"
        return (
            f"work_universe_{target}_not_audited",
            f"work-universe posture must be audited before {target}; current posture is {posture}",
        )

    if not policy or not bool(policy.get("hard_enforced")):
        return None

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

    resolution_state = effective_resolution_state(loop_memory=loop_memory, action_plan=action_plan)
    items_requiring_hitl = [
        str(getattr(row, "item_id", "") or "").strip()
        for row in (getattr(resolution_state, "items", ()) or ())
        if bool(getattr(row, "requires_hitl", False))
    ]
    items_requiring_hitl = [item_id for item_id in items_requiring_hitl if item_id]
    if items_requiring_hitl:
        target = "publish" if is_publish else "complete"
        return (
            f"closure_{target}_items_require_hitl",
            (
                "closure enforcement requires HITL integration for one or more resolution items "
                f"before {target}: {items_requiring_hitl}"
            ),
        )

    if is_publish and not bool(getattr(cs, "ready_to_publish", False)):
        return (
            "closure_publish_not_ready",
            "closure enforcement requires ready_to_publish before publish",
        )

    if is_complete and not bool(getattr(cs, "ready_to_close", False)):
        return (
            "closure_complete_not_ready",
            "closure enforcement requires ready_to_close before complete_run",
        )

    output_failure = required_output_artifact_enforcement_failure(
        run_ctx=run_ctx,
        loop_memory=loop_memory,
        action_plan=action_plan,
    )
    if output_failure is not None:
        return output_failure

    return None
