from __future__ import annotations

import json
import time
from collections.abc import Callable
from functools import partial
from typing import Any

from agent_kernel.models import ActionType, StepExecutionState
from agent_kernel.session import KernelSessionManager
from transcript_edit.persistence import TranscriptionEditPersistenceService

from .contracts import TranscriptEditAgentRunRequest
from .decision_ledger import (
    choose_investigation_focus,
    has_unresolved_target_scope_mapping_blocking_closure,
    is_unresolved_mapping_blocking_decision,
    is_unresolved_target_scope_mapping_blocking_decision,
    ledger_snapshot_for_payload,
    list_external_context_injections,
    mark_human_resolution_ticket_state,
    upsert_human_resolution_ticket,
    unresolved_mapping_blocking_requirements,
    unresolved_target_scope_mapping_blocking_requirements,
    unresolved_closure_requirements,
    update_ledger_from_iteration,
)
from .blocker_registry import (
    apply_proposed_emergent_blocker_updates,
    append_iteration_recap,
    blocker_registry_delta,
    link_prompt_to_blocker,
    mark_feedback_received,
    mark_feedback_stale,
    registry_snapshot_for_payload,
    select_primary_emergent_blocker_with_reason,
    select_primary_blocker_with_reason,
    select_primary_blocker,
    supersede_prompt_link,
    sync_registry_from_ledger,
)
from .blocker_iteration_reporting import append_blocker_iteration_recap
from .evidence_executor import execute_evidence_request, normalize_evidence_request
from .evidence_runtime import (
    cache_image_verification_for_key,
    cache_span_context_for_key,
    cache_visual_evidence_for_key,
    cached_image_verification_for_key,
    cached_span_context_for_key,
    cached_visual_evidence_for_key,
    clear_cached_focus_evidence,
    coerce_artifact_ref_for_state,
    coerce_visual_evidence_state,
    evidence_request_mode_hint,
    image_verify_runtime_config,
    open_planner_context_spans_adapter,
    run_image_evidence_mode,
    selector_type_from_target,
    verify_mapping_critical_with_image_adapter,
    visual_evidence_from_verify_payload,
)
from .feedback_lifecycle import (
    active_ticket_snapshot,
    append_hitl_lifecycle_event,
    apply_consumed_feedback,
    drain_pending_feedback,
    emit_ticket_lifecycle_transition,
    feedback_payload_from_registry_row,
    feedback_payload_from_ticket,
    latest_human_resolution_ticket,
    normalize_feedback_selected_value,
    set_pending_feedback_prompt,
    stable_feedback_confirmation_count,
    ticket_lifecycle_snapshot_for_key,
)
from .draft_persistence import persist_agent_edit_draft
from .focus_packet import build_focus_packet
from .focus_resolver import resolve_focus_move
from .focus_runtime import (
    baseline_evidence_attempts,
    baseline_residual_from_unresolved,
    conflict_map_from_ledger,
    decision_key_for_finding,
    findings_for_focus_key,
    next_recommended_action_text,
    recent_image_evidence_attempt_count,
    registry_row_for_decision_key,
    select_focus_decision_key,
)
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
from .resolver_gates import (
    accept_apply_edit_plan,
    accept_mark_blocked,
    accept_mark_resolved_no_edit,
    extract_validation_error_class,
    resolver_result_category,
)
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
    blocker_update_payload,
    final_verify_retry_payload,
    human_feedback_needed_payload,
    human_feedback_prompt_superseded_payload,
    human_feedback_received_payload,
    human_feedback_reused_payload,
    human_resolution_ticket_state_payload,
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
    resolver_attempt_payload,
    resolver_move_gate_payload,
    resolver_outcome_payload,
    stabilize_payload,
    ticker_payload,
)

MAX_EVIDENCE_REPEATS_PER_SIGNATURE = 2


def _append_blocker_iteration_recap_for_state(
    *,
    state: TranscriptEditLoopState,
    blocker_registry_before_iteration: dict[str, Any],
    iterations: int,
    active_blocker_id: str | None,
    active_blocker_prior_state: str | None,
    selection_reason_code: str,
    action_attempted: str,
    result: str,
    decision_key: str | None,
    reason: str | None,
    progress_cb: Callable[[dict[str, Any]], None] | None,
) -> None:
    state.blocker_registry = append_blocker_iteration_recap(
        registry=state.blocker_registry,
        before_registry=blocker_registry_before_iteration,
        iteration=iterations,
        active_blocker_id=active_blocker_id,
        active_blocker_prior_state=active_blocker_prior_state,
        action_attempted=action_attempted,
        result=result,
        decision_key=decision_key,
        reason=reason,
        selection_reason_code=selection_reason_code,
        latest_refs=state.latest_refs,
        progress_cb=progress_cb,
    )


def _emit_ticket_lifecycle_transition_for_state(
    *,
    state: TranscriptEditLoopState,
    iterations: int,
    progress_cb: Callable[[dict[str, Any]], None] | None,
    ticket_id: str | None,
    decision_key: str | None,
    lifecycle_state: str,
    strength: str | None = "binding",
    relevance: str | None = None,
    reason: str | None = None,
) -> None:
    emit_ticket_lifecycle_transition(
        state=state,
        iterations=iterations,
        latest_refs=state.latest_refs,
        progress_cb=progress_cb,
        ticket_id=ticket_id,
        decision_key=decision_key,
        lifecycle_state=lifecycle_state,
        strength=strength,
        relevance=relevance,
        reason=reason,
    )


