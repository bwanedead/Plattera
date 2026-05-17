from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from ...execution.contracts import ExecutionState
from ...execution.session import ExecutionSessionManager

from .contracts import ActionPlan, KernelLoopResult, OrchestrationAdapter, OrchestratorContext
from .lifecycle import OrchestrationLifecycle, TurnCompletionObserver
from ..memory import LoopMemoryState
from ..memory.resume_snapshot import build_kernel_resume_snapshot
from ..hitl.request_shape import normalize_hitl_request, validate_hitl_consumed_prompt_ids
from ..hitl.transport import (
    apply_hitl_consumed_prompt_ids,
    clamp_hitl_lists,
    hitl_has_answer_for_prompt,
    hitl_poll_feedback_store,
    hitl_refresh_derived_state,
)
from ..hitl.watch import write_hitl_operator_sidecar
from .hitl_ledger_hooks import (
    make_inbound_hitl_callback,
    record_consumed_hitl,
    record_outbound_hitl,
)
from .user_message_hooks import (
    poll_and_record_user_messages,
    record_consumed_and_deferred_user_messages,
)
from .orchestrator_coercion import (
    coerce_kernel_action_plan,
    coerce_projection,
    coerce_step_request,
    coerce_terminal_evaluation,
)
from .orchestrator_policy import (
    closure_enforcement_failure,
    resolution_inventory_enforcement_failure,
)
from .run_control import build_kernel_loop_result, maybe_exit_for_run_control
from .recoverable_turn_failure import RecoverableTurnFailure
from .orchestrator_turn import (
    accumulate_image_evidence,
    append_kernel_step_result_continuity,
    observe_turn_completed,
    record_turn_continuity,
)
from .state_patch_apply import (
    sync_state_patch_after_committed_gate,
    sync_state_patch_after_step_refusal,
    sync_state_patch_when_no_step_dispatched,
)
from .trace_collector import KernelTraceCollector

_LOG = logging.getLogger(__name__)

_DEFAULT_RECOVERABLE_TURN_FAILURE_BUDGET = 2


def _hitl_loop_kind(opaque_run_context: dict[str, Any]) -> str:
    return str(opaque_run_context.get("hitl_loop_kind") or opaque_run_context.get("loop_kind") or "harness_cli").strip() or "harness_cli"


def _action_id_for_plan(action_plan: ActionPlan) -> str:
    if action_plan.complete_run:
        return "complete_run"
    if action_plan.wait_for_human:
        return "wait_for_human"
    return str(action_plan.action_type or "no_action")


def _materialize_dispatch_idempotency_key(
    action_plan: ActionPlan,
    *,
    request_id_prefix: str,
    iteration: int,
) -> ActionPlan:
    """Host-own transport idempotency for real dispatch turns only."""
    if (
        action_plan.action_type is None
        or action_plan.skip_execution
        or action_plan.wait_for_human
        or action_plan.complete_run
    ):
        return action_plan
    if str(action_plan.idempotency_key).strip():
        return action_plan
    generated = f"{request_id_prefix}:iter:{int(iteration)}:dispatch:{action_plan.action_type}"
    return replace(action_plan, idempotency_key=generated)


def _recoverable_turn_failure_budget(run_ctx: dict[str, Any]) -> int:
    try:
        return max(0, int(run_ctx.get("recoverable_turn_failure_budget", _DEFAULT_RECOVERABLE_TURN_FAILURE_BUDGET)))
    except (TypeError, ValueError):
        return _DEFAULT_RECOVERABLE_TURN_FAILURE_BUDGET


def _write_resume_checkpoint(
    *,
    lifecycle: OrchestrationLifecycle,
    loop_memory: LoopMemoryState,
    session_manager: ExecutionSessionManager,
    session_id: str,
    iteration: int,
) -> None:
    """Best-effort per-turn ``kernel_resume.json`` snapshot; never raises."""
    writer = lifecycle.resume_checkpoint_writer
    if writer is None:
        return
    try:
        snap = build_kernel_resume_snapshot(
            loop_memory=loop_memory,
            session_manager=session_manager,
            session_id=session_id,
            next_iteration=iteration + 1,
        )
        writer(snap)
    except Exception:
        _LOG.warning("resume_checkpoint_write_failed", exc_info=True)


