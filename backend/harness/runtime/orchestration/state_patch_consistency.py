"""Pre-dispatch consistency gate for contradictory closed resolution state.

Previews the same state_patch merge used at commit time, then blocks dispatch
when an addressed resolved-like row would retain live-work posture.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from harness.mission_state import (
    MissionState,
    ResolutionState,
    TerminalRowConsistencyResult,
    evaluate_addressed_terminal_row_consistency,
)
from harness.mission_state.terminal_row_consistency import (
    REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
)
from harness.runtime.memory import LoopMemoryState

from .contracts import ActionPlan
from .lifecycle import OrchestrationLifecycle, TurnCompletionObserver
from .orchestrator_policy_block import action_id_for_plan
from .orchestrator_turn import observe_turn_completed, record_turn_continuity
from .resume_checkpointing import write_resume_checkpoint
from .state_patch_apply import (
    StatePatchError,
    _build_state_patch_feedback,
    _normalize_state_patch_aliases,
    apply_state_patch,
)
from .state_patch_shape_repair import repair_state_patch_container_shapes
from .trace_collector import KernelTraceCollector

_LOG = logging.getLogger(__name__)

_REPAIR_HINT = (
    "A closed/earned/resolved row still carries live-work posture "
    "(next_needed_step, requires_hitl, and/or no_further_progress). "
    "Either clear the stale live-work fields because closure is genuinely earned, "
    "or reopen/reclassify the row because work remains. "
    "The harness does not choose which is correct."
)


def collect_addressed_resolution_coordinates(
    state_patch: Mapping[str, Any] | None,
) -> tuple[list[str], dict[str, list[str]]]:
    """Return first-seen parent item ids and per-item unit ids addressed by the patch.

    Parent items are addressed only when the patch row carries item-own fields
    (not merely ``item_id`` / ``covered_units`` nesting). Covered units are
    addressed only when the unit row carries at least one field besides
    ``unit_id`` (identity-only rows do not activate legacy contradictions).
    """
    if not isinstance(state_patch, Mapping):
        return [], {}
    try:
        patch = _normalize_state_patch_aliases(dict(state_patch))
    except StatePatchError:
        return [], {}
    patch, _ = repair_state_patch_container_shapes(patch)
    resolution = patch.get("resolution")
    if not isinstance(resolution, Mapping):
        return [], {}
    items_raw = resolution.get("items")
    if not isinstance(items_raw, list):
        return [], {}

    item_ids: list[str] = []
    units_by_item: dict[str, list[str]] = {}
    seen_items: set[str] = set()
    for row in items_raw:
        if not isinstance(row, Mapping):
            continue
        item_id = row.get("item_id")
        if type(item_id) is not str or not item_id.strip():
            continue
        own_fields = [key for key in row.keys() if key not in {"item_id", "covered_units"}]
        if own_fields and item_id not in seen_items:
            seen_items.add(item_id)
            item_ids.append(item_id)
        covered = row.get("covered_units")
        if not isinstance(covered, list):
            continue
        unit_list = units_by_item.setdefault(item_id, [])
        seen_units = set(unit_list)
        for unit in covered:
            if not isinstance(unit, Mapping):
                continue
            unit_id = unit.get("unit_id")
            if type(unit_id) is not str or not unit_id.strip():
                continue
            unit_own_fields = [key for key in unit.keys() if key != "unit_id"]
            if not unit_own_fields:
                continue
            if unit_id in seen_units:
                continue
            seen_units.add(unit_id)
            unit_list.append(unit_id)
        if not unit_list:
            units_by_item.pop(item_id, None)
    return item_ids, units_by_item


def preview_state_patch_merge(
    *,
    mission_state: MissionState,
    resolution_state: ResolutionState,
    state_patch: Mapping[str, Any] | None,
) -> tuple[MissionState, ResolutionState] | None:
    """Pure preview using the live merge pipeline; returns None on rejectable patch shape."""
    try:
        ms, rs, _ = apply_state_patch(
            mission_state=mission_state,
            resolution_state=resolution_state,
            state_patch=state_patch,
        )
    except StatePatchError:
        return None
    return ms, rs


def evaluate_state_patch_terminal_row_consistency(
    *,
    mission_state: MissionState,
    resolution_state: ResolutionState,
    state_patch: Mapping[str, Any] | None,
) -> TerminalRowConsistencyResult | None:
    """Preview merge then evaluate only patch-addressed resolution coordinates."""
    if not isinstance(state_patch, Mapping) or not state_patch:
        return None
    item_ids, units_by_item = collect_addressed_resolution_coordinates(state_patch)
    if not item_ids and not units_by_item:
        return None
    preview = preview_state_patch_merge(
        mission_state=mission_state,
        resolution_state=resolution_state,
        state_patch=state_patch,
    )
    if preview is None:
        return None
    _ms, preview_rs = preview
    return evaluate_addressed_terminal_row_consistency(
        resolution_state=preview_rs,
        addressed_item_ids=item_ids,
        addressed_unit_ids_by_item=units_by_item,
    )


def _conflict_feedback_detail(result: TerminalRowConsistencyResult) -> dict[str, Any]:
    payload = result.as_dict()
    first = result.conflicts[0].coordinate if result.conflicts else "resolution.items"
    return {
        "failing_path": first,
        "repair_hint": _REPAIR_HINT,
        "repair_targets": ["resolve_terminal_row_live_work_contradiction"],
        "conflicts": payload["conflicts"],
        "conflicts_omitted_count": payload["conflicts_omitted_count"],
    }


def record_terminal_row_consistency_rejection(
    *,
    loop_memory: LoopMemoryState,
    tracer: KernelTraceCollector | None,
    iteration: int,
    result: TerminalRowConsistencyResult,
) -> None:
    """Record bounded rejected state_patch_feedback without mutating mission/resolution."""
    detail = _conflict_feedback_detail(result)
    loop_memory.continuity.state_patch_feedback = _build_state_patch_feedback(
        loop_memory.continuity.state_patch_feedback,
        outcome="rejected",
        iteration=iteration,
        reason_code=REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
        message=(
            "state_patch would leave a closed/earned resolution row with live-work posture"
        ),
        detail=detail,
        gate="pre_dispatch_terminal_row_consistency",
    )
    if tracer is not None:
        tracer.emit_state_patch_outcome(
            iteration=iteration,
            outcome="rejected",
            reason_code=REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
            message="resolution_terminal_row_has_live_work",
            detail=detail,
            gate="pre_dispatch_terminal_row_consistency",
        )


def block_contradictory_closed_resolution_before_dispatch(
    *,
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
    tracer: KernelTraceCollector,
    iteration: int,
    lifecycle: OrchestrationLifecycle,
    session_manager: Any,
    session_id: str,
    turn_completion_observer: TurnCompletionObserver | None,
) -> bool:
    """Return True when the turn is blocked before tool dispatch / patch commit."""
    state_patch = action_plan.state_patch
    if not isinstance(state_patch, Mapping) or not state_patch:
        return False

    mission_state = loop_memory.continuity.mission_state
    resolution_state = loop_memory.continuity.resolution_state

    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mission_state,
        resolution_state=resolution_state,
        state_patch=state_patch,
    )
    if result is None:
        return False

    _LOG.info(
        "KERNEL pre_dispatch_terminal_row_consistency_blocked ► reason_code=%s conflicts=%s",
        result.reason_code,
        len(result.conflicts),
    )
    record_terminal_row_consistency_rejection(
        loop_memory=loop_memory,
        tracer=tracer,
        iteration=iteration,
        result=result,
    )
    tracer.emit_execution_result(
        iteration=iteration,
        action_type=action_id_for_plan(action_plan),
        execution_state="refused",
        reason_code=REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
        retryable=True,
        refs_delta=None,
    )
    record_turn_continuity(
        loop_memory=loop_memory,
        action_plan=action_plan,
        iteration=iteration,
        execution_state="refused",
        execution_reason_code=REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
    )
    observe_turn_completed(
        turn_completion_observer,
        iteration,
        action_plan=action_plan,
        step_result=None,
        loop_memory=loop_memory,
        terminal_decision="state_patch_consistency_blocked",
    )
    write_resume_checkpoint(
        lifecycle=lifecycle,
        loop_memory=loop_memory,
        session_manager=session_manager,
        session_id=session_id,
        iteration=iteration,
    )
    return True
