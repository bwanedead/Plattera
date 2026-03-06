from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from agent_kernel.models import ActionType, StepExecutionState
from agent_kernel.session import KernelSessionManager
from transcript_edit.persistence import TranscriptionEditPersistenceService

from .contracts import TranscriptEditAgentRunRequest
from .decision_ledger import (
    choose_investigation_focus,
    has_unresolved_mapping_blocking_closure,
    is_unresolved_mapping_blocking_decision,
    ledger_snapshot_for_payload,
    list_external_context_injections,
    mark_human_resolution_ticket_state,
    upsert_human_resolution_ticket,
    unresolved_mapping_blocking_requirements,
    unresolved_closure_requirements,
    update_ledger_from_iteration,
)
from .evidence_executor import execute_evidence_request, normalize_evidence_request
from .draft_persistence import persist_agent_edit_draft
from .focus_packet import build_focus_packet
from .focus_resolver import resolve_focus_move
from .hitl_feedback import (
    build_feedback_override_plan,
    build_human_feedback_prompt,
    feedback_entry_signature,
    list_feedback_entries,
    normalize_feedback_response,
    poll_feedback_response,
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
    max_change_class_from_plan,
    plan_has_review_required,
    plan_op_to_display_dict,
)
from .planner import TranscriptEditPlanPlanner
from .progress_evaluation import blocking_signature, blocking_unresolved_count
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
    human_feedback_prompt_superseded_payload,
    human_feedback_received_payload,
    human_feedback_reused_payload,
    human_feedback_stale_payload,
    human_feedback_consumed_payload,
    investigation_baseline_payload,
    investigation_baseline_result_payload,
    image_verify_payload,
    image_verify_progress_payload,
    image_verify_result_payload,
    open_spans_payload,
    open_spans_result_payload,
    plan_result_payload,
    promote_payload,
    resolver_invalid_payload,
    stabilize_payload,
    ticker_payload,
)

