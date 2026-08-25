from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from ...execution.session import ExecutionSessionManager

from .contracts import ActionPlan, KernelLoopResult, OrchestrationAdapter, OrchestratorContext
from .lifecycle import OrchestrationLifecycle, TurnCompletionObserver
from ..memory import LoopMemoryState
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
from .action_sequence import effective_actions
from .action_sequence_hooks import (
    clear_stale_action_sequence_result,
    run_action_sequence_turn_if_present,
)
from .hydrate_next_hooks import (
    capture_hydrate_next_after_step,
    clear_surfaced_hydration,
    surface_pending_hydration_before_choose_action,
)
from .pinned_refs_hooks import (
    apply_pin_refs_from_action_plan,
    clear_surfaced_pinned_hydration,
    surface_active_pinned_refs_before_choose_action,
)
from .required_output_gate import (
    MAX_CONSECUTIVE_MISSING_OUTPUT_COMPLETE_ATTEMPTS,
    is_missing_required_output_reason,
    maybe_reset_missing_required_output_counter,
    missing_output_terminal_summary,
    required_output_ref_from_policy,
)
from .orchestrator_coercion import (
    coerce_kernel_action_plan,
    coerce_projection,
    coerce_terminal_evaluation,
)
from .orchestrator_policy import (
    closure_enforcement_failure,
    resolution_inventory_enforcement_failure,
)
from .orchestrator_policy_block import handle_policy_block
from .resume_checkpointing import write_resume_checkpoint
from .run_control import build_kernel_loop_result, maybe_exit_for_run_control
from .recoverable_turn_failure import RecoverableTurnFailure
from .resumable_model_interruption import ResumableModelInterruption
from .orchestrator_turn import observe_turn_completed, record_turn_continuity
from .state_patch_apply import (
    sync_state_patch_after_committed_gate,
    sync_state_patch_when_no_step_dispatched,
)
from .state_patch_consistency import block_contradictory_closed_resolution_before_dispatch
from .trace_collector import KernelTraceCollector

_LOG = logging.getLogger(__name__)

_DEFAULT_RECOVERABLE_TURN_FAILURE_BUDGET = 2


def _hitl_loop_kind(opaque_run_context: dict[str, Any]) -> str:
    return str(opaque_run_context.get("hitl_loop_kind") or opaque_run_context.get("loop_kind") or "harness_cli").strip() or "harness_cli"


def _record_action_turn_observability(*, loop_memory: LoopMemoryState, action_plan: ActionPlan) -> None:
    action_count = len(effective_actions(action_plan))
    if action_count <= 0:
        return
    if action_count == 1:
        loop_memory.continuity.single_action_turn_count += 1
    else:
        loop_memory.continuity.multi_action_turn_count += 1
    loop_memory.continuity.max_actions_in_turn = max(
        loop_memory.continuity.max_actions_in_turn,
        action_count,
    )


def _materialize_dispatch_idempotency_key(
    action_plan: ActionPlan,
    *,
    request_id_prefix: str,
    iteration: int,
) -> ActionPlan:
    """Host-own transport idempotency for real dispatch turns only."""
    actions = effective_actions(action_plan)
    if (
        not actions
        or len(actions) != 1
        or action_plan.skip_execution
        or action_plan.wait_for_human
        or action_plan.complete_run
    ):
        return action_plan
    if str(action_plan.idempotency_key).strip():
        return action_plan
    generated = f"{request_id_prefix}:iter:{int(iteration)}:dispatch:{actions[0].action_type}"
    return replace(action_plan, idempotency_key=generated)


