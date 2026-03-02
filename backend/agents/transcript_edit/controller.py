from __future__ import annotations

import json
from typing import Any
from pathlib import Path
from collections.abc import Callable

from agent_kernel.models import (
    ActionType,
    KernelBudgets,
    KernelGoal,
    KernelSessionStartRequest,
    StepExecutionState,
)
from agent_kernel.session import KernelSessionManager
from transcript_edit.persistence import TranscriptionEditPersistenceService
from services.dossier.edit_persistence_service import EditPersistenceService

from .contracts import TranscriptEditAgentRunRequest, TranscriptEditAgentRunResult
from .context_spans import (
    fallback_spans_for_findings,
    open_planner_context_spans,
)
from .disagreement_analysis import (
    build_deterministic_consensus_plan,
    candidate_disagreement_hints,
    critical_disagreement_findings,
    deterministic_numeric_replace_op,
    dominant_bucket_value,
    extract_numeric_literals,
    first_expected_token_from_message,
    first_numeric_like,
    has_blocking_warnings,
    image_checks_from_disagreement_hints,
    image_numeric_signals,
    is_critical_tie_distance,
    mapping_priority_focus,
    merge_findings_summary_with_disagreement,
    prioritized_findings_for_planning,
    resolved_disagreement_hints,
)
from .hitl_feedback import (
    build_human_feedback_prompt,
    build_range_feedback_plan,
    range_number_from_feedback,
    viewer_run_id_from_request_prefix,
    wait_for_feedback_response,
)
from .image_verification import (
    final_image_sanity_pass_before_promote,
    verify_mapping_critical_with_image,
)
from .loop_runtime import (
    emit_progress,
    normalized_mode,
    read_int,
    read_step_outputs_inline,
    read_str,
    read_str_from_latest_refs,
    step_kernel_action,
)
from .plan_interpretation import (
    build_apply_inputs_for_plan,
    coerce_findings,
    finding_signature,
    finding_to_display_dict,
    max_change_class_from_plan,
    plan_has_no_ops,
    plan_has_review_required,
    plan_op_to_display_dict,
    top_findings_summary_text,
)
from .planner import TranscriptEditPlanPlanner

_MODE_OFF = "off"
_MODE_AUDIT_ONLY = "audit_only"
_MODE_AUDIT_REPAIR = "audit_then_repair"
_MODE_AUDIT_REPAIR_PROMOTE = "audit_then_repair_then_promote"
_EDIT_LOOP_LLM_MODEL = "gpt-5.2"