MAX_EVIDENCE_REPEATS_PER_SIGNATURE = 2


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
    source_transcript_hash: str,
    progress_cb: Callable[[dict[str, Any]], None] | None,
    model: str,
) -> TranscriptEditDecision | None:
    unresolved_mapping_blocking_closure = has_unresolved_mapping_blocking_closure(state.decision_ledger)
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
        unresolved_mapping_blocking_closure=unresolved_mapping_blocking_closure,
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
            disagreement_hints={},
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
                disagreement_hints={},
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
    progress_cb: Callable[[dict[str, Any]], None] | None,
    model: str,
) -> TranscriptEditDecision | None:
    mapping_focus: dict[str, Any] = choose_investigation_focus(state.decision_ledger) or {}
    manual_plan_override: dict[str, Any] | None = None
    focus_feedback: dict[str, Any] | None = state.latest_feedback if isinstance(state.latest_feedback, dict) else None
    viewer_run_id = viewer_run_id_from_request_prefix(request_id_prefix)

    def _append_hitl_lifecycle_event(event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        state.hitl_lifecycle_log.append(event)
        if len(state.hitl_lifecycle_log) > 120:
            state.hitl_lifecycle_log = state.hitl_lifecycle_log[-120:]

    def _set_pending_feedback_prompt(
        *,
        feedback_prompt: dict[str, Any],
        decision_key: str,
        supersession_reason: str,
    ) -> None:
        new_prompt_id = str(feedback_prompt.get("prompt_id") or "").strip() or None
        old_prompt_id = str(state.pending_feedback_prompt_id or "").strip() or None
        if old_prompt_id and new_prompt_id and old_prompt_id != new_prompt_id:
            state.feedback_superseded_count += 1
            state.superseded_feedback_prompt_ids.add(old_prompt_id)
            state.decision_ledger = mark_human_resolution_ticket_state(
                ledger=state.decision_ledger,
                ticket_id=old_prompt_id,
                decision_key=decision_key,
                lifecycle_state="superseded",
                relevance="inactive",
            )
            superseded_event = {
                "iteration": iterations,
                "phase": "human_feedback_prompt_superseded",
                "event_type": "human_feedback_needed",
                "prompt_id": old_prompt_id,
                "replacement_prompt_id": new_prompt_id,
                "decision_key": decision_key,
                "reason": supersession_reason,
            }
            _append_hitl_lifecycle_event(superseded_event)
            emit_progress(
                progress_cb,
                human_feedback_prompt_superseded_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    superseded_prompt_id=old_prompt_id,
                    replacement_prompt_id=new_prompt_id,
                    decision_key=decision_key or None,
                    reason=supersession_reason,
                ),
            )
        state.pending_feedback_prompt_id = new_prompt_id
        state.pending_feedback_prompt = feedback_prompt if isinstance(feedback_prompt, dict) else None
        state.pending_feedback_decision_key = decision_key or None
        state.pending_feedback_emitted_iteration = iterations
        if new_prompt_id:
            state.decision_ledger = upsert_human_resolution_ticket(
                ledger=state.decision_ledger,
                ticket_id=new_prompt_id,
                decision_key=decision_key,
                lifecycle_state="issued_waiting_feedback",
                strength="binding",
                payload={
                    "issue_summary": str(feedback_prompt.get("line1") or "").strip(),
                    "original_prompt_summary": str(feedback_prompt.get("line2") or "").strip(),
                    "selected_choice": None,
                    "normalized_answer_summary": None,
                    "note": None,
                    "alternatives": [
                        str(v).strip()
                        for v in list(feedback_prompt.get("choices") or [])
                        if str(v).strip()
                    ][:6],
                },
                relevance="active",
            )
        _append_hitl_lifecycle_event(
            {
                "iteration": iterations,
                "phase": "human_feedback_needed",
                "event_type": "human_feedback_needed",
                "prompt_id": new_prompt_id,
                "decision_key": decision_key or None,
            }
        )

    def _drain_pending_feedback(*, checkpoint_label: str) -> dict[str, Any] | None:
        if not state.pending_feedback_prompt_id:
            return None
        pending_prompt_id = str(state.pending_feedback_prompt_id or "").strip()
        all_entries = list_feedback_entries(run_id=viewer_run_id)
        if all_entries:
            for entry in all_entries:
                signature = feedback_entry_signature(entry)
                if signature in state.feedback_entry_seen_keys:
                    continue
                entry_prompt_id = str(entry.get("prompt_id") or "").strip()
                if not entry_prompt_id:
                    continue
                if entry_prompt_id == pending_prompt_id:
                    continue
                state.feedback_entry_seen_keys.add(signature)
                state.feedback_stale_count += 1
                stale_decision_key = (
                    str(entry.get("metadata", {}).get("decision_key") or "").strip().lower()
                    if isinstance(entry.get("metadata"), dict)
                    else ""
                ) or str(state.pending_feedback_decision_key or "").strip().lower()
                if entry_prompt_id and stale_decision_key:
                    state.decision_ledger = mark_human_resolution_ticket_state(
                        ledger=state.decision_ledger,
                        ticket_id=entry_prompt_id,
                        decision_key=stale_decision_key,
                        lifecycle_state="stale",
                        relevance="inactive",
                    )
                stale_reason = (
                    "superseded_prompt_reply"
                    if entry_prompt_id in state.superseded_feedback_prompt_ids
                    else "stale_prompt_reply"
                )
                stale_event = {
                    "iteration": iterations,
                    "phase": "human_feedback_stale",
                    "event_type": "human_feedback",
                    "prompt_id": entry_prompt_id,
                    "active_prompt_id": pending_prompt_id,
                    "reason": stale_reason,
                }
                _append_hitl_lifecycle_event(stale_event)
                emit_progress(
                    progress_cb,
                    human_feedback_stale_payload(
                        iteration=iterations,
                        latest_refs=state.latest_refs,
                        prompt_id=entry_prompt_id,
                        active_prompt_id=pending_prompt_id,
                        reason=stale_reason,
                    ),
                )
        feedback_entry = poll_feedback_response(
            run_id=viewer_run_id,
            prompt_id=pending_prompt_id,
        )
        if feedback_entry is None:
            return None
        signature = feedback_entry_signature(feedback_entry)
        if signature in state.feedback_entry_seen_keys:
            return None
        state.feedback_entry_seen_keys.add(signature)
        state.feedback_received_count += 1
        _append_hitl_lifecycle_event(
            {
                "iteration": iterations,
                "phase": "human_feedback_received",
                "event_type": "human_feedback",
                "prompt_id": pending_prompt_id,
                "decision_key": state.pending_feedback_decision_key,
            }
        )
        emit_progress(
            progress_cb,
            human_feedback_received_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
                prompt_id=pending_prompt_id,
                feedback_entry=feedback_entry,
            ),
        )
        normalized_feedback = normalize_feedback_response(
            feedback_entry=feedback_entry,
            prompt_id=pending_prompt_id,
            prompt_context=state.pending_feedback_prompt,
        )
        if not isinstance(normalized_feedback, dict):
            state.feedback_stale_count += 1
            _append_hitl_lifecycle_event(
                {
                    "iteration": iterations,
                    "phase": "human_feedback_stale",
                    "event_type": "human_feedback",
                    "prompt_id": pending_prompt_id,
                    "active_prompt_id": pending_prompt_id,
                    "reason": "invalid_feedback_payload",
                }
            )
            emit_progress(
                progress_cb,
                human_feedback_stale_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    prompt_id=pending_prompt_id,
                    active_prompt_id=pending_prompt_id,
                    reason="invalid_feedback_payload",
                ),
            )
            return None
        emit_progress(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="human_feedback_needed",
                message=f"Feedback received at {checkpoint_label}; incorporating into current iteration.",
                latest_refs=state.latest_refs,
            ),
        )
        active_prompt_context = (
            dict(state.pending_feedback_prompt)
            if isinstance(state.pending_feedback_prompt, dict)
            else {}
        )
        state.used_human_feedback = True
        state.feedback_consumed_count += 1
        state.pending_feedback_prompt_id = None
        state.pending_feedback_prompt = None
        state.pending_feedback_decision_key = None
        state.pending_feedback_emitted_iteration = None
        state.decision_ledger = upsert_human_resolution_ticket(
            ledger=state.decision_ledger,
            ticket_id=pending_prompt_id,
            decision_key=str(normalized_feedback.get("decision_key") or "").strip().lower(),
            lifecycle_state="answered_unintegrated",
            strength="binding",
            payload={
                "issue_summary": str(active_prompt_context.get("line1") or "").strip(),
                "original_prompt_summary": str(active_prompt_context.get("line2") or "").strip(),
                "selected_choice": str(normalized_feedback.get("choice") or "").strip() or None,
                "normalized_answer_summary": str(normalized_feedback.get("selected_value") or "").strip() or None,
                "note": str(normalized_feedback.get("note") or "").strip() or None,
                "alternatives": [
                    str(v).strip()
                    for v in list(active_prompt_context.get("choices") or [])
                    if str(v).strip()
                ][:6],
            },
            answered_at=int(time.time()),
            relevance="active",
        )
        _append_hitl_lifecycle_event(
            {
                "iteration": iterations,
                "phase": "human_feedback_consumed",
                "event_type": "human_feedback",
                "prompt_id": pending_prompt_id,
                "decision_key": normalized_feedback.get("decision_key"),
                "selected_value": normalized_feedback.get("selected_value"),
            }
        )
        emit_progress(
            progress_cb,
            human_feedback_consumed_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
                prompt_id=pending_prompt_id,
                decision_key=str(normalized_feedback.get("decision_key") or "").strip() or None,
                selected_value=str(normalized_feedback.get("selected_value") or "").strip() or None,
            ),
        )
        return normalized_feedback

    def _apply_consumed_feedback(feedback_payload: dict[str, Any]) -> None:
        nonlocal focus_feedback
        focus_feedback = feedback_payload
        state.latest_feedback = feedback_payload
        state.evidence_signal_counter += 1
        state.no_progress_streak = 0
        state.last_progress_reason = "human_feedback_consumed"

    drained_plan = _drain_pending_feedback(checkpoint_label="iteration_start")
    if drained_plan is not None:
        _apply_consumed_feedback(drained_plan)
        emit_progress(
            progress_cb,
            human_feedback_reused_payload(
                iteration=iterations,
                decision_key=str(drained_plan.get("decision_key") or "decision"),
                selected_value=str(drained_plan.get("selected_value") or "selected"),
                latest_refs=state.latest_refs,
            ),
        )
    elif state.pending_feedback_prompt_id:
        emit_progress(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="human_feedback_needed",
                message="Waiting for human feedback while continuing other checks.",
                latest_refs=state.latest_refs,
            ),
        )
    if state.no_progress_streak >= request.max_no_progress_iterations:
        # One bounded last-chance drain before no-progress terminalization so
        # newly posted feedback for an active pending prompt is not skipped.
        if state.pending_feedback_prompt_id:
            drained_plan = _drain_pending_feedback(checkpoint_label="no_progress_grace")
            if drained_plan is not None:
                _apply_consumed_feedback(drained_plan)
                emit_progress(
                    progress_cb,
                    human_feedback_reused_payload(
                        iteration=iterations,
                        decision_key=str(drained_plan.get("decision_key") or "decision"),
                        selected_value=str(drained_plan.get("selected_value") or "selected"),
                        latest_refs=state.latest_refs,
                    ),
                )
        reason = "tx_agent_no_progress"
        if state.last_progress_reason and state.last_progress_reason != "not_evaluated":
            reason = f"{reason}:{state.last_progress_reason}"
        if state.no_progress_streak >= request.max_no_progress_iterations:
            return TranscriptEditDecision(status="needs_review", reason_code=reason, review_required=True)
    if not state.current_transcript_ref:
        return TranscriptEditDecision(
            status="needs_review",
            reason_code="tx_agent_missing_source_ref_for_planning",
            review_required=True,
        )

    span_context: list[dict[str, Any]] = []
    image_verification: dict[str, Any] = {}
    if manual_plan_override is None:
        conflict_map = _conflict_map_from_ledger(state.decision_ledger)
        emit_progress(
            progress_cb,
            investigation_baseline_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
                conflict_map=conflict_map,
            ),
        )
        focus = choose_investigation_focus(state.decision_ledger)
        focus_reason = str((focus or {}).get("next_check_reason") or "Prioritizing highest-risk unresolved item.")
        focus_reason_code = str((focus or {}).get("next_check_reason_code") or "next_open_item")
        focus_key = str((focus or {}).get("decision_key") or "").strip()
        prior_focus_key = str(state.last_focus_key or "").strip().lower()
        if focus_key and focus_key.lower() == prior_focus_key:
            state.focus_stagnation_streak += 1
        else:
            state.focus_stagnation_streak = 0
        state.last_focus_key = focus_key.lower() or state.last_focus_key
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
        if not focused_findings and focus_key:
            emit_progress(
                progress_cb,
                ticker_payload(
                    iteration=iterations,
                    phase="investigate",
                    message=(
                        f"No direct findings matched focus {focus_key}; using broader mapping-critical image checks "
                        "for this focus-cycle."
                    ),
                    latest_refs=state.latest_refs,
                    detail={
                        "decision_key": focus_key,
                        "evidence_kind": "image_verify",
                        "focus_fallback": True,
                    },
                ),
            )
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
        drained_plan = _drain_pending_feedback(checkpoint_label="open_spans")
        if drained_plan is not None:
            _apply_consumed_feedback(drained_plan)
        emit_progress(
            progress_cb,
            image_verify_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
                message="Cross-referencing mapping-critical values (PLSS tokens, distances, bearings) against the source deed image.",
                decision_key=focus_key or None,
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
            source_image_refs=request.source_image_refs,
            model=model,
            progress_cb=progress_cb,
            focus_decision_key=focus_key or None,
            llm_call_seq_start=state.llm_call_seq,
        )
        if image_verification:
            state.llm_call_seq = int(image_verification.get("llm_call_seq_end") or state.llm_call_seq)
            state.latest_refs = image_verification.get("latest_refs", state.latest_refs)
            iv_payload = image_verification.get("payload") or {}
            iv_results = iv_payload.get("results") if isinstance(iv_payload, dict) else []
            iv_results = iv_results if isinstance(iv_results, list) else []
            iv_diagnostics = iv_payload.get("diagnostics") if isinstance(iv_payload.get("diagnostics"), list) else []
            before_sig = blocking_signature(state.decision_ledger)
            state.decision_ledger = update_ledger_from_iteration(
                ledger=state.decision_ledger,
                findings=planning_findings,
                image_results=[result for result in iv_results if isinstance(result, dict)],
            )
            after_sig = blocking_signature(state.decision_ledger)
            if iv_results and before_sig != after_sig:
                state.evidence_signal_counter += 1
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
                            "decision_key": r.get("decision_key"),
                            "focus_decision_key": r.get("focus_decision_key"),
                            "llm_call_seq": r.get("llm_call_seq"),
                            "phase_attempt": r.get("phase_attempt"),
                            "observed_text": str(r.get("observed_text") or "")[:120],
                        }
                        for r in iv_results[:8]
                        if isinstance(r, dict)
                    ],
                    iv_confirmed=iv_confirmed,
                    iv_rejected=iv_rejected,
                    iv_total=iv_total,
                    decision_ledger=ledger_snapshot_for_payload(state.decision_ledger),
                    decision_key=focus_key or None,
                    llm_call_seq_end=state.llm_call_seq,
                    diagnostics=[d for d in iv_diagnostics if isinstance(d, dict)],
                ),
            )
        drained_plan = _drain_pending_feedback(checkpoint_label="image_verify")
        if drained_plan is not None:
            _apply_consumed_feedback(drained_plan)
    else:
        emit_progress(
            progress_cb,
            image_verify_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
                message="Running post-feedback image verification before applying the override plan.",
                decision_key=focus_key if 'focus_key' in locals() else None,
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
            source_image_refs=request.source_image_refs,
            model=model,
            progress_cb=progress_cb,
            focus_decision_key=focus_key if 'focus_key' in locals() else None,
            llm_call_seq_start=state.llm_call_seq,
        )
        if image_verification:
            state.llm_call_seq = int(image_verification.get("llm_call_seq_end") or state.llm_call_seq)
            state.latest_refs = image_verification.get("latest_refs", state.latest_refs)
            iv_payload = image_verification.get("payload") or {}
            iv_results = iv_payload.get("results") if isinstance(iv_payload, dict) else []
            iv_results = iv_results if isinstance(iv_results, list) else []
            iv_diagnostics = iv_payload.get("diagnostics") if isinstance(iv_payload.get("diagnostics"), list) else []
            before_sig = blocking_signature(state.decision_ledger)
            state.decision_ledger = update_ledger_from_iteration(
                ledger=state.decision_ledger,
                findings=planning_findings,
                image_results=[result for result in iv_results if isinstance(result, dict)],
            )
            after_sig = blocking_signature(state.decision_ledger)
            if iv_results and before_sig != after_sig:
                state.evidence_signal_counter += 1
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
                            "decision_key": r.get("decision_key"),
                            "observed_text": str(r.get("observed_text") or "")[:120],
                        }
                        for r in iv_results[:8]
                        if isinstance(r, dict)
                    ],
                    iv_confirmed=sum(
                        1
                        for r in iv_results
                        if isinstance(r, dict) and str(r.get("status") or "").lower() in {"confirmed", "match"}
                    ),
                    iv_rejected=sum(
                        1
                        for r in iv_results
                        if isinstance(r, dict) and str(r.get("status") or "").lower() in {"rejected", "mismatch"}
                    ),
                    iv_total=len(iv_results),
                    decision_ledger=ledger_snapshot_for_payload(state.decision_ledger),
                    decision_key=focus_key if 'focus_key' in locals() else None,
                    llm_call_seq_end=state.llm_call_seq,
                    diagnostics=[d for d in iv_diagnostics if isinstance(d, dict)],
                ),
            )
        drained_plan = _drain_pending_feedback(checkpoint_label="post_feedback_image_verify")
        if drained_plan is not None:
            _apply_consumed_feedback(drained_plan)

    baseline_unresolved = unresolved_closure_requirements(state.decision_ledger)
    baseline_mapping_blocking_unresolved = unresolved_mapping_blocking_requirements(state.decision_ledger)
    baseline_residual = [_baseline_residual_from_unresolved(item) for item in baseline_unresolved]
    mapping_blocking_count = len(baseline_mapping_blocking_unresolved)
    optional_count = max(0, len(baseline_residual) - mapping_blocking_count)
    has_mapping_blocking_residual = mapping_blocking_count > 0
    next_recommended_action = _next_recommended_action_text(baseline_residual)
    baseline_attempts_list = _baseline_evidence_attempts(
        span_context=span_context,
        image_verification=image_verification,
    )
    evidence_attempts_counts = {
        "open_spans_count": next(
            (int(item.get("result_count") or 0) for item in baseline_attempts_list if str(item.get("attempt") or "") == "open_spans"),
            0,
        ),
        "image_verify_count": next(
            (int(item.get("result_count") or 0) for item in baseline_attempts_list if str(item.get("attempt") or "") == "image_verify"),
            0,
        ),
        "retrieval_count": 0,
    }
    emit_progress(
        progress_cb,
        investigation_baseline_result_payload(
            iteration=iterations,
            latest_refs=state.latest_refs,
            evidence_attempts=baseline_attempts_list,
            residual_blockers=baseline_residual[:6],
            mapping_blocking_count=mapping_blocking_count,
            optional_count=optional_count,
            next_recommended_action=next_recommended_action,
            decision_ledger=ledger_snapshot_for_payload(state.decision_ledger),
        ),
    )

    if (
        manual_plan_override is None
        and has_mapping_blocking_residual
        and request.hitl_enabled
        and not state.pending_feedback_prompt_id
        and focus_feedback is None
    ):
        feedback_prompt = build_human_feedback_prompt(
            decision_ledger=state.decision_ledger,
            iteration=iterations,
        )
        if feedback_prompt is not None:
            emit_progress(
                progress_cb,
                ticker_payload(
                    iteration=iterations,
                    phase="human_feedback_needed",
                    message="Unable to self-resolve a mapping-blocking decision after evidence checks; requesting your confirmation.",
                    latest_refs=state.latest_refs,
                ),
            )
            emit_progress(
                progress_cb,
                human_feedback_needed_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    feedback_prompt=feedback_prompt,
                    evidence_attempts=evidence_attempts_counts,
                ),
            )
            _set_pending_feedback_prompt(
                feedback_prompt=feedback_prompt,
                decision_key=str((feedback_prompt.get("context") or {}).get("decision_key") or "").strip().lower(),
                supersession_reason="baseline_residual_mapping_blocker",
            )

    if state.pending_feedback_prompt_id and focus_feedback is None:
        # Keep the loop alive for feedback ingestion instead of terminalizing immediately on no-safe-plan.
        emit_progress(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="human_feedback_needed",
                message="Awaiting user feedback for unresolved mapping-blocking decision; deferring plan/apply this iteration.",
                latest_refs=state.latest_refs,
            ),
        )
        state.last_reason = "tx_agent_closure_requirements_unresolved"
        return None

    focus_key = _select_focus_decision_key(
        decision_ledger=state.decision_ledger,
        fallback_focus=mapping_focus,
        focus_feedback=focus_feedback,
    )
    mapping_focus = mapping_focus or {"decision_key": focus_key}
    focus_packet = build_focus_packet(
        decision_ledger=state.decision_ledger,
        decision_key=focus_key or None,
        source_transcript_ref=state.current_transcript_ref,
        source_transcript_hash=source_transcript_hash,
        span_context=span_context,
        image_verification_payload=(image_verification.get("payload") if isinstance(image_verification, dict) else {}),
        feedback=focus_feedback,
        continuity_log=state.continuity_log,
    )
    resolver_outcome = resolve_focus_move(
        focus_packet=focus_packet,
        planner_client=planner_client,
        model=model,
        findings_summary=findings_summary,
        planning_findings=planning_findings,
        max_invalid_plan_attempts=request.max_invalid_plan_attempts,
    )
    state.llm_call_seq += 1
    move = str((resolver_outcome or {}).get("move") or "").strip().lower()
    resolver_reason = str((resolver_outcome or {}).get("reason") or "").strip() or "resolver_no_reason"
    resolver_decision_key = str((resolver_outcome or {}).get("decision_key") or "").strip().lower()
    if resolver_decision_key and resolver_decision_key != focus_key:
        move = "mark_blocked"
        resolver_reason = f"resolver_decision_key_mismatch:{resolver_decision_key}"
    answered_ticket = _latest_human_resolution_ticket(
        decision_ledger=state.decision_ledger,
        decision_key=focus_key,
        lifecycle_states={"answered_unintegrated"},
    )
    stable_feedback_count = _stable_feedback_confirmation_count(
        hitl_lifecycle_log=state.hitl_lifecycle_log,
        decision_key=focus_key,
        selected_value=(
            str((focus_feedback or {}).get("selected_value") or "").strip()
            if isinstance(focus_feedback, dict)
            else (
                str(((answered_ticket or {}).get("payload") or {}).get("normalized_answer_summary") or "").strip()
                if isinstance((answered_ticket or {}).get("payload"), dict)
                else ""
            )
        ),
    )
    decisive_feedback_payload = (
        dict(focus_feedback)
        if isinstance(focus_feedback, dict)
        else _feedback_payload_from_ticket(answered_ticket=answered_ticket, decision_key=focus_key)
    )
    if (
        move in {"request_human_feedback", "gather_more_evidence"}
        and isinstance(decisive_feedback_payload, dict)
        and (answered_ticket is not None or stable_feedback_count >= 2)
    ):
        decisive_plan = build_feedback_override_plan(
            source_transcript_ref=state.current_transcript_ref or "",
            source_transcript_hash=source_transcript_hash,
            normalized_feedback=decisive_feedback_payload,
        )
        if isinstance(decisive_plan, dict):
            if isinstance(resolver_outcome, dict):
                resolver_outcome["move"] = "apply_edit_plan"
                resolver_outcome["edit_plan"] = decisive_plan
            move = "apply_edit_plan"
            resolver_reason = f"stable_feedback_override_plan:{resolver_reason}"
        else:
            if isinstance(answered_ticket, dict):
                state.decision_ledger = mark_human_resolution_ticket_state(
                    ledger=state.decision_ledger,
                    ticket_id=str(answered_ticket.get("ticket_id") or ""),
                    decision_key=str(answered_ticket.get("decision_key") or ""),
                    lifecycle_state="integration_attempted_failed",
                    relevance="active",
                )
            return TranscriptEditDecision(
                status="needs_review",
                reason_code="tx_agent_consistent_feedback_no_safe_plan",
                review_required=True,
            )
    state.continuity_log.append(
        {
            "decision_key": focus_key or "",
            "move": move or "unknown_move",
            "outcome": resolver_reason,
        }
    )
    if len(state.continuity_log) > 50:
        state.continuity_log = state.continuity_log[-50:]
    if move == "request_human_feedback":
        if not state.pending_feedback_prompt_id and request.hitl_enabled:
            resolver_prompt = (
                dict(resolver_outcome.get("feedback_prompt"))
                if isinstance(resolver_outcome, dict) and isinstance(resolver_outcome.get("feedback_prompt"), dict)
                else {}
            )
            feedback_prompt = None
            if resolver_prompt:
                feedback_prompt = {
                    "prompt_id": f"hitl_{focus_key}_{iterations}_resolver",
                    "line1": str(resolver_prompt.get("line1") or "").strip() or "Human feedback needed.",
                    "line2": str(resolver_prompt.get("line2") or "").strip() or "Please choose the best-supported option.",
                    "choices": [str(v).strip() for v in list(resolver_prompt.get("choices") or []) if str(v).strip()][:6],
                    "default_choice": None,
                    "context": {"decision_key": focus_key or None},
                }
                if feedback_prompt["choices"]:
                    feedback_prompt["default_choice"] = feedback_prompt["choices"][0]
            if feedback_prompt is None:
                feedback_prompt = build_human_feedback_prompt(
                    decision_ledger=state.decision_ledger,
                    iteration=iterations,
                )
            if feedback_prompt is not None:
                emit_progress(
                    progress_cb,
                    human_feedback_needed_payload(
                        iteration=iterations,
                        latest_refs=state.latest_refs,
                        feedback_prompt=feedback_prompt,
                        evidence_attempts=evidence_attempts_counts,
                    ),
                )
                _set_pending_feedback_prompt(
                    feedback_prompt=feedback_prompt,
                    decision_key=str((feedback_prompt.get("context") or {}).get("decision_key") or "").strip().lower(),
                    supersession_reason="resolver_requested_feedback",
                )
        state.last_reason = "tx_agent_closure_requirements_unresolved"
        return None
    if move == "mark_blocked":
        if not _accept_mark_blocked(
            decision_ledger=state.decision_ledger,
            decision_key=focus_key,
            resolver_reason=resolver_reason,
            hitl_enabled=request.hitl_enabled,
        ):
            state.last_reason = f"mark_blocked_rejected:{resolver_reason}"
            return None
        if resolver_reason.startswith(("resolver_move_invalid:", "resolver_plan_invalid:")):
            reason_suffix = resolver_reason
            if reason_suffix.startswith("resolver_move_invalid:"):
                reason_suffix = reason_suffix.replace("resolver_move_invalid:", "", 1)
            if reason_suffix.startswith("resolver_plan_invalid:"):
                reason_suffix = reason_suffix.replace("resolver_plan_invalid:", "", 1)
            state.invalid_plan_strikes += 1
            exhausted = state.invalid_plan_strikes >= request.max_invalid_plan_attempts
            emit_progress(
                progress_cb,
                resolver_invalid_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    reason=reason_suffix,
                    invalid_plan_strikes=state.invalid_plan_strikes,
                    max_invalid_plan_attempts=request.max_invalid_plan_attempts,
                    exhausted=exhausted,
                ),
            )
            if exhausted:
                return TranscriptEditDecision(
                    status="needs_review",
                    reason_code=f"tx_agent_plan_invalid_exhausted:{reason_suffix}",
                    review_required=True,
                )
            state.last_reason = f"tx_agent_plan_invalid_retrying:{reason_suffix}"
            return None
        return TranscriptEditDecision(
            status="needs_review",
            reason_code="tx_agent_closure_requirements_unresolved",
            review_required=True,
        )
    if move == "mark_resolved_no_edit":
        if _accept_mark_resolved_no_edit(
            decision_ledger=state.decision_ledger,
            decision_key=focus_key,
        ):
            state.last_reason = resolver_reason
            return None
        state.last_reason = f"mark_resolved_no_edit_rejected:{resolver_reason}"
        return None
    if move == "gather_more_evidence":
        normalized_request, normalize_reason = normalize_evidence_request(
            evidence_request=(
                resolver_outcome.get("evidence_request")
                if isinstance(resolver_outcome, dict) and isinstance(resolver_outcome.get("evidence_request"), dict)
                else None
            ),
            decision_key=focus_key,
        )
        if normalized_request is None:
            state.last_reason = f"gather_more_evidence_rejected:{normalize_reason}"
            return None
        focused_findings = _findings_for_focus_key(top_findings=planning_findings, focus_key=focus_key)
        focus_findings = focused_findings if focused_findings else planning_findings
        evidence_result = execute_evidence_request(
            normalized_request=normalized_request,
            source_transcript_hash=source_transcript_hash,
            repeat_guard=state.evidence_repeat_guard,
            evidence_signal_counter=state.evidence_signal_counter,
            max_repeats_per_signature=MAX_EVIDENCE_REPEATS_PER_SIGNATURE,
            open_spans_runner=lambda _req: _open_planner_context_spans(
                session_manager=session_manager,
                session_id=session_id,
                iteration=iterations,
                dossier_id=request.dossier_id,
                source_transcript_ref=state.current_transcript_ref or "",
                top_findings=focus_findings,
            ),
            image_verify_runner=lambda _req: _verify_mapping_critical_with_image(
                session_manager=session_manager,
                session_id=session_id,
                iteration=iterations,
                dossier_id=request.dossier_id,
                source_transcript_ref=state.current_transcript_ref or "",
                top_findings=focus_findings,
                source_image_refs=request.source_image_refs,
                model=model,
                progress_cb=progress_cb,
                focus_decision_key=focus_key,
                llm_call_seq_start=state.llm_call_seq,
            ),
            retrieve_dependency_runner=None,
        )
        state.continuity_log.append(
            {
                "decision_key": focus_key,
                "move": "gather_more_evidence",
                "outcome": str(evidence_result.get("reason") or "evidence_result_unknown"),
                "evidence_kind": str(evidence_result.get("kind") or ""),
            }
        )
        if len(state.continuity_log) > 50:
            state.continuity_log = state.continuity_log[-50:]
        if str(evidence_result.get("status") or "") == "repeat_blocked":
            return TranscriptEditDecision(
                status="needs_review",
                reason_code="tx_agent_evidence_repeat_budget_exhausted",
                review_required=True,
            )
        if str(evidence_result.get("status") or "") in {"unsupported", "invalid"}:
            state.last_reason = f"gather_more_evidence_failed:{evidence_result.get('reason')}"
            return None
        extra_spans = evidence_result.get("span_context") if isinstance(evidence_result.get("span_context"), list) else []
        if extra_spans:
            span_context = [s for s in extra_spans if isinstance(s, dict)]
            state.evidence_signal_counter += 1
            emit_progress(
                progress_cb,
                open_spans_result_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    spans_display=[_span_to_display_dict(s) for s in span_context[:6]],
                ),
            )
        extra_image_verification = (
            evidence_result.get("image_verification")
            if isinstance(evidence_result.get("image_verification"), dict)
            else {}
        )
        if extra_image_verification:
            image_verification = extra_image_verification
            state.llm_call_seq = int(image_verification.get("llm_call_seq_end") or state.llm_call_seq)
            state.latest_refs = image_verification.get("latest_refs", state.latest_refs)
            iv_payload = image_verification.get("payload") if isinstance(image_verification.get("payload"), dict) else {}
            iv_results = iv_payload.get("results") if isinstance(iv_payload, dict) else []
            iv_results = iv_results if isinstance(iv_results, list) else []
            iv_diagnostics = iv_payload.get("diagnostics") if isinstance(iv_payload.get("diagnostics"), list) else []
            before_sig = blocking_signature(state.decision_ledger)
            state.decision_ledger = update_ledger_from_iteration(
                ledger=state.decision_ledger,
                findings=planning_findings,
                image_results=[result for result in iv_results if isinstance(result, dict)],
            )
            after_sig = blocking_signature(state.decision_ledger)
            if iv_results and before_sig != after_sig:
                state.evidence_signal_counter += 1
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
                    iv_confirmed=sum(
                        1
                        for r in iv_results
                        if isinstance(r, dict) and str(r.get("status") or "").lower() in {"confirmed", "match"}
                    ),
                    iv_rejected=sum(
                        1
                        for r in iv_results
                        if isinstance(r, dict) and str(r.get("status") or "").lower() in {"rejected", "mismatch"}
                    ),
                    iv_total=len(iv_results),
                    decision_ledger=ledger_snapshot_for_payload(state.decision_ledger),
                    decision_key=focus_key,
                    llm_call_seq_end=state.llm_call_seq,
                    diagnostics=[d for d in iv_diagnostics if isinstance(d, dict)],
                ),
            )
        state.last_reason = resolver_reason
        return None

    manual_plan = (
        (resolver_outcome.get("edit_plan") if isinstance(resolver_outcome, dict) else None)
        if move == "apply_edit_plan"
        else None
    )
    if manual_plan is None:
        manual_plan = request.edit_plan if isinstance(request.edit_plan, dict) else None

    if manual_plan is not None:
        if not _accept_apply_edit_plan(
            resolver_decision_key=resolver_decision_key or focus_key,
            focus_key=focus_key,
            plan_payload=manual_plan,
        ):
            state.invalid_plan_strikes += 1
            if state.invalid_plan_strikes >= request.max_invalid_plan_attempts:
                return TranscriptEditDecision(
                    status="needs_review",
                    reason_code="tx_agent_plan_invalid:focus_scope_mismatch",
                    review_required=True,
                )
            return None
        selected_plan_payload = manual_plan
        plan_reason = "resolver_edit_plan" if move == "apply_edit_plan" else "manual_plan"
        raw_plan_text = json.dumps(manual_plan, ensure_ascii=False)
    else:
        state.invalid_plan_strikes += 1
        if state.invalid_plan_strikes >= request.max_invalid_plan_attempts:
            return TranscriptEditDecision(
                status="needs_review",
                reason_code="tx_agent_plan_invalid:missing_apply_edit_plan",
                review_required=True,
            )
        return None

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
        state.pending_reaudit_after_apply = True
        state.apply_reaudit_baseline_blocking_count = blocking_unresolved_count(state.decision_ledger)
        ticket_prompt_id = (
            str((focus_feedback or {}).get("prompt_id") or "").strip()
            if isinstance(focus_feedback, dict)
            else ""
        )
        ticket_decision_key = (
            str((focus_feedback or {}).get("decision_key") or "").strip().lower()
            if isinstance(focus_feedback, dict)
            else str(focus_key or "").strip().lower()
        )
        if not ticket_prompt_id:
            answered_ticket = _latest_human_resolution_ticket(
                decision_ledger=state.decision_ledger,
                decision_key=ticket_decision_key,
                lifecycle_states={"answered_unintegrated", "integration_attempted_failed"},
            )
            ticket_prompt_id = str((answered_ticket or {}).get("ticket_id") or "").strip()
            ticket_decision_key = str((answered_ticket or {}).get("decision_key") or ticket_decision_key).strip().lower()
        if ticket_prompt_id and ticket_decision_key:
            state.decision_ledger = mark_human_resolution_ticket_state(
                ledger=state.decision_ledger,
                ticket_id=ticket_prompt_id,
                decision_key=ticket_decision_key,
                lifecycle_state="integrated",
                integrated=True,
                relevance="inactive",
            )
    state.invalid_plan_strikes = 0
    state.last_reason = "tx_apply_completed_waiting_reaudit"
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


