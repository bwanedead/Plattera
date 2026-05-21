"""Orchestrator hooks for generic pinned-ref hydration and pin mutations."""

from __future__ import annotations

import logging
from typing import Any

from ...execution.contracts import ExecutionState, ExecutionStepRequest
from ...execution.session import ExecutionSessionManager
from ..memory import LoopMemoryState
from .contracts import ActionPlan
from .hydrate_next import HYDRATE_ARTIFACT_REFS_ACTION_ID
from .hydrate_next_hooks import _attach_hydration_result
from .orchestrator_turn import accumulate_image_evidence
from .pinned_refs import (
    MAX_PINNED_REFS,
    active_pinned_rows,
    apply_pin_updates,
)

_LOG = logging.getLogger(__name__)


def apply_pin_refs_from_action_plan(
    *,
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
    iteration: int,
) -> None:
    if not action_plan.pin_refs and not action_plan.unpin_refs:
        return
    loop_memory.continuity.pinned_refs = apply_pin_updates(
        loop_memory.continuity.pinned_refs,
        pin_refs=action_plan.pin_refs,
        unpin_refs=action_plan.unpin_refs,
        current_turn=iteration,
    )


def _refs_already_scheduled_for_hydration(loop_memory: LoopMemoryState) -> set[str]:
    scheduled: set[str] = set()
    pending = loop_memory.continuity.pending_agent_hydration
    if isinstance(pending, dict):
        for ref in list(pending.get("resolved_refs") or []):
            text = str(ref).strip()
            if text:
                scheduled.add(text)
        for ref in list(pending.get("requested_refs") or []):
            text = str(ref).strip()
            if text:
                scheduled.add(text)
    pinned_record = loop_memory.continuity.pinned_refs_hydration
    if isinstance(pinned_record, dict):
        for ref in list(pinned_record.get("refs") or []):
            text = str(ref).strip()
            if text:
                scheduled.add(text)
    return scheduled


def surface_active_pinned_refs_before_choose_action(
    *,
    loop_memory: LoopMemoryState,
    session_manager: ExecutionSessionManager,
    session_id: str,
    request_id_prefix: str,
    run_id: str,
    iteration: int,
) -> None:
    """Auto-hydrate active pinned refs once per turn (bounded, no duplicate refs)."""
    active = active_pinned_rows(loop_memory.continuity.pinned_refs, current_turn=iteration)
    if not active:
        loop_memory.continuity.pinned_refs_hydration = None
        return

    scheduled = _refs_already_scheduled_for_hydration(loop_memory)
    refs = [row["ref"] for row in active if row["ref"] not in scheduled]
    refs = refs[:MAX_PINNED_REFS]
    if not refs:
        loop_memory.continuity.pinned_refs_hydration = None
        return

    record: dict[str, Any] = {
        "refs": refs,
        "status": "surfaced",
        "surfaced_iteration": int(iteration),
        "hydrated_results": [],
        "hydration_errors": [],
    }
    idem = f"{request_id_prefix}:iter:{int(iteration)}:pinned_refs_hydrate"
    req = ExecutionStepRequest(
        session_id=session_id,
        action_id=HYDRATE_ARTIFACT_REFS_ACTION_ID,
        inputs={"ref_ids": refs},
        idempotency_key=idem,
        run_id=run_id or None,
    )
    try:
        step_result = session_manager.step(req)
    except Exception:  # noqa: BLE001 — compact failure, do not crash run
        _LOG.warning("pinned_refs_hydration_dispatch_failed", exc_info=True)
        record["hydration_errors"] = [{"reason_code": "hydration_dispatch_exception"}]
    else:
        if getattr(step_result, "execution_state", None) == ExecutionState.EXECUTED:
            accumulate_image_evidence(loop_memory=loop_memory, step_result=step_result)
        _attach_hydration_result(record, step_result)

    loop_memory.continuity.pinned_refs_hydration = record


def clear_surfaced_pinned_hydration(*, loop_memory: LoopMemoryState) -> None:
    record = loop_memory.continuity.pinned_refs_hydration
    if isinstance(record, dict) and str(record.get("status") or "") == "surfaced":
        loop_memory.continuity.pinned_refs_hydration = None
