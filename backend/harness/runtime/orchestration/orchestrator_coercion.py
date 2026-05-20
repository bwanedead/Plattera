"""Coercion helpers for ``run_orchestration_kernel_loop`` wire shapes."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ...execution.contracts import ExecutionStepRequest
from ...mission_state import MissionState, ResolutionState
from .action_sequence import effective_actions
from .contracts import ActionPlan, SharedStateProjection, TerminalEvaluation


def coerce_projection(value: Any) -> SharedStateProjection | None:
    if value is None:
        return None
    if isinstance(value, SharedStateProjection):
        return value
    if isinstance(value, dict):
        mission_state = value.get("mission_state")
        resolution_state = value.get("resolution_state")
        if not isinstance(mission_state, MissionState) or not isinstance(resolution_state, ResolutionState):
            return None
        return SharedStateProjection(
            mission_state=mission_state,
            resolution_state=resolution_state,
            latest_refs=dict(value.get("latest_refs") or {}),
            active_item_id=str(value.get("active_item_id") or "").strip() or None,
        )
    mission_state = getattr(value, "mission_state", None)
    resolution_state = getattr(value, "resolution_state", None)
    if not isinstance(mission_state, MissionState) or not isinstance(resolution_state, ResolutionState):
        return None
    latest_refs = getattr(value, "latest_refs", {})
    active_item_id = getattr(value, "active_item_id", None)
    return SharedStateProjection(
        mission_state=mission_state,
        resolution_state=resolution_state,
        latest_refs=dict(latest_refs) if isinstance(latest_refs, dict) else {},
        active_item_id=str(active_item_id or "").strip() or None,
    )


def coerce_kernel_action_plan(value: Any) -> ActionPlan | None:
    if value is None:
        return None
    if isinstance(value, ActionPlan):
        return _normalize_no_dispatch_action_plan(value)
    if isinstance(value, dict):
        raw_sp = value.get("state_patch")
        sp_coerced: dict[str, Any] | None = dict(raw_sp) if isinstance(raw_sp, dict) else None
        raw_cje = value.get("continuity_journal_entry")
        cje: dict[str, Any] | None = dict(raw_cje) if isinstance(raw_cje, dict) else None
        raw_hitl = value.get("hitl_request")
        hitl_req: dict[str, Any] | None = dict(raw_hitl) if isinstance(raw_hitl, dict) else None
        raw_cons = value.get("hitl_consumed_prompt_ids")
        if raw_cons is None:
            cons = ()
        elif isinstance(raw_cons, list):
            cons = tuple(str(x).strip() for x in raw_cons if isinstance(x, str) and str(x).strip())
        elif isinstance(raw_cons, tuple):
            cons = tuple(str(x).strip() for x in raw_cons if isinstance(x, str) and str(x).strip())
        else:
            cons = ()
        opm = value.get("operator_progress_message")
        opm_out: str | None = str(opm).strip() if opm is not None else None
        if opm_out == "":
            opm_out = None
        return _normalize_no_dispatch_action_plan(ActionPlan(
            action_type=str(value.get("action_type") or "").strip() or None,
            action_inputs=dict(value.get("action_inputs") or {}),
            idempotency_key=str(value.get("idempotency_key") or ""),
            skip_execution=bool(value.get("skip_execution", False)),
            wait_for_human=bool(value.get("wait_for_human", False)),
            complete_run=bool(value.get("complete_run", False)),
            hitl_request=hitl_req,
            hitl_consumed_prompt_ids=cons,
            rationale=str(value.get("rationale") or "").strip() or None,
            state_patch=sp_coerced,
            continuity_journal_entry=cje,
            operator_progress_message=opm_out,
        ))
    action_inputs = getattr(value, "action_inputs", None)
    raw_sp = getattr(value, "state_patch", None)
    sp_obj = dict(raw_sp) if isinstance(raw_sp, dict) else None
    raw_cje = getattr(value, "continuity_journal_entry", None)
    cje_obj = dict(raw_cje) if isinstance(raw_cje, dict) else None
    raw_hitl = getattr(value, "hitl_request", None)
    hitl_obj = dict(raw_hitl) if isinstance(raw_hitl, dict) else None
    raw_cons = getattr(value, "hitl_consumed_prompt_ids", ())
    cons_attr: tuple[str, ...] = ()
    if isinstance(raw_cons, list):
        cons_attr = tuple(str(x).strip() for x in raw_cons if isinstance(x, str) and str(x).strip())
    elif isinstance(raw_cons, tuple):
        cons_attr = tuple(str(x).strip() for x in raw_cons if isinstance(x, str) and str(x).strip())
    opm_raw = getattr(value, "operator_progress_message", None)
    opm_attr: str | None = str(opm_raw).strip() if opm_raw is not None else None
    if opm_attr == "":
        opm_attr = None
    return _normalize_no_dispatch_action_plan(ActionPlan(
        action_type=str(getattr(value, "action_type", "") or "").strip() or None,
        action_inputs=action_inputs if isinstance(action_inputs, dict) else {},
        idempotency_key=str(getattr(value, "idempotency_key", "") or ""),
        skip_execution=bool(getattr(value, "skip_execution", False)),
        wait_for_human=bool(getattr(value, "wait_for_human", False)),
        complete_run=bool(getattr(value, "complete_run", False)),
        hitl_request=hitl_obj,
        hitl_consumed_prompt_ids=cons_attr,
        rationale=str(getattr(value, "rationale", "") or "").strip() or None,
        state_patch=sp_obj,
        continuity_journal_entry=cje_obj,
        operator_progress_message=opm_attr,
    ))


def _normalize_no_dispatch_action_plan(action_plan: ActionPlan) -> ActionPlan:
    """Promote unambiguous sparse no-dispatch turns to ``skip_execution=True``.

    This keeps generic runtime adapters aligned with the parser-backed LLM seam:
    if a turn omits ``action_type`` but authors durable state or HITL transport,
    it is mechanically a no-dispatch turn rather than a deferred patch.
    """
    if action_plan.complete_run or effective_actions(action_plan) or action_plan.skip_execution:
        return action_plan
    if action_plan.state_patch is None and action_plan.hitl_request is None:
        return action_plan
    return replace(action_plan, skip_execution=True)


def coerce_step_request(value: Any, *, session_id: str) -> ExecutionStepRequest | None:
    if value is None:
        return None
    if isinstance(value, ExecutionStepRequest):
        return value
    if isinstance(value, ActionPlan):
        if value.action_type is None:
            return None
        return ExecutionStepRequest(
            session_id=session_id,
            action_id=value.action_type,
            inputs=dict(value.action_inputs),
            idempotency_key=value.idempotency_key,
        )
    if isinstance(value, dict):
        action_type = value.get("action_type")
        inputs = value.get("inputs")
        if action_type is None:
            return None
        return ExecutionStepRequest(
            session_id=str(value.get("session_id") or session_id),
            action_id=action_type,
            inputs=inputs if isinstance(inputs, dict) else {},
            idempotency_key=str(value.get("idempotency_key") or ""),
        )
    action_type = getattr(value, "action_type", None)
    inputs = getattr(value, "inputs", None)
    if action_type is None:
        return None
    return ExecutionStepRequest(
        session_id=str(getattr(value, "session_id", None) or session_id),
        action_id=action_type,
        inputs=inputs if isinstance(inputs, dict) else {},
        idempotency_key=str(getattr(value, "idempotency_key", "") or ""),
    )


def coerce_terminal_evaluation(value: Any) -> TerminalEvaluation | None:
    if value is None:
        return None
    if isinstance(value, TerminalEvaluation):
        return value
    if isinstance(value, dict):
        terminal_class = value.get("terminal_class")
        reason_code = str(value.get("reason_code") or "").strip()
        if terminal_class is None or not reason_code:
            return None
        return TerminalEvaluation(terminal_class=terminal_class, reason_code=reason_code)
    terminal_class = getattr(value, "terminal_class", None)
    reason_code = str(getattr(value, "reason_code", "") or "").strip()
    if terminal_class is None or not reason_code:
        return None
    return TerminalEvaluation(terminal_class=terminal_class, reason_code=reason_code)