def _select_focus_decision_key(
    *,
    decision_ledger: dict[str, Any],
    fallback_focus: dict[str, Any] | None,
    focus_feedback: dict[str, Any] | None,
) -> str:
    if isinstance(focus_feedback, dict):
        feedback_key = str(focus_feedback.get("decision_key") or "").strip().lower()
        if feedback_key and is_unresolved_mapping_blocking_decision(decision_ledger, feedback_key):
            return feedback_key
    key = str((fallback_focus or {}).get("decision_key") or "").strip().lower()
    if key:
        return key
    fallback = choose_investigation_focus(decision_ledger) or {}
    return str(fallback.get("decision_key") or "").strip().lower()


def _normalize_feedback_selected_value(*, decision_key: str, selected_value: str) -> str:
    key = str(decision_key or "").strip().lower()
    value = str(selected_value or "").strip().lower()
    if not value:
        return ""
    if key in {"range", "township", "section", "tie_distance"}:
        import re

        match = re.search(r"\b(\d{1,4})\b", value)
        if match:
            return f"{key}:{match.group(1)}"
    return f"{key}:{value}"


def _stable_feedback_confirmation_count(
    *,
    hitl_lifecycle_log: list[dict[str, Any]],
    decision_key: str | None,
    selected_value: str | None,
) -> int:
    key = str(decision_key or "").strip().lower()
    normalized_target = _normalize_feedback_selected_value(
        decision_key=key,
        selected_value=str(selected_value or ""),
    )
    if not key or not normalized_target:
        return 0
    count = 0
    for entry in reversed(hitl_lifecycle_log):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("phase") or "").strip().lower() != "human_feedback_consumed":
            continue
        entry_key = str(entry.get("decision_key") or "").strip().lower()
        if entry_key != key:
            continue
        entry_value = _normalize_feedback_selected_value(
            decision_key=key,
            selected_value=str(entry.get("selected_value") or ""),
        )
        if entry_value == normalized_target:
            count += 1
            continue
        break
    return count