def run_transcript_edit_controller_loop(
    *,
    session_manager: KernelSessionManager,
    request: TranscriptEditAgentRunRequest,
    request_id_prefix: str,
    planner: TranscriptEditPlanPlanner | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
) -> TranscriptEditAgentRunResult:
    if not request.source_transcript_ref and not request.source_text:
        raise ValueError("source_transcript_ref_or_source_text_required")
    mode = _normalized_mode(request.mode)
    if mode == _MODE_OFF:
        return TranscriptEditAgentRunResult(
            run_artifact_ref=None,
            session_id="",
            iterations=0,
            status="completed",
            reason_code="tx_agent_mode_off",
            latest_refs={},
            review_required=False,
        )
    start = session_manager.start_session(
        KernelSessionStartRequest(
            request_id=f"{request_id_prefix}-kernel",
            goal=KernelGoal(
                requires_global_placement=False,
                render_required=False,
                objective="transcript_edit_agent",
            ),
            budgets=KernelBudgets(
                max_steps=max(8, request.max_iterations * 4),
                max_wall_time_seconds=600,
                max_retrieval_calls=100,
                max_semantic_calls=100,
                max_patch_calls=100,
            ),
            dossier_id=request.dossier_id,
            source_entry_ref=(f"final:{request.dossier_id}" if request.dossier_id else None),
            initial_graph_json={
                "graph_id": f"tx_agent_{request_id_prefix}",
                "nodes": [],
                "edges": [],
                "metadata": {
                    "source": "transcript_edit_agent",
                    "dossier_id": request.dossier_id,
                },
            },
        )
    )
    if start.refusal is not None or start.session_id is None:
        raise RuntimeError(f"kernel_start_refused:{start.refusal.reason_code if start.refusal else 'missing_session'}")

    session_id = start.session_id
    latest_refs = start.dashboard.latest_refs.model_dump(mode="json") if start.dashboard else {}
    current_transcript_ref = request.source_transcript_ref
    planner_client = planner or TranscriptEditPlanPlanner()
    tx_persistence = TranscriptionEditPersistenceService()
    iterations = 0
    invalid_plan_strikes = 0
    no_progress_streak = 0
    previous_finding_signature: str | None = None
    applied_non_normalization = False
    applied_requires_review = False
    span_seeds_ref: str | None = None
    sticky_range_selection: int | None = None
    last_reason = "tx_agent_not_started"
    applied_any_edits = False
    disagreement_hints = _candidate_disagreement_hints(request.candidate_texts)
    candidate_count = len(request.candidate_texts) if request.candidate_texts else 0
    has_disagreements = bool(
        disagreement_hints.get("range_values")
        or disagreement_hints.get("distance_values")
        or disagreement_hints.get("bearing_values")
        or disagreement_hints.get("acreage_values")
    )
    min_iterations_before_complete = max(
        1,
        min(int(request.max_iterations), int(request.min_iterations_before_complete)),
    )
    used_human_feedback = False
    _emit_progress(
        progress_cb,
        {
            "iteration": 0,
            "phase": "starting",
            "message": (
                f"Starting transcript edit loop ({mode.replace('_', ' ')}). "
                f"{'Analyzing ' + str(candidate_count) + ' draft(s) for consistency. ' if candidate_count > 1 else ''}"
                f"{'Disagreements detected between drafts — will investigate.' if has_disagreements else 'Auditing transcript for errors and mapping-critical issues.'}"
            ),
            "latest_refs": latest_refs,
            "execution_state": "starting",
        },
    )

    for iterations in range(1, request.max_iterations + 1):
        audit_inputs: dict[str, Any] = {"dossier_id": request.dossier_id}
        if current_transcript_ref:
            audit_inputs["source_transcript_ref"] = current_transcript_ref
        elif request.source_text:
            audit_inputs["source_text"] = request.source_text
        audit = _step(
            session_manager=session_manager,
            session_id=session_id,
            prefix="tx_audit",
            iteration=iterations,
            action_type=ActionType.TX_AUDIT_TRANSCRIPT,
            inputs=audit_inputs,
        )
        latest_refs = audit.dashboard.latest_refs.model_dump(mode="json")
        _emit_progress(
            progress_cb,
            {
                "iteration": iterations,
                "phase": "audit",
                "message": f"Auditing transcript for deterministic errors and mapping-critical issues (iteration {iterations}).",
                "latest_refs": latest_refs,
                "execution_state": str(audit.execution_state.value),
            },
        )
        if audit.execution_state != StepExecutionState.EXECUTED:
            reason = audit.refusal.reason_code if audit.refusal is not None else "tx_audit_refused"
            return _result(
                start=start,
                session_id=session_id,
                iterations=iterations,
                status="failed",
                reason=reason,
                latest_refs=latest_refs,
                review_required=True,
            )
        inline = _read_step_outputs_inline(audit.step_record)
        source_ref_candidate = _read_str(inline.get("tx_source_transcript_ref"))
        if source_ref_candidate:
            current_transcript_ref = source_ref_candidate
        finding_count = _read_int(inline.get("tx_findings_count"), 0)
        error_count = _read_int(inline.get("tx_error_findings_count"), 0)
        findings_summary = inline.get("tx_validator_summary") if isinstance(inline.get("tx_validator_summary"), dict) else {}
        top_findings = inline.get("tx_top_findings") if isinstance(inline.get("tx_top_findings"), list) else []
        source_transcript_hash = _read_str(inline.get("tx_source_transcript_hash")) or ""
        if not source_transcript_hash:
            source_transcript_hash = _read_str_from_latest_refs(latest_refs, "tx_source_transcript_ref") or ""
        effective_disagreement_hints = _resolved_disagreement_hints(
            disagreement_hints=disagreement_hints,
            sticky_range_selection=sticky_range_selection,
        )
        mapping_focus = _mapping_priority_focus(disagreement_hints=effective_disagreement_hints)
        disagreement_findings = _critical_disagreement_findings(effective_disagreement_hints)
        # Include disagreement findings on first iteration (to gate obvious cross-draft conflicts),
        # and on later iterations only when the validator still finds issues. This prevents
        # stale disagreement hints from re-triggering HITL after a clean re-audit.
        include_disagreement_findings = bool(disagreement_findings and (finding_count > 0 or iterations == 1 or sticky_range_selection is None))
        if include_disagreement_findings:
            top_findings = [*top_findings, *disagreement_findings]
            findings_summary = _merge_findings_summary_with_disagreement(
                findings_summary=findings_summary,
                disagreement_findings=disagreement_findings,
            )
        planning_findings = _prioritized_findings_for_planning(top_findings=top_findings)
        blocking_warning_present = _has_blocking_warnings(top_findings)
        warning_count = _read_int(findings_summary.get("warnings") if isinstance(findings_summary, dict) else None, 0)
        _emit_progress(
            progress_cb,
            {
                "iteration": iterations,
                "phase": "audit_result",
                "message": (
                    f"Found {finding_count} issues ({error_count} errors, {warning_count} warnings)."
                    if finding_count > 0
                    else "Transcript is clean — no issues found."
                ),
                "latest_refs": latest_refs,
                "execution_state": str(audit.execution_state.value),
                "detail": {
                    "finding_count": finding_count,
                    "error_count": error_count,
                    "warning_count": warning_count,
                    "top_findings": [_finding_to_display_dict(f) for f in top_findings[:6]],
                    "summary_text": _top_findings_summary_text(top_findings),
                },
            },
        )

        finding_signature = _finding_signature(summary=findings_summary, findings=top_findings)
        if previous_finding_signature is not None and finding_signature == previous_finding_signature:
            no_progress_streak += 1
        else:
            no_progress_streak = 0
        previous_finding_signature = finding_signature

        if error_count <= 0 and not blocking_warning_present:
            must_verify_before_terminal = bool(applied_any_edits or has_disagreements or used_human_feedback)
            final_verify_ran = False
            if must_verify_before_terminal and current_transcript_ref:
                final_verify_ran = True
                final_verify = _final_image_sanity_pass_before_promote(
                    session_manager=session_manager,
                    session_id=session_id,
                    iteration=iterations,
                    dossier_id=request.dossier_id,
                    source_transcript_ref=current_transcript_ref,
                    source_image_refs=request.source_image_refs,
                    disagreement_hints=effective_disagreement_hints,
                    model=_edit_loop_model(request.model),
                )
                latest_refs = final_verify.get("latest_refs", latest_refs)
                if not bool(final_verify.get("passed")):
                    reason = _read_str(final_verify.get("reason")) or "tx_agent_final_image_verify_failed"
                    if iterations < request.max_iterations:
                        _emit_progress(
                            progress_cb,
                            {
                                "iteration": iterations,
                                "phase": "final_verify_retry",
                                "message": "Final image verification found unresolved map-critical uncertainty; re-checking before terminal decision.",
                                "latest_refs": latest_refs,
                                "execution_state": "retrying",
                            },
                        )
                        continue
                    return _result(
                        start=start,
                        session_id=session_id,
                        iterations=iterations,
                        status="needs_review",
                        reason=reason,
                        latest_refs=latest_refs,
                        review_required=True,
                    )
            if (
                iterations < min_iterations_before_complete
                and (applied_any_edits or has_disagreements or used_human_feedback)
            ):
                _emit_progress(
                    progress_cb,
                    {
                        "iteration": iterations,
                        "phase": "stabilize",
                        "message": f"Clean audit achieved; running additional stabilization pass ({iterations}/{min_iterations_before_complete}) before terminalizing.",
                        "latest_refs": latest_refs,
                        "execution_state": "running",
                    },
                )
                continue
            if (
                request.dossier_id
                and current_transcript_ref
                and source_transcript_hash
                and error_count <= 0
            ):
                seeds_step = _step(
                    session_manager=session_manager,
                    session_id=session_id,
                    prefix="tx_span_seeds",
                    iteration=iterations,
                    action_type=ActionType.TX_SAVE_TRANSCRIPT_SPAN_SEEDS,
                    inputs={
                        "dossier_id": request.dossier_id,
                        "source_transcript_ref": current_transcript_ref,
                        "source_transcript_hash": source_transcript_hash,
                        "max_seeds": 24,
                    },
                )
                latest_refs = seeds_step.dashboard.latest_refs.model_dump(mode="json")
                seeds_inline = _read_step_outputs_inline(seeds_step.step_record)
                span_seeds_ref_candidate = _read_str(seeds_inline.get("tx_span_seeds_ref"))
                if span_seeds_ref_candidate:
                    span_seeds_ref = span_seeds_ref_candidate
            should_promote = (
                mode == _MODE_AUDIT_REPAIR_PROMOTE
                and request.auto_promote
                and not applied_non_normalization
                and not applied_requires_review
                and error_count <= 0
            )
            if should_promote and current_transcript_ref:
                _emit_progress(
                    progress_cb,
                    {
                        "iteration": iterations,
                        "phase": "promote",
                        "message": "Next, I will run a final image sanity check before promotion.",
                        "latest_refs": latest_refs,
                        "execution_state": "running",
                    },
                )
                if not final_verify_ran:
                    final_verify = _final_image_sanity_pass_before_promote(
                        session_manager=session_manager,
                        session_id=session_id,
                        iteration=iterations,
                        dossier_id=request.dossier_id,
                        source_transcript_ref=current_transcript_ref,
                        source_image_refs=request.source_image_refs,
                        disagreement_hints=effective_disagreement_hints,
                        model=_edit_loop_model(request.model),
                    )
                    latest_refs = final_verify.get("latest_refs", latest_refs)
                    if not bool(final_verify.get("passed")):
                        reason = _read_str(final_verify.get("reason")) or "tx_agent_final_image_verify_failed"
                        return _result(
                            start=start,
                            session_id=session_id,
                            iterations=iterations,
                            status="needs_review",
                            reason=reason,
                            latest_refs=latest_refs,
                            review_required=True,
                        )
                promote = _step(
                    session_manager=session_manager,
                    session_id=session_id,
                    prefix="tx_promote",
                    iteration=iterations,
                    action_type=ActionType.TX_PROMOTE_TRANSCRIPT_FOR_MAPPING,
                    inputs={
                        "dossier_id": request.dossier_id,
                        "transcript_ref": current_transcript_ref,
                        "run_id": request_id_prefix,
                        "tx_span_seeds_ref": span_seeds_ref,
                    },
                )
                latest_refs = promote.dashboard.latest_refs.model_dump(mode="json")
                if span_seeds_ref:
                    latest_refs["tx_span_seeds_ref"] = {"artifact_path": span_seeds_ref}
                if promote.execution_state != StepExecutionState.EXECUTED:
                    reason = promote.refusal.reason_code if promote.refusal is not None else "tx_promote_refused"
                    return _result(
                        start=start,
                        session_id=session_id,
                        iterations=iterations,
                        status="failed",
                        reason=reason,
                        latest_refs=latest_refs,
                        review_required=True,
                    )
                if applied_any_edits:
                    _persist_agent_edit_draft(
                        dossier_id=request.dossier_id,
                        transcription_id=request.transcription_id,
                        source_transcript_ref=current_transcript_ref,
                        run_id=request_id_prefix,
                        reason_code="tx_agent_clean_promoted",
                    )
                return _result(
                    start=start,
                    session_id=session_id,
                    iterations=iterations,
                    status="completed",
                    reason="tx_agent_clean_promoted",
                    latest_refs=latest_refs,
                    review_required=False,
                )
            if applied_any_edits:
                _persist_agent_edit_draft(
                    dossier_id=request.dossier_id,
                    transcription_id=request.transcription_id,
                    source_transcript_ref=current_transcript_ref,
                    run_id=request_id_prefix,
                    reason_code="tx_agent_clean_no_promote" if error_count <= 0 else "tx_agent_blocked_error_findings",
                )
            return _result(
                start=start,
                session_id=session_id,
                iterations=iterations,
                status="completed" if error_count <= 0 and not applied_requires_review else "needs_review",
                reason="tx_agent_clean_no_promote" if error_count <= 0 else "tx_agent_blocked_error_findings",
                latest_refs=latest_refs,
                review_required=(error_count > 0 or applied_requires_review or applied_non_normalization),
            )

        if mode == _MODE_AUDIT_ONLY:
            return _result(
                start=start,
                session_id=session_id,
                iterations=iterations,
                status="needs_review",
                reason="tx_agent_audit_only_findings_present",
                latest_refs=latest_refs,
                review_required=True,
            )

        manual_plan_override: dict[str, Any] | None = None
        if sticky_range_selection is not None and current_transcript_ref and source_transcript_hash:
            manual_plan_override = _build_range_feedback_plan(
                source_transcript_ref=current_transcript_ref,
                source_transcript_hash=source_transcript_hash,
                selected_number=sticky_range_selection,
            )
            if manual_plan_override is not None:
                _emit_progress(
                    progress_cb,
                    {
                        "event_type": "human_feedback",
                        "iteration": iterations,
                        "phase": "human_feedback_reused",
                        "message": f"Reusing prior human range decision ({sticky_range_selection}) to continue safely.",
                        "execution_state": "received",
                        "latest_refs": latest_refs,
                    },
                )
        viewer_run_id = _viewer_run_id_from_request_prefix(request_id_prefix)
        if (
            manual_plan_override is None
            and blocking_warning_present
            and request.hitl_enabled
            and (viewer_run_id.startswith("tx_agent_") or viewer_run_id.startswith("tx_post_t0_"))
        ):
            feedback_prompt = _build_human_feedback_prompt(
                disagreement_hints=effective_disagreement_hints,
                top_findings=top_findings,
                iteration=iterations,
            )
            if feedback_prompt is not None:
                _emit_progress(
                    progress_cb,
                    {
                        "event_type": "human_feedback_needed",
                        "iteration": iterations,
                        "phase": "human_feedback_needed",
                        "message": feedback_prompt.get("line1"),
                        "execution_state": "waiting",
                        "latest_refs": latest_refs,
                        "prompt_id": feedback_prompt.get("prompt_id"),
                        "blocking": True,
                        "choices": feedback_prompt.get("choices", []),
                        "default_choice": feedback_prompt.get("default_choice"),
                        "context": feedback_prompt.get("context", {}),
                    },
                )
                feedback_entry = _wait_for_feedback_response(
                    run_id=viewer_run_id,
                    prompt_id=str(feedback_prompt.get("prompt_id")),
                    timeout_seconds=request.hitl_wait_timeout_seconds,
                    poll_interval_seconds=request.hitl_poll_interval_seconds,
                )
                if feedback_entry is None:
                    return _result(
                        start=start,
                        session_id=session_id,
                        iterations=iterations,
                        status="needs_review",
                        reason="human_feedback_timeout",
                        latest_refs=latest_refs,
                        review_required=True,
                    )
                _emit_progress(
                    progress_cb,
                    {
                        "event_type": "human_feedback",
                        "iteration": iterations,
                        "phase": "human_feedback_received",
                        "message": "Human feedback received for blocking ambiguity.",
                        "execution_state": "received",
                        "latest_refs": latest_refs,
                        "prompt_id": feedback_prompt.get("prompt_id"),
                        "feedback": feedback_entry,
                    },
                )
                selected_number = _range_number_from_feedback(feedback_entry)
                used_human_feedback = True
                if selected_number is not None and current_transcript_ref and source_transcript_hash:
                    sticky_range_selection = selected_number
                    manual_plan_override = _build_range_feedback_plan(
                        source_transcript_ref=current_transcript_ref,
                        source_transcript_hash=source_transcript_hash,
                        selected_number=selected_number,
                    )

        if no_progress_streak >= request.max_no_progress_iterations:
            return _result(
                start=start,
                session_id=session_id,
                iterations=iterations,
                status="needs_review",
                reason="tx_agent_no_progress",
                latest_refs=latest_refs,
                review_required=True,
            )

        if not current_transcript_ref:
            return _result(
                start=start,
                session_id=session_id,
                iterations=iterations,
                status="needs_review",
                reason="tx_agent_missing_source_ref_for_planning",
                latest_refs=latest_refs,
                review_required=True,
            )

        span_context: list[dict[str, Any]] = []
        image_verification: dict[str, Any] = {}
        if manual_plan_override is None:
            _emit_progress(
                progress_cb,
                {
                    "iteration": iterations,
                    "phase": "open_spans",
                    "message": "Opening localized transcript spans around flagged areas for detailed inspection.",
                    "latest_refs": latest_refs,
                    "execution_state": "running",
                },
            )
            span_context = _open_planner_context_spans(
                session_manager=session_manager,
                session_id=session_id,
                iteration=iterations,
                dossier_id=request.dossier_id,
                source_transcript_ref=current_transcript_ref,
                top_findings=planning_findings,
            )
            _emit_progress(
                progress_cb,
                {
                    "iteration": iterations,
                    "phase": "open_spans_result",
                    "message": f"Opened {len(span_context)} text spans for context.",
                    "latest_refs": latest_refs,
                    "detail": {
                        "span_count": len(span_context),
                        "spans": [_span_to_display_dict(s) for s in span_context[:6]],
                    },
                },
            )
            _emit_progress(
                progress_cb,
                {
                    "iteration": iterations,
                    "phase": "image_verify",
                    "message": "Cross-referencing mapping-critical values (PLSS tokens, distances, bearings) against the source deed image.",
                    "latest_refs": latest_refs,
                    "execution_state": "running",
                },
            )
            image_verification = _verify_mapping_critical_with_image(
                session_manager=session_manager,
                session_id=session_id,
                iteration=iterations,
                dossier_id=request.dossier_id,
                source_transcript_ref=current_transcript_ref,
                top_findings=planning_findings,
                disagreement_hints=effective_disagreement_hints,
                source_image_refs=request.source_image_refs,
                model=_edit_loop_model(request.model),
            )
            if image_verification:
                latest_refs = image_verification.get("latest_refs", latest_refs)
                iv_payload = image_verification.get("payload") or {}
                iv_results = iv_payload.get("results") if isinstance(iv_payload, dict) else []
                iv_results = iv_results if isinstance(iv_results, list) else []
                iv_confirmed = sum(1 for r in iv_results if isinstance(r, dict) and str(r.get("status") or "").lower() in {"confirmed", "match"})
                iv_rejected = sum(1 for r in iv_results if isinstance(r, dict) and str(r.get("status") or "").lower() in {"rejected", "mismatch"})
                iv_total = len(iv_results)
                _emit_progress(
                    progress_cb,
                    {
                        "iteration": iterations,
                        "phase": "image_verify_result",
                        "message": f"Image check: {iv_confirmed} confirmed, {iv_rejected} rejected out of {iv_total} checks.",
                        "latest_refs": latest_refs,
                        "image_verification": iv_payload,
                        "detail": {
                            "confirmed": iv_confirmed,
                            "rejected": iv_rejected,
                            "total": iv_total,
                            "results": [
                                {
                                    "check_id": r.get("check_id"),
                                    "status": r.get("status"),
                                    "observed_text": str(r.get("observed_text") or "")[:120],
                                }
                                for r in iv_results[:8]
                                if isinstance(r, dict)
                            ],
                        },
                    },
                )
        else:
            _emit_progress(
                progress_cb,
                {
                    "iteration": iterations,
                    "phase": "image_verify",
                    "message": "Running post-feedback image verification before applying the override plan.",
                    "latest_refs": latest_refs,
                    "execution_state": "running",
                },
            )
            image_verification = _verify_mapping_critical_with_image(
                session_manager=session_manager,
                session_id=session_id,
                iteration=iterations,
                dossier_id=request.dossier_id,
                source_transcript_ref=current_transcript_ref,
                top_findings=planning_findings,
                disagreement_hints=effective_disagreement_hints,
                source_image_refs=request.source_image_refs,
                model=_edit_loop_model(request.model),
            )
            if image_verification:
                latest_refs = image_verification.get("latest_refs", latest_refs)
        manual_plan = manual_plan_override or (request.edit_plan if isinstance(request.edit_plan, dict) else None)
        consensus_plan_payload = None
        if manual_plan is None:
            consensus_plan_payload = _build_deterministic_consensus_plan(
                source_transcript_ref=current_transcript_ref,
                source_transcript_hash=source_transcript_hash,
                disagreement_hints=effective_disagreement_hints,
                image_verification=image_verification.get("payload") if isinstance(image_verification, dict) else {},
                top_findings=planning_findings,
            )
        if manual_plan is not None:
            plan_payload = manual_plan
            plan_reason = "manual_plan"
            raw_plan_text = json.dumps(manual_plan, ensure_ascii=False)
        elif consensus_plan_payload is not None:
            plan_payload = consensus_plan_payload
            plan_reason = "deterministic_consensus_plan"
            raw_plan_text = json.dumps(consensus_plan_payload, ensure_ascii=False)
        else:
            _emit_progress(
                progress_cb,
                {
                    "iteration": iterations,
                    "phase": "plan",
                    "message": "Building a drift-safe edit plan from verified findings and image evidence.",
                    "latest_refs": latest_refs,
                    "execution_state": "running",
                },
            )
            try:
                plan, plan_reason, raw_plan_text = planner_client.propose_plan(
                    model=_edit_loop_model(request.model),
                    source_transcript_ref=current_transcript_ref,
                    source_transcript_hash=source_transcript_hash,
                    findings_summary=findings_summary,
                    top_findings=_coerce_findings(planning_findings),
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
            plan_payload = plan.model_dump(mode="json") if plan is not None else None
            if plan_payload is None:
                invalid_plan_strikes += 1
                if invalid_plan_strikes >= request.max_invalid_plan_attempts:
                    return _result(
                        start=start,
                        session_id=session_id,
                        iterations=iterations,
                        status="needs_review",
                        reason=f"tx_agent_plan_invalid:{plan_reason}",
                        latest_refs=latest_refs,
                        review_required=True,
                    )
                continue
            if _plan_has_no_ops(plan_payload):
                reason = "tx_agent_no_safe_plan_for_findings"
                if manual_plan is None:
                    reason = f"{reason}:{plan_reason}"
                return _result(
                    start=start,
                    session_id=session_id,
                    iterations=iterations,
                    status="needs_review",
                    reason=reason,
                    latest_refs=latest_refs,
                    review_required=True,
                )
        plan_ops = plan_payload.get("ops") if isinstance(plan_payload, dict) else []
        plan_ops = plan_ops if isinstance(plan_ops, list) else []
        _emit_progress(
            progress_cb,
            {
                "iteration": iterations,
                "phase": "plan_result",
                "message": f"Edit plan ready ({plan_reason}): {len(plan_ops)} operations proposed.",
                "latest_refs": latest_refs,
                "execution_state": "running",
                "detail": {
                    "plan_reason": plan_reason,
                    "op_count": len(plan_ops),
                    "ops_preview": [_plan_op_to_display_dict(op) for op in plan_ops[:6] if isinstance(op, dict)],
                },
            },
        )
        apply = _step(
            session_manager=session_manager,
            session_id=session_id,
            prefix="tx_apply",
            iteration=iterations,
            action_type=ActionType.TX_APPLY_EDIT_PLAN,
            inputs=_build_apply_inputs_for_plan(
                persistence=tx_persistence,
                dossier_id=request.dossier_id,
                plan_payload=plan_payload,
            ),
        )
        latest_refs = apply.dashboard.latest_refs.model_dump(mode="json")
        _emit_progress(
            progress_cb,
            {
                "iteration": iterations,
                "phase": "apply_result",
                "message": f"Applied {len(plan_ops)} edits. Re-auditing transcript.",
                "latest_refs": latest_refs,
                "execution_state": str(apply.execution_state.value),
                "detail": {
                    "plan_op_count": len(plan_ops),
                    "ops": [_plan_op_to_display_dict(op) for op in plan_ops[:6] if isinstance(op, dict)],
                },
            },
        )
        if apply.execution_state != StepExecutionState.EXECUTED:
            reason = apply.refusal.reason_code if apply.refusal is not None else "tx_apply_refused"
            return _result(
                start=start,
                session_id=session_id,
                iterations=iterations,
                status="needs_review",
                reason=reason,
                latest_refs=latest_refs,
                review_required=True,
            )
        apply_inline = _read_step_outputs_inline(apply.step_record)
        edited_ref = _read_str(apply_inline.get("tx_edited_transcript_ref"))
        if edited_ref:
            current_transcript_ref = edited_ref
        plan_cc = _max_change_class_from_plan(plan_payload or {})
        if plan_cc in {"semantic", "structural"}:
            applied_non_normalization = True
        if _plan_has_review_required(plan_payload or {}):
            applied_requires_review = True
        if len(plan_ops) > 0:
            applied_any_edits = True
        if manual_plan is None:
            invalid_plan_strikes = 0
        last_reason = plan_reason if plan_reason else "tx_apply_completed"
        if raw_plan_text:
            _ = raw_plan_text  # retain variable for debugging parity without expanding artifacts

    if applied_any_edits:
        _persist_agent_edit_draft(
            dossier_id=request.dossier_id,
            transcription_id=request.transcription_id,
            source_transcript_ref=current_transcript_ref,
            run_id=request_id_prefix,
            reason_code=last_reason if last_reason != "tx_agent_not_started" else "tx_agent_max_iterations_reached",
        )
    return _result(
        start=start,
        session_id=session_id,
        iterations=iterations,
        status="needs_review",
        reason=last_reason if last_reason != "tx_agent_not_started" else "tx_agent_max_iterations_reached",
        latest_refs=latest_refs,
        review_required=True,
    )


def _emit_progress(progress_cb: Callable[[dict[str, Any]], None] | None, payload: dict[str, Any]) -> None:
    emit_progress(progress_cb, payload)


def _step(
    *,
    session_manager: KernelSessionManager,
    session_id: str,
    prefix: str,
    iteration: int,
    action_type: ActionType,
    inputs: dict[str, Any],
):
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
    return open_planner_context_spans(
        session_manager=session_manager,
        session_id=session_id,
        iteration=iteration,
        dossier_id=dossier_id,
        source_transcript_ref=source_transcript_ref,
        top_findings=top_findings,
        step_fn=_step,
        read_step_outputs_inline_fn=_read_step_outputs_inline,
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
) -> dict[str, Any]:
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
        step_fn=_step,
        read_step_outputs_inline_fn=_read_step_outputs_inline,
        read_str_fn=_read_str,
    )


