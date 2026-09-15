"""Pre-dispatch mission-framing consistency gate.

Previews the live state_patch merge, then blocks dispatch when the effective
mission would enter or continue resolution-grade posture without authored
objective and success conditions. Does not invent framing content.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from harness.mission_state import MissionState
from harness.mission_state.mission_framing_consistency import (
    REASON_MISSION_FRAMING_REQUIRED,
    MissionFramingConsistencyResult,
    evaluate_mission_framing_consistency,
)
from harness.runtime.memory import LoopMemoryState

from .action_sequence import effective_actions
from .contracts import ActionPlan
from .lifecycle import OrchestrationLifecycle, TurnCompletionObserver
from .orchestrator_policy_block import action_id_for_plan
from .orchestrator_turn import observe_turn_completed, record_turn_continuity
from .resume_checkpointing import write_resume_checkpoint
from .state_patch_apply import _build_state_patch_feedback
from .state_patch_consistency import (
    MAX_IDENTICAL_TERMINAL_ROW_CONFLICT_REJECTIONS,
    StatePatchConsistencyGateOutcome,
    preview_state_patch_merge,
)
from .trace_collector import KernelTraceCollector

_LOG = logging.getLogger(__name__)

REASON_MISSION_FRAMING_CONSISTENCY_REPAIR_BUDGET_EXHAUSTED = (
    "mission_framing_consistency_repair_budget_exhausted"
)
GATE_NAME = "pre_dispatch_mission_framing_consistency"

_REPAIR_HINT = (
    "Mission framing is incomplete for the effective posture. "
    "Either author a real nonblank mission.objective and at least one typed "
    "mission.success_conditions row and continue, or honestly return to "
    "work_universe_posture initial|partial with motion_posture=inventory if "
    "readiness was premature. The harness does not invent that framing and "
    "does not prefer either path. Do not write placeholder or fabricated "
    "framing merely to satisfy this rail."
)
_REPAIR_TARGETS = ("author_mission_framing_or_return_to_inventory",)


def plan_attempts_tool_dispatch_publish_or_completion(action_plan: ActionPlan) -> bool:
    """True for tool rows, publish actions, or complete_run. HITL-only is not dispatch."""
    if action_plan.complete_run:
        return True
    if action_plan.skip_execution:
        return False
    return bool(effective_actions(action_plan))


def evaluate_plan_mission_framing_consistency(
    *,
    mission_state: MissionState,
    resolution_state: Any,
    action_plan: ActionPlan,
) -> MissionFramingConsistencyResult | None:
    """Preview the proposed sparse patch, then evaluate the framing predicate."""
    state_patch = action_plan.state_patch if isinstance(action_plan.state_patch, Mapping) else None
    preview = preview_state_patch_merge(
        mission_state=mission_state,
        resolution_state=resolution_state,
        state_patch=state_patch,
    )
    effective_ms = preview[0] if preview is not None else mission_state
    return evaluate_mission_framing_consistency(
        persisted=mission_state,
        effective=effective_ms,
        attempts_tool_dispatch_publish_or_completion=(
            plan_attempts_tool_dispatch_publish_or_completion(action_plan)
        ),
    )


def _parse_same_conflict_streak(raw: Any) -> int:
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
    framing_identity: str,
) -> int:
    previous = previous_feedback if isinstance(previous_feedback, Mapping) else {}
    reason_code = previous.get("reason_code")
    conflict_identity = previous.get("conflict_identity")
    if (
        type(reason_code) is str
        and reason_code == REASON_MISSION_FRAMING_REQUIRED
        and type(conflict_identity) is str
        and conflict_identity == framing_identity
    ):
        prev = _parse_same_conflict_streak(previous.get("same_conflict_streak"))
        return min(prev + 1, MAX_IDENTICAL_TERMINAL_ROW_CONFLICT_REJECTIONS)
    return 1


def _framing_feedback_detail(
    result: MissionFramingConsistencyResult,
    *,
    same_conflict_streak: int,
) -> dict[str, Any]:
    payload = result.as_dict()
    return {
        "failing_path": "mission",
        "repair_hint": _REPAIR_HINT,
        "repair_targets": list(_REPAIR_TARGETS),
        "missing_fields": payload["missing_fields"],
        "effective_work_universe_posture": payload["effective_work_universe_posture"],
        "effective_motion_posture": payload["effective_motion_posture"],
        "conflict_identity": result.framing_identity(),
        "same_conflict_streak": int(same_conflict_streak),
    }


def record_mission_framing_consistency_rejection(
    *,
    loop_memory: LoopMemoryState,
    tracer: KernelTraceCollector | None,
    iteration: int,
    result: MissionFramingConsistencyResult,
) -> int:
    """Record bounded rejected feedback without mutating mission/resolution."""
    same_conflict_streak = _next_same_conflict_streak(
        loop_memory.continuity.state_patch_feedback,
        framing_identity=result.framing_identity(),
    )
    detail = _framing_feedback_detail(
        result,
        same_conflict_streak=same_conflict_streak,
    )
    loop_memory.continuity.state_patch_feedback = _build_state_patch_feedback(
        loop_memory.continuity.state_patch_feedback,
        outcome="rejected",
        iteration=iteration,
        reason_code=REASON_MISSION_FRAMING_REQUIRED,
        message="effective mission framing is incomplete for the proposed posture",
        detail=detail,
        gate=GATE_NAME,
        carry_prior_repair_bundle=False,
    )
    if tracer is not None:
        tracer.emit_state_patch_outcome(
            iteration=iteration,
            outcome="rejected",
            reason_code=REASON_MISSION_FRAMING_REQUIRED,
            message="mission_framing_required",
            detail=detail,
            gate=GATE_NAME,
        )
    return same_conflict_streak


def block_incomplete_mission_framing_before_dispatch(
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
    """Return a typed gate outcome when blocked; ``None`` when framing is sufficient."""
    result = evaluate_plan_mission_framing_consistency(
        mission_state=loop_memory.continuity.mission_state,
        resolution_state=loop_memory.continuity.resolution_state,
        action_plan=action_plan,
    )
    if result is None:
        return None

    same_conflict_streak = record_mission_framing_consistency_rejection(
        loop_memory=loop_memory,
        tracer=tracer,
        iteration=iteration,
        result=result,
    )
    repair_budget_exhausted = (
        same_conflict_streak >= MAX_IDENTICAL_TERMINAL_ROW_CONFLICT_REJECTIONS
    )
    reason_code = (
        REASON_MISSION_FRAMING_CONSISTENCY_REPAIR_BUDGET_EXHAUSTED
        if repair_budget_exhausted
        else REASON_MISSION_FRAMING_REQUIRED
    )
    terminal_decision = (
        REASON_MISSION_FRAMING_CONSISTENCY_REPAIR_BUDGET_EXHAUSTED
        if repair_budget_exhausted
        else "mission_framing_consistency_blocked"
    )

    _LOG.info(
        "KERNEL pre_dispatch_mission_framing_consistency_blocked ► reason_code=%s "
        "missing_fields=%s same_conflict_streak=%s repair_budget_exhausted=%s",
        reason_code,
        list(result.missing_fields),
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