def _handle_policy_block(
    *,
    turn_completion_observer: TurnCompletionObserver | None,
    tracer: KernelTraceCollector,
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
    iteration: int,
    reason_code: str,
    lifecycle: OrchestrationLifecycle,
    session_manager: ExecutionSessionManager,
    session_id: str,
) -> None:
    tracer.emit_execution_result(
        iteration=iteration,
        action_type=_action_id_for_plan(action_plan),
        execution_state="refused",
        reason_code=reason_code,
        retryable=False,
        refs_delta=None,
    )
    sync_state_patch_after_committed_gate(
        loop_memory=loop_memory,
        action_plan=action_plan,
        tracer=tracer,
        iteration=iteration,
        gate="closure_enforcement_blocked",
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
        terminal_decision="closure_enforcement_blocked",
    )
    _write_resume_checkpoint(
        lifecycle=lifecycle,
        loop_memory=loop_memory,
        session_manager=session_manager,
        session_id=session_id,
        iteration=iteration,
    )


def run_orchestration_kernel_loop(
    *,
    orchestration_adapter: OrchestrationAdapter,
    session_manager: ExecutionSessionManager,
    session_id: str,
    run_artifact_ref: str | None,
    request_id_prefix: str,
    run_id: str = "",
    opaque_run_context: dict[str, Any] | None = None,
    max_iterations: int,
    resume_hitl_response: dict[str, Any] | None = None,
    initial_loop_memory: LoopMemoryState | None = None,
    resume_start_iteration: int = 1,
    lifecycle: OrchestrationLifecycle | None = None,
    tracer: KernelTraceCollector | None = None,
) -> KernelLoopResult:
    """Drive the bounded per-run loop with explicit semantic and mechanical collaborators."""
    loop_memory = initial_loop_memory if initial_loop_memory is not None else LoopMemoryState()
    start_iteration = max(1, int(resume_start_iteration))
    active_lifecycle = lifecycle if lifecycle is not None else OrchestrationLifecycle()
    if isinstance(resume_hitl_response, dict) and resume_hitl_response:
        pid = str(resume_hitl_response.get("prompt_id") or "").strip()
        if not pid and initial_loop_memory is not None:
            pid = str(
                initial_loop_memory.hitl.blocking_prompt_id
                or initial_loop_memory.hitl.pending_feedback_prompt_id
                or ""
            ).strip()
        if not pid:
            pid = "resume_injected"
        loop_memory.hitl.answered_hitl_responses.append(
            {"prompt_id": pid, "feedback": dict(resume_hitl_response)}
        )
        loop_memory.hitl.pending_feedback_response = dict(resume_hitl_response)
        loop_memory.hitl.pending_feedback_prompt_id = pid
        hitl_refresh_derived_state(loop_memory.hitl)
        _LOG.info("KERNEL resume_hitl_preseeded ► request_id=%s", request_id_prefix)

    run_ctx = dict(opaque_run_context) if isinstance(opaque_run_context, dict) else {}
    context = OrchestratorContext(
        session_manager=session_manager,
        session_id=session_id,
        loop_memory=loop_memory,
        request_id_prefix=request_id_prefix,
        opaque_run_context=run_ctx,
        prompt_event_observer=active_lifecycle.prompt_event_observer,
        raw_llm_io_observer=active_lifecycle.raw_llm_io_observer,
    )

    tracer = tracer if tracer is not None else KernelTraceCollector(session_id=session_id, request_id=request_id_prefix, run_id=run_id)
    tracer.emit_request_start(
        opaque_run_context=run_ctx,
        max_iterations=max_iterations,
        run_artifact_ref=run_artifact_ref,
    )
    orchestration_adapter.initialize(context)

    def _checkpoint(iter_idx: int) -> None:
        _write_resume_checkpoint(
            lifecycle=active_lifecycle, loop_memory=loop_memory,
            session_manager=session_manager, session_id=session_id, iteration=iter_idx,
        )

    for offset in range(max_iterations):
        iterations = start_iteration + offset
        loop_memory.iterations = iterations
        # Safe boundary: before a new iteration / before choose_action.
        control_result = maybe_exit_for_run_control(
            lifecycle=active_lifecycle,
            loop_memory=loop_memory,
            session_manager=session_manager,
            session_id=session_id,
            run_artifact_ref=run_artifact_ref,
            tracer=tracer,
            iteration=max(1, iterations - 1),
            checkpoint_writer=_checkpoint,
        )
        if control_result is not None:
            return control_result
        tracer.emit_iteration_start(iteration=iterations, hitl_state=loop_memory.hitl.hitl_state)

        hitl_poll_feedback_store(
            posture=loop_memory.hitl,
            loop_kind=_hitl_loop_kind(run_ctx),
            run_id=run_id or request_id_prefix,
            on_inbound=make_inbound_hitl_callback(
                loop_memory=loop_memory, tracer=tracer, iteration=iterations,
            ),
        )
        hitl_refresh_derived_state(loop_memory.hitl)

        # Generic harness-owned user-to-agent message channel (CLI/UI/API).
        # Reads the on-disk message store, ingests new entries into the durable
        # ledger, and emits trace events.  No semantic interpretation here —
        # the agent reads pending messages on the next turn and decides what
        # state changes to make (or defers with a reason).
        poll_and_record_user_messages(
            loop_memory=loop_memory,
            tracer=tracer,
            iteration=iterations,
            loop_kind=_hitl_loop_kind(run_ctx),
            run_id=run_id or request_id_prefix,
        )

        if loop_memory.hitl.hitl_state == "waiting" and loop_memory.hitl.blocking_prompt_id:
            if not hitl_has_answer_for_prompt(loop_memory.hitl, loop_memory.hitl.blocking_prompt_id):
                return build_kernel_loop_result(
                    loop_memory=loop_memory,
                    terminal_class="waiting_human",
                    reason_code="waiting_human_feedback",
                    iterations=iterations,
                    session_id=session_id,
                    run_artifact_ref=run_artifact_ref,
                    tracer=tracer,
                    session_manager=session_manager,
                )

        projection = coerce_projection(orchestration_adapter.sync(context))
        if projection is not None:
            loop_memory.continuity.mission_state = projection.mission_state
            loop_memory.continuity.resolution_state = projection.resolution_state
            if projection.latest_refs:
                loop_memory.continuity.latest_refs = dict(projection.latest_refs)
            loop_memory.continuity.active_item_id = (
                projection.active_item_id
                or projection.resolution_state.active_item_id
                or loop_memory.continuity.active_item_id
            )

        terminal = coerce_terminal_evaluation(orchestration_adapter.evaluate_terminal(context, projection))
        if terminal is not None:
            return build_kernel_loop_result(
                loop_memory=loop_memory,
                terminal_class=terminal.terminal_class,
                reason_code=terminal.reason_code,
                terminal_summary=terminal.terminal_summary,
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
                session_manager=session_manager,
            )

        participant = active_lifecycle.pre_choose_action_participant
        if participant is not None:
            participant.before_choose_action(context, projection, tracer=tracer)

        try:
            action_plan = coerce_kernel_action_plan(orchestration_adapter.choose_action(context, projection))
        except RecoverableTurnFailure as exc:
            failure_record = dict(exc.failure_record)
            loop_memory.turn_recovery.record_failure(failure_record)
            budget = _recoverable_turn_failure_budget(run_ctx)
            _LOG.warning(
                "KERNEL recoverable_turn_failure ► iteration=%s consecutive=%s budget=%s reason=%s",
                iterations,
                loop_memory.turn_recovery.consecutive_failures,
                budget,
                failure_record.get("reason_code"),
            )
            _checkpoint(iterations)
            if loop_memory.turn_recovery.consecutive_failures > budget:
                return build_kernel_loop_result(
                    loop_memory=loop_memory,
                    terminal_class="failed",
                    reason_code="recoverable_turn_failure_budget_exhausted",
                    terminal_summary=str(exc),
                    iterations=iterations,
                    session_id=session_id,
                    run_artifact_ref=run_artifact_ref,
                    tracer=tracer,
                    session_manager=session_manager,
                )
            continue
        # Safe boundary: after choose_action completes / before tool dispatch.
        control_result = maybe_exit_for_run_control(
            lifecycle=active_lifecycle,
            loop_memory=loop_memory,
            session_manager=session_manager,
            session_id=session_id,
            run_artifact_ref=run_artifact_ref,
            tracer=tracer,
            iteration=iterations,
            checkpoint_writer=_checkpoint,
        )
        if control_result is not None:
            return control_result
        if action_plan is None:
            continue
        action_plan = _materialize_dispatch_idempotency_key(
            action_plan,
            request_id_prefix=request_id_prefix,
            iteration=iterations,
        )

        patch_present = bool(action_plan.state_patch)

        try:
            consumed_ids = validate_hitl_consumed_prompt_ids(action_plan.hitl_consumed_prompt_ids)
        except ValueError:
            _LOG.warning("KERNEL invalid hitl_consumed_prompt_ids ► skipping iteration")
            continue
        apply_hitl_consumed_prompt_ids(loop_memory.hitl, consumed_ids)
        record_consumed_hitl(
            loop_memory=loop_memory,
            tracer=tracer,
            iteration=iterations,
            consumed_ids=consumed_ids,
        )

        # Apply user-message acknowledgments (consumed / deferred).  The agent
        # owns interpretation; this just updates ledger status and emits trace.
        record_consumed_and_deferred_user_messages(
            loop_memory=loop_memory,
            tracer=tracer,
            iteration=iterations,
            consumed_ids=action_plan.user_message_consumed_ids,
            defers=action_plan.user_message_defers,
        )

        if action_plan.wait_for_human and action_plan.hitl_request is None:
            _LOG.warning("KERNEL wait_for_human without hitl_request ► skipping iteration")
            continue

        resolution_failure = resolution_inventory_enforcement_failure(
            run_ctx=run_ctx,
            loop_memory=loop_memory,
            action_plan=action_plan,
        )
        if resolution_failure is not None:
            reason_code, message = resolution_failure
            _LOG.info("KERNEL resolution_inventory_blocked ► reason_code=%s message=%s", reason_code, message)
            _handle_policy_block(
                turn_completion_observer=active_lifecycle.turn_completion_observer,
                tracer=tracer,
                loop_memory=loop_memory,
                action_plan=action_plan,
                iteration=iterations,
                reason_code=reason_code,
                lifecycle=active_lifecycle,
                session_manager=session_manager,
                session_id=session_id,
            )
            continue

        if action_plan.hitl_request is not None:
            try:
                norm = normalize_hitl_request(dict(action_plan.hitl_request), iteration=iterations)
            except ValueError as exc:
                _LOG.warning("KERNEL invalid hitl_request ► %s", exc)
                continue
            loop_memory.hitl.pending_hitl_requests.append(norm)
            clamp_hitl_lists(loop_memory.hitl)
            write_hitl_operator_sidecar(
                run_id=run_id or request_id_prefix,
                latest_record=norm,
                pending_snapshot=list(loop_memory.hitl.pending_hitl_requests),
            )
            record_outbound_hitl(
                loop_memory=loop_memory,
                tracer=tracer,
                iteration=iterations,
                prompt_id=str(norm["prompt_id"]),
                request_payload=norm,
                blocking=bool(action_plan.wait_for_human),
            )
            if action_plan.wait_for_human:
                sync_state_patch_after_committed_gate(
                    loop_memory=loop_memory,
                    action_plan=action_plan,
                    tracer=tracer,
                    iteration=iterations,
                    gate="wait_for_human",
                )
                record_turn_continuity(
                    loop_memory=loop_memory,
                    action_plan=action_plan,
                    iteration=iterations,
                    execution_state="wait_for_human",
                    execution_reason_code=None,
                )
                loop_memory.hitl.blocking_prompt_id = str(norm["prompt_id"])
                loop_memory.hitl.pending_feedback_prompt_id = str(norm["prompt_id"])
                hitl_refresh_derived_state(loop_memory.hitl)
                observe_turn_completed(
                    active_lifecycle.turn_completion_observer,
                    iterations,
                    action_plan=action_plan, step_result=None,
                    loop_memory=loop_memory, terminal_decision="wait_for_human",
                )
                _checkpoint(iterations)
                return build_kernel_loop_result(
                    loop_memory=loop_memory,
                    terminal_class="waiting_human",
                    reason_code="waiting_human_feedback",
                    iterations=iterations,
                    session_id=session_id,
                    run_artifact_ref=run_artifact_ref,
                    tracer=tracer,
                    session_manager=session_manager,
                )
            hitl_refresh_derived_state(loop_memory.hitl)
            sync_state_patch_after_committed_gate(
                loop_memory=loop_memory,
                action_plan=action_plan,
                tracer=tracer,
                iteration=iterations,
                gate="hitl_request_async",
            )

        if action_plan.complete_run and action_plan.hitl_request is not None:
            _LOG.warning("KERNEL complete_run with hitl_request ► skipping iteration")
            continue

        closure_failure = closure_enforcement_failure(
            run_ctx=run_ctx,
            loop_memory=loop_memory,
            action_plan=action_plan,
        )
        if closure_failure is not None:
            reason_code, message = closure_failure
            _LOG.info("KERNEL closure_enforcement_blocked ► reason_code=%s message=%s", reason_code, message)
            _handle_policy_block(
                turn_completion_observer=active_lifecycle.turn_completion_observer,
                tracer=tracer,
                loop_memory=loop_memory,
                action_plan=action_plan,
                iteration=iterations,
                reason_code=reason_code,
                lifecycle=active_lifecycle,
                session_manager=session_manager,
                session_id=session_id,
            )
            continue

        if action_plan.complete_run:
            sync_state_patch_after_committed_gate(
                loop_memory=loop_memory,
                action_plan=action_plan,
                tracer=tracer,
                iteration=iterations,
                gate="complete_run",
            )
            record_turn_continuity(
                loop_memory=loop_memory,
                action_plan=action_plan,
                iteration=iterations,
                execution_state="complete_run",
                execution_reason_code=None,
            )
            observe_turn_completed(
                active_lifecycle.turn_completion_observer,
                iterations,
                action_plan=action_plan, step_result=None,
                loop_memory=loop_memory, terminal_decision="complete_run",
            )
            _checkpoint(iterations)
            return build_kernel_loop_result(
                loop_memory=loop_memory,
                terminal_class="completed",
                reason_code="complete_run",
                terminal_summary=str(action_plan.rationale) if action_plan.rationale is not None else None,
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
                session_manager=session_manager,
            )

        step_request = coerce_step_request(action_plan, session_id=session_id)
        if step_request is not None and not action_plan.skip_execution:
            step_result = session_manager.step(step_request)
            append_kernel_step_result_continuity(
                loop_memory=loop_memory,
                iteration=iterations,
                action_type=action_plan.action_type,
                step_result=step_result,
            )
            accumulate_image_evidence(loop_memory=loop_memory, step_result=step_result)
            if step_result.execution_state != ExecutionState.EXECUTED:
                refusal = step_result.refusal
                reason = refusal.reason_code if refusal is not None else "step_execution_refused"
                retryable = refusal.retryable if refusal is not None else False
                tracer.emit_execution_result(
                    iteration=iterations,
                    action_type=str(step_request.action_id),
                    execution_state="refused",
                    reason_code=reason,
                    retryable=retryable,
                    refs_delta=None,
                )
                sync_state_patch_after_step_refusal(
                    loop_memory=loop_memory,
                    tracer=tracer,
                    iteration=iterations,
                    patch_present=patch_present,
                    execution_reason_code=reason,
                    action_plan=action_plan,
                )
                is_retryable = (
                    refusal is not None
                    and refusal.retryable
                    and not refusal.blocked_by_budget
                    and not refusal.blocked_by_invariant
                )
                if not is_retryable:
                    record_turn_continuity(
                        loop_memory=loop_memory,
                        action_plan=action_plan,
                        iteration=iterations,
                        execution_state="refused",
                        execution_reason_code=reason,
                    )
                    observe_turn_completed(
                        active_lifecycle.turn_completion_observer,
                        iterations,
                        action_plan=action_plan, step_result=step_result,
                        loop_memory=loop_memory, terminal_decision="refused",
                    )
                    _checkpoint(iterations)
                    return build_kernel_loop_result(
                        loop_memory=loop_memory,
                        terminal_class="failed",
                        reason_code=reason,
                        iterations=iterations,
                        session_id=session_id,
                        run_artifact_ref=run_artifact_ref,
                        tracer=tracer,
                        session_manager=session_manager,
                    )
                record_turn_continuity(
                    loop_memory=loop_memory,
                    action_plan=action_plan,
                    iteration=iterations,
                    execution_state="refused",
                    execution_reason_code=reason,
                )
                if step_result.dashboard is not None:
                    loop_memory.continuity.latest_refs = step_result.dashboard.latest_refs.model_dump(mode="json")
                observe_turn_completed(
                    active_lifecycle.turn_completion_observer,
                    iterations,
                    action_plan=action_plan, step_result=step_result,
                    loop_memory=loop_memory,
                )
                _checkpoint(iterations)
            else:
                if step_result.dashboard is not None:
                    loop_memory.continuity.latest_refs = step_result.dashboard.latest_refs.model_dump(mode="json")
                tracer.emit_execution_result(
                    iteration=iterations,
                    action_type=str(step_request.action_id),
                    execution_state="executed",
                    reason_code=None,
                    retryable=None,
                    refs_delta=loop_memory.continuity.latest_refs,
                )
                sync_state_patch_after_committed_gate(
                    loop_memory=loop_memory,
                    action_plan=action_plan,
                    tracer=tracer,
                    iteration=iterations,
                    gate="step_executed",
                )
                record_turn_continuity(
                    loop_memory=loop_memory,
                    action_plan=action_plan,
                    iteration=iterations,
                    execution_state="executed",
                    execution_reason_code=None,
                )
                observe_turn_completed(
                    active_lifecycle.turn_completion_observer,
                    iterations,
                    action_plan=action_plan, step_result=step_result,
                    loop_memory=loop_memory,
                )
                _checkpoint(iterations)
        else:
            sync_state_patch_when_no_step_dispatched(
                loop_memory=loop_memory,
                action_plan=action_plan,
                tracer=tracer,
                iteration=iterations,
                patch_present=patch_present,
                skip_execution=action_plan.skip_execution,
            )
            record_turn_continuity(
                loop_memory=loop_memory,
                action_plan=action_plan,
                iteration=iterations,
                execution_state="skipped" if action_plan.skip_execution else "not_dispatched",
                execution_reason_code=None,
            )
            observe_turn_completed(
                active_lifecycle.turn_completion_observer,
                iterations,
                action_plan=action_plan, step_result=None,
                loop_memory=loop_memory,
            )
            _checkpoint(iterations)

    return build_kernel_loop_result(
        loop_memory=loop_memory,
        terminal_class="exhausted",
        reason_code="max_iterations_reached",
        iterations=loop_memory.iterations,
        session_id=session_id,
        run_artifact_ref=run_artifact_ref,
        tracer=tracer,
        session_manager=session_manager,
    )