def _final_image_sanity_pass_before_promote(
    *,
    session_manager: KernelSessionManager,
    session_id: str,
    iteration: int,
    dossier_id: str | None,
    source_transcript_ref: str,
    source_image_refs: list[str],
    disagreement_hints: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    return final_image_sanity_pass_before_promote(
        session_manager=session_manager,
        session_id=session_id,
        iteration=iteration,
        dossier_id=dossier_id,
        source_transcript_ref=source_transcript_ref,
        source_image_refs=source_image_refs,
        disagreement_hints=disagreement_hints,
        model=model,
        step_fn=_step,
        read_step_outputs_inline_fn=_read_step_outputs_inline,
        read_str_fn=_read_str,
        read_int_fn=_read_int,
    )


def _result(
    *,
    start,
    session_id: str,
    iterations: int,
    status: str,
    reason: str,
    latest_refs: dict[str, Any],
    review_required: bool,
) -> TranscriptEditAgentRunResult:
    return TranscriptEditAgentRunResult(
        run_artifact_ref=start.run_artifact_ref,
        session_id=session_id,
        iterations=iterations,
        status=status,
        reason_code=reason,
        latest_refs=latest_refs,
        review_required=review_required,
    )


def _normalized_mode(raw: str | None) -> str:
    return normalized_mode(
        raw,
        {_MODE_OFF, _MODE_AUDIT_ONLY, _MODE_AUDIT_REPAIR, _MODE_AUDIT_REPAIR_PROMOTE},
        _MODE_AUDIT_REPAIR_PROMOTE,
    )


def _read_step_outputs_inline(step_record: dict[str, Any] | None) -> dict[str, Any]:
    return read_step_outputs_inline(step_record)


def _read_str(value: object) -> str | None:
    return read_str(value)


def _read_int(value: object, default: int) -> int:
    return read_int(value, default)


def _coerce_findings(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return coerce_findings(values)


def _finding_signature(*, summary: dict[str, Any], findings: list[dict[str, Any]]) -> str:
    return finding_signature(summary=summary, findings=findings)


def _max_change_class_from_plan(plan: dict[str, Any]) -> str:
    return max_change_class_from_plan(plan)


def _plan_has_review_required(plan: dict[str, Any]) -> bool:
    return plan_has_review_required(plan)


def _plan_has_no_ops(plan: dict[str, Any]) -> bool:
    return plan_has_no_ops(plan)


def _build_apply_inputs_for_plan(
    *,
    persistence: TranscriptionEditPersistenceService,
    dossier_id: str | None,
    plan_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    return build_apply_inputs_for_plan(
        persistence=persistence,
        dossier_id=dossier_id,
        plan_payload=plan_payload,
    )


def _read_str_from_latest_refs(latest_refs: dict[str, Any], key: str) -> str | None:
    return read_str_from_latest_refs(latest_refs, key)


def _has_blocking_warnings(top_findings: list[dict[str, Any]]) -> bool:
    return has_blocking_warnings(top_findings)


def _fallback_spans_for_findings(
    *,
    source_transcript_ref: str,
    top_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return fallback_spans_for_findings(
        source_transcript_ref=source_transcript_ref,
        top_findings=top_findings,
    )


def _candidate_disagreement_hints(candidate_texts: list[str]) -> dict[str, Any]:
    return candidate_disagreement_hints(candidate_texts)


def _resolved_disagreement_hints(
    *,
    disagreement_hints: dict[str, Any],
    sticky_range_selection: int | None,
) -> dict[str, Any]:
    return resolved_disagreement_hints(
        disagreement_hints=disagreement_hints,
        sticky_range_selection=sticky_range_selection,
    )


def _extract_numeric_literals(message: str) -> list[str]:
    return extract_numeric_literals(message)


def _image_checks_from_disagreement_hints(disagreement_hints: dict[str, Any]) -> list[dict[str, Any]]:
    return image_checks_from_disagreement_hints(disagreement_hints)


def _image_numeric_signals(image_verification: dict[str, Any]) -> dict[str, str | None]:
    return image_numeric_signals(image_verification)


def _first_numeric_like(
    values: list[str],
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> str | None:
    return first_numeric_like(values, minimum=minimum, maximum=maximum)


def _first_expected_token_from_message(message: str) -> str | None:
    return first_expected_token_from_message(message)


def _edit_loop_model(preferred: str | None) -> str:
    del preferred
    return _EDIT_LOOP_LLM_MODEL


def _prioritized_findings_for_planning(*, top_findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return prioritized_findings_for_planning(top_findings=top_findings)


def _viewer_run_id_from_request_prefix(request_id_prefix: str) -> str:
    return viewer_run_id_from_request_prefix(request_id_prefix)


def _build_human_feedback_prompt(
    *,
    disagreement_hints: dict[str, Any],
    top_findings: list[dict[str, Any]],
    iteration: int,
) -> dict[str, Any] | None:
    return build_human_feedback_prompt(
        disagreement_hints=disagreement_hints,
        top_findings=top_findings,
        iteration=iteration,
    )


def _wait_for_feedback_response(
    *,
    run_id: str,
    prompt_id: str,
    timeout_seconds: int,
    poll_interval_seconds: int,
) -> dict[str, Any] | None:
    return wait_for_feedback_response(
        run_id=run_id,
        prompt_id=prompt_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )


def _range_number_from_feedback(feedback_entry: dict[str, Any]) -> int | None:
    return range_number_from_feedback(feedback_entry)


def _build_range_feedback_plan(
    *,
    source_transcript_ref: str,
    source_transcript_hash: str,
    selected_number: int,
) -> dict[str, Any] | None:
    return build_range_feedback_plan(
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
        selected_number=selected_number,
    )


def _mapping_priority_focus(disagreement_hints: dict[str, Any]) -> dict[str, Any]:
    return mapping_priority_focus(disagreement_hints)


def _critical_disagreement_findings(disagreement_hints: dict[str, Any]) -> list[dict[str, Any]]:
    return critical_disagreement_findings(disagreement_hints)


def _build_deterministic_consensus_plan(
    *,
    source_transcript_ref: str,
    source_transcript_hash: str,
    disagreement_hints: dict[str, Any],
    image_verification: dict[str, Any],
    top_findings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    return build_deterministic_consensus_plan(
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
        disagreement_hints=disagreement_hints,
        image_verification=image_verification,
        top_findings=top_findings,
    )


def _deterministic_numeric_replace_op(
    *,
    text: str,
    bucket: Any,
    value_regex: str,
    value_guard,
    op_id: str,
    reason: str,
    preferred_value: str | None = None,
    preferred_strength: str | None = None,
) -> dict[str, Any] | None:
    return deterministic_numeric_replace_op(
        text=text,
        bucket=bucket,
        value_regex=value_regex,
        value_guard=value_guard,
        op_id=op_id,
        reason=reason,
        preferred_value=preferred_value,
        preferred_strength=preferred_strength,
    )


def _dominant_bucket_value(bucket: Any) -> tuple[str, int, int] | None:
    return dominant_bucket_value(bucket)


def _merge_findings_summary_with_disagreement(
    *,
    findings_summary: dict[str, Any],
    disagreement_findings: list[dict[str, Any]],
) -> dict[str, Any]:
    return merge_findings_summary_with_disagreement(
        findings_summary=findings_summary,
        disagreement_findings=disagreement_findings,
    )


def _is_critical_tie_distance(value: Any) -> bool:
    return is_critical_tie_distance(value)


# ---------------------------------------------------------------------------
# Display helpers for rich progress emissions
# ---------------------------------------------------------------------------

def _top_findings_summary_text(findings: list[dict[str, Any]]) -> str:
    return top_findings_summary_text(findings)


def _finding_to_display_dict(finding: dict[str, Any]) -> dict[str, Any]:
    return finding_to_display_dict(finding)


def _span_to_display_dict(span: dict[str, Any]) -> dict[str, Any]:
    """span_id + text excerpt (120 chars)."""
    text = str(span.get("text") or span.get("content") or "").strip()
    return {
        "span_id": span.get("span_id"),
        "text": text[:120] + ("..." if len(text) > 120 else ""),
    }


def _persist_agent_edit_draft(
    *,
    dossier_id: str | None,
    transcription_id: str | None,
    source_transcript_ref: str | None,
    run_id: str | None,
    reason_code: str | None,
) -> None:
    if not dossier_id or not transcription_id or not source_transcript_ref:
        return
    try:
        raw = json.loads(Path(source_transcript_ref).read_text(encoding="utf-8"))
    except Exception:
        return
    sections = raw.get("sections") if isinstance(raw, dict) else None
    if not isinstance(sections, list):
        text_value = ""
        if isinstance(raw, dict):
            text_value = str(raw.get("text") or raw.get("extracted_text") or "")
        elif isinstance(raw, str):
            text_value = raw
        sections = [{"id": 1, "body": text_value}]
    try:
        EditPersistenceService().save_agent_edit_draft(
            dossier_id=str(dossier_id),
            transcription_id=str(transcription_id),
            sections=sections,
            source_ref=source_transcript_ref,
            run_id=run_id,
            reason_code=reason_code,
        )
    except Exception:
        return


def _plan_op_to_display_dict(op: dict[str, Any]) -> dict[str, Any]:
    return plan_op_to_display_dict(op)
