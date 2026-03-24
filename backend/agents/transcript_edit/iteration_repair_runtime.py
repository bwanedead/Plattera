from __future__ import annotations

import json
import time
from collections.abc import Callable
from functools import partial
from typing import Any

from agent_kernel.models import StepExecutionState

from .execution_action_ids import TX_PROMOTE_TRANSCRIPT_FOR_MAPPING, TX_SAVE_TRANSCRIPT_SPAN_SEEDS
from agent_kernel import KernelSessionManager
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
from .llm_startup_understanding import select_startup_focus_key
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
from .decision_ledger_adapter import transcript_edit_unified_and_closure_read_from_loop_state
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
from .iteration_repair_focus import (
    _accept_apply_edit_plan,
    _accept_mark_blocked,
    _accept_mark_resolved_no_edit,
    _accept_request_human_feedback,
    _active_ticket_snapshot,
    _baseline_evidence_attempts,
    _baseline_residual_from_unresolved,
    _conflict_map_from_ledger,
    _decision_key_for_finding,
    _extract_validation_error_class,
    _feedback_payload_from_registry_row,
    _feedback_payload_from_ticket,
    _findings_for_focus_key,
    _latest_human_resolution_ticket,
    _next_recommended_action_text,
    _normalize_feedback_selected_value,
    _recent_image_evidence_attempt_count,
    _registry_row_for_decision_key,
    _resolver_result_category,
    _select_focus_decision_key,
    _select_focus_target,
    _stable_feedback_confirmation_count,
    _ticket_lifecycle_snapshot_for_key,
)
from .iteration_repair_moves import (
    _cache_image_verification_for_key,
    _cache_span_context_for_key,
    _cache_visual_evidence_for_key,
    _cached_image_verification_for_key,
    _cached_span_context_for_key,
    _cached_visual_evidence_for_key,
    _clear_cached_focus_evidence,
    _coerce_artifact_ref_for_state,
    _coerce_visual_evidence_state,
    _evidence_request_mode_hint,
    _image_verify_runtime_config,
    _open_planner_context_spans,
    _run_image_evidence_mode,
    _selector_type_from_target,
    _span_to_display_dict,
    _step_kernel_action,
    _verify_mapping_critical_with_image,
    _visual_evidence_from_verify_payload,
    handle_repair_move_outcome,
)

MAX_EVIDENCE_REPEATS_PER_SIGNATURE = 2


