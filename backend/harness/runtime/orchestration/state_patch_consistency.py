"""Pre-dispatch consistency gate for contradictory terminal-row state.

Previews the same state_patch merge used at commit time, then blocks dispatch
when an addressed terminal row would retain live-work posture. Completion also
checks every retained mission closure dimension and success condition.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from harness.mission_state import (
    MissionState,
    ResolutionState,
    TerminalRowConsistencyResult,
    evaluate_addressed_terminal_row_consistency,
    evaluate_mission_terminal_row_consistency,
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
from .state_patch_repair_bundle import build_terminal_row_consistency_repair_bundle
from .state_patch_shape_repair import repair_state_patch_container_shapes
from .trace_collector import KernelTraceCollector

_LOG = logging.getLogger(__name__)

MAX_IDENTICAL_TERMINAL_ROW_CONFLICT_REJECTIONS = 4
REASON_STATE_PATCH_CONSISTENCY_REPAIR_BUDGET_EXHAUSTED = (
    "state_patch_consistency_repair_budget_exhausted"
)

_SPARSE_CLEAR_MECHANICS = (
    "Resolution item and covered-unit patches are sparse per-field overlays. "
    "Omitting a field preserves its existing value. "
    "For an already-existing coordinate whose resolution remains honestly earned, "
    "prefer transition {\"kind\":\"resolve\"} with only new or changed semantic fields; "
    "existing earned fields persist without restatement. "
    "Do not combine transition with direct consequence fields. "
    "Without a transition, clear next_needed_step with null and boolean posture with false."
)

_REPAIR_HINT = (
    f"{_SPARSE_CLEAR_MECHANICS} "
    "A closed/earned/resolved row still carries live-work posture "
    "(next_needed_step, requires_hitl, and/or no_further_progress). "
    "Either author a resolve transition (or explicit sparse clears) because closure is "
    "genuinely earned, or reopen/reclassify the row because work remains. "
    "The transition is not evidence and does not prove earning; "
    "the harness does not choose which outcome is correct and only realizes an authored "
    "resolve mechanically."
)

_MISSION_REPAIR_HINT = (
    "Mission closure dimensions and success-condition patches are sparse per-field overlays; "
    "omitting a field preserves its existing value. A terminal row still carries live-work "
    "posture (next_needed_step and/or a true posture flag). If its terminal posture is "
    "genuinely correct, explicitly clear next_needed_step with null and posture flags with "
    "false where present; otherwise author a non-terminal status or determination. The "
    "harness does not choose either outcome."
)


@dataclass(frozen=True)
class StatePatchConsistencyGateOutcome:
    """Typed pre-dispatch gate result for terminal-row consistency conflicts."""

    blocked: bool
    repair_budget_exhausted: bool


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


def collect_addressed_mission_terminal_coordinates(
    state_patch: Mapping[str, Any] | None,
) -> tuple[list[str], list[str]]:
    """Return first-seen closure-dimension and success-condition ids in a patch."""
    if not isinstance(state_patch, Mapping):
        return [], []
    try:
        patch = _normalize_state_patch_aliases(dict(state_patch))
    except StatePatchError:
        return [], []
    patch, _ = repair_state_patch_container_shapes(patch)
    mission = patch.get("mission")
    if not isinstance(mission, Mapping):
        return [], []

    def _ids(rows: Any, key: str) -> list[str]:
        if not isinstance(rows, list):
            return []
        found: list[str] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            value = row.get(key)
            if type(value) is str and value.strip() and value not in seen:
                seen.add(value)
                found.append(value)
        return found

    closure = mission.get("closure_state")
    dimensions = closure.get("dimensions") if isinstance(closure, Mapping) else None
    return _ids(dimensions, "dimension_id"), _ids(
        mission.get("success_conditions"), "condition_id"
    )


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
    check_all_mission_terminal_rows: bool = False,
) -> TerminalRowConsistencyResult | None:
    """Preview merge then evaluate addressed rows, or all mission rows at completion."""
    if not isinstance(state_patch, Mapping) or not state_patch:
        if not check_all_mission_terminal_rows:
            return None
        return evaluate_mission_terminal_row_consistency(
            mission_state=mission_state,
            addressed_dimension_ids=[
                row.dimension_id for row in mission_state.closure_state.dimensions
            ],
            addressed_condition_ids=[row.condition_id for row in mission_state.success_conditions],
        )
    item_ids, units_by_item = collect_addressed_resolution_coordinates(state_patch)
    dimension_ids, condition_ids = collect_addressed_mission_terminal_coordinates(state_patch)
    if (
        not item_ids
        and not units_by_item
        and not dimension_ids
        and not condition_ids
        and not check_all_mission_terminal_rows
    ):
        return None
    preview = preview_state_patch_merge(
        mission_state=mission_state,
        resolution_state=resolution_state,
        state_patch=state_patch,
    )
    if preview is None:
        return None
    preview_ms, preview_rs = preview
    resolution_result = evaluate_addressed_terminal_row_consistency(
        resolution_state=preview_rs,
        addressed_item_ids=item_ids,
        addressed_unit_ids_by_item=units_by_item,
    )
    if resolution_result is not None:
        return resolution_result
    if check_all_mission_terminal_rows:
        dimension_ids = [row.dimension_id for row in preview_ms.closure_state.dimensions]
        condition_ids = [row.condition_id for row in preview_ms.success_conditions]
    return evaluate_mission_terminal_row_consistency(
        mission_state=preview_ms,
        addressed_dimension_ids=dimension_ids,
        addressed_condition_ids=condition_ids,
    )


def canonical_terminal_conflict_identity(
    result: TerminalRowConsistencyResult,
) -> str:
    """Stable bounded mechanical identity for identical-conflict streak tracking."""
    rows = [
        {
            "coordinate": conflict.coordinate,
            "fields": list(conflict.fields),
        }
        for conflict in result.conflicts
    ]
    rows.sort(key=lambda row: str(row.get("coordinate") or ""))
    payload = {
        "conflicts": rows,
        "conflicts_omitted_count": int(result.conflicts_omitted_count),
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _parse_same_conflict_streak(raw: Any) -> int:
    """Return a safe streak base; reject non-ints, bools, negatives, and oversize."""
    # ``bool`` is a subclass of ``int``; require exact ``int``.
    if type(raw) is not int:
        return 0
    if raw < 0:
        return 0
    if raw > MAX_IDENTICAL_TERMINAL_ROW_CONFLICT_REJECTIONS:
        return MAX_IDENTICAL_TERMINAL_ROW_CONFLICT_REJECTIONS
    return raw


def _next_same_conflict_streak(
    previous_feedback: Mapping[str, Any] | None,
    *,
    reason_code: str,
    conflict_identity: str,
) -> int:
    previous = previous_feedback if isinstance(previous_feedback, Mapping) else {}
    previous_reason_code = previous.get("reason_code")
    previous_conflict_identity = previous.get("conflict_identity")
    if (
        type(previous_reason_code) is str
        and previous_reason_code == reason_code
        and type(previous_conflict_identity) is str
        and previous_conflict_identity == conflict_identity
    ):
        prev = _parse_same_conflict_streak(previous.get("same_conflict_streak"))
        return min(prev + 1, MAX_IDENTICAL_TERMINAL_ROW_CONFLICT_REJECTIONS)
    return 1


def _conflict_feedback_detail(
    result: TerminalRowConsistencyResult,
    *,
    state_patch: Mapping[str, Any] | None,
    conflict_identity: str,
    same_conflict_streak: int,
) -> dict[str, Any]:
    payload = result.as_dict()
    first = result.conflicts[0].coordinate if result.conflicts else "resolution.items"
    is_resolution_conflict = (
        result.reason_code == REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK
    )
    detail: dict[str, Any] = {
        "failing_path": first,
        "repair_hint": _REPAIR_HINT if is_resolution_conflict else _MISSION_REPAIR_HINT,
        "repair_targets": [
            "resolve_terminal_row_live_work_contradiction"
            if is_resolution_conflict
            else "repair_mission_terminal_row_live_work_contradiction"
        ],
        "conflicts": payload["conflicts"],
        "conflicts_omitted_count": payload["conflicts_omitted_count"],
        "conflict_identity": conflict_identity,
        "same_conflict_streak": int(same_conflict_streak),
    }
    if is_resolution_conflict and isinstance(state_patch, Mapping) and state_patch:
        bundle = build_terminal_row_consistency_repair_bundle(
            state_patch=state_patch,
            result=result,
        )
        if bundle is not None:
            detail["state_patch_repair_bundle"] = bundle
    return detail


def record_terminal_row_consistency_rejection(
    *,
    loop_memory: LoopMemoryState,
    tracer: KernelTraceCollector | None,
    iteration: int,
    result: TerminalRowConsistencyResult,
    state_patch: Mapping[str, Any] | None = None,
) -> int:
    """Record bounded rejected state_patch_feedback without mutating mission/resolution.

    Returns the updated ``same_conflict_streak`` for the recorded conflict identity.
    """
    conflict_identity = canonical_terminal_conflict_identity(result)
    same_conflict_streak = _next_same_conflict_streak(
        loop_memory.continuity.state_patch_feedback,
        reason_code=result.reason_code,
        conflict_identity=conflict_identity,
    )
    detail = _conflict_feedback_detail(
        result,
        state_patch=state_patch,
        conflict_identity=conflict_identity,
        same_conflict_streak=same_conflict_streak,
    )
    loop_memory.continuity.state_patch_feedback = _build_state_patch_feedback(
        loop_memory.continuity.state_patch_feedback,
        outcome="rejected",
        iteration=iteration,
        reason_code=result.reason_code,
        message=(
            "state_patch would leave a closed/earned terminal row with live-work posture"
        ),
        detail=detail,
        gate="pre_dispatch_terminal_row_consistency",
        carry_prior_repair_bundle=(
            result.reason_code == REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK
        ),
    )
    if tracer is not None:
        tracer.emit_state_patch_outcome(
            iteration=iteration,
            outcome="rejected",
            reason_code=result.reason_code,
            message=result.reason_code,
            detail=detail,
            gate="pre_dispatch_terminal_row_consistency",
        )
    return same_conflict_streak


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
) -> StatePatchConsistencyGateOutcome | None:
    """Return a typed gate outcome when blocked; ``None`` when no conflict."""
    state_patch = action_plan.state_patch
    if (
        (not isinstance(state_patch, Mapping) or not state_patch)
        and not action_plan.complete_run
    ):
        return None

    mission_state = loop_memory.continuity.mission_state
    resolution_state = loop_memory.continuity.resolution_state

    result = evaluate_state_patch_terminal_row_consistency(
        mission_state=mission_state,
        resolution_state=resolution_state,
        state_patch=state_patch,
        check_all_mission_terminal_rows=bool(action_plan.complete_run),
    )
    if result is None:
        return None

    same_conflict_streak = record_terminal_row_consistency_rejection(
        loop_memory=loop_memory,
        tracer=tracer,
        iteration=iteration,
        result=result,
        state_patch=state_patch,
    )
    repair_budget_exhausted = (
        same_conflict_streak >= MAX_IDENTICAL_TERMINAL_ROW_CONFLICT_REJECTIONS
    )
    reason_code = (
        REASON_STATE_PATCH_CONSISTENCY_REPAIR_BUDGET_EXHAUSTED
        if repair_budget_exhausted
        else REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK
    )
    terminal_decision = (
        REASON_STATE_PATCH_CONSISTENCY_REPAIR_BUDGET_EXHAUSTED
        if repair_budget_exhausted
        else "state_patch_consistency_blocked"
    )

    _LOG.info(
        "KERNEL pre_dispatch_terminal_row_consistency_blocked ► reason_code=%s "
        "conflicts=%s same_conflict_streak=%s repair_budget_exhausted=%s",
        reason_code,
        len(result.conflicts),
        same_conflict_streak,
        repair_budget_exhausted,
    )

    tracer.emit_execution_result(
        iteration=iteration,
        action_type=action_id_for_plan(action_plan),
        execution_state="refused",
        reason_code=reason_code,
        retryable=not repair_budget_exhausted,
        refs_delta=None,
    )
    record_turn_continuity(
        loop_memory=loop_memory,
        action_plan=action_plan,
        iteration=iteration,
        execution_state="refused",
        execution_reason_code=reason_code,
    )
    observe_turn_completed(
        turn_completion_observer,
        iteration,
        action_plan=action_plan,
        step_result=None,
        loop_memory=loop_memory,
        terminal_decision=terminal_decision,
    )
    write_resume_checkpoint(
        lifecycle=lifecycle,
        loop_memory=loop_memory,
        session_manager=session_manager,
        session_id=session_id,
        iteration=iteration,
    )
    return StatePatchConsistencyGateOutcome(
        blocked=True,
        repair_budget_exhausted=repair_budget_exhausted,
    )
