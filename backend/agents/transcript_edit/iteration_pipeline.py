from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from agent_kernel.models import ActionType, StepExecutionState
from agent_kernel.session import KernelSessionManager
from transcript_edit.persistence import TranscriptionEditPersistenceService

from .contracts import TranscriptEditAgentRunRequest
from .decision_ledger import (
    choose_investigation_focus,
    has_blocking_dispute,
    ledger_snapshot_for_payload,
    update_ledger_from_iteration,
)
from .draft_persistence import persist_agent_edit_draft
from .hitl_feedback import (
    build_human_feedback_prompt,
    build_range_feedback_plan,
    poll_feedback_response,
    range_number_from_feedback,
    viewer_run_id_from_request_prefix,
)
from .image_verification import (
    final_image_sanity_pass_before_promote,
    verify_mapping_critical_with_image,
)
from .loop_runtime import (
    emit_progress,
    read_int,
    read_step_outputs_inline,
    read_str,
)
from .loop_state import TranscriptEditLoopState
from .plan_interpretation import (
    build_apply_inputs_for_plan,
    coerce_findings,
    max_change_class_from_plan,
    plan_has_no_ops,
    plan_has_review_required,
    plan_op_to_display_dict,
)
from .planner import TranscriptEditPlanPlanner
from .result_policy import (
    TranscriptEditDecision,
    TranscriptEditFacts,
    clean_no_promote_decision,
    clean_promoted_decision,
    must_verify_before_terminal,
    should_attempt_promote,
    should_run_stabilization_pass,
)
from .run_reporting import (
    apply_result_payload,
    final_verify_retry_payload,
    human_feedback_needed_payload,
    human_feedback_received_payload,
    human_feedback_reused_payload,
    image_verify_payload,
    image_verify_result_payload,
    open_spans_payload,
    open_spans_result_payload,
    plan_payload,
    plan_result_payload,
    promote_payload,
    stabilize_payload,
    ticker_payload,
)