def _latest_human_resolution_ticket(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str | None,
    lifecycle_states: set[str],
) -> dict[str, Any] | None:
    rows = list_external_context_injections(
        decision_ledger,
        decision_key=str(decision_key or "").strip().lower(),
        type_filter="human_resolution_ticket",
        lifecycle_states={str(v).strip().lower() for v in lifecycle_states if str(v).strip()},
    )
    if not rows:
        return None
    rows.sort(key=lambda row: int(row.get("updated_at") or row.get("created_at") or 0), reverse=True)
    return dict(rows[0]) if isinstance(rows[0], dict) else None


def _feedback_payload_from_ticket(
    *,
    answered_ticket: dict[str, Any] | None,
    decision_key: str | None,
) -> dict[str, Any] | None:
    if not isinstance(answered_ticket, dict):
        return None
    payload = answered_ticket.get("payload") if isinstance(answered_ticket.get("payload"), dict) else {}
    selected_value = (
        str(payload.get("normalized_answer_summary") or "").strip()
        or str(payload.get("selected_choice") or "").strip()
    )
    if not selected_value:
        return None
    key = str(answered_ticket.get("decision_key") or decision_key or "").strip().lower()
    if not key:
        return None
    return {
        "decision_key": key,
        "selected_value": selected_value,
        "choice": str(payload.get("selected_choice") or "").strip() or None,
        "note": str(payload.get("note") or "").strip() or None,
        "prompt_id": str(answered_ticket.get("ticket_id") or "").strip() or None,
        "metadata": {"ticket_id": str(answered_ticket.get("ticket_id") or "").strip() or None},
    }