def _recoverable_turn_failure_budget(run_ctx: dict[str, Any]) -> int:
    try:
        return max(0, int(run_ctx.get("recoverable_turn_failure_budget", _DEFAULT_RECOVERABLE_TURN_FAILURE_BUDGET)))
    except (TypeError, ValueError):
        return _DEFAULT_RECOVERABLE_TURN_FAILURE_BUDGET


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

    from .subtasks.delegate_result_hydration import install_delegate_result_hydration

    install_delegate_result_hydration(
        session_manager.executor,
        lambda: loop_memory.continuity.delegate_subtask_results,
    )

    tracer = tracer if tracer is not None else KernelTraceCollector(session_id=session_id, request_id=request_id_prefix, run_id=run_id)
    tracer.emit_request_start(
        opaque_run_context=run_ctx,
        max_iterations=max_iterations,
        run_artifact_ref=run_artifact_ref,
    )
    orchestration_adapter.initialize(context)

    def _checkpoint(iter_idx: int) -> None:
        write_resume_checkpoint(
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

        # Drop a prior-iteration ``hydrate_next`` record once it has been
        # surfaced.  Keeps the lane strictly one-shot and prevents the same
        # hydrated payload from re-appearing in subsequent prompts.
        clear_surfaced_hydration(loop_memory=loop_memory)
        clear_surfaced_pinned_hydration(loop_memory=loop_memory)
        clear_stale_action_sequence_result(loop_memory=loop_memory, iteration=iterations)

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
            maybe_reset_missing_required_output_counter(
                run_ctx=run_ctx,
                loop_memory=loop_memory,
            )
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

        # Surface any agent-authored ``hydrate_next`` request from the prior
        # turn.  Dispatches a single bounded ``hydrate_artifact_refs`` step
        # via the session manager, attaches the result to the pending record,
        # and flips status to ``surfaced`` so the prompt builder includes it.
        surface_pending_hydration_before_choose_action(
            loop_memory=loop_memory,
            session_manager=session_manager,
            session_id=session_id,
            request_id_prefix=request_id_prefix,
            run_id=run_id,
            iteration=iterations,
        )
        surface_active_pinned_refs_before_choose_action(
            loop_memory=loop_memory,
            session_manager=session_manager,
            session_id=session_id,
            request_id_prefix=request_id_prefix,
            run_id=run_id,
            iteration=iterations,
        )

        participant = active_lifecycle.pre_choose_action_participant
        if participant is not None:
            participant.before_choose_action(context, projection, tracer=tracer)

        try:
            action_plan = coerce_kernel_action_plan(orchestration_adapter.choose_action(context, projection))
        except ResumableModelInterruption as exc:
            _LOG.warning(
                "KERNEL resumable_model_interruption ► iteration=%s reason_code=%s",
                iterations,
                exc.reason_code,
            )
            _checkpoint(iterations)
            return build_kernel_loop_result(
                loop_memory=loop_memory,
                terminal_class="paused",
                reason_code=exc.reason_code,
                terminal_summary=exc.terminal_summary,
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
                session_manager=session_manager,
                resumable=True,
                resume_hint=exc.user_guidance,
            )
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

        # Earliest post-parse / pre-dispatch consistency gate: before pin, HITL,
        # user-message, observability, or policy-block paths that may commit patches.
        if block_contradictory_closed_resolution_before_dispatch(
            loop_memory=loop_memory,
            action_plan=action_plan,
            tracer=tracer,
            iteration=iterations,
            lifecycle=active_lifecycle,
            session_manager=session_manager,
            session_id=session_id,
            turn_completion_observer=active_lifecycle.turn_completion_observer,
        ):
            continue

        patch_present = bool(action_plan.state_patch)
        apply_pin_refs_from_action_plan(
            loop_memory=loop_memory,
            action_plan=action_plan,
            iteration=iterations,
        )
        _record_action_turn_observability(loop_memory=loop_memory, action_plan=action_plan)

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
            handle_policy_block(
                turn_completion_observer=active_lifecycle.turn_completion_observer,
                tracer=tracer,
                loop_memory=loop_memory,
                action_plan=action_plan,
                iteration=iterations,
                reason_code=reason_code,
                lifecycle=active_lifecycle,
                session_manager=session_manager,
                session_id=session_id,
                run_ctx=run_ctx,
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
            if is_missing_required_output_reason(reason_code):
                loop_memory.continuity.missing_required_output_complete_attempts += 1
                strike_count = int(loop_memory.continuity.missing_required_output_complete_attempts)
                gate_outcome = (
                    "terminal_blocked"
                    if strike_count >= MAX_CONSECUTIVE_MISSING_OUTPUT_COMPLETE_ATTEMPTS
                    else "repairable_continue"
                )
                handle_policy_block(
                    turn_completion_observer=active_lifecycle.turn_completion_observer,
                    tracer=tracer,
                    loop_memory=loop_memory,
                    action_plan=action_plan,
                    iteration=iterations,
                    reason_code=reason_code,
                    lifecycle=active_lifecycle,
                    session_manager=session_manager,
                    session_id=session_id,
                    run_ctx=run_ctx,
                    required_output_gate_outcome=gate_outcome,
                )
                if (
                    loop_memory.continuity.missing_required_output_complete_attempts
                    >= MAX_CONSECUTIVE_MISSING_OUTPUT_COMPLETE_ATTEMPTS
                ):
                    required_ref = required_output_ref_from_policy(run_ctx) or "output"
                    _checkpoint(iterations)
                    return build_kernel_loop_result(
                        loop_memory=loop_memory,
                        terminal_class="blocked",
                        reason_code="required_output_artifact_unavailable",
                        terminal_summary=missing_output_terminal_summary(
                            required_ref=required_ref,
                            attempts=loop_memory.continuity.missing_required_output_complete_attempts,
                        ),
                        iterations=iterations,
                        session_id=session_id,
                        run_artifact_ref=run_artifact_ref,
                        tracer=tracer,
                        session_manager=session_manager,
                    )
                continue
            handle_policy_block(
                turn_completion_observer=active_lifecycle.turn_completion_observer,
                tracer=tracer,
                loop_memory=loop_memory,
                action_plan=action_plan,
                iteration=iterations,
                reason_code=reason_code,
                lifecycle=active_lifecycle,
                session_manager=session_manager,
                session_id=session_id,
                run_ctx=run_ctx,
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

        seq_outcome = run_action_sequence_turn_if_present(
            loop_memory=loop_memory,
            session_manager=session_manager,
            session_id=session_id,
            action_plan=action_plan,
            iteration=iterations,
            request_id_prefix=request_id_prefix,
            run_id=run_id,
            run_ctx=run_ctx,
            tracer=tracer,
            turn_completion_observer=active_lifecycle.turn_completion_observer,
            patch_present=patch_present,
        )
        if seq_outcome.handled:
            maybe_reset_missing_required_output_counter(
                run_ctx=run_ctx,
                loop_memory=loop_memory,
                action_plan=action_plan,
                executed_meaningful_dispatch=True,
            )
            if seq_outcome.terminal_class:
                _checkpoint(iterations)
                return build_kernel_loop_result(
                    loop_memory=loop_memory,
                    terminal_class=seq_outcome.terminal_class,
                    reason_code=str(seq_outcome.terminal_reason_code or "step_execution_refused"),
                    iterations=iterations,
                    session_id=session_id,
                    run_artifact_ref=run_artifact_ref,
                    tracer=tracer,
                    session_manager=session_manager,
                )
            actions = effective_actions(action_plan)
            if action_plan.hydrate_next and (
                len(actions) > 1 or not any(item.hydrate_next for item in actions)
            ):
                capture_hydrate_next_after_step(
                    loop_memory=loop_memory,
                    action_plan=action_plan,
                    step_result=None,
                    iteration=iterations,
                )
            _checkpoint(iterations)
            continue

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
        capture_hydrate_next_after_step(
            loop_memory=loop_memory,
            action_plan=action_plan,
            step_result=None,
            iteration=iterations,
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