def handle_clean_iteration(
    *,
    state: TranscriptEditLoopState,
    session_manager: KernelSessionManager,
    session_id: str,
    request: TranscriptEditAgentRunRequest,
    request_id_prefix: str,
    mode: str,
    promote_mode: str,
    min_iterations_before_complete: int,
    iterations: int,
    error_count: int,
    has_disagreements: bool,
    effective_disagreement_hints: dict[str, Any],
    source_transcript_hash: str,
    progress_cb: Callable[[dict[str, Any]], None] | None,
    model: str,
) -> TranscriptEditDecision | None:
    actionable_blocking_closure = _has_actionable_blocking_closure(state.decision_ledger)
    policy_facts = TranscriptEditFacts(
        iterations=iterations,
        mode=mode,
        auto_promote=request.auto_promote,
        error_count=error_count,
        applied_any_edits=state.applied_any_edits,
        applied_non_normalization=state.applied_non_normalization,
        applied_requires_review=state.applied_requires_review,
        used_human_feedback=state.used_human_feedback,
        has_disagreements=has_disagreements,
        has_images=bool(request.source_image_refs),
        min_iterations_before_complete=min_iterations_before_complete,
        actionable_blocking_closure=actionable_blocking_closure,
    )
    needs_terminal_verify = must_verify_before_terminal(policy_facts)
    final_verify_ran = False
    if needs_terminal_verify and state.current_transcript_ref:
        emit_progress(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="image_verify",
                message="Running final mapping-readiness sanity checks against the deed image.",
                latest_refs=state.latest_refs,
            ),
        )
        final_verify_ran = True
        final_verify = final_image_sanity_pass_before_promote(
            session_manager=session_manager,
            session_id=session_id,
            iteration=iterations,
            dossier_id=request.dossier_id,
            source_transcript_ref=state.current_transcript_ref,
            source_image_refs=request.source_image_refs,
            disagreement_hints=effective_disagreement_hints,
            model=model,
            step_fn=_step_kernel_action,
            read_step_outputs_inline_fn=read_step_outputs_inline,
            read_str_fn=read_str,
            read_int_fn=read_int,
        )
        state.latest_refs = final_verify.get("latest_refs", state.latest_refs)
        if not bool(final_verify.get("passed")):
            reason = read_str(final_verify.get("reason")) or "tx_agent_final_image_verify_failed"
            if iterations < request.max_iterations:
                emit_progress(
                    progress_cb,
                    final_verify_retry_payload(
                        iteration=iterations,
                        latest_refs=state.latest_refs,
                    ),
                )
                return None
            return TranscriptEditDecision(status="needs_review", reason_code=reason, review_required=True)
    if should_run_stabilization_pass(policy_facts):
        emit_progress(
            progress_cb,
            stabilize_payload(
                iteration=iterations,
                min_iterations_before_complete=min_iterations_before_complete,
                latest_refs=state.latest_refs,
            ),
        )
        return None
    if (
        request.dossier_id
        and state.current_transcript_ref
        and source_transcript_hash
        and error_count <= 0
    ):
        emit_progress(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="stabilize",
                message="Saving mapping span seeds from the clean transcript for downstream mapping context.",
                latest_refs=state.latest_refs,
            ),
        )
        seeds_step = _step_kernel_action(
            session_manager=session_manager,
            session_id=session_id,
            prefix="tx_span_seeds",
            iteration=iterations,
            action_type=ActionType.TX_SAVE_TRANSCRIPT_SPAN_SEEDS,
            inputs={
                "dossier_id": request.dossier_id,
                "source_transcript_ref": state.current_transcript_ref,
                "source_transcript_hash": source_transcript_hash,
                "max_seeds": 24,
            },
        )
        state.latest_refs = seeds_step.dashboard.latest_refs.model_dump(mode="json")
        seeds_inline = read_step_outputs_inline(seeds_step.step_record)
        span_seeds_ref_candidate = read_str(seeds_inline.get("tx_span_seeds_ref"))
        if span_seeds_ref_candidate:
            state.span_seeds_ref = span_seeds_ref_candidate
    should_promote = should_attempt_promote(policy_facts, promote_mode)
    if should_promote and state.current_transcript_ref:
        emit_progress(
            progress_cb,
            promote_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
            ),
        )
        if not final_verify_ran:
            emit_progress(
                progress_cb,
                ticker_payload(
                    iteration=iterations,
                    phase="image_verify",
                    message="Running final sanity checks before promotion.",
                    latest_refs=state.latest_refs,
                ),
            )
            final_verify = final_image_sanity_pass_before_promote(
                session_manager=session_manager,
                session_id=session_id,
                iteration=iterations,
                dossier_id=request.dossier_id,
                source_transcript_ref=state.current_transcript_ref,
                source_image_refs=request.source_image_refs,
                disagreement_hints=effective_disagreement_hints,
                model=model,
                step_fn=_step_kernel_action,
                read_step_outputs_inline_fn=read_step_outputs_inline,
                read_str_fn=read_str,
                read_int_fn=read_int,
            )
            state.latest_refs = final_verify.get("latest_refs", state.latest_refs)
            if not bool(final_verify.get("passed")):
                reason = read_str(final_verify.get("reason")) or "tx_agent_final_image_verify_failed"
                return TranscriptEditDecision(status="needs_review", reason_code=reason, review_required=True)
        promote = _step_kernel_action(
            session_manager=session_manager,
            session_id=session_id,
            prefix="tx_promote",
            iteration=iterations,
            action_type=ActionType.TX_PROMOTE_TRANSCRIPT_FOR_MAPPING,
            inputs={
                "dossier_id": request.dossier_id,
                "transcript_ref": state.current_transcript_ref,
                "run_id": request_id_prefix,
                "tx_span_seeds_ref": state.span_seeds_ref,
            },
        )
        state.latest_refs = promote.dashboard.latest_refs.model_dump(mode="json")
        if state.span_seeds_ref:
            state.latest_refs["tx_span_seeds_ref"] = {"artifact_path": state.span_seeds_ref}
        if promote.execution_state != StepExecutionState.EXECUTED:
            reason = promote.refusal.reason_code if promote.refusal is not None else "tx_promote_refused"
            return TranscriptEditDecision(status="failed", reason_code=reason, review_required=True)
        if state.applied_any_edits:
            persist_agent_edit_draft(
                dossier_id=request.dossier_id,
                transcription_id=request.transcription_id,
                source_transcript_ref=state.current_transcript_ref,
                run_id=request_id_prefix,
                reason_code="tx_agent_clean_promoted",
            )
        return clean_promoted_decision()
    if state.applied_any_edits:
        persist_agent_edit_draft(
            dossier_id=request.dossier_id,
            transcription_id=request.transcription_id,
            source_transcript_ref=state.current_transcript_ref,
            run_id=request_id_prefix,
            reason_code="tx_agent_clean_no_promote" if error_count <= 0 else "tx_agent_blocked_error_findings",
        )
    return clean_no_promote_decision(policy_facts)