def _focus_packet_support_state(focus_packet: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(focus_packet, dict):
        return {}
    support_state = focus_packet.get("support_state")
    if isinstance(support_state, dict):
        return dict(support_state)
    out: dict[str, Any] = {}
    if isinstance(focus_packet.get("investigation_brief"), dict):
        out["investigation_brief"] = focus_packet.get("investigation_brief")
    if isinstance(focus_packet.get("working_plan"), dict):
        out["working_plan"] = focus_packet.get("working_plan")
    if isinstance(focus_packet.get("policy_signals"), dict):
        out["policy_signals"] = focus_packet.get("policy_signals")
    return out


def run_standalone_edit_planner_for_focus_packet(
    *,
    planner_client: TranscriptEditPlanPlanner,
    model: str,
    focus_packet: dict[str, Any],
    findings_summary: dict[str, Any],
    top_findings: list[dict[str, Any]],
    span_context: list[dict[str, Any]],
    image_verification: dict[str, Any] | None,
    mapping_priority_focus: dict[str, Any] | None,
    max_attempts: int,
    run_link_id: str = "",
    mission_objective: str = "",
) -> tuple[Any, str, str]:
    """Invoke ``propose_plan`` with the same bounded ``execution_context`` as the resolver path.

    Lives here (not a separate bridge module) so the edit-planner call stays next to repair iteration wiring.
    """
    execution_context = focus_packet.get("execution_context") if isinstance(focus_packet.get("execution_context"), dict) else None
    support_state = _focus_packet_support_state(focus_packet)
    investigation_brief = support_state.get("investigation_brief") if isinstance(support_state.get("investigation_brief"), dict) else None
    working_plan = support_state.get("working_plan") if isinstance(support_state.get("working_plan"), dict) else None
    span_trim = [dict(x) for x in span_context if isinstance(x, dict)][:32]
    findings_trim = [dict(x) for x in top_findings if isinstance(x, dict)][:12]
    return planner_client.propose_plan(
        model=model,
        source_transcript_ref=str(focus_packet.get("source_transcript_ref") or ""),
        source_transcript_hash=str(focus_packet.get("source_transcript_hash") or ""),
        findings_summary=findings_summary if isinstance(findings_summary, dict) else {},
        top_findings=findings_trim,
        span_context=span_trim,
        image_verification=image_verification if isinstance(image_verification, dict) else {},
        candidate_disagreement_hints=None,
        mapping_priority_focus=mapping_priority_focus if isinstance(mapping_priority_focus, dict) else {},
        max_attempts=max_attempts,
        investigation_brief=investigation_brief,
        working_plan=working_plan,
        run_link_id=run_link_id,
        mission_objective=mission_objective,
        execution_context=execution_context,
    )


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
    _, closure_read = transcript_edit_unified_and_closure_read_from_loop_state(state)
    prompt = build_human_feedback_prompt(
        decision_ledger=closure_read,
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
    _, closure_read = transcript_edit_unified_and_closure_read_from_loop_state(state)
    unresolved_mapping_blocking_closure = has_unresolved_target_scope_mapping_blocking_closure(closure_read)
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
            action_type=TX_SAVE_TRANSCRIPT_SPAN_SEEDS,
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
            action_type=TX_PROMOTE_TRANSCRIPT_FOR_MAPPING,
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
    unified_decision_ledger, closure_read_ledger = transcript_edit_unified_and_closure_read_from_loop_state(state)
    state.blocker_registry = sync_registry_from_ledger(
        registry=state.blocker_registry,
        decision_ledger=closure_read_ledger,
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
    startup_focus_key = select_startup_focus_key(
        last_focus_key=None,
        startup=(
            dict(state.llm_startup_understanding)
            if isinstance(state.llm_startup_understanding, dict)
            else (
                dict(state.decision_ledger.get("llm_startup_understanding"))
                if isinstance(state.decision_ledger, dict)
                and isinstance(state.decision_ledger.get("llm_startup_understanding"), dict)
                else None
            )
        ),
    )
    ledger_focus_fallback: dict[str, Any] = (
        {"decision_key": startup_focus_key, "focus_source": "startup_understanding"}
        if startup_focus_key
        else {}
    )
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
            and is_unresolved_target_scope_mapping_blocking_decision(closure_read_ledger, no_progress_focus_key)
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

    conflict_map = _conflict_map_from_ledger(closure_read_ledger)
    emit_progress(
        progress_cb,
        investigation_baseline_payload(
            iteration=iterations,
            latest_refs=state.latest_refs,
            conflict_map=conflict_map,
            step_story={
                "step_kind": "investigation_baseline",
                "why_now": "The run needs a baseline case model before deeper action.",
                "trigger": "baseline_investigation",
                "state_before_summary": {
                    "conflict_count": len(conflict_map),
                },
                "next_step_rationale": "Use the baseline to decide whether the case is still weak or ready for narrower work.",
            },
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

    baseline_unresolved = unresolved_closure_requirements(closure_read_ledger)
    baseline_mapping_blocking_unresolved = unresolved_target_scope_mapping_blocking_requirements(closure_read_ledger)
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
            step_story={
                "step_kind": "investigation_baseline_result",
                "why_now": "The baseline pass produced a current summary of the case.",
                "trigger": "baseline_investigation_complete",
                "state_before_summary": {
                    "mapping_blocking_count": mapping_blocking_count,
                    "optional_count": optional_count,
                },
                "state_delta": {"next_recommended_action": next_recommended_action},
                "outcome_class": "informational",
                "next_step_rationale": next_recommended_action,
            },
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

    continuity_focus = (
        {"decision_key": str(state.last_focus_key or "").strip().lower()}
        if str(state.last_focus_key or "").strip()
        else {}
    )
    fallback_focus = mapping_focus or continuity_focus or ledger_focus_fallback
    focus_target = _select_focus_target(
        blocker_registry=state.blocker_registry,
        decision_ledger=closure_read_ledger,
        fallback_focus=fallback_focus,
        focus_feedback=focus_feedback,
    )
    focus_key = str((focus_target or {}).get("decision_key") or "").strip().lower()
    focus_source = str((focus_target or {}).get("focus_source") or "legacy_fallback").strip().lower() or "legacy_fallback"
    focus_reason_code = str((focus_target or {}).get("focus_reason_code") or "fallback_focus").strip() or "fallback_focus"
    focus_target_kind_selected = str((focus_target or {}).get("focus_target_kind") or "").strip() or None
    focus_authority_snapshot = (
        dict((focus_target or {})["focus_authority"])
        if isinstance((focus_target or {}).get("focus_authority"), dict)
        else None
    )
    if focus_authority_snapshot is None and isinstance(ledger_focus_fallback, dict):
        fk_fb = str(ledger_focus_fallback.get("decision_key") or "").strip().lower()
        if fk_fb and fk_fb == str(focus_key or "").strip().lower():
            fa_fb = ledger_focus_fallback.get("focus_authority")
            if isinstance(fa_fb, dict):
                focus_authority_snapshot = dict(fa_fb)
    active_emergent_blocker = (
        dict((focus_target or {}).get("active_blocker"))
        if isinstance((focus_target or {}).get("active_blocker"), dict)
        else None
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
    # Native store only — ``build_focus_packet`` derives unified + closure reads internally.
    focus_packet = build_focus_packet(
        decision_ledger=state.decision_ledger,
        blocker_registry=state.blocker_registry,
        decision_key=focus_key or None,
        focus_source=focus_source,
        focus_reason_code=focus_reason_code,
        loop_iteration=iterations,
        active_emergent_blocker=active_emergent_blocker,
        source_transcript_ref=state.current_transcript_ref,
        source_transcript_hash=source_transcript_hash,
        span_context=span_context,
        image_verification_payload=(image_verification if isinstance(image_verification, dict) else {}),
        visual_evidence_state=visual_evidence,
        feedback=focus_feedback,
        continuity_log=state.continuity_log,
        evidence_repeat_guard=state.evidence_repeat_guard,
        evidence_signal_counter=state.evidence_signal_counter,
        harness_emergent_board_items=state.harness_emergent_board_items,
        harness_board_context_notes=state.harness_board_context_notes,
    )
    if request.run_standalone_edit_planner:
        run_standalone_edit_planner_for_focus_packet(
            planner_client=planner_client,
            model=model,
            focus_packet=focus_packet,
            findings_summary=findings_summary,
            top_findings=top_findings,
            span_context=span_context,
            image_verification=image_verification if isinstance(image_verification, dict) else {},
            mapping_priority_focus=mapping_focus if isinstance(mapping_focus, dict) else {},
            max_attempts=request.max_invalid_plan_attempts,
            run_link_id=str(viewer_run_id or ""),
            mission_objective=request.mission_objective or "",
        )
    focus_policy_signals = _focus_packet_support_state(focus_packet).get("policy_signals") or {}
    if (
        focus_source == "legacy_fallback"
        and not str((fallback_focus or {}).get("decision_key") or "").strip()
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
                    "fallback_source": "startup_understanding",
                    "focus_source": focus_source,
                    "step_story": {
                        "step_kind": "focus_selection",
                        "why_now": "The runtime needed a defensible next focus from existing ledger state, and the current posture makes fresh signal versus cached context visible.",
                        "trigger": "legacy_focus_fallback",
                        "state_before_summary": {
                            "focus_stagnation_streak": int(state.focus_stagnation_streak),
                            "understanding_strength": str((focus_policy_signals or {}).get("understanding_strength") or "unknown").strip().lower() or "unknown",
                            "has_fresh_signal": bool((focus_policy_signals or {}).get("has_fresh_signal")),
                            "cached_context_present": bool((focus_policy_signals or {}).get("cached_context_present")),
                            "repeat_without_signal": bool((focus_policy_signals or {}).get("repeat_without_signal")),
                        },
                        "outcome_class": "fallback",
                        "next_step_rationale": "Continue from the selected focus item rather than rediscovering the entire case.",
                    },
                },
            ),
        )
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
                "step_story": {
                    "step_kind": "focus_selection",
                    "why_now": "The loop needs a single focus target before deeper work, and the current posture shows whether it is driven by fresh signal or cached context.",
                    "trigger": focus_reason_code,
                    "state_before_summary": {
                        "previous_focus_decision_key": prior_focus_key or None,
                        "focus_stagnation_streak": int(state.focus_stagnation_streak),
                        "understanding_strength": str((focus_policy_signals or {}).get("understanding_strength") or "unknown").strip().lower() or "unknown",
                        "has_fresh_signal": bool((focus_policy_signals or {}).get("has_fresh_signal")),
                        "cached_context_present": bool((focus_policy_signals or {}).get("cached_context_present")),
                        "repeat_without_signal": bool((focus_policy_signals or {}).get("repeat_without_signal")),
                    },
                    "state_delta": {
                        "focus_decision_key": normalized_focus_key or None,
                        "focus_advanced": bool(focus_advanced),
                        "focus_target_kind": focus_target_kind_selected,
                        "board_authority_mode": (
                            (focus_authority_snapshot or {}).get("mode") if isinstance(focus_authority_snapshot, dict) else None
                        ),
                    },
                    "outcome_class": "advanced" if focus_advanced else "steady",
                    "next_step_rationale": "Use the selected focus to gather evidence, update support state, or promote blockers if the posture still needs narrowing.",
                },
            },
        ),
    )
    active_ticket_snapshot = _active_ticket_snapshot(
        decision_ledger=closure_read_ledger,
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
            step_story={
                "step_kind": "resolver_attempt",
                "why_now": "The selected focus needs a bounded next move, with the current freshness posture shaping the attempt.",
                "trigger": "resolve_focus_move",
                "state_before_summary": {
                    "focus_key": focus_key or None,
                    "understanding_strength": str((focus_policy_signals or {}).get("understanding_strength") or "unknown").strip().lower() or "unknown",
                    "has_fresh_signal": bool((focus_policy_signals or {}).get("has_fresh_signal")),
                    "cached_context_present": bool((focus_policy_signals or {}).get("cached_context_present")),
                    "repeat_without_signal": bool((focus_policy_signals or {}).get("repeat_without_signal")),
                },
                "next_step_rationale": "Read the resolver outcome and gate it against runtime policy with freshness posture in view.",
            },
        ),
    )
    resolver_outcome = resolve_focus_move(
        focus_packet=focus_packet,
        planner_client=planner_client,
        model=model,
        findings_summary=findings_summary,
        planning_findings=planning_findings,
        max_invalid_plan_attempts=request.max_invalid_plan_attempts,
        validation_mode=validation_mode,
        run_link_id=str(viewer_run_id or ""),
        mission_objective=request.mission_objective or "",
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
            step_story={
                "step_kind": "resolver_outcome",
                "why_now": "The resolver produced the immediate next move candidate, which still needs to be interpreted against the current freshness posture.",
                "trigger": result_category,
                "state_before_summary": {
                    "focus_key": focus_key or None,
                    "resolver_attempt_number": resolver_attempt_number,
                    "understanding_strength": str((focus_policy_signals or {}).get("understanding_strength") or "unknown").strip().lower() or "unknown",
                    "has_fresh_signal": bool((focus_policy_signals or {}).get("has_fresh_signal")),
                    "cached_context_present": bool((focus_policy_signals or {}).get("cached_context_present")),
                    "repeat_without_signal": bool((focus_policy_signals or {}).get("repeat_without_signal")),
                },
                "state_delta": {
                    "move": move or None,
                    "reason": resolver_reason,
                },
                "outcome_class": result_category,
                "next_step_rationale": "Apply runtime gating and then update the case state from the accepted move or gate rejection, keeping freshness posture explicit.",
            },
        ),
    )
    supported_moves = {
        "gather_more_evidence",
        "apply_edit_plan",
        "request_human_feedback",
        "mark_blocked",
        "mark_resolved_no_edit",
        "propose_blocker_updates",
        "propose_work_board_changes",
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
        decision_ledger=closure_read_ledger,
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
    pre_move_decision = handle_repair_move_outcome(
        state=state,
        request=request,
        tx_persistence=tx_persistence,
        session_manager=session_manager,
        session_id=session_id,
        iterations=iterations,
        focus_key=focus_key,
        focus_source=focus_source,
        move=move,
        resolver_reason=resolver_reason,
        resolver_outcome=resolver_outcome if isinstance(resolver_outcome, dict) else None,
        answered_ticket=answered_ticket,
        focus_feedback=focus_feedback,
        planning_findings=planning_findings,
        source_transcript_hash=source_transcript_hash,
        model=model,
        validation_mode=validation_mode,
        active_ticket_snapshot=active_ticket_snapshot,
        visual_evidence=visual_evidence,
        image_verification=image_verification,
        evidence_attempts_counts=evidence_attempts_counts,
        raw_output_excerpt=raw_output_excerpt,
        policy_signals=_focus_packet_support_state(focus_packet).get("policy_signals") or {},
        emit_progress_fn=emit_progress,
        progress_cb=progress_cb,
        append_blocker_iteration_recap_fn=append_blocker_iteration_recap_fn,
        emit_ticket_lifecycle_transition_fn=emit_ticket_lifecycle_transition_fn,
        set_pending_feedback_prompt_fn=set_pending_feedback_prompt_fn,
        build_feedback_prompt_fn=_build_feedback_prompt_with_optional_image,
        accept_mark_blocked_fn=_accept_mark_blocked,
        accept_mark_resolved_no_edit_fn=_accept_mark_resolved_no_edit,
        accept_apply_edit_plan_fn=_accept_apply_edit_plan,
        findings_for_focus_key_fn=_findings_for_focus_key,
        extract_validation_error_class_fn=_extract_validation_error_class,
        ticket_lifecycle_snapshot_for_key_fn=_ticket_lifecycle_snapshot_for_key,
        latest_human_resolution_ticket_fn=_latest_human_resolution_ticket,
        registry_row_for_decision_key_fn=_registry_row_for_decision_key,
    )
    lob = state.last_board_observability
    if isinstance(lob, dict) and lob:
        emit_progress(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="board_observability",
                message="Board lifecycle or work-board promotion recorded for audit.",
                latest_refs=state.latest_refs,
                detail={
                    "board_observability_compact": {
                        "event": lob.get("event"),
                        "focus_target_kind": lob.get("focus_target_kind"),
                        "board_item_id": lob.get("board_item_id"),
                        "board_state_before": lob.get("board_state_before"),
                        "board_state_after": lob.get("board_state_after"),
                        "board_transition_reason": lob.get("board_transition_reason"),
                        "board_recency_rank": lob.get("board_recency_rank"),
                        "newly_promoted": lob.get("newly_promoted"),
                        "recently_touched": lob.get("recently_touched"),
                    },
                    "step_story": {
                        "step_kind": "board_progress",
                        "why_now": "A durable work-board row changed or was promoted; this makes harness-emergent work inspectable from run output.",
                        "trigger": str(lob.get("event") or "board_progress"),
                        "state_before_summary": {
                            "board_item_id": lob.get("board_item_id"),
                            "board_state_before": lob.get("board_state_before"),
                            "focus_target_kind": lob.get("focus_target_kind"),
                        },
                        "state_delta": {
                            "board_state_after": lob.get("board_state_after"),
                            "board_transition_reason": lob.get("board_transition_reason"),
                            "board_recency_rank": lob.get("board_recency_rank"),
                        },
                        "outcome_class": "board_progress",
                        "next_step_rationale": "Bounded board_focus_context on the next focus packet carries active-item posture.",
                    },
                },
            ),
        )
        state.last_board_observability = None
    if move in {
        "propose_blocker_updates",
        "request_human_feedback",
        "mark_blocked",
        "mark_resolved_no_edit",
        "gather_more_evidence",
        "apply_edit_plan",
    }:
        return pre_move_decision
    state.last_reason = resolver_reason
    return None