def _build_feedback_prompt_with_optional_image(
    *,
    state: TranscriptEditLoopState,
    iterations: int,
    image_verification: dict[str, Any],
    visual_evidence: dict[str, Any],
) -> dict[str, Any] | None:
    image_payload = image_verification.get("payload") if isinstance(image_verification, dict) else None
    prompt = build_human_feedback_prompt(
        decision_ledger=state.decision_ledger,
        iteration=iterations,
        image_verification_payload=image_payload,
        visual_evidence_state=visual_evidence,
    )
    if not isinstance(prompt, dict):
        return None
    context = prompt.get("context")
    if not isinstance(context, dict):
        context = {}
        prompt["context"] = context
    focused = context.get("focused_image_evidence")
    focused_dict = focused if isinstance(focused, dict) else {}
    focused_region_ref = _coerce_artifact_ref_for_state(focused_dict.get("tx_image_evidence_region_ref"))
    focused_context_ref = _coerce_artifact_ref_for_state(focused_dict.get("tx_image_evidence_context_ref"))
    if focused_region_ref is not None or focused_context_ref is not None:
        return prompt
    visual_region_ref = _coerce_artifact_ref_for_state((visual_evidence or {}).get("tx_image_evidence_region_ref"))
    visual_context_ref = _coerce_artifact_ref_for_state((visual_evidence or {}).get("tx_image_evidence_context_ref"))
    latest_region_ref = _coerce_artifact_ref_for_state((state.latest_refs.get("tx_image_evidence_region_ref") or {}))
    latest_context_ref = _coerce_artifact_ref_for_state((state.latest_refs.get("tx_image_evidence_context_ref") or {}))
    region_ref = visual_region_ref or latest_region_ref
    context_ref = visual_context_ref or latest_context_ref
    if region_ref is None and context_ref is None:
        return prompt
    context["focused_image_evidence"] = {
        "check_id": str((visual_evidence or {}).get("check_id") or "").strip() or None,
        "status": str((visual_evidence or {}).get("status") or "").strip().lower() or None,
        "query": str((visual_evidence or {}).get("query") or "").strip()[:220] or None,
        "observed_text": str((visual_evidence or {}).get("observed_text") or "").strip()[:220] or None,
        "crop_box": (
            dict((visual_evidence or {}).get("crop_box"))
            if isinstance((visual_evidence or {}).get("crop_box"), dict)
            else None
        ),
        "zoom_factor": (visual_evidence or {}).get("zoom_factor"),
        "selector_type": str((visual_evidence or {}).get("selector_type") or "").strip().lower() or None,
        "region_lineage": (
            dict((visual_evidence or {}).get("region_lineage"))
            if isinstance((visual_evidence or {}).get("region_lineage"), dict)
            else {}
        ),
        "tx_image_evidence_region_ref": region_ref,
        "tx_image_evidence_context_ref": context_ref,
    }
    return prompt


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
    unresolved_mapping_blocking_closure = has_unresolved_target_scope_mapping_blocking_closure(state.decision_ledger)
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
    validation_mode: str,
) -> TranscriptEditDecision | None:
    blocker_registry_before_iteration = registry_snapshot_for_payload(state.blocker_registry)
    state.blocker_registry = sync_registry_from_ledger(
        registry=state.blocker_registry,
        decision_ledger=state.decision_ledger,
        source_transcript_ref=state.current_transcript_ref,
    )
    selection = select_primary_blocker_with_reason(state.blocker_registry)
    primary_registry_blocker = (
        dict(selection.get("row"))
        if isinstance(selection.get("row"), dict)
        else {}
    )
    selection_reason_code = str(selection.get("reason_code") or "no_active_blockers")
    primary_registry_state = str(primary_registry_blocker.get("state") or "").strip().lower()
    mapping_focus: dict[str, Any] = (
        {"decision_key": str(primary_registry_blocker.get("decision_key") or "").strip().lower()}
        if (
            str(primary_registry_blocker.get("decision_key") or "").strip()
            and primary_registry_state in {"answered_unintegrated", "waiting_feedback"}
        )
        else {}
    )
    ledger_focus_fallback: dict[str, Any] = choose_investigation_focus(state.decision_ledger) or {}
    manual_plan_override: dict[str, Any] | None = None
    focus_feedback: dict[str, Any] | None = state.latest_feedback if isinstance(state.latest_feedback, dict) else None
    viewer_run_id = viewer_run_id_from_request_prefix(request_id_prefix)
    active_blocker_id = str((primary_registry_blocker or {}).get("blocker_id") or "").strip() or None
    active_blocker_prior_state = str((primary_registry_blocker or {}).get("state") or "").strip().lower() or None

    append_blocker_iteration_recap_fn = partial(
        _append_blocker_iteration_recap_for_state,
        state=state,
        blocker_registry_before_iteration=blocker_registry_before_iteration,
        iterations=iterations,
        active_blocker_id=active_blocker_id,
        active_blocker_prior_state=active_blocker_prior_state,
        selection_reason_code=selection_reason_code,
        progress_cb=progress_cb,
    )
    emit_ticket_lifecycle_transition_fn = partial(
        _emit_ticket_lifecycle_transition_for_state,
        state=state,
        iterations=iterations,
        progress_cb=progress_cb,
    )
    set_pending_feedback_prompt_fn = partial(
        set_pending_feedback_prompt,
        state=state,
        iterations=iterations,
        latest_refs=state.latest_refs,
        progress_cb=progress_cb,
        emit_ticket_lifecycle_transition_fn=emit_ticket_lifecycle_transition_fn,
    )
    drain_pending_feedback_fn = partial(
        drain_pending_feedback,
        state=state,
        viewer_run_id=viewer_run_id,
        iterations=iterations,
        latest_refs=state.latest_refs,
        progress_cb=progress_cb,
        append_blocker_iteration_recap_fn=append_blocker_iteration_recap_fn,
        emit_ticket_lifecycle_transition_fn=emit_ticket_lifecycle_transition_fn,
        list_feedback_entries_fn=list_feedback_entries,
        poll_feedback_response_fn=poll_feedback_response,
        feedback_entry_signature_fn=feedback_entry_signature,
        normalize_feedback_response_fn=normalize_feedback_response,
    )

    if (
        isinstance(primary_registry_blocker, dict)
        and str(primary_registry_blocker.get("state") or "").strip().lower() == "answered_unintegrated"
        and not isinstance(focus_feedback, dict)
    ):
        focus_feedback = _feedback_payload_from_registry_row(primary_registry_blocker)
        if isinstance(focus_feedback, dict):
            state.latest_feedback = dict(focus_feedback)
            emit_progress(
                progress_cb,
                ticker_payload(
                    iteration=iterations,
                    phase="feedback_integration_branch",
                    message="Prioritizing answered_unintegrated blocker feedback integration before fresh evidence gathering.",
                    latest_refs=state.latest_refs,
                    detail={
                        "decision_key": str(focus_feedback.get("decision_key") or "").strip().lower() or None,
                        "blocker_id": str(primary_registry_blocker.get("blocker_id") or "").strip() or None,
                        "selection_reason_code": selection_reason_code,
                    },
                ),
            )

    span_context: list[dict[str, Any]] = []
    image_verification: dict[str, Any] = {}
    visual_evidence: dict[str, Any] = {}

    drained_plan = drain_pending_feedback_fn(checkpoint_label="iteration_start")
    if drained_plan is not None:
        focus_feedback = apply_consumed_feedback(state=state, feedback_payload=drained_plan)
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
            drained_plan = drain_pending_feedback_fn(checkpoint_label="no_progress_grace")
            if drained_plan is not None:
                focus_feedback = apply_consumed_feedback(state=state, feedback_payload=drained_plan)
                emit_progress(
                    progress_cb,
                    human_feedback_reused_payload(
                        iteration=iterations,
                        decision_key=str(drained_plan.get("decision_key") or "decision"),
                        selected_value=str(drained_plan.get("selected_value") or "selected"),
                        latest_refs=state.latest_refs,
                    ),
                )
        no_progress_focus_key = str(state.last_focus_key or "").strip().lower()
        recent_image_attempts = _recent_image_evidence_attempt_count(
            continuity_log=state.continuity_log,
            decision_key=no_progress_focus_key,
            window=8,
        )
        should_fallback_hitl_on_no_progress = (
            request.hitl_enabled
            and not state.pending_feedback_prompt_id
            and bool(no_progress_focus_key)
            and is_unresolved_target_scope_mapping_blocking_decision(state.decision_ledger, no_progress_focus_key)
            and recent_image_attempts >= 2
        )
        if should_fallback_hitl_on_no_progress:
            visual_evidence = _cached_visual_evidence_for_key(
                state=state,
                decision_key=no_progress_focus_key,
                source_transcript_ref=state.current_transcript_ref,
                source_transcript_hash=source_transcript_hash,
            )
            feedback_prompt = _build_feedback_prompt_with_optional_image(state=state, iterations=iterations, image_verification=image_verification, visual_evidence=visual_evidence)
            if isinstance(feedback_prompt, dict):
                emit_progress(
                    progress_cb,
                    ticker_payload(
                        iteration=iterations,
                        phase="human_feedback_needed",
                        message="Fallback HITL prompt issued after repeated image-evidence attempts with no material progress.",
                        latest_refs=state.latest_refs,
                        detail={
                            "fallback_driven": True,
                            "fallback_reason": "no_progress_repeated_image_evidence",
                            "decision_key": no_progress_focus_key,
                            "recent_image_evidence_attempts": int(recent_image_attempts),
                        },
                    ),
                )
                emit_progress(
                    progress_cb,
                    human_feedback_needed_payload(
                        iteration=iterations,
                        latest_refs=state.latest_refs,
                        feedback_prompt=feedback_prompt,
                        evidence_attempts={
                            "open_spans_count": 0,
                            "image_verify_count": int(recent_image_attempts),
                            "retrieval_count": 0,
                        },
                    ),
                )
                prompt_decision_key = (
                    str((feedback_prompt.get("context") or {}).get("decision_key") or "").strip().lower()
                    if isinstance(feedback_prompt.get("context"), dict)
                    else ""
                ) or no_progress_focus_key
                set_pending_feedback_prompt_fn(
                    feedback_prompt=feedback_prompt,
                    decision_key=prompt_decision_key,
                    supersession_reason="fallback_no_progress_repeated_image_evidence",
                )
                state.last_reason = "tx_agent_waiting_feedback_fallback_no_progress"
                append_blocker_iteration_recap_fn(
                    action_attempted="fallback_request_hitl",
                    result="waiting_feedback",
                    decision_key=prompt_decision_key,
                    reason="tx_agent_no_progress_fallback:repeated_image_evidence",
                )
                return TranscriptEditDecision(
                    status="waiting_feedback",
                    reason_code="tx_agent_waiting_feedback",
                    review_required=False,
                )
        reason = "tx_agent_no_progress"
        if state.last_progress_reason and state.last_progress_reason != "not_evaluated":
            reason = f"{reason}:{state.last_progress_reason}"
        if state.no_progress_streak >= request.max_no_progress_iterations:
            append_blocker_iteration_recap_fn(
                action_attempted="no_progress_guard",
                result="needs_review",
                decision_key=state.last_focus_key,
                reason=reason,
            )
            return TranscriptEditDecision(status="needs_review", reason_code=reason, review_required=True)
    if not state.current_transcript_ref:
        return TranscriptEditDecision(
            status="needs_review",
            reason_code="tx_agent_missing_source_ref_for_planning",
            review_required=True,
        )

    conflict_map = _conflict_map_from_ledger(state.decision_ledger)
    emit_progress(
        progress_cb,
        investigation_baseline_payload(
            iteration=iterations,
            latest_refs=state.latest_refs,
            conflict_map=conflict_map,
        ),
    )
    if manual_plan_override is not None:
        emit_progress(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="investigate",
                message="Manual plan override present; skipping automatic evidence gathering and proceeding to resolver/runtime gates.",
                latest_refs=state.latest_refs,
            ),
        )

    baseline_unresolved = unresolved_closure_requirements(state.decision_ledger)
    baseline_mapping_blocking_unresolved = unresolved_target_scope_mapping_blocking_requirements(state.decision_ledger)
    baseline_residual = [_baseline_residual_from_unresolved(item) for item in baseline_unresolved]
    mapping_blocking_count = len(baseline_mapping_blocking_unresolved)
    optional_count = max(0, len(baseline_residual) - mapping_blocking_count)
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
        append_blocker_iteration_recap_fn(
            action_attempted="await_feedback",
            result="no_advance",
            decision_key=state.pending_feedback_decision_key,
            reason="pending_feedback_prompt",
        )
        return None

    fallback_focus = mapping_focus or ledger_focus_fallback
    focus_target = _select_focus_target(
        blocker_registry=state.blocker_registry,
        decision_ledger=state.decision_ledger,
        fallback_focus=fallback_focus,
        focus_feedback=focus_feedback,
    )
    focus_key = str((focus_target or {}).get("decision_key") or "").strip().lower()
    focus_source = str((focus_target or {}).get("focus_source") or "legacy_fallback").strip().lower() or "legacy_fallback"
    focus_reason_code = str((focus_target or {}).get("focus_reason_code") or "fallback_focus").strip() or "fallback_focus"
    active_emergent_blocker = (
        dict((focus_target or {}).get("active_blocker"))
        if isinstance((focus_target or {}).get("active_blocker"), dict)
        else None
    )
    if (
        focus_source == "legacy_fallback"
        and not str((mapping_focus or {}).get("decision_key") or "").strip()
        and str((ledger_focus_fallback or {}).get("decision_key") or "").strip()
        and str((ledger_focus_fallback or {}).get("decision_key") or "").strip().lower() == str(focus_key or "").strip().lower()
    ):
        emit_progress(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="investigate",
                message="Resolver focus fallback applied from ledger helper due missing explicit primary focus context.",
                latest_refs=state.latest_refs,
                detail={
                    "focus_decision_key": str(focus_key or "").strip().lower() or None,
                    "fallback_driven": True,
                    "fallback_source": "choose_investigation_focus",
                    "focus_source": focus_source,
                },
            ),
        )
    mapping_focus = fallback_focus or {"decision_key": focus_key}
    if not str(focus_key or "").strip():
        append_blocker_iteration_recap_fn(
            action_attempted="resolver_focus_selection",
            result="needs_review",
            decision_key=None,
            reason="resolver_focus_missing",
        )
        return TranscriptEditDecision(
            status="needs_review",
            reason_code="tx_agent_focus_selection_failed",
            review_required=True,
        )
    prior_focus_key = str(state.last_focus_key or "").strip().lower()
    normalized_focus_key = str(focus_key or "").strip().lower()
    focus_advanced = bool(normalized_focus_key and prior_focus_key and normalized_focus_key != prior_focus_key)
    if normalized_focus_key and normalized_focus_key == prior_focus_key:
        state.focus_stagnation_streak += 1
    else:
        state.focus_stagnation_streak = 0
    state.last_focus_key = normalized_focus_key or state.last_focus_key
    emit_progress(
        progress_cb,
        ticker_payload(
            iteration=iterations,
            phase="investigate",
            message=f"Resolver focus selected: {normalized_focus_key or 'unknown'}.",
            latest_refs=state.latest_refs,
            detail={
                "focus_decision_key": normalized_focus_key or None,
                "previous_focus_decision_key": prior_focus_key or None,
                "focus_advanced": bool(focus_advanced),
                "focus_reason_code": focus_reason_code,
                "focus_source": focus_source,
                "active_blocker_id": (
                    str((active_emergent_blocker or {}).get("blocker_id") or "").strip() or None
                ),
                "active_blocker_kind": (
                    str((active_emergent_blocker or {}).get("blocker_kind") or "").strip().lower() or None
                ),
                "active_blocker_blocking_class": (
                    str((active_emergent_blocker or {}).get("blocking_class") or "").strip().lower() or None
                ),
                "focus_stagnation_streak": int(state.focus_stagnation_streak),
            },
        ),
    )
    span_context = _cached_span_context_for_key(
        state=state,
        decision_key=focus_key,
        source_transcript_ref=state.current_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )
    image_verification = _cached_image_verification_for_key(
        state=state,
        decision_key=focus_key,
        source_transcript_ref=state.current_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )
    visual_evidence = _cached_visual_evidence_for_key(
        state=state,
        decision_key=focus_key,
        source_transcript_ref=state.current_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )
    focus_packet = build_focus_packet(
        decision_ledger=state.decision_ledger,
        blocker_registry=state.blocker_registry,
        decision_key=focus_key or None,
        focus_source=focus_source,
        active_emergent_blocker=active_emergent_blocker,
        source_transcript_ref=state.current_transcript_ref,
        source_transcript_hash=source_transcript_hash,
        span_context=span_context,
        image_verification_payload=(image_verification if isinstance(image_verification, dict) else {}),
        visual_evidence_state=visual_evidence,
        feedback=focus_feedback,
        continuity_log=state.continuity_log,
    )
    active_ticket_snapshot = _active_ticket_snapshot(
        decision_ledger=state.decision_ledger,
        decision_key=focus_key,
    )
    resolver_attempt_number = int(state.invalid_plan_strikes) + 1
    emit_progress(
        progress_cb,
        resolver_attempt_payload(
            iteration=iterations,
            latest_refs=state.latest_refs,
            decision_key=focus_key or "",
            resolver_attempt_number=resolver_attempt_number,
            is_repair_attempt=bool(state.invalid_plan_strikes > 0),
            ticket_snapshot=active_ticket_snapshot,
        ),
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
    resolver_diag = (
        (resolver_outcome or {}).get("resolver_invalid_diagnostic")
        if isinstance(resolver_outcome, dict) and isinstance((resolver_outcome or {}).get("resolver_invalid_diagnostic"), dict)
        else {}
    )
    raw_output_excerpt = (
        str(resolver_diag.get("raw_output_excerpt") or "").strip()
        or str((resolver_outcome or {}).get("resolver_raw_output_excerpt") or "").strip()
        or None
    )
    validation_error_class = _extract_validation_error_class(resolver_reason)
    result_category = _resolver_result_category(move=move, reason=resolver_reason)
    emit_progress(
        progress_cb,
        resolver_outcome_payload(
            iteration=iterations,
            latest_refs=state.latest_refs,
            decision_key=focus_key or "",
            move=move or None,
            result_category=result_category,
            reason=resolver_reason,
            resolver_attempt_number=resolver_attempt_number,
            is_repair_attempt=bool(state.invalid_plan_strikes > 0),
            ticket_snapshot=active_ticket_snapshot,
            validation_error_class=validation_error_class,
            raw_output_excerpt=raw_output_excerpt,
        ),
    )
    supported_moves = {
        "gather_more_evidence",
        "apply_edit_plan",
        "request_human_feedback",
        "mark_blocked",
        "mark_resolved_no_edit",
        "propose_blocker_updates",
    }
    if move not in supported_moves:
        fallback_requested_hitl = (
            request.hitl_enabled
            and not state.pending_feedback_prompt_id
            and focus_feedback is None
            and mapping_blocking_count > 0
        )
        if fallback_requested_hitl:
            feedback_prompt = _build_feedback_prompt_with_optional_image(state=state, iterations=iterations, image_verification=image_verification, visual_evidence=visual_evidence)
            if feedback_prompt is not None:
                emit_progress(
                    progress_cb,
                    ticker_payload(
                        iteration=iterations,
                        phase="human_feedback_needed",
                        message="Fallback HITL prompt issued after resolver returned no usable move.",
                        latest_refs=state.latest_refs,
                        detail={
                            "decision_key": str((feedback_prompt.get("context") or {}).get("decision_key") or "").strip().lower() or None,
                            "fallback_driven": True,
                            "fallback_reason": "resolver_move_unusable",
                            "resolver_reason": resolver_reason,
                        },
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
                set_pending_feedback_prompt_fn(
                    feedback_prompt=feedback_prompt,
                    decision_key=str((feedback_prompt.get("context") or {}).get("decision_key") or "").strip().lower(),
                    supersession_reason="fallback_resolver_unusable_move",
                )
                state.last_reason = "tx_agent_closure_requirements_unresolved"
                append_blocker_iteration_recap_fn(
                    action_attempted="resolver_unusable_move",
                    result="waiting_feedback",
                    decision_key=focus_key,
                    reason=resolver_reason,
                )
                return None
        state.last_reason = "tx_agent_closure_requirements_unresolved"
        append_blocker_iteration_recap_fn(
            action_attempted="resolver_unusable_move",
            result="no_advance",
            decision_key=focus_key,
            reason=resolver_reason,
        )
        return None
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
    should_attempt_decisive_feedback_override = (
        move in {"request_human_feedback", "gather_more_evidence"}
        or (
            move == "mark_blocked"
            and resolver_reason.startswith("blocked_no_safe_integration_after_feedback")
        )
    )
    if (
        should_attempt_decisive_feedback_override
        and isinstance(decisive_feedback_payload, dict)
        and (answered_ticket is not None or stable_feedback_count >= 2)
    ):
        source_candidates: list[str] = []
        for candidate in (
            str(state.current_transcript_ref or "").strip(),
            str(request.source_transcript_ref or "").strip(),
        ):
            if candidate and candidate not in source_candidates:
                source_candidates.append(candidate)
        decisive_plan = None
        attempted_refs: list[str] = []
        for source_candidate in source_candidates:
            attempted_refs.append(source_candidate)
            decisive_plan = build_feedback_override_plan(
                source_transcript_ref=source_candidate,
                source_transcript_hash=source_transcript_hash,
                normalized_feedback=decisive_feedback_payload,
            )
            if isinstance(decisive_plan, dict):
                break
        if isinstance(decisive_plan, dict):
            if isinstance(resolver_outcome, dict):
                resolver_outcome["move"] = "apply_edit_plan"
                resolver_outcome["edit_plan"] = decisive_plan
            move = "apply_edit_plan"
            resolver_reason = f"stable_feedback_override_plan:{resolver_reason}"
        else:
            emit_progress(
                progress_cb,
                {
                    "iteration": iterations,
                    "phase": "feedback_override_plan",
                    "event_type": "resolver_outcome",
                    "message": "No safe deterministic override plan could be built from consumed feedback.",
                    "detail": {
                        "decision_key": str(decisive_feedback_payload.get("decision_key") or "").strip().lower() or focus_key,
                        "selected_value": str(decisive_feedback_payload.get("selected_value") or "").strip()[:120] or None,
                        "attempted_source_refs": attempted_refs,
                        "source_transcript_hash_present": bool(str(source_transcript_hash or "").strip()),
                        "stable_feedback_count": stable_feedback_count,
                    },
                    "latest_refs": state.latest_refs,
                },
            )
            if isinstance(answered_ticket, dict):
                state.decision_ledger = mark_human_resolution_ticket_state(
                    ledger=state.decision_ledger,
                    ticket_id=str(answered_ticket.get("ticket_id") or ""),
                    decision_key=str(answered_ticket.get("decision_key") or ""),
                    lifecycle_state="integration_attempted_failed",
                    relevance="active",
                )
                emit_ticket_lifecycle_transition_fn(
                    ticket_id=str(answered_ticket.get("ticket_id") or ""),
                    decision_key=str(answered_ticket.get("decision_key") or ""),
                    lifecycle_state="integration_attempted_failed",
                    relevance="active",
                    reason="no_safe_feedback_override_plan",
                )
            append_blocker_iteration_recap_fn(
                action_attempted="integrate_feedback",
                result="feedback_present_no_safe_plan",
                decision_key=focus_key,
                reason="no_safe_feedback_override_plan",
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
    if move == "propose_blocker_updates":
        blocker_updates = (
            resolver_outcome.get("blocker_updates")
            if isinstance(resolver_outcome, dict) and isinstance(resolver_outcome.get("blocker_updates"), list)
            else []
        )
        apply_result = apply_proposed_emergent_blocker_updates(
            registry=state.blocker_registry,
            blocker_updates=[
                row for row in blocker_updates if isinstance(row, dict)
            ],
            fallback_decision_key=focus_key,
        )
        state.blocker_registry = (
            dict(apply_result.get("registry"))
            if isinstance(apply_result.get("registry"), dict)
            else state.blocker_registry
        )
        accepted = [row for row in list(apply_result.get("accepted") or []) if isinstance(row, dict)]
        rejected = [row for row in list(apply_result.get("rejected") or []) if isinstance(row, dict)]
        emit_progress(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="blocker_update",
                message=(
                    f"Processed emergent blocker proposals: accepted={len(accepted)}, rejected={len(rejected)}."
                ),
                latest_refs=state.latest_refs,
                detail={
                    "accepted_count": len(accepted),
                    "rejected_count": len(rejected),
                    "move": "propose_blocker_updates",
                },
            ),
        )
        for row in accepted[:12]:
            emit_progress(
                progress_cb,
                blocker_update_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    status="accepted",
                    operation=str(row.get("operation") or "").strip().lower() or None,
                    blocker_id=str(row.get("blocker_id") or "").strip() or None,
                    blocker_kind=str(row.get("blocker_kind") or "").strip().lower() or None,
                    blocking_class=str(row.get("blocking_class") or "").strip().lower() or None,
                    reason=resolver_reason,
                ),
            )
        for row in rejected[:12]:
            emit_progress(
                progress_cb,
                blocker_update_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    status="rejected",
                    operation=str(row.get("operation") or "").strip().lower() or None,
                    blocker_id=str(row.get("blocker_id") or "").strip() or None,
                    blocker_kind=None,
                    blocking_class=None,
                    reason=str(row.get("reason") or "").strip() or "unknown_rejection",
                ),
            )
        if len(accepted) > 0:
            state.evidence_signal_counter += 1
            state.no_progress_streak = 0
            state.last_progress_reason = "emergent_blocker_update_accepted"
            append_blocker_iteration_recap_fn(
                action_attempted="propose_blocker_updates",
                result="accepted",
                decision_key=focus_key,
                reason=resolver_reason,
            )
            return None
        state.last_reason = "tx_agent_blocker_update_rejected"
        append_blocker_iteration_recap_fn(
            action_attempted="propose_blocker_updates",
            result="rejected",
            decision_key=focus_key,
            reason=resolver_reason,
        )
        return None
    if move == "request_human_feedback":
        emit_progress(
            progress_cb,
            resolver_move_gate_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
                decision_key=focus_key,
                move=move,
                gate_outcome="accepted",
                gate_reason="accepted_request_human_feedback",
                ticket_snapshot=active_ticket_snapshot,
            ),
        )
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
                feedback_prompt = _build_feedback_prompt_with_optional_image(state=state, iterations=iterations, image_verification=image_verification, visual_evidence=visual_evidence)
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
                set_pending_feedback_prompt_fn(
                    feedback_prompt=feedback_prompt,
                    decision_key=str((feedback_prompt.get("context") or {}).get("decision_key") or "").strip().lower(),
                    supersession_reason="resolver_requested_feedback",
                )
        state.last_reason = "tx_agent_closure_requirements_unresolved"
        append_blocker_iteration_recap_fn(
            action_attempted="request_hitl",
            result="waiting_feedback",
            decision_key=focus_key,
            reason=resolver_reason,
        )
        return None
    if move == "mark_blocked":
        if resolver_reason.startswith(("resolver_move_invalid:", "resolver_plan_invalid:")):
            emit_progress(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="retrying" if state.invalid_plan_strikes + 1 < request.max_invalid_plan_attempts else "blocked",
                    gate_reason="resolver_invalid_payload",
                    ticket_snapshot=active_ticket_snapshot,
                ),
            )
        if not _accept_mark_blocked(
            decision_ledger=state.decision_ledger,
            decision_key=focus_key,
            resolver_reason=resolver_reason,
            hitl_enabled=request.hitl_enabled,
        ):
            state.last_reason = f"mark_blocked_rejected:{resolver_reason}"
            emit_progress(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="rejected",
                    gate_reason="mark_blocked_rejected_by_runtime_gate",
                    ticket_snapshot=active_ticket_snapshot,
                ),
            )
            append_blocker_iteration_recap_fn(
                action_attempted="mark_blocked",
                result="rejected",
                decision_key=focus_key,
                reason=resolver_reason,
            )
            return None
        if not resolver_reason.startswith(("resolver_move_invalid:", "resolver_plan_invalid:")):
            emit_progress(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="accepted",
                    gate_reason=(
                        "blocked_no_safe_integration_after_feedback"
                        if resolver_reason.startswith("blocked_no_safe_integration_after_feedback")
                        else "accepted_mark_blocked"
                    ),
                    ticket_snapshot=active_ticket_snapshot,
                ),
            )
        if resolver_reason.startswith(("resolver_move_invalid:", "resolver_plan_invalid:")):
            reason_suffix = resolver_reason
            if reason_suffix.startswith("resolver_move_invalid:"):
                reason_suffix = reason_suffix.replace("resolver_move_invalid:", "", 1)
            if reason_suffix.startswith("resolver_plan_invalid:"):
                reason_suffix = reason_suffix.replace("resolver_plan_invalid:", "", 1)
            state.invalid_plan_strikes += 1
            exhausted = state.invalid_plan_strikes >= request.max_invalid_plan_attempts
            post_feedback_ticket_state = (
                str((resolver_outcome or {}).get("post_feedback_ticket_state") or "").strip().lower()
                if isinstance(resolver_outcome, dict)
                else ""
            ) or ("answered_unintegrated" if isinstance(answered_ticket, dict) else None)
            post_feedback_ticket_id = (
                str((resolver_outcome or {}).get("post_feedback_ticket_id") or "").strip()
                if isinstance(resolver_outcome, dict)
                else ""
            ) or (str((answered_ticket or {}).get("ticket_id") or "").strip() if isinstance(answered_ticket, dict) else None)
            validation_error_class = _extract_validation_error_class(reason_suffix)
            emit_progress(
                progress_cb,
                resolver_invalid_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    reason=reason_suffix,
                    invalid_plan_strikes=state.invalid_plan_strikes,
                    max_invalid_plan_attempts=request.max_invalid_plan_attempts,
                    exhausted=exhausted,
                    decision_key=focus_key,
                    post_feedback_ticket_state=post_feedback_ticket_state,
                    post_feedback_ticket_id=post_feedback_ticket_id,
                    validation_error_class=validation_error_class,
                    raw_output_excerpt=raw_output_excerpt,
                ),
            )
            if exhausted:
                if post_feedback_ticket_state in {"answered_unintegrated", "integration_attempted_failed"}:
                    if post_feedback_ticket_id:
                        state.decision_ledger = mark_human_resolution_ticket_state(
                            ledger=state.decision_ledger,
                            ticket_id=post_feedback_ticket_id,
                            decision_key=focus_key,
                            lifecycle_state="integration_attempted_failed",
                            relevance="active",
                        )
                    emit_ticket_lifecycle_transition_fn(
                        ticket_id=post_feedback_ticket_id,
                        decision_key=focus_key,
                        lifecycle_state="integration_attempted_failed",
                        relevance="active",
                        reason="resolver_invalid_exhausted",
                    )
                return TranscriptEditDecision(
                    status="needs_review",
                    reason_code=(
                        f"tx_agent_post_feedback_resolver_invalid_exhausted:{reason_suffix}"
                        if post_feedback_ticket_state in {"answered_unintegrated", "integration_attempted_failed"}
                        else f"tx_agent_plan_invalid_exhausted:{reason_suffix}"
                    ),
                    review_required=True,
                )
            state.last_reason = f"tx_agent_plan_invalid_retrying:{reason_suffix}"
            emit_progress(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="retrying",
                    gate_reason="resolver_invalid_retry_budget_remaining",
                    ticket_snapshot=active_ticket_snapshot,
                ),
            )
            return None
        return TranscriptEditDecision(
            status="needs_review",
            reason_code=(
                "tx_agent_consistent_feedback_no_safe_plan"
                if resolver_reason.startswith("blocked_no_safe_integration_after_feedback")
                else "tx_agent_closure_requirements_unresolved"
            ),
            review_required=True,
        )
    if move == "mark_resolved_no_edit":
        if _accept_mark_resolved_no_edit(
            decision_ledger=state.decision_ledger,
            decision_key=focus_key,
        ):
            emit_progress(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="accepted",
                    gate_reason="accepted_mark_resolved_no_edit",
                    ticket_snapshot=active_ticket_snapshot,
                ),
            )
            state.last_reason = resolver_reason
            return None
        state.last_reason = f"mark_resolved_no_edit_rejected:{resolver_reason}"
        emit_progress(
            progress_cb,
            resolver_move_gate_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
                decision_key=focus_key,
                move=move,
                gate_outcome="rejected",
                gate_reason="mark_resolved_no_edit_rejected_by_runtime_gate",
                ticket_snapshot=active_ticket_snapshot,
            ),
        )
        return None
    if move == "gather_more_evidence":
        evidence_request = (
            resolver_outcome.get("evidence_request")
            if isinstance(resolver_outcome, dict) and isinstance(resolver_outcome.get("evidence_request"), dict)
            else None
        )
        normalized_request, normalize_reason = normalize_evidence_request(
            evidence_request=evidence_request,
            decision_key=focus_key,
        )
        if normalized_request is None:
            evidence_kind = str((evidence_request or {}).get("kind") or "").strip().lower() or None
            evidence_mode = _evidence_request_mode_hint(evidence_request)
            state.last_reason = f"gather_more_evidence_rejected:{normalize_reason}"
            emit_progress(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="rejected",
                    gate_reason="invalid_evidence_request",
                    ticket_snapshot=active_ticket_snapshot,
                    normalize_reason=normalize_reason,
                    evidence_request_kind=evidence_kind,
                    evidence_request_mode=evidence_mode,
                ),
            )
            return None
        emit_progress(
            progress_cb,
            resolver_move_gate_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
                decision_key=focus_key,
                move=move,
                gate_outcome="accepted",
                gate_reason=f"accepted_new_evidence_kind:{str(normalized_request.get('kind') or '')}",
                ticket_snapshot=active_ticket_snapshot,
            ),
        )
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
                validation_mode=validation_mode,
            ),
            image_evidence_runner=lambda _req: _run_image_evidence_mode(
                normalized_request=_req,
                session_manager=session_manager,
                session_id=session_id,
                iteration=iterations,
                dossier_id=request.dossier_id,
                source_transcript_ref=state.current_transcript_ref or "",
                source_image_refs=request.source_image_refs,
                model=model,
                focus_decision_key=focus_key,
                top_findings=focus_findings,
                llm_call_seq_start=state.llm_call_seq,
                progress_cb=progress_cb,
                latest_visual_evidence=visual_evidence,
            ),
            retrieve_dependency_runner=None,
        )
        state.continuity_log.append(
            {
                "decision_key": focus_key,
                "move": "gather_more_evidence",
                "outcome": str(evidence_result.get("reason") or "evidence_result_unknown"),
                "evidence_kind": (
                    f"{str(evidence_result.get('kind') or '')}:{str(evidence_result.get('mode') or '')}".rstrip(":")
                ),
            }
        )
        if len(state.continuity_log) > 50:
            state.continuity_log = state.continuity_log[-50:]
        if str(evidence_result.get("status") or "") == "repeat_blocked":
            emit_progress(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="blocked",
                    gate_reason="rejected_repeated_evidence_after_binding_feedback",
                    ticket_snapshot=active_ticket_snapshot,
                ),
            )
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
            _cache_span_context_for_key(
                state=state,
                decision_key=focus_key,
                span_context=span_context,
                source_transcript_ref=state.current_transcript_ref,
                source_transcript_hash=source_transcript_hash,
            )
            state.evidence_signal_counter += 1
            emit_progress(
                progress_cb,
                open_spans_result_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    spans_display=[_span_to_display_dict(s) for s in span_context[:6]],
                ),
            )
        extra_image_evidence = (
            evidence_result.get("image_evidence")
            if isinstance(evidence_result.get("image_evidence"), dict)
            else {}
        )
        if extra_image_evidence:
            visual_evidence = _coerce_visual_evidence_state(extra_image_evidence)
            _cache_visual_evidence_for_key(
                state=state,
                decision_key=focus_key,
                visual_evidence=visual_evidence,
                source_transcript_ref=state.current_transcript_ref,
                source_transcript_hash=source_transcript_hash,
            )
            state.latest_refs = (
                dict(extra_image_evidence.get("latest_refs"))
                if isinstance(extra_image_evidence.get("latest_refs"), dict)
                else state.latest_refs
            )
            state.llm_call_seq = int(extra_image_evidence.get("llm_call_seq_end") or state.llm_call_seq)
            mode = str(extra_image_evidence.get("mode") or "").strip().lower() or "unknown"
            emit_progress(
                progress_cb,
                ticker_payload(
                    iteration=iterations,
                    phase="image_verify",
                    message=f"Image evidence {mode} completed for {focus_key}.",
                    latest_refs=state.latest_refs,
                    detail={
                        "evidence_kind": "image_evidence",
                        "mode": mode,
                        "decision_key": focus_key,
                        "tx_image_evidence_region_ref": visual_evidence.get("tx_image_evidence_region_ref"),
                        "tx_image_evidence_context_ref": visual_evidence.get("tx_image_evidence_context_ref"),
                        "locator_status": str((visual_evidence.get("locator") or {}).get("status") or ""),
                        "selector_type": visual_evidence.get("selector_type"),
                        "crop_box": visual_evidence.get("crop_box"),
                        "zoom_factor": visual_evidence.get("zoom_factor"),
                        "region_lineage": (
                            dict(visual_evidence.get("region_lineage"))
                            if isinstance(visual_evidence.get("region_lineage"), dict)
                            else {}
                        ),
                    },
                ),
            )
        extra_image_verification = (
            evidence_result.get("image_verification")
            if isinstance(evidence_result.get("image_verification"), dict)
            else {}
        )
        if extra_image_verification:
            image_verification = extra_image_verification
            _cache_image_verification_for_key(
                state=state,
                decision_key=focus_key,
                image_verification=image_verification,
                source_transcript_ref=state.current_transcript_ref,
                source_transcript_hash=source_transcript_hash,
            )
            state.llm_call_seq = int(image_verification.get("llm_call_seq_end") or state.llm_call_seq)
            state.latest_refs = image_verification.get("latest_refs", state.latest_refs)
            iv_payload = image_verification.get("payload") if isinstance(image_verification.get("payload"), dict) else {}
            if iv_payload:
                merged_visual = _visual_evidence_from_verify_payload(
                    verify_payload=iv_payload,
                    existing_visual_evidence=visual_evidence,
                )
                if merged_visual:
                    visual_evidence = merged_visual
                    _cache_visual_evidence_for_key(
                        state=state,
                        decision_key=focus_key,
                        visual_evidence=visual_evidence,
                        source_transcript_ref=state.current_transcript_ref,
                        source_transcript_hash=source_transcript_hash,
                    )
            iv_results = iv_payload.get("results") if isinstance(iv_payload, dict) else []
            iv_results = iv_results if isinstance(iv_results, list) else []
            iv_diagnostics = iv_payload.get("diagnostics") if isinstance(iv_payload.get("diagnostics"), list) else []
            before_sig = blocking_signature(state.decision_ledger)
            state.decision_ledger = update_ledger_from_iteration(
                ledger=state.decision_ledger,
                findings=planning_findings,
                image_results=[result for result in iv_results if isinstance(result, dict)],
            )
            state.blocker_registry = sync_registry_from_ledger(
                registry=state.blocker_registry,
                decision_ledger=state.decision_ledger,
                source_transcript_ref=state.current_transcript_ref,
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
                            "locator_status": str((r.get("locator") or {}).get("status") or ""),
                            "tx_image_evidence_region_ref": r.get("tx_image_evidence_region_ref"),
                            "tx_image_evidence_context_ref": r.get("tx_image_evidence_context_ref"),
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
                emit_progress(
                    progress_cb,
                    resolver_move_gate_payload(
                        iteration=iterations,
                        latest_refs=state.latest_refs,
                        decision_key=focus_key,
                        move="apply_edit_plan",
                        gate_outcome="rejected",
                        gate_reason="apply_scope_mismatch",
                        ticket_snapshot=active_ticket_snapshot,
                    ),
                )
                return TranscriptEditDecision(
                    status="needs_review",
                    reason_code="tx_agent_plan_invalid:focus_scope_mismatch",
                    review_required=True,
                )
            return None
        selected_plan_payload = manual_plan
        plan_reason = "resolver_edit_plan" if move == "apply_edit_plan" else "manual_plan"
        raw_plan_text = json.dumps(manual_plan, ensure_ascii=False)
        emit_progress(
            progress_cb,
            resolver_move_gate_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
                decision_key=focus_key,
                move="apply_edit_plan",
                gate_outcome="accepted",
                gate_reason="accepted_apply_for_answered_ticket" if isinstance(answered_ticket, dict) else "accepted_apply_edit_plan",
                ticket_snapshot=active_ticket_snapshot,
            ),
        )
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
            ticket_lifecycle_snapshot=_ticket_lifecycle_snapshot_for_key(
                decision_ledger=state.decision_ledger,
                decision_key=focus_key,
            ),
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
        prior_ref = str(state.current_transcript_ref or "").strip()
        next_ref = str(edited_ref).strip()
        if next_ref and next_ref != prior_ref:
            _clear_cached_focus_evidence(state=state)
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
        state.apply_reaudit_baseline_blocking_signature = blocking_signature(state.decision_ledger)
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
            emit_ticket_lifecycle_transition_fn(
                ticket_id=ticket_prompt_id,
                decision_key=ticket_decision_key,
                lifecycle_state="integrated",
                relevance="inactive",
                reason="apply_edit_plan",
            )
        state.blocker_registry = sync_registry_from_ledger(
            registry=state.blocker_registry,
            decision_ledger=state.decision_ledger,
            source_transcript_ref=state.current_transcript_ref,
        )
        remaining_for_focus = _registry_row_for_decision_key(
            registry=state.blocker_registry,
            decision_key=focus_key,
        )
        outcome_code = (
            "feedback_integrated_blocker_still_open"
            if isinstance(remaining_for_focus, dict)
            and str(remaining_for_focus.get("state") or "").strip().lower() in {"open", "waiting_feedback", "answered_unintegrated"}
            else "feedback_integrated_blocker_cleared"
        )
        append_blocker_iteration_recap_fn(
            action_attempted="integrate_feedback",
            result=outcome_code,
            decision_key=focus_key,
            reason="apply_edit_plan",
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


def _select_focus_target(
    *,
    decision_ledger: dict[str, Any],
    fallback_focus: dict[str, Any] | None,
    focus_feedback: dict[str, Any] | None,
    blocker_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    emergent_selection = (
        select_primary_emergent_blocker_with_reason(blocker_registry)
        if isinstance(blocker_registry, dict)
        else {"row": None, "reason_code": "no_registry"}
    )
    emergent_row = (
        dict(emergent_selection.get("row"))
        if isinstance(emergent_selection.get("row"), dict)
        else {}
    )
    if emergent_row:
        emergent_state = str(emergent_row.get("state") or "").strip().lower()
        if emergent_state in {"answered_unintegrated", "waiting_feedback", "open"}:
            emergent_decision_key = (
                str(emergent_row.get("legacy_decision_key") or "").strip().lower()
                or str(emergent_row.get("decision_key") or "").strip().lower()
            )
            # Bridge emergent blocker focus into current decision-key-driven runtime contracts.
            if not emergent_decision_key:
                emergent_decision_key = str((fallback_focus or {}).get("decision_key") or "").strip().lower()
            if emergent_decision_key:
                return {
                    "decision_key": emergent_decision_key,
                    "focus_source": "emergent_blocker",
                    "focus_reason_code": str(emergent_selection.get("reason_code") or "emergent_selected"),
                    "active_blocker": emergent_row,
                }

    primary = select_primary_blocker(blocker_registry if isinstance(blocker_registry, dict) else None) or {}
    primary_key = str(primary.get("decision_key") or "").strip().lower()
    primary_state = str(primary.get("state") or "").strip().lower()
    if (
        primary_key
        and primary_state in {"answered_unintegrated", "waiting_feedback"}
        and is_unresolved_target_scope_mapping_blocking_decision(decision_ledger, primary_key)
    ):
        return {
            "decision_key": primary_key,
            "focus_source": "legacy_fallback",
            "focus_reason_code": "legacy_priority_feedback_state",
            "active_blocker": None,
        }
    if isinstance(focus_feedback, dict):
        feedback_key = str(focus_feedback.get("decision_key") or "").strip().lower()
        if feedback_key and is_unresolved_target_scope_mapping_blocking_decision(decision_ledger, feedback_key):
            return {
                "decision_key": feedback_key,
                "focus_source": "legacy_fallback",
                "focus_reason_code": "legacy_feedback_key",
                "active_blocker": None,
            }
    key = str((fallback_focus or {}).get("decision_key") or "").strip().lower()
    if key:
        return {
            "decision_key": key,
            "focus_source": "legacy_fallback",
            "focus_reason_code": "legacy_fallback_focus",
            "active_blocker": None,
        }
    return {
        "decision_key": "",
        "focus_source": "legacy_fallback",
        "focus_reason_code": "legacy_focus_missing",
        "active_blocker": None,
    }


def _select_focus_decision_key(
    *,
    decision_ledger: dict[str, Any],
    fallback_focus: dict[str, Any] | None,
    focus_feedback: dict[str, Any] | None,
    blocker_registry: dict[str, Any] | None = None,
) -> str:
    return select_focus_decision_key(
        decision_ledger=decision_ledger,
        fallback_focus=fallback_focus,
        focus_feedback=focus_feedback,
        blocker_registry=blocker_registry,
        select_focus_target_fn=_select_focus_target,
    )


def _normalize_feedback_selected_value(*, decision_key: str, selected_value: str) -> str:
    return normalize_feedback_selected_value(decision_key=decision_key, selected_value=selected_value)


def _stable_feedback_confirmation_count(
    *,
    hitl_lifecycle_log: list[dict[str, Any]],
    decision_key: str | None,
    selected_value: str | None,
) -> int:
    return stable_feedback_confirmation_count(
        hitl_lifecycle_log=hitl_lifecycle_log,
        decision_key=decision_key,
        selected_value=selected_value,
    )


def _latest_human_resolution_ticket(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str | None,
    lifecycle_states: set[str],
) -> dict[str, Any] | None:
    return latest_human_resolution_ticket(
        decision_ledger=decision_ledger,
        decision_key=decision_key,
        lifecycle_states=lifecycle_states,
    )


def _feedback_payload_from_ticket(
    *,
    answered_ticket: dict[str, Any] | None,
    decision_key: str | None,
) -> dict[str, Any] | None:
    return feedback_payload_from_ticket(answered_ticket=answered_ticket, decision_key=decision_key)


def _feedback_payload_from_registry_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return feedback_payload_from_registry_row(row)


def _extract_validation_error_class(reason_suffix: str) -> str | None:
    return extract_validation_error_class(reason_suffix)


def _ticket_lifecycle_snapshot_for_key(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str | None,
) -> list[dict[str, Any]]:
    return ticket_lifecycle_snapshot_for_key(
        decision_ledger=decision_ledger,
        decision_key=decision_key,
    )


def _active_ticket_snapshot(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str | None,
) -> dict[str, Any] | None:
    return active_ticket_snapshot(
        decision_ledger=decision_ledger,
        decision_key=decision_key,
    )


def _resolver_result_category(*, move: str, reason: str) -> str:
    return resolver_result_category(move=move, reason=reason)


def _accept_mark_resolved_no_edit(*, decision_ledger: dict[str, Any], decision_key: str) -> bool:
    return accept_mark_resolved_no_edit(decision_ledger=decision_ledger, decision_key=decision_key)


def _accept_mark_blocked(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str,
    resolver_reason: str,
    hitl_enabled: bool,
) -> bool:
    return accept_mark_blocked(
        decision_ledger=decision_ledger,
        decision_key=decision_key,
        resolver_reason=resolver_reason,
        hitl_enabled=hitl_enabled,
    )


def _recent_image_evidence_attempt_count(
    *,
    continuity_log: list[dict[str, Any]],
    decision_key: str | None,
    window: int = 8,
) -> int:
    return recent_image_evidence_attempt_count(
        continuity_log=continuity_log,
        decision_key=decision_key,
        window=window,
    )


def _accept_apply_edit_plan(
    *,
    resolver_decision_key: str,
    focus_key: str,
    plan_payload: dict[str, Any],
) -> bool:
    return accept_apply_edit_plan(
        resolver_decision_key=resolver_decision_key,
        focus_key=focus_key,
        plan_payload=plan_payload,
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
    return open_planner_context_spans_adapter(
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
    validation_mode: str = "off",
) -> dict[str, Any]:
    return verify_mapping_critical_with_image_adapter(
        session_manager=session_manager,
        session_id=session_id,
        iteration=iteration,
        dossier_id=dossier_id,
        source_transcript_ref=source_transcript_ref,
        top_findings=top_findings,
        source_image_refs=source_image_refs,
        model=model,
        progress_cb=progress_cb,
        focus_decision_key=focus_decision_key,
        llm_call_seq_start=llm_call_seq_start,
        validation_mode=validation_mode,
        step_fn=_step_kernel_action,
        read_step_outputs_inline_fn=read_step_outputs_inline,
        read_str_fn=read_str,
    )


def _run_image_evidence_mode(
    *,
    normalized_request: dict[str, Any],
    session_manager: KernelSessionManager,
    session_id: str,
    iteration: int,
    dossier_id: str | None,
    source_transcript_ref: str,
    source_image_refs: list[str],
    model: str,
    focus_decision_key: str | None,
    top_findings: list[dict[str, Any]],
    llm_call_seq_start: int,
    progress_cb: Callable[[dict[str, Any]], None] | None,
    latest_visual_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    return run_image_evidence_mode(
        normalized_request=normalized_request,
        session_manager=session_manager,
        session_id=session_id,
        iteration=iteration,
        dossier_id=dossier_id,
        source_transcript_ref=source_transcript_ref,
        source_image_refs=source_image_refs,
        model=model,
        focus_decision_key=focus_decision_key,
        top_findings=top_findings,
        llm_call_seq_start=llm_call_seq_start,
        progress_cb=progress_cb,
        latest_visual_evidence=latest_visual_evidence,
        step_fn=_step_kernel_action,
        read_step_outputs_inline_fn=read_step_outputs_inline,
    )


def _image_verify_runtime_config(validation_mode: str | None) -> dict[str, Any]:
    return image_verify_runtime_config(validation_mode)


def _span_to_display_dict(span: dict[str, Any]) -> dict[str, Any]:
    text = str(span.get("text") or span.get("content") or "").strip()
    return {
        "span_id": span.get("span_id"),
        "text": text[:120] + ("..." if len(text) > 120 else ""),
    }


def _findings_for_focus_key(*, top_findings: list[dict[str, Any]], focus_key: str) -> list[dict[str, Any]]:
    return findings_for_focus_key(top_findings=top_findings, focus_key=focus_key)


def _decision_key_for_finding(finding: dict[str, Any]) -> str:
    return decision_key_for_finding(finding)


def _conflict_map_from_ledger(ledger: dict[str, Any] | None) -> list[dict[str, Any]]:
    return conflict_map_from_ledger(ledger)


def _baseline_residual_from_unresolved(item: dict[str, Any]) -> dict[str, Any]:
    return baseline_residual_from_unresolved(item)


def _baseline_evidence_attempts(
    *,
    span_context: list[dict[str, Any]],
    image_verification: dict[str, Any],
) -> list[dict[str, Any]]:
    return baseline_evidence_attempts(
        span_context=span_context,
        image_verification=image_verification,
    )


def _next_recommended_action_text(residual_blockers: list[dict[str, Any]]) -> str:
    return next_recommended_action_text(residual_blockers)


def _cached_span_context_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> list[dict[str, Any]]:
    return cached_span_context_for_key(
        state=state,
        decision_key=decision_key,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )


def _cache_span_context_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    span_context: list[dict[str, Any]],
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> None:
    cache_span_context_for_key(
        state=state,
        decision_key=decision_key,
        span_context=span_context,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )


def _cached_image_verification_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> dict[str, Any]:
    return cached_image_verification_for_key(
        state=state,
        decision_key=decision_key,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )


def _cached_visual_evidence_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> dict[str, Any]:
    return cached_visual_evidence_for_key(
        state=state,
        decision_key=decision_key,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )


def _cache_image_verification_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    image_verification: dict[str, Any],
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> None:
    cache_image_verification_for_key(
        state=state,
        decision_key=decision_key,
        image_verification=image_verification,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )


def _cache_visual_evidence_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    visual_evidence: dict[str, Any],
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> None:
    cache_visual_evidence_for_key(
        state=state,
        decision_key=decision_key,
        visual_evidence=visual_evidence,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )


def _coerce_visual_evidence_state(raw: dict[str, Any] | None) -> dict[str, Any]:
    return coerce_visual_evidence_state(raw)


def _selector_type_from_target(target: dict[str, Any]) -> str | None:
    return selector_type_from_target(target)


def _evidence_request_mode_hint(evidence_request: dict[str, Any] | None) -> str | None:
    return evidence_request_mode_hint(evidence_request)


def _visual_evidence_from_verify_payload(
    *,
    verify_payload: dict[str, Any],
    existing_visual_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    return visual_evidence_from_verify_payload(
        verify_payload=verify_payload,
        existing_visual_evidence=existing_visual_evidence,
    )


def _coerce_artifact_ref_for_state(raw: Any) -> dict[str, Any] | None:
    return coerce_artifact_ref_for_state(raw)


def _cache_entry_matches_transcript(
    *,
    entry: dict[str, Any],
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> bool:
    return cache_entry_matches_transcript(
        entry=entry,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )


def _clear_cached_focus_evidence(
    *,
    state: TranscriptEditLoopState,
) -> None:
    clear_cached_focus_evidence(state=state)


def _registry_row_for_decision_key(
    *,
    registry: dict[str, Any] | None,
    decision_key: str | None,
) -> dict[str, Any] | None:
    return registry_row_for_decision_key(
        registry=registry,
        decision_key=decision_key,
    )