def handle_repair_iteration(
    *,
    state: TranscriptEditLoopState,
    session_manager: KernelSessionManager,
    session_id: str,
    request: TranscriptEditAgentRunRequest,
    request_id_prefix: str,
    iterations: int,
    planner_client: TranscriptEditPlanPlanner,
    tx_persistence: TranscriptionEditPersistenceService,
    planning_findings: list[dict[str, Any]],
    top_findings: list[dict[str, Any]],
    findings_summary: dict[str, Any],
    source_transcript_hash: str,
    effective_disagreement_hints: dict[str, Any],
    mapping_focus: dict[str, Any],
    blocking_warning_present: bool,
    progress_cb: Callable[[dict[str, Any]], None] | None,
    model: str,
) -> TranscriptEditDecision | None:
    manual_plan_override: dict[str, Any] | None = None
    if state.sticky_range_selection is not None and state.current_transcript_ref and source_transcript_hash:
        manual_plan_override = build_range_feedback_plan(
            source_transcript_ref=state.current_transcript_ref,
            source_transcript_hash=source_transcript_hash,
            selected_number=state.sticky_range_selection,
        )
        if manual_plan_override is not None:
            emit_progress(
                progress_cb,
                human_feedback_reused_payload(
                    iteration=iterations,
                    sticky_range_selection=state.sticky_range_selection,
                    latest_refs=state.latest_refs,
                ),
            )
    viewer_run_id = viewer_run_id_from_request_prefix(request_id_prefix)
    if state.pending_feedback_prompt_id:
        feedback_entry = poll_feedback_response(
            run_id=viewer_run_id,
            prompt_id=state.pending_feedback_prompt_id,
        )
        if feedback_entry is not None:
            emit_progress(
                progress_cb,
                human_feedback_received_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    prompt_id=state.pending_feedback_prompt_id,
                    feedback_entry=feedback_entry,
                ),
            )
            selected_number = range_number_from_feedback(feedback_entry)
            state.used_human_feedback = True
            state.pending_feedback_prompt_id = None
            if selected_number is not None and state.current_transcript_ref and source_transcript_hash:
                state.sticky_range_selection = selected_number
                manual_plan_override = build_range_feedback_plan(
                    source_transcript_ref=state.current_transcript_ref,
                    source_transcript_hash=source_transcript_hash,
                    selected_number=selected_number,
                )
        else:
            emit_progress(
                progress_cb,
                ticker_payload(
                    iteration=iterations,
                    phase="human_feedback_needed",
                    message="Waiting for optional range confirmation while continuing other checks.",
                    latest_refs=state.latest_refs,
                ),
            )
    if (
        manual_plan_override is None
        and blocking_warning_present
        and request.hitl_enabled
        and (viewer_run_id.startswith("tx_agent_") or viewer_run_id.startswith("tx_post_t0_"))
        and not state.pending_feedback_prompt_id
    ):
        feedback_prompt = build_human_feedback_prompt(
            disagreement_hints=effective_disagreement_hints,
            top_findings=top_findings,
            iteration=iterations,
        )
        if feedback_prompt is not None:
            emit_progress(
                progress_cb,
                human_feedback_needed_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    feedback_prompt=feedback_prompt,
                ),
            )
            state.pending_feedback_prompt_id = str(feedback_prompt.get("prompt_id") or "").strip() or None

    if state.no_progress_streak >= request.max_no_progress_iterations:
        return TranscriptEditDecision(status="needs_review", reason_code="tx_agent_no_progress", review_required=True)
    if not state.current_transcript_ref:
        return TranscriptEditDecision(
            status="needs_review",
            reason_code="tx_agent_missing_source_ref_for_planning",
            review_required=True,
        )

    span_context: list[dict[str, Any]] = []
    image_verification: dict[str, Any] = {}
    if manual_plan_override is None:
        focus = choose_investigation_focus(state.decision_ledger)
        focus_reason = str((focus or {}).get("next_check_reason") or "Prioritizing highest-risk unresolved item.")
        focus_reason_code = str((focus or {}).get("next_check_reason_code") or "next_open_item")
        focus_key = str((focus or {}).get("decision_key") or "").strip()
        if focus:
            emit_progress(
                progress_cb,
                ticker_payload(
                    iteration=iterations,
                    phase="investigate",
                    message=focus_reason,
                    latest_refs=state.latest_refs,
                ),
            )
        emit_progress(
            progress_cb,
            open_spans_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
            ),
        )
        emit_progress(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="open_spans",
                message=f"Gathering localized spans for {focus_key or 'priority findings'} ({focus_reason_code}).",
                latest_refs=state.latest_refs,
            ),
        )
        focused_findings = _findings_for_focus_key(top_findings=planning_findings, focus_key=focus_key)
        focus_findings = focused_findings if focused_findings else planning_findings
        span_context = _open_planner_context_spans(
            session_manager=session_manager,
            session_id=session_id,
            iteration=iterations,
            dossier_id=request.dossier_id,
            source_transcript_ref=state.current_transcript_ref,
            top_findings=focus_findings,
        )
        emit_progress(
            progress_cb,
            open_spans_result_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
                spans_display=[_span_to_display_dict(s) for s in span_context[:6]],
            ),
        )
        emit_progress(
            progress_cb,
            image_verify_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
                message="Cross-referencing mapping-critical values (PLSS tokens, distances, bearings) against the source deed image.",
            ),
        )
        emit_progress(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="image_verify",
                message="Verifying mapping-critical tokens against source imagery.",
                latest_refs=state.latest_refs,
            ),
        )
        image_verification = _verify_mapping_critical_with_image(
            session_manager=session_manager,
            session_id=session_id,
            iteration=iterations,
            dossier_id=request.dossier_id,
            source_transcript_ref=state.current_transcript_ref,
            top_findings=focus_findings,
            disagreement_hints=effective_disagreement_hints,
            source_image_refs=request.source_image_refs,
            model=model,
            progress_cb=progress_cb,
        )
        if image_verification:
            state.latest_refs = image_verification.get("latest_refs", state.latest_refs)
            iv_payload = image_verification.get("payload") or {}
            iv_results = iv_payload.get("results") if isinstance(iv_payload, dict) else []
            iv_results = iv_results if isinstance(iv_results, list) else []
            state.decision_ledger = update_ledger_from_iteration(
                ledger=state.decision_ledger,
                findings=planning_findings,
                disagreement_hints=effective_disagreement_hints,
                image_results=[result for result in iv_results if isinstance(result, dict)],
            )
            iv_confirmed = sum(1 for r in iv_results if isinstance(r, dict) and str(r.get("status") or "").lower() in {"confirmed", "match"})
            iv_rejected = sum(1 for r in iv_results if isinstance(r, dict) and str(r.get("status") or "").lower() in {"rejected", "mismatch"})
            iv_total = len(iv_results)
            emit_progress(
                progress_cb,
                image_verify_result_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    iv_payload=iv_payload,
                    iv_results=[
                        {
                            "check_id": r.get("check_id"),
                            "status": r.get("status"),
                            "observed_text": str(r.get("observed_text") or "")[:120],
                        }
                        for r in iv_results[:8]
                        if isinstance(r, dict)
                    ],
                    iv_confirmed=iv_confirmed,
                    iv_rejected=iv_rejected,
                    iv_total=iv_total,
                    decision_ledger=ledger_snapshot_for_payload(state.decision_ledger),
                ),
            )
    else:
        emit_progress(
            progress_cb,
            image_verify_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
                message="Running post-feedback image verification before applying the override plan.",
            ),
        )
        emit_progress(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="image_verify",
                message="Running image verification for the human-selected override path.",
                latest_refs=state.latest_refs,
            ),
        )
        image_verification = _verify_mapping_critical_with_image(
            session_manager=session_manager,
            session_id=session_id,
            iteration=iterations,
            dossier_id=request.dossier_id,
            source_transcript_ref=state.current_transcript_ref,
            top_findings=planning_findings,
            disagreement_hints=effective_disagreement_hints,
            source_image_refs=request.source_image_refs,
            model=model,
            progress_cb=progress_cb,
        )
        if image_verification:
            state.latest_refs = image_verification.get("latest_refs", state.latest_refs)
            iv_payload = image_verification.get("payload") or {}
            iv_results = iv_payload.get("results") if isinstance(iv_payload, dict) else []
            iv_results = iv_results if isinstance(iv_results, list) else []
            state.decision_ledger = update_ledger_from_iteration(
                ledger=state.decision_ledger,
                findings=planning_findings,
                disagreement_hints=effective_disagreement_hints,
                image_results=[result for result in iv_results if isinstance(result, dict)],
            )

    manual_plan = manual_plan_override or (request.edit_plan if isinstance(request.edit_plan, dict) else None)
    consensus_plan_payload = None
    if manual_plan is None and not has_blocking_dispute(state.decision_ledger):
        consensus_plan_payload = _build_deterministic_consensus_plan(
            source_transcript_ref=state.current_transcript_ref,
            source_transcript_hash=source_transcript_hash,
            disagreement_hints=effective_disagreement_hints,
            image_verification=image_verification.get("payload") if isinstance(image_verification, dict) else {},
            top_findings=planning_findings,
        )
    elif manual_plan is None:
        emit_progress(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="plan",
                message="Skipping deterministic shortcut plan because blocking conflicting evidence remains.",
                latest_refs=state.latest_refs,
            ),
        )

    if manual_plan is not None:
        selected_plan_payload = manual_plan
        plan_reason = "manual_plan"
        raw_plan_text = json.dumps(manual_plan, ensure_ascii=False)
    elif consensus_plan_payload is not None:
        selected_plan_payload = consensus_plan_payload
        plan_reason = "deterministic_consensus_plan"
        raw_plan_text = json.dumps(consensus_plan_payload, ensure_ascii=False)
    else:
        emit_progress(
            progress_cb,
            plan_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
            ),
        )
        emit_progress(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="plan",
                message="Drafting a drift-safe correction plan from validated evidence.",
                latest_refs=state.latest_refs,
            ),
        )
        try:
            plan, plan_reason, raw_plan_text = planner_client.propose_plan(
                model=model,
                source_transcript_ref=state.current_transcript_ref,
                source_transcript_hash=source_transcript_hash,
                findings_summary=findings_summary,
                top_findings=coerce_findings(planning_findings),
                span_context=span_context,
                image_verification=image_verification.get("payload") if isinstance(image_verification, dict) else {},
                candidate_disagreement_hints=effective_disagreement_hints,
                mapping_priority_focus=mapping_focus,
                max_attempts=request.max_invalid_plan_attempts,
            )
        except Exception as exc:
            plan = None
            plan_reason = f"planner_exception:{type(exc).__name__}"
            raw_plan_text = ""
        selected_plan_payload = plan.model_dump(mode="json") if plan is not None else None
        if selected_plan_payload is None:
            state.invalid_plan_strikes += 1
            if state.invalid_plan_strikes >= request.max_invalid_plan_attempts:
                return TranscriptEditDecision(
                    status="needs_review",
                    reason_code=f"tx_agent_plan_invalid:{plan_reason}",
                    review_required=True,
                )
            return None
        if plan_has_no_ops(selected_plan_payload):
            reason = "tx_agent_no_safe_plan_for_findings"
            if manual_plan is None:
                reason = f"{reason}:{plan_reason}"
            return TranscriptEditDecision(
                status="needs_review",
                reason_code=reason,
                review_required=True,
            )

    plan_ops = selected_plan_payload.get("ops") if isinstance(selected_plan_payload, dict) else []
    plan_ops = plan_ops if isinstance(plan_ops, list) else []
    emit_progress(
        progress_cb,
        plan_result_payload(
            iteration=iterations,
            latest_refs=state.latest_refs,
            plan_reason=plan_reason,
            op_count=len(plan_ops),
            ops_preview=[plan_op_to_display_dict(op) for op in plan_ops[:6] if isinstance(op, dict)],
        ),
    )
    emit_progress(
        progress_cb,
        ticker_payload(
            iteration=iterations,
            phase="apply",
            message="Applying the selected edit operations and preparing re-audit.",
            latest_refs=state.latest_refs,
        ),
    )
    apply = _step_kernel_action(
        session_manager=session_manager,
        session_id=session_id,
        prefix="tx_apply",
        iteration=iterations,
        action_type=ActionType.TX_APPLY_EDIT_PLAN,
        inputs=build_apply_inputs_for_plan(
            persistence=tx_persistence,
            dossier_id=request.dossier_id,
            plan_payload=selected_plan_payload,
        ),
    )
    state.latest_refs = apply.dashboard.latest_refs.model_dump(mode="json")
    emit_progress(
        progress_cb,
        apply_result_payload(
            iteration=iterations,
            latest_refs=state.latest_refs,
            execution_state=str(apply.execution_state.value),
            plan_op_count=len(plan_ops),
            ops_display=[plan_op_to_display_dict(op) for op in plan_ops[:6] if isinstance(op, dict)],
        ),
    )
    if apply.execution_state != StepExecutionState.EXECUTED:
        reason = apply.refusal.reason_code if apply.refusal is not None else "tx_apply_refused"
        return TranscriptEditDecision(status="needs_review", reason_code=reason, review_required=True)

    apply_inline = read_step_outputs_inline(apply.step_record)
    edited_ref = read_str(apply_inline.get("tx_edited_transcript_ref"))
    if edited_ref:
        state.current_transcript_ref = edited_ref
    plan_cc = max_change_class_from_plan(selected_plan_payload or {})
    if plan_cc in {"semantic", "structural"}:
        state.applied_non_normalization = True
    if plan_has_review_required(selected_plan_payload or {}):
        state.applied_requires_review = True
    if len(plan_ops) > 0:
        state.applied_any_edits = True
    if manual_plan is None:
        state.invalid_plan_strikes = 0
    state.last_reason = plan_reason if plan_reason else "tx_apply_completed"
    if raw_plan_text:
        _ = raw_plan_text
    return None


