from __future__ import annotations

import logging
from typing import Any, Callable

from agent_kernel.session import KernelSessionManager
from agent_kernel.models import KernelStepRequest, StepExecutionState

from ..terminal_taxonomy import TerminalClass
from .contracts import (
    ClosureEvaluation,
    DomainPack,
    KernelLoopResult,
    MoveDecision,
    OrchestratorContext,
)
from .loop_memory import LoopMemoryState
from .progress import evaluate_progress
from .trace_collector import KernelTraceCollector

_LOG = logging.getLogger(__name__)

# Move types that signal a dead-end or invalid plan (increment invalid_plan_strikes).
_STRIKE_MOVE_TYPES = frozenset({"mark_blocked"})
# Move types that skip execution phase (no KernelSessionManager.step call).
_SKIP_EXEC_MOVE_TYPES = frozenset({"mark_blocked", "mark_resolved_no_edit", "skip_no_action"})


def run_orchestration_kernel_loop(
    *,
    domain_pack: DomainPack,
    session_manager: KernelSessionManager,
    session_id: str,
    run_artifact_ref: str | None,
    request_id_prefix: str,
    dossier_id: str | None,
    max_iterations: int,
    max_no_progress_iterations: int,
    max_invalid_plan_attempts: int,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    resume_hitl_response: dict[str, Any] | None = None,
) -> KernelLoopResult:
    """Drive the phase grammar loop with domain_pack as the content + policy surface.

    Phase grammar per iteration:
      Pre-phase: if hitl_state == "answered_unintegrated" → hook 9 (integrate feedback)
      Phase 2:  refresh     → hook 2
      Phase 3:  project     → hook 3 (kernel writes work-state atomically)
      Phase 4:  select-focus (kernel uses ranked list from hook 3; ephemeral)
      [no focus → phase 8 → terminalize-or-continue]
      Phase 5a: build_focus_packet → hook 4
      Phase 5b: resolve_move       → hook 5
      Phase 5c: compile_move       → hook 6
      Phase 6:  execute (kernel dispatches via KernelSessionManager.step)
      Phase 7:  supply_progress_metrics → hook 7 + shared evaluate_progress
      Phase 8:  supply_closure_rules    → hook 8
      Phase 9:  terminalize-or-continue (kernel)

    Phase 1 (orient) runs once before the loop.

    The kernel owns: focus state, HitlState, stagnation/progress counters,
    evidence_signal_counter, TerminalDecision emission.
    Domain pack owns: work-item schema, evidence assembly, move selection,
    compilation, closure rules.
    """
    loop_memory = LoopMemoryState()
    # P3: pre-seed HITL state so the first iteration's pre-phase fires integrate_feedback.
    if isinstance(resume_hitl_response, dict) and resume_hitl_response:
        loop_memory.hitl_state = "answered_unintegrated"
        loop_memory.pending_feedback_response = resume_hitl_response
        _LOG.info("TX_KERNEL resume_hitl_preseeded ► request_id=%s", request_id_prefix)

    context = OrchestratorContext(
        session_manager=session_manager,
        session_id=session_id,
        loop_memory=loop_memory,
        request_id_prefix=request_id_prefix,
        dossier_id=dossier_id,
    )

    # Phase 11 D1: live trace collector — accumulates RawTraceEvent dicts per phase.
    tracer = KernelTraceCollector(session_id=session_id, request_id=request_id_prefix)
    tracer.emit_request_start(
        dossier_id=dossier_id,
        max_iterations=max_iterations,
        run_artifact_ref=run_artifact_ref,
    )

    # Phase 1: Orient — runs once at loop start.
    _LOG.info("TX_KERNEL orient ► request_id=%s", request_id_prefix)
    domain_pack.orient(context)

    for iterations in range(1, max_iterations + 1):
        loop_memory.iterations = iterations
        _LOG.info(
            "TX_KERNEL iteration ► request_id=%s iter=%s hitl_state=%s",
            request_id_prefix,
            iterations,
            loop_memory.hitl_state,
        )
        tracer.emit_iteration_start(iteration=iterations, hitl_state=loop_memory.hitl_state)

        # Pre-phase: integrate feedback if waiting for integration.
        if (
            loop_memory.hitl_state == "answered_unintegrated"
            and loop_memory.pending_feedback_response is not None
        ):
            _LOG.info("TX_KERNEL hook9_integrate_feedback ► iter=%s", iterations)
            result = domain_pack.integrate_feedback(context, loop_memory.pending_feedback_response)
            if result.integrated:
                loop_memory.hitl_state = "consumed"
                loop_memory.pending_feedback_response = None
                # Integration counts as new evidence arrival.
                loop_memory.evidence_signal_counter += 1
                _LOG.info("TX_KERNEL feedback_integrated ► iter=%s", iterations)
            else:
                _LOG.warning("TX_KERNEL feedback_integration_failed ► iter=%s", iterations)

        # Phase 2: Refresh — conditional on kernel-owned pending_refresh flag or first iteration.
        if iterations == 1 or loop_memory.pending_refresh:
            _LOG.info(
                "TX_KERNEL hook2_refresh ► iter=%s pending_refresh=%s",
                iterations,
                loop_memory.pending_refresh,
            )
            refresh_result = domain_pack.refresh(context)
            if not refresh_result.execution_succeeded:
                reason = refresh_result.refusal_reason or "refresh_step_refused"
                _LOG.warning("TX_KERNEL refresh_refused ► iter=%s reason=%s", iterations, reason)
                return _make_result(
                    loop_memory=loop_memory,
                    terminal_class="failed",
                    reason_code=reason,
                    iterations=iterations,
                    session_id=session_id,
                    run_artifact_ref=run_artifact_ref,
                    tracer=tracer,
                )
            loop_memory.latest_refs = dict(refresh_result.latest_refs)
        else:
            _LOG.info("TX_KERNEL hook2_refresh_skipped ► iter=%s no_pending_refresh", iterations)

        # Phase 3: Project — kernel writes work-state atomically.
        _LOG.info("TX_KERNEL hook3_project ► iter=%s", iterations)
        projection = domain_pack.project(context)
        loop_memory.work_item_collection = list(projection.work_item_collection)
        loop_memory.blocker_surface = list(projection.blocker_surface)
        loop_memory.closure_posture_summary = dict(projection.closure_posture_summary)
        # Ephemeral — consumed only in phase 4; discarded after selection.
        ranked_list = list(projection.ranked_work_item_list)

        # Phase 4: Select focus (kernel).
        prev_focus_key = loop_memory.active_focus_key
        selected_focus_key = _select_focus(
            ranked_work_item_list=ranked_list,
            current_focus_key=loop_memory.active_focus_key,
        )
        if selected_focus_key != prev_focus_key:
            loop_memory.active_focus_key = selected_focus_key
            loop_memory.focus_stagnation_streak = 0
        tracer.emit_focus_selected(
            iteration=iterations,
            focus_key=selected_focus_key,
            candidates=ranked_list,
            stagnation_streak=loop_memory.focus_stagnation_streak,
        )

        # If no actionable focus: go straight to decide without executing.
        if selected_focus_key is None:
            _LOG.info("TX_KERNEL no_actionable_focus ► iter=%s going_to_decide", iterations)
            # No-focus iteration makes no progress; advance stagnation counters so the
            # stagnation brake can fire instead of silently burning max_iterations.
            loop_memory.no_progress_streak += 1
            loop_memory.focus_stagnation_streak += 1
            closure_eval = domain_pack.supply_closure_rules(context)
            terminal = _decide_terminal(
                closure_eval=closure_eval,
                loop_memory=loop_memory,
                max_no_progress=max_no_progress_iterations,
                max_invalid_plan=max_invalid_plan_attempts,
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
            )
            if terminal is not None:
                return terminal
            # Domain says "not done yet" with no actionable focus — continue loop.
            continue

        # Phase 5a: Build focus packet.
        _LOG.info("TX_KERNEL hook4_build_focus_packet ► iter=%s focus=%s", iterations, selected_focus_key)
        focus_packet = domain_pack.build_focus_packet(context, selected_focus_key)

        # Phase 5b: Resolve move.
        _LOG.info("TX_KERNEL hook5_resolve_move ► iter=%s focus=%s", iterations, selected_focus_key)
        move_decision = domain_pack.resolve_move(context, focus_packet)
        _move_payload = move_decision.domain_move_payload or {}
        _evidence_req = _move_payload.get("evidence_request") if isinstance(_move_payload.get("evidence_request"), dict) else None
        tracer.emit_move_resolved(
            iteration=iterations,
            move_type=move_decision.move_type,
            focus_key=move_decision.focus_key,
            rationale=move_decision.rationale,
            evidence_kind=str((_evidence_req or {}).get("kind") or "").strip().lower() or None,
            used_hitl_feedback=bool(_move_payload.get("used_hitl_feedback")) if "used_hitl_feedback" in _move_payload else None,
        )

        # Increment strike counter for dead-end moves.
        if move_decision.move_type in _STRIKE_MOVE_TYPES:
            loop_memory.invalid_plan_strikes += 1
            _LOG.info(
                "TX_KERNEL invalid_plan_strike ► iter=%s move=%s strikes=%s",
                iterations,
                move_decision.move_type,
                loop_memory.invalid_plan_strikes,
            )

        # Phase 5c: Compile move → execution plan.
        _LOG.info("TX_KERNEL hook6_compile_move ► iter=%s move=%s", iterations, move_decision.move_type)
        execution_plan = domain_pack.compile_move(context, move_decision)
        tracer.emit_plan_compiled(
            iteration=iterations,
            action_type=str(execution_plan.action_type),
            idempotency_key=execution_plan.idempotency_key,
        )

        # HITL short-circuit via hitl_intent_flag on MoveExecutionPlan.
        if execution_plan.hitl_intent_flag:
            feedback_prompt_id = (
                str(execution_plan.action_inputs.get("feedback_prompt_id") or "").strip() or None
            )
            loop_memory.hitl_state = "waiting"
            loop_memory.pending_feedback_prompt_id = feedback_prompt_id
            _LOG.info(
                "TX_KERNEL hitl_intent_flag ► iter=%s prompt_id=%s", iterations, feedback_prompt_id
            )
            return _make_result(
                loop_memory=loop_memory,
                terminal_class="waiting_human",
                reason_code="waiting_human_feedback",
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
            )

        # Declare done short-circuit.
        if execution_plan.declare_done_flag:
            _LOG.info("TX_KERNEL declare_done ► iter=%s", iterations)
            return _make_result(
                loop_memory=loop_memory,
                terminal_class="completed",
                reason_code="domain_declare_done",
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
            )

        # Phase 6: Execute (kernel dispatches).
        skip = execution_plan.skip_execution or move_decision.move_type in _SKIP_EXEC_MOVE_TYPES
        if skip:
            tracer.emit_execution_result(
                iteration=iterations,
                action_type=str(execution_plan.action_type),
                execution_state="skipped",
                reason_code=None,
                retryable=None,
                refs_delta=None,
            )
        else:
            _LOG.info(
                "TX_KERNEL execute ► iter=%s action=%s", iterations, execution_plan.action_type
            )
            step_result = session_manager.step(
                KernelStepRequest(
                    session_id=session_id,
                    action_type=execution_plan.action_type,
                    inputs=execution_plan.action_inputs,
                    idempotency_key=execution_plan.idempotency_key,
                )
            )
            if step_result.execution_state != StepExecutionState.EXECUTED:
                _refusal = step_result.refusal
                reason = (
                    _refusal.reason_code
                    if _refusal is not None
                    else "step_execution_refused"
                )
                _LOG.warning("TX_KERNEL step_refused ► iter=%s reason=%s", iterations, reason)
                _retryable = _refusal.retryable if _refusal is not None else False
                tracer.emit_execution_result(
                    iteration=iterations,
                    action_type=str(execution_plan.action_type),
                    execution_state="refused",
                    reason_code=reason,
                    retryable=_retryable,
                    refs_delta=None,
                )
                # Retryable tool refusals (e.g. anchor-not-found, bad inputs) should not
                # terminate the loop immediately — the refused step is recorded in the run
                # artifact so the next context packet can inform the LLM. Advance stagnation
                # counters and continue; supply_closure_rules decides when to stop.
                # Non-retryable / budget / invariant refusals remain immediately fatal.
                _is_retryable_tool_refusal = (
                    _refusal is not None
                    and _refusal.retryable
                    and not _refusal.blocked_by_budget
                    and not _refusal.blocked_by_invariant
                )
                if not _is_retryable_tool_refusal:
                    return _make_result(
                        loop_memory=loop_memory,
                        terminal_class="failed",
                        reason_code=reason,
                        iterations=iterations,
                        session_id=session_id,
                        run_artifact_ref=run_artifact_ref,
                        tracer=tracer,
                    )
                # Retryable: sync latest_refs from dashboard if available, then continue.
                # Do NOT increment stagnation here — phase 7 (supply_progress_metrics) will
                # evaluate progress and increment naturally. Double-counting would cause
                # premature stagnation termination.
                # Surface the step record so domain packs can extract rejection context.
                if step_result.dashboard is not None:
                    loop_memory.latest_refs = step_result.dashboard.latest_refs.model_dump(mode="json")
                loop_memory.last_step_refusal_record = (
                    dict(step_result.step_record)
                    if isinstance(step_result.step_record, dict)
                    else None
                )
                _LOG.info(
                    "TX_KERNEL retryable_refusal_continuing ► iter=%s reason=%s",
                    iterations,
                    reason,
                )
            else:
                # Successful execution → kernel flags that a re-observation pass is needed.
                loop_memory.last_step_refusal_record = None  # Clear on success.
                loop_memory.pending_refresh = True
                _exec_refs: dict[str, Any] = {}
                if step_result.dashboard is not None:
                    _exec_refs = step_result.dashboard.latest_refs.model_dump(mode="json")
                    loop_memory.latest_refs = _exec_refs
                tracer.emit_execution_result(
                    iteration=iterations,
                    action_type=str(execution_plan.action_type),
                    execution_state="executed",
                    reason_code=None,
                    retryable=None,
                    refs_delta=_exec_refs,
                )

        # Phase 7: Progress evaluation.
        _LOG.info("TX_KERNEL hook7_supply_progress_metrics ► iter=%s", iterations)
        prev_evidence_counter = loop_memory.evidence_signal_counter
        metrics = domain_pack.supply_progress_metrics(context)

        # Domain-supplied evidence signal → kernel increments counter.
        if metrics.new_evidence_signal:
            loop_memory.evidence_signal_counter += 1

        # Build a metrics view with the current kernel-owned counter for evaluator.
        # The evaluator uses new_evidence_signal bool, not the counter directly.
        delta = evaluate_progress(metrics)

        if delta.reset_refresh:
            loop_memory.pending_refresh = False

        if delta.made_progress:
            loop_memory.no_progress_streak = 0
            loop_memory.focus_stagnation_streak = 0
        else:
            loop_memory.no_progress_streak += 1
            loop_memory.focus_stagnation_streak += 1
        loop_memory.last_progress_reason = delta.reason_code
        _LOG.info(
            "TX_KERNEL progress ► iter=%s progress=%s reason=%s streak=%s",
            iterations,
            delta.made_progress,
            delta.reason_code,
            loop_memory.no_progress_streak,
        )
        tracer.emit_progress_delta(
            iteration=iterations,
            made_progress=delta.made_progress,
            reason_code=delta.reason_code,
            no_progress_streak=loop_memory.no_progress_streak,
            evidence_signal_counter=loop_memory.evidence_signal_counter,
            baseline_blocking_count=metrics.previous_blocking_count,
            current_blocking_count=metrics.current_blocking_count,
            signature_changed=metrics.previous_blocking_signature != metrics.current_blocking_signature,
        )

        # Phase 8: Decide.
        _LOG.info("TX_KERNEL hook8_supply_closure_rules ► iter=%s", iterations)
        closure_eval = domain_pack.supply_closure_rules(context)
        terminal = _decide_terminal(
            closure_eval=closure_eval,
            loop_memory=loop_memory,
            max_no_progress=max_no_progress_iterations,
            max_invalid_plan=max_invalid_plan_attempts,
            iterations=iterations,
            session_id=session_id,
            run_artifact_ref=run_artifact_ref,
            tracer=tracer,
        )
        if terminal is not None:
            return terminal

    # Phase 9: Max iterations exhausted.
    _LOG.info("TX_KERNEL max_iterations_exhausted ► iter=%s", loop_memory.iterations)
    return _make_result(
        loop_memory=loop_memory,
        terminal_class="exhausted",
        reason_code="max_iterations_reached",
        iterations=loop_memory.iterations,
        session_id=session_id,
        run_artifact_ref=run_artifact_ref,
        tracer=tracer,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _select_focus(
    *,
    ranked_work_item_list: list[dict[str, Any]],
    current_focus_key: str | None,
) -> str | None:
    """Kernel phase-4 focus selection.

    Selects the first actionable item from the domain-supplied ranked list.
    An item is actionable if it has a non-empty "focus_key" and is not marked
    as "resolved" or "completed" in its state field.

    Returns None if the ranked list is empty or contains no actionable items.
    """
    non_terminal_states = frozenset(
        {"unknown", "candidate_found", "disputed", "accepted_with_risk", "open", "unresolved"}
    )
    for item in ranked_work_item_list:
        if not isinstance(item, dict):
            continue
        key = str(item.get("focus_key") or "").strip()
        if not key:
            continue
        state = str(item.get("state") or "open").strip().lower()
        if state in non_terminal_states or state not in {"resolved", "completed", "closed", "skipped"}:
            return key
    return None


def _decide_terminal(
    *,
    closure_eval: ClosureEvaluation,
    loop_memory: LoopMemoryState,
    max_no_progress: int,
    max_invalid_plan: int,
    iterations: int,
    session_id: str,
    run_artifact_ref: str | None,
    tracer: KernelTraceCollector,
) -> KernelLoopResult | None:
    """Phase 8 terminal decision.

    Checks kernel loop brakes first (higher priority), then domain closure.
    Returns KernelLoopResult if the run should stop, None to continue.

    Loop brake priority (kernel):
    1. stagnation threshold → exhausted
    2. invalid plan strike threshold → blocked (reason: invalid_refused)
    3. domain_complete → completed
    4. domain signals cannot-proceed → use domain_terminal_class
    """
    # Brake 1: stagnation.
    if loop_memory.no_progress_streak >= max_no_progress:
        _LOG.info(
            "TX_KERNEL brake_stagnation ► iter=%s streak=%s", iterations, loop_memory.no_progress_streak
        )
        return _make_result(
            loop_memory=loop_memory,
            terminal_class="exhausted",
            reason_code="stagnation_threshold_reached",
            iterations=iterations,
            session_id=session_id,
            run_artifact_ref=run_artifact_ref,
            tracer=tracer,
        )

    # Brake 2: invalid plan strikes.
    if loop_memory.invalid_plan_strikes >= max_invalid_plan:
        _LOG.info(
            "TX_KERNEL brake_invalid_plan ► iter=%s strikes=%s",
            iterations,
            loop_memory.invalid_plan_strikes,
        )
        return _make_result(
            loop_memory=loop_memory,
            terminal_class="blocked",
            reason_code="invalid_refused",
            iterations=iterations,
            session_id=session_id,
            run_artifact_ref=run_artifact_ref,
            tracer=tracer,
        )

    # Domain closure: complete.
    if closure_eval.domain_complete:
        _LOG.info("TX_KERNEL domain_complete ► iter=%s reason=%s", iterations, closure_eval.closure_reason_code)
        return _make_result(
            loop_memory=loop_memory,
            terminal_class="completed",
            reason_code=closure_eval.closure_reason_code,
            iterations=iterations,
            session_id=session_id,
            run_artifact_ref=run_artifact_ref,
            tracer=tracer,
        )

    # Domain closure: cannot proceed.
    if closure_eval.domain_terminal_class not in ("completed",) and _is_cannot_proceed(
        closure_eval.closure_reason_code
    ):
        _LOG.info(
            "TX_KERNEL domain_cannot_proceed ► iter=%s class=%s reason=%s",
            iterations,
            closure_eval.domain_terminal_class,
            closure_eval.closure_reason_code,
        )
        return _make_result(
            loop_memory=loop_memory,
            terminal_class=closure_eval.domain_terminal_class,
            reason_code=closure_eval.closure_reason_code,
            iterations=iterations,
            session_id=session_id,
            run_artifact_ref=run_artifact_ref,
            tracer=tracer,
        )

    return None


def _is_cannot_proceed(reason_code: str) -> bool:
    """True when the domain reason_code signals it cannot proceed (not just "not yet done")."""
    cannot_proceed_markers = (
        "impossible",
        "unsupported",
        "invalid_refused",
        "failed",
        "unrecoverable",
        "abort",
    )
    code = reason_code.strip().lower()
    return any(marker in code for marker in cannot_proceed_markers)


def _make_result(
    *,
    loop_memory: LoopMemoryState,
    terminal_class: TerminalClass,
    reason_code: str,
    iterations: int,
    session_id: str,
    run_artifact_ref: str | None,
    tracer: KernelTraceCollector,
) -> KernelLoopResult:
    tracer.emit_terminal(
        iteration=iterations,
        terminal_class=terminal_class,
        reason_code=reason_code,
    )
    return KernelLoopResult(
        terminal_class=terminal_class,
        reason_code=reason_code,
        iterations=iterations,
        session_id=session_id,
        run_artifact_ref=run_artifact_ref,
        latest_refs=dict(loop_memory.latest_refs),
        domain_runtime_state={
            "hitl_state": loop_memory.hitl_state,
            "pending_feedback_prompt_id": loop_memory.pending_feedback_prompt_id,
            "no_progress_streak": loop_memory.no_progress_streak,
            "invalid_plan_strikes": loop_memory.invalid_plan_strikes,
            "evidence_signal_counter": loop_memory.evidence_signal_counter,
        },
        trace_events=tracer.build_raw_events(),
    )