def _accept_mark_resolved_no_edit(*, decision_ledger: dict[str, Any], decision_key: str) -> bool:
    return not is_unresolved_mapping_blocking_decision(decision_ledger, decision_key)


def _accept_mark_blocked(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str,
    resolver_reason: str,
    hitl_enabled: bool,
) -> bool:
    reason = str(resolver_reason or "").strip().lower()
    if reason.startswith(
        (
            "resolver_move_invalid:",
            "resolver_plan_invalid:",
            "resolver_move_invalid",
            "resolver_plan_invalid",
        )
    ):
        return True
    unresolved = unresolved_mapping_blocking_requirements(decision_ledger)
    focus_item = next(
        (
            item
            for item in unresolved
            if isinstance(item, dict) and str(item.get("key") or "").strip().lower() == decision_key
        ),
        None,
    )
    requirement = focus_item.get("closure_requirement") if isinstance(focus_item, dict) else {}
    block_reason = str(requirement.get("block_reason") or "").strip().lower() if isinstance(requirement, dict) else ""
    if block_reason == "dependency":
        return True
    if "repeat_budget" in reason or "evidence_budget" in reason:
        return True
    if not hitl_enabled and is_unresolved_mapping_blocking_decision(decision_ledger, decision_key):
        return True
    return False