def _step_kernel_action(
    *,
    session_manager: KernelSessionManager,
    session_id: str,
    prefix: str,
    iteration: int,
    action_type: ActionType,
    inputs: dict[str, Any],
):
    from .loop_runtime import step_kernel_action

    return step_kernel_action(
        session_manager=session_manager,
        session_id=session_id,
        prefix=prefix,
        iteration=iteration,
        action_type=action_type,
        inputs=inputs,
    )


def _open_planner_context_spans(
    *,
    session_manager: KernelSessionManager,
    session_id: str,
    iteration: int,
    dossier_id: str | None,
    source_transcript_ref: str,
    top_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from .context_spans import open_planner_context_spans

    return open_planner_context_spans(
        session_manager=session_manager,
        session_id=session_id,
        iteration=iteration,
        dossier_id=dossier_id,
        source_transcript_ref=source_transcript_ref,
        top_findings=top_findings,
        step_fn=_step_kernel_action,
        read_step_outputs_inline_fn=read_step_outputs_inline,
    )


def _verify_mapping_critical_with_image(
    *,
    session_manager: KernelSessionManager,
    session_id: str,
    iteration: int,
    dossier_id: str | None,
    source_transcript_ref: str,
    top_findings: list[dict[str, Any]],
    disagreement_hints: dict[str, Any],
    source_image_refs: list[str],
    model: str,
    progress_cb: Callable[[dict[str, Any]], None] | None,
) -> dict[str, Any]:
    def _emit_check_progress(update: dict[str, Any]) -> None:
        check_index = int(update.get("check_index") or 0)
        check_total = int(update.get("check_total") or 0)
        check_id = str(update.get("check_id") or "").strip() or "unknown_check"
        stage = str(update.get("stage") or "running")
        emit_progress(
            progress_cb,
            ticker_payload(
                iteration=iteration,
                phase="image_verify",
                message=f"Image check {check_index}/{check_total} ({check_id}) {stage}.",
                latest_refs={},
            ),
        )

    return verify_mapping_critical_with_image(
        session_manager=session_manager,
        session_id=session_id,
        iteration=iteration,
        dossier_id=dossier_id,
        source_transcript_ref=source_transcript_ref,
        top_findings=top_findings,
        disagreement_hints=disagreement_hints,
        source_image_refs=source_image_refs,
        model=model,
        step_fn=_step_kernel_action,
        read_step_outputs_inline_fn=read_step_outputs_inline,
        read_str_fn=read_str,
        progress_cb=_emit_check_progress,
    )


def _build_deterministic_consensus_plan(
    *,
    source_transcript_ref: str,
    source_transcript_hash: str,
    disagreement_hints: dict[str, Any],
    image_verification: dict[str, Any],
    top_findings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    from .disagreement_analysis import build_deterministic_consensus_plan

    return build_deterministic_consensus_plan(
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
        disagreement_hints=disagreement_hints,
        image_verification=image_verification,
        top_findings=top_findings,
    )


def _span_to_display_dict(span: dict[str, Any]) -> dict[str, Any]:
    text = str(span.get("text") or span.get("content") or "").strip()
    return {
        "span_id": span.get("span_id"),
        "text": text[:120] + ("..." if len(text) > 120 else ""),
    }


def _findings_for_focus_key(*, top_findings: list[dict[str, Any]], focus_key: str) -> list[dict[str, Any]]:
    key = str(focus_key or "").strip().lower()
    if not key:
        return []
    keyword_map: dict[str, tuple[str, ...]] = {
        "township": ("township", "plss"),
        "range": ("range", "plss"),
        "section": ("section", "plss"),
        "tie_distance": ("distance", "tie distance"),
        "tie_bearing": ("bearing",),
        "acreage": ("acre", "acreage"),
        "closure_or_pob": ("closure", "point of beginning", "pob"),
    }
    keywords = keyword_map.get(key, ())
    if not keywords:
        return []
    focused: list[dict[str, Any]] = []
    for finding in top_findings:
        if not isinstance(finding, dict):
            continue
        blob = f"{str(finding.get('finding_type') or '')} {str(finding.get('message') or '')}".lower()
        if any(token in blob for token in keywords):
            focused.append(finding)
    return focused


def _has_actionable_blocking_closure(ledger: dict[str, Any] | None) -> bool:
    if not isinstance(ledger, dict):
        return False
    items = ledger.get("items")
    if not isinstance(items, list):
        return False
    actionable_states = {"disputed", "accepted_with_risk"}
    for item in items:
        if not isinstance(item, dict):
            continue
        if not bool(item.get("blocking")):
            continue
        state = str(item.get("state") or "unknown")
        if state in actionable_states:
            return True
    return False