def _accept_apply_edit_plan(
    *,
    resolver_decision_key: str,
    focus_key: str,
    plan_payload: dict[str, Any],
) -> bool:
    if resolver_decision_key != focus_key:
        return False
    if not isinstance(plan_payload, dict):
        return False
    ops = plan_payload.get("ops")
    if not isinstance(ops, list) or len(ops) <= 0:
        return False
    return True


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
    source_image_refs: list[str],
    model: str,
    progress_cb: Callable[[dict[str, Any]], None] | None,
    focus_decision_key: str | None = None,
    llm_call_seq_start: int = 0,
) -> dict[str, Any]:
    def _emit_check_progress(update: dict[str, Any]) -> None:
        check_index = int(update.get("check_index") or 0)
        check_total = int(update.get("check_total") or 0)
        check_id = str(update.get("check_id") or "").strip() or "unknown_check"
        stage = str(update.get("stage") or "running")
        elapsed_seconds = int(update.get("elapsed_seconds") or 0)
        llm_call_seq = int(update.get("llm_call_seq") or 0)
        phase_attempt = int(update.get("phase_attempt") or 1)
        check_decision_key = str(update.get("check_decision_key") or "").strip().lower() or None
        focus_key = str(update.get("focus_decision_key") or focus_decision_key or "").strip().lower() or None
        emit_progress(
            progress_cb,
            image_verify_progress_payload(
                iteration=iteration,
                decision_key=focus_key,
                evidence_kind="image_verify",
                check_id=f"{check_index}/{check_total}:{check_id}",
                check_decision_key=check_decision_key,
                llm_call_seq=llm_call_seq,
                phase_attempt=phase_attempt,
                stage=stage,
                elapsed_seconds=elapsed_seconds,
                diagnostic=(update.get("diagnostic") if isinstance(update.get("diagnostic"), dict) else None),
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
        disagreement_hints={},
        source_image_refs=source_image_refs,
        model=model,
        step_fn=_step_kernel_action,
        read_step_outputs_inline_fn=read_step_outputs_inline,
        read_str_fn=read_str,
        progress_cb=_emit_check_progress,
        focus_decision_key=focus_decision_key,
        llm_call_seq_start=llm_call_seq_start,
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
    focused: list[dict[str, Any]] = []
    for finding in top_findings:
        if not isinstance(finding, dict):
            continue
        inferred_key = _decision_key_for_finding(finding)
        if inferred_key == key:
            focused.append(finding)
    return focused


def _decision_key_for_finding(finding: dict[str, Any]) -> str:
    finding_id = str(finding.get("finding_id") or "").strip().lower()
    finding_type = str(finding.get("finding_type") or "").strip().lower()
    message = str(finding.get("message") or "").strip().lower()
    blob = f"{finding_id} {finding_type} {message}"
    if "range" in blob:
        return "range"
    if "township" in blob:
        return "township"
    if "section" in blob:
        return "section"
    if "distance" in blob:
        return "tie_distance"
    if "bearing" in blob:
        return "tie_bearing"
    if "acre" in blob:
        return "acreage"
    if "closure" in blob or "point of beginning" in blob or "pob" in blob:
        return "closure_or_pob"
    return ""


def _conflict_map_from_ledger(ledger: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(ledger, dict):
        return []
    items = ledger.get("items")
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        alternatives = [str(v).strip() for v in list(item.get("alternatives") or []) if str(v).strip()]
        if len(alternatives) < 2:
            continue
        state = str(item.get("state") or "").strip().lower()
        if state not in {"disputed", "accepted_with_risk", "candidate_found", "unknown"}:
            continue
        out.append(
            {
                "decision_key": str(item.get("key") or ""),
                "values": alternatives[:6],
                "conflict": True,
            }
        )
    return out


def _baseline_residual_from_unresolved(item: dict[str, Any]) -> dict[str, Any]:
    requirement = item.get("closure_requirement") if isinstance(item.get("closure_requirement"), dict) else {}
    return {
        "decision_key": str(item.get("key") or ""),
        "label": str(item.get("label") or item.get("key") or "decision"),
        "state": str(item.get("state") or "unknown"),
        "mapping_blocking": bool(item.get("mapping_blocking")),
        "required_information": str(requirement.get("required_information") or "").strip(),
        "minimal_user_action": str(requirement.get("minimal_user_action") or "").strip(),
    }


def _baseline_evidence_attempts(
    *,
    span_context: list[dict[str, Any]],
    image_verification: dict[str, Any],
) -> list[dict[str, Any]]:
    image_payload = image_verification.get("payload") if isinstance(image_verification, dict) else {}
    image_results = image_payload.get("results") if isinstance(image_payload, dict) else []
    image_count = len(image_results) if isinstance(image_results, list) else 0
    return [
        {
            "attempt": "open_spans",
            "status": "completed",
            "result_count": len(span_context),
        },
        {
            "attempt": "image_verify",
            "status": "completed" if image_count > 0 else "attempted",
            "result_count": image_count,
        },
    ]


def _next_recommended_action_text(residual_blockers: list[dict[str, Any]]) -> str:
    if not residual_blockers:
        return "Proceed with plan/apply stage."
    for item in residual_blockers:
        if not isinstance(item, dict):
            continue
        if not bool(item.get("mapping_blocking")):
            continue
        label = str(item.get("label") or item.get("decision_key") or "decision")
        action = str(item.get("minimal_user_action") or item.get("required_information") or "").strip()
        if action:
            return f"{label}: {action}"
        return f"Resolve {label}."
    first = residual_blockers[0] if isinstance(residual_blockers[0], dict) else {}
    label = str(first.get("label") or first.get("decision_key") or "decision")
    return f"Review optional transcript-quality issue: {label}."
