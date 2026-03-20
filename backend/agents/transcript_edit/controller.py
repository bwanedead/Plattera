from __future__ import annotations

import json
import logging
import time
from typing import Any
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

from .contracts import TranscriptEditAgentRunRequest, TranscriptEditAgentRunResult
from .context_spans import (
    fallback_spans_for_findings,
    open_planner_context_spans,
)
from .disagreement_analysis import has_blocking_warnings, prioritized_findings_for_planning
from .decision_ledger import (
    has_unresolved_target_scope_mapping_blocking_closure,
    initialize_decision_ledger,
    ledger_snapshot_for_payload,
    list_external_context_injections,
    unresolved_closure_requirements,
    update_ledger_from_orient_baseline,
    update_ledger_from_iteration,
)
from .decision_ledger_adapter import transcript_edit_unified_and_closure_read_from_loop_state
from .transcript_edit_ledger_discovery_prep import (
    append_discovery_merge_continuity,
    merge_discovery_from_audit_findings,
)
from .blocker_registry import (
    blocker_health_snapshot,
    initialize_blocker_registry,
    set_convention_context,
    registry_snapshot_for_payload,
    select_primary_blocker,
    sync_registry_from_ledger,
)
from .convention_situating import situate_document_convention
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
from .draft_persistence import persist_agent_edit_draft
from .iteration_pipeline import handle_clean_iteration, handle_repair_iteration
from .loop_state import TranscriptEditLoopState
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
    finding_signature,
    finding_to_display_dict,
    top_findings_summary_text,
)
from .progress_evaluation import (
    blocking_signature,
    blocking_unresolved_count,
    classify_iteration_progress,
)
from .result_policy import (
    max_iterations_decision,
)
from .runtime_summary import derive_mission_runtime_summary
from .state_projection import (
    derive_waiting_feedback_projection,
    sync_pending_feedback_cache_from_registry,
)
from .run_feed_persistence import (
    TranscriptEditRunFeedPersistenceService,
    write_transcript_edit_run_snapshot,
)
from .terminalization import build_run_result, terminal_message, terminal_summary
from .run_reporting import (
    audit_payload,
    audit_result_payload,
    investigation_baseline_result_payload,
    preflight_countdown_payload,
    starting_payload,
    ticker_payload,
)
from .planner import TranscriptEditPlanPlanner

_MODE_OFF = "off"
_MODE_AUDIT_ONLY = "audit_only"
_MODE_AUDIT_REPAIR = "audit_then_repair"
_MODE_AUDIT_REPAIR_PROMOTE = "audit_then_repair_then_promote"
_EDIT_LOOP_LLM_MODEL = "gpt-5.2"
_KERNEL_STEP_INPUT_BUDGET_BYTES = 4096
_MAX_CANDIDATES = 10
_VALIDATION_MODE_OFF = "off"
_VALIDATION_MODE_LIVE_HITL = "live_hitl"
_LOG = logging.getLogger(__name__)
_RUN_FEED_PERSISTENCE = TranscriptEditRunFeedPersistenceService()


def run_transcript_edit_controller_loop(
    *,
    session_manager: KernelSessionManager,
    request: TranscriptEditAgentRunRequest,
    request_id_prefix: str,
    planner: TranscriptEditPlanPlanner | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    startup_countdown_seconds: int = 0,
) -> TranscriptEditAgentRunResult:
    import os as _os
    if not _os.environ.get("PLATTERA_ENABLE_LEGACY_CONTROLLERS"):
        raise RuntimeError(
            "run_transcript_edit_controller_loop is a retired legacy entrypoint. "
            "Use run_orchestration_kernel_transcript_loop instead. "
            "Set PLATTERA_ENABLE_LEGACY_CONTROLLERS=1 to temporarily re-enable for testing."
        )
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
    validation_mode = _normalized_validation_mode(request.validation_mode)
    validation_profile = _validation_runtime_profile(validation_mode)
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
                max_wall_time_seconds=int(validation_profile.get("max_wall_time_seconds") or 600),
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
    planner_client = planner or TranscriptEditPlanPlanner()
    tx_persistence = TranscriptionEditPersistenceService()
    state = TranscriptEditLoopState(
        latest_refs=start.dashboard.latest_refs.model_dump(mode="json") if start.dashboard else {},
        current_transcript_ref=request.source_transcript_ref,
        decision_ledger=initialize_decision_ledger(),
        blocker_registry=(
            dict(request.resume_blocker_registry)
            if isinstance(request.resume_blocker_registry, dict)
            else initialize_blocker_registry(
                run_id=request_id_prefix,
                session_id=session_id,
                source_transcript_ref=request.source_transcript_ref,
            )
        ),
        pending_feedback_prompt_id=None,
        pending_feedback_decision_key=None,
        pending_feedback_prompt=(
            dict(request.resume_pending_feedback_prompt)
            if isinstance(request.resume_pending_feedback_prompt, dict)
            else None
        ),
    )
    resume_fallback_prompt_id = str(request.resume_pending_feedback_prompt_id or "").strip() or None
    resume_fallback_decision_key = str(request.resume_pending_feedback_decision_key or "").strip().lower() or None
    state.pending_feedback_prompt_id = resume_fallback_prompt_id
    state.pending_feedback_decision_key = resume_fallback_decision_key
    sync_pending_feedback_cache_from_registry(state=state)
    authoritative_prompt_id = str(state.pending_feedback_prompt_id or "").strip() or None
    authoritative_decision_key = str(state.pending_feedback_decision_key or "").strip().lower() or None
    if not authoritative_prompt_id:
        state.pending_feedback_prompt = None
    elif (
        (resume_fallback_prompt_id and authoritative_prompt_id != resume_fallback_prompt_id)
        or (
            resume_fallback_decision_key
            and authoritative_decision_key
            and authoritative_decision_key != resume_fallback_decision_key
        )
    ):
        # Resume payload prompt context is compatibility metadata; clear it when
        # registry-authoritative ownership points at a different prompt/decision.
        state.pending_feedback_prompt = None
    state.convention_context = (
        dict((state.blocker_registry or {}).get("convention_context"))
        if isinstance((state.blocker_registry or {}).get("convention_context"), dict)
        else {}
    )
    progress_log: list[dict[str, Any]] = []
    upstream_progress_cb = progress_cb

    def _captured_progress_cb(event: dict[str, Any]) -> None:
        if isinstance(event, dict):
            progress_log.append(dict(event))
        if upstream_progress_cb is not None:
            upstream_progress_cb(event)

    progress_cb = _captured_progress_cb
    candidate_count = (
        len(request.candidate_refs)
        if request.candidate_refs
        else len(request.candidate_texts)
    )
    min_iterations_before_complete = max(
        1,
        min(int(request.max_iterations), int(request.min_iterations_before_complete)),
    )
    loop_model = _edit_loop_model(request.model)
    countdown_seconds = max(0, int(startup_countdown_seconds))
    if countdown_seconds > 0:
        _run_prestart_countdown(
            progress_cb=progress_cb,
            latest_refs=state.latest_refs,
            countdown_seconds=countdown_seconds,
        )
        _emit_progress(
            progress_cb,
            starting_payload(
                mode=mode,
                candidate_count=candidate_count,
                latest_refs=state.latest_refs,
            ),
        )
    if validation_mode != _VALIDATION_MODE_OFF:
        _emit_progress(
            progress_cb,
            ticker_payload(
                iteration=0,
                phase="validation_mode",
                message=f"Validation mode active: {validation_mode}.",
                latest_refs=state.latest_refs,
                detail=dict(validation_profile),
            ),
        )

    # Deterministic canonical audit runs first for source/hash safety and advisory lints.
    pre_audit_inputs: dict[str, Any] = {"dossier_id": request.dossier_id}
    if state.current_transcript_ref:
        pre_audit_inputs["source_transcript_ref"] = state.current_transcript_ref
    elif request.source_text:
        pre_audit_inputs["source_text"] = request.source_text
    pre_audit = _step(
        session_manager=session_manager,
        session_id=session_id,
        prefix="tx_pre_audit",
        iteration=0,
        action_type=ActionType.TX_AUDIT_TRANSCRIPT,
        inputs=pre_audit_inputs,
    )
    state.latest_refs = pre_audit.dashboard.latest_refs.model_dump(mode="json")
    if pre_audit.execution_state != StepExecutionState.EXECUTED:
        reason = pre_audit.refusal.reason_code if pre_audit.refusal is not None else "tx_pre_audit_refused"
        status = "failed"
        if _should_convert_timeout_to_waiting_feedback(reason=reason, state=state):
            status = "needs_review"
        return _finalize_result_and_project_run_feed(
            start=start,
            request=request,
            request_id_prefix=request_id_prefix,
            progress_log=progress_log,
            session_id=session_id,
            iterations=0,
            status=status,
            reason=reason,
            latest_refs=state.latest_refs,
            review_required=True,
            runtime_hitl_state=_runtime_hitl_state(state),
        )
    pre_audit_inline = _read_step_outputs_inline(pre_audit.step_record)
    pre_source_ref = _read_str(pre_audit_inline.get("tx_source_transcript_ref"))
    if pre_source_ref:
        state.current_transcript_ref = pre_source_ref
    pre_source_hash = _read_str(pre_audit_inline.get("tx_source_transcript_hash")) or ""

    orient_inputs = _build_orient_inputs(
        dossier_id=request.dossier_id,
        model=loop_model,
        source_transcript_ref=state.current_transcript_ref,
        source_text=request.source_text,
        candidate_refs=request.candidate_refs,
        candidate_texts=request.candidate_texts,
        max_candidates_for_orient=request.max_candidates_for_orient,
        max_total_hydrated_bytes_for_orient=request.max_total_hydrated_bytes_for_orient,
        max_bytes_per_candidate_for_orient=request.max_bytes_per_candidate_for_orient,
        orient_hydration_selection_strategy=request.orient_hydration_selection_strategy,
    )
    orient = _step(
        session_manager=session_manager,
        session_id=session_id,
        prefix="tx_orient_baseline",
        iteration=0,
        action_type=ActionType.TX_ORIENT_AND_BASELINE,
        inputs=orient_inputs,
    )
    state.latest_refs = orient.dashboard.latest_refs.model_dump(mode="json")
    if orient.execution_state != StepExecutionState.EXECUTED:
        reason = orient.refusal.reason_code if orient.refusal is not None else "tx_orient_baseline_refused"
        return _finalize_result_and_project_run_feed(
            start=start,
            request=request,
            request_id_prefix=request_id_prefix,
            progress_log=progress_log,
            session_id=session_id,
            iterations=0,
            status="needs_review",
            reason=reason,
            latest_refs=state.latest_refs,
            review_required=True,
            runtime_hitl_state=_runtime_hitl_state(state),
        )
    orient_inline = _read_step_outputs_inline(orient.step_record)
    orient_source_ref = _read_str(orient_inline.get("tx_source_transcript_ref"))
    if orient_source_ref:
        state.current_transcript_ref = orient_source_ref
    if _read_str(orient_inline.get("tx_span_seeds_ref")):
        state.span_seeds_ref = _read_str(orient_inline.get("tx_span_seeds_ref"))
    state.decision_ledger = update_ledger_from_orient_baseline(
        ledger=state.decision_ledger,
        orient_items=[
            item
            for item in (
                orient_inline.get("tx_orient_items")
                if isinstance(orient_inline.get("tx_orient_items"), list)
                else []
            )
            if isinstance(item, dict)
        ],
    )
    state.convention_context = situate_document_convention(
        orient_items=[
            item
            for item in (
                orient_inline.get("tx_orient_items")
                if isinstance(orient_inline.get("tx_orient_items"), list)
                else []
            )
            if isinstance(item, dict)
        ],
    )
    state.blocker_registry = set_convention_context(
        registry=state.blocker_registry,
        convention_context=state.convention_context,
    )
    _emit_progress(
        progress_cb,
        ticker_payload(
            iteration=0,
            phase="convention_situating",
            message=(
                "Document convention situated before blocker selection; archetype menu exposed as advisory scaffolding."
            ),
            latest_refs=state.latest_refs,
            detail=dict(state.convention_context),
        ),
    )
    _, orient_read_ledger = transcript_edit_unified_and_closure_read_from_loop_state(state)
    state.blocker_registry = sync_registry_from_ledger(
        registry=state.blocker_registry,
        decision_ledger=orient_read_ledger,
        run_id=request_id_prefix,
        session_id=session_id,
        source_transcript_ref=state.current_transcript_ref,
    )
    sync_pending_feedback_cache_from_registry(state=state)
    blocker_health = blocker_health_snapshot(
        registry=state.blocker_registry,
        decision_ledger=orient_read_ledger,
    )
    _emit_progress(
        progress_cb,
        ticker_payload(
            iteration=0,
            phase="blocker_health_check",
            message="Blocker registry health snapshot completed.",
            latest_refs=state.latest_refs,
            detail=blocker_health,
        ),
    )
    if bool(blocker_health.get("ledger_registry_mismatch")):
        state.blocker_registry = sync_registry_from_ledger(
            registry=state.blocker_registry,
            decision_ledger=orient_read_ledger,
            run_id=request_id_prefix,
            session_id=session_id,
            source_transcript_ref=state.current_transcript_ref,
        )
        sync_pending_feedback_cache_from_registry(state=state)
        _, orient_read_ledger = transcript_edit_unified_and_closure_read_from_loop_state(state)
        _emit_progress(
            progress_cb,
            ticker_payload(
                iteration=0,
                phase="blocker_health_reconcile",
                message="Detected ledger/registry mismatch; projection resynced from ledger.",
                latest_refs=state.latest_refs,
                detail=blocker_health_snapshot(
                    registry=state.blocker_registry,
                    decision_ledger=orient_read_ledger,
                ),
            ),
        )
    baseline_unresolved = unresolved_closure_requirements(orient_read_ledger)
    baseline_residual = [item for item in baseline_unresolved if isinstance(item, dict)]
    mapping_blocking_count = sum(1 for item in baseline_residual if bool(item.get("mapping_blocking")))
    optional_count = max(0, len(baseline_residual) - mapping_blocking_count)
    _emit_progress(
        progress_cb,
        investigation_baseline_result_payload(
            iteration=0,
            latest_refs=state.latest_refs,
            evidence_attempts=[
                {
                    "attempt": "tx_orient_and_baseline",
                    "status": "completed",
                    "result_count": len(
                        orient_inline.get("tx_orient_items")
                        if isinstance(orient_inline.get("tx_orient_items"), list)
                        else []
                    ),
                }
            ],
            residual_blockers=baseline_residual[:6],
            mapping_blocking_count=mapping_blocking_count,
            optional_count=optional_count,
            next_recommended_action=(
                "Proceed to clean-path checks."
                if mapping_blocking_count == 0
                else "Proceed to investigation and evidence waterfall."
            ),
            decision_ledger=ledger_snapshot_for_payload(state.decision_ledger),
        ),
    )

    for iterations in range(1, request.max_iterations + 1):
        state.iterations = iterations
        audit_inputs: dict[str, Any] = {"dossier_id": request.dossier_id}
        if state.current_transcript_ref:
            audit_inputs["source_transcript_ref"] = state.current_transcript_ref
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
        state.latest_refs = audit.dashboard.latest_refs.model_dump(mode="json")
        _emit_progress(
            progress_cb,
            audit_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
                execution_state=str(audit.execution_state.value),
            ),
        )
        if audit.execution_state != StepExecutionState.EXECUTED:
            reason = audit.refusal.reason_code if audit.refusal is not None else "tx_audit_refused"
            status = "failed"
            if _should_convert_timeout_to_waiting_feedback(reason=reason, state=state):
                status = "needs_review"
            return _finalize_result_and_project_run_feed(
                start=start,
                request=request,
                request_id_prefix=request_id_prefix,
                progress_log=progress_log,
                session_id=session_id,
                iterations=iterations,
                status=status,
                reason=reason,
                latest_refs=state.latest_refs,
                review_required=True,
                runtime_hitl_state=_runtime_hitl_state(state),
            )
        inline = _read_step_outputs_inline(audit.step_record)
        source_ref_candidate = _read_str(inline.get("tx_source_transcript_ref"))
        if source_ref_candidate:
            state.current_transcript_ref = source_ref_candidate
        finding_count = _read_int(inline.get("tx_findings_count"), 0)
        error_count = _read_int(inline.get("tx_error_findings_count"), 0)
        findings_summary = inline.get("tx_validator_summary") if isinstance(inline.get("tx_validator_summary"), dict) else {}
        top_findings = inline.get("tx_top_findings") if isinstance(inline.get("tx_top_findings"), list) else []
        source_transcript_hash = _read_str(inline.get("tx_source_transcript_hash")) or pre_source_hash
        if not source_transcript_hash:
            source_transcript_hash = _read_str_from_latest_refs(state.latest_refs, "tx_source_transcript_ref") or ""
        planning_findings = _prioritized_findings_for_planning(top_findings=top_findings)
        blocking_warning_present = _has_blocking_warnings(top_findings)
        warning_count = _read_int(findings_summary.get("warnings") if isinstance(findings_summary, dict) else None, 0)
        # Phase 16: deterministic seed/template touch from audit findings first, then bounded discovery merge.
        # Organized-work default remains discovery-first; template rows wake only when findings touch them.
        state.decision_ledger = update_ledger_from_iteration(
            ledger=state.decision_ledger,
            findings=top_findings,
        )
        _disc_merge_stats: dict[str, Any] = {}
        state.decision_ledger = merge_discovery_from_audit_findings(
            state.decision_ledger,
            top_findings,
            merge_stats=_disc_merge_stats,
        )
        append_discovery_merge_continuity(
            state.continuity_log,
            iteration=iterations,
            merge_stats=_disc_merge_stats,
        )
        _, audit_read_ledger = transcript_edit_unified_and_closure_read_from_loop_state(state)
        state.blocker_registry = sync_registry_from_ledger(
            registry=state.blocker_registry,
            decision_ledger=audit_read_ledger,
            run_id=request_id_prefix,
            session_id=session_id,
            source_transcript_ref=state.current_transcript_ref,
        )
        sync_pending_feedback_cache_from_registry(state=state)
        unresolved_items = unresolved_closure_requirements(audit_read_ledger)
        has_open_closure = bool(unresolved_items)
        has_mapping_blocking_closure = has_unresolved_target_scope_mapping_blocking_closure(audit_read_ledger)
        # Warnings outside the target scope should not block scoped closure gates.
        blocking_warning_present = bool(blocking_warning_present and has_mapping_blocking_closure)
        _emit_progress(
            progress_cb,
            audit_result_payload(
                iteration=iterations,
                finding_count=finding_count,
                error_count=error_count,
                warning_count=warning_count,
                top_findings_display=[finding_to_display_dict(f) for f in top_findings[:6]],
                summary_text=top_findings_summary_text(top_findings),
                latest_refs=state.latest_refs,
                execution_state=str(audit.execution_state.value),
                decision_ledger=ledger_snapshot_for_payload(state.decision_ledger),
            ),
        )

        current_finding_signature = finding_signature(summary=findings_summary, findings=top_findings)
        current_blocking_signature = blocking_signature(audit_read_ledger)
        current_blocking_count = blocking_unresolved_count(audit_read_ledger)
        apply_reaudit_baseline_count = state.apply_reaudit_baseline_blocking_count
        apply_reaudit_baseline_signature = state.apply_reaudit_baseline_blocking_signature
        progressed, progress_reason, clear_pending_reaudit = classify_iteration_progress(
            previous_finding_signature=state.previous_finding_signature,
            current_finding_signature=current_finding_signature,
            previous_blocking_signature=state.previous_blocking_signature,
            current_blocking_signature=current_blocking_signature,
            previous_blocking_count=state.previous_blocking_unresolved_count,
            current_blocking_count=current_blocking_count,
            previous_signal_counter=state.previous_signal_counter,
            current_signal_counter=state.evidence_signal_counter,
            pending_feedback_prompt_id=state.pending_feedback_prompt_id,
            pending_reaudit_after_apply=state.pending_reaudit_after_apply,
            apply_reaudit_baseline_blocking_count=apply_reaudit_baseline_count,
            apply_reaudit_baseline_blocking_signature=apply_reaudit_baseline_signature,
        )
        _emit_progress(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="progress_evaluation",
                message=f"Progress evaluation: {progress_reason}.",
                latest_refs=state.latest_refs,
                detail={
                    "progressed": bool(progressed),
                    "progress_reason": progress_reason,
                    "pre_apply_blocker_signature": (
                        apply_reaudit_baseline_signature
                        if state.pending_reaudit_after_apply
                        else None
                    ),
                    "post_apply_blocker_signature": current_blocking_signature,
                    "pre_apply_blocker_count": (
                        int(apply_reaudit_baseline_count)
                        if state.pending_reaudit_after_apply and apply_reaudit_baseline_count is not None
                        else None
                    ),
                    "post_apply_blocker_count": int(current_blocking_count),
                    "pending_reaudit_after_apply": bool(state.pending_reaudit_after_apply),
                },
            ),
        )
        if clear_pending_reaudit:
            state.pending_reaudit_after_apply = False
            state.apply_reaudit_baseline_blocking_count = None
            state.apply_reaudit_baseline_blocking_signature = None
        state.no_progress_streak = 0 if progressed else state.no_progress_streak + 1
        state.last_progress_reason = progress_reason
        state.previous_finding_signature = current_finding_signature
        state.previous_blocking_signature = current_blocking_signature
        state.previous_blocking_unresolved_count = current_blocking_count
        state.previous_signal_counter = state.evidence_signal_counter

        if error_count <= 0 and not blocking_warning_present and not has_mapping_blocking_closure:
            decision = handle_clean_iteration(
                state=state,
                session_manager=session_manager,
                session_id=session_id,
                request=request,
                request_id_prefix=request_id_prefix,
                mode=mode,
                promote_mode=_MODE_AUDIT_REPAIR_PROMOTE,
                min_iterations_before_complete=min_iterations_before_complete,
                iterations=iterations,
                error_count=error_count,
                has_disagreements=has_open_closure,
                source_transcript_hash=source_transcript_hash,
                progress_cb=progress_cb,
                model=loop_model,
            )
            if decision is None:
                continue
            return _finalize_result_and_project_run_feed(
                start=start,
                request=request,
                request_id_prefix=request_id_prefix,
                progress_log=progress_log,
                session_id=session_id,
                iterations=iterations,
                status=decision.status,
                reason=decision.reason_code,
                latest_refs=state.latest_refs,
                review_required=decision.review_required,
                runtime_hitl_state=_runtime_hitl_state(state),
            )

        if mode == _MODE_AUDIT_ONLY:
            return _finalize_result_and_project_run_feed(
                start=start,
                request=request,
                request_id_prefix=request_id_prefix,
                progress_log=progress_log,
                session_id=session_id,
                iterations=iterations,
                status="needs_review",
                reason="tx_agent_audit_only_findings_present",
                latest_refs=state.latest_refs,
                review_required=True,
                runtime_hitl_state=_runtime_hitl_state(state),
            )

        decision = handle_repair_iteration(
            state=state,
            session_manager=session_manager,
            session_id=session_id,
            request=request,
            request_id_prefix=request_id_prefix,
            iterations=iterations,
            planner_client=planner_client,
            tx_persistence=tx_persistence,
            planning_findings=planning_findings,
            top_findings=top_findings,
            findings_summary=findings_summary,
            source_transcript_hash=source_transcript_hash,
            progress_cb=progress_cb,
            model=loop_model,
            validation_mode=validation_mode,
        )
        if decision is not None:
            return _finalize_result_and_project_run_feed(
                start=start,
                request=request,
                request_id_prefix=request_id_prefix,
                progress_log=progress_log,
                session_id=session_id,
                iterations=iterations,
                status=decision.status,
                reason=decision.reason_code,
                latest_refs=state.latest_refs,
                review_required=decision.review_required,
                runtime_hitl_state=_runtime_hitl_state(state),
            )

    terminal_decision = max_iterations_decision(state.last_reason)
    if state.applied_any_edits:
        persist_agent_edit_draft(
            dossier_id=request.dossier_id,
            transcription_id=request.transcription_id,
            source_transcript_ref=state.current_transcript_ref,
            run_id=request_id_prefix,
            reason_code=terminal_decision.reason_code,
        )
    return _finalize_result_and_project_run_feed(
        start=start,
        request=request,
        request_id_prefix=request_id_prefix,
        progress_log=progress_log,
        session_id=session_id,
        iterations=iterations,
        status=terminal_decision.status,
        reason=terminal_decision.reason_code,
        latest_refs=state.latest_refs,
        review_required=terminal_decision.review_required,
        runtime_hitl_state=_runtime_hitl_state(state),
    )


def _emit_progress(progress_cb: Callable[[dict[str, Any]], None] | None, payload: dict[str, Any]) -> None:
    emit_progress(progress_cb, payload)


def _run_prestart_countdown(
    *,
    progress_cb: Callable[[dict[str, Any]], None] | None,
    latest_refs: dict[str, Any],
    countdown_seconds: int,
) -> None:
    _LOG.info(
        "TX_LOOP_PRESTART_COUNTDOWN ► state=starting remaining_seconds=%s",
        countdown_seconds,
    )
    for remaining_seconds in range(countdown_seconds, -1, -1):
        _emit_progress(
            progress_cb,
            preflight_countdown_payload(
                remaining_seconds=remaining_seconds,
                latest_refs=latest_refs,
            ),
        )
        _LOG.info(
            "TX_LOOP_PRESTART_COUNTDOWN ► remaining_seconds=%s",
            remaining_seconds,
        )
        if remaining_seconds > 0:
            time.sleep(1)
    _LOG.info("TX_LOOP_PRESTART_COUNTDOWN ► state=completed")


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
    runtime_hitl_state: dict[str, Any] | None = None,
) -> TranscriptEditAgentRunResult:
    return build_run_result(
        run_artifact_ref=start.run_artifact_ref,
        session_id=session_id,
        iterations=iterations,
        status=status,
        reason_code=reason,
        latest_refs=latest_refs,
        review_required=review_required,
        runtime_hitl_state=runtime_hitl_state,
    )


def _finalize_result_and_project_run_feed(
    *,
    start,
    request: TranscriptEditAgentRunRequest,
    request_id_prefix: str,
    progress_log: list[dict[str, Any]],
    session_id: str | None,
    iterations: int,
    status: str,
    reason: str,
    latest_refs: dict[str, Any],
    review_required: bool,
    runtime_hitl_state: dict[str, Any] | None = None,
    feed_service: TranscriptEditRunFeedPersistenceService | None = None,
    handoff_packet_ref: str | None = None,
    handoff_summary: str | None = None,
) -> TranscriptEditAgentRunResult:
    effective_session_id = str(session_id or getattr(start, "session_id", "") or "")
    result = _result(
        start=start,
        session_id=effective_session_id,
        iterations=iterations,
        status=status,
        reason=reason,
        latest_refs=latest_refs,
        review_required=review_required,
        runtime_hitl_state=runtime_hitl_state,
    )
    run_terminal_message = terminal_message(result)
    run_terminal_summary = terminal_summary(
        progress_log,
        result,
        critical_events=[],
        runtime_hitl_state=runtime_hitl_state,
    )
    freshness_posture = run_terminal_summary.get("final_freshness_posture")
    freshness_summary = str(run_terminal_summary.get("final_freshness_summary") or "").strip() or None
    try:
        write_transcript_edit_run_snapshot(
            request_id=request_id_prefix,
            run_id=str(result.session_id or request_id_prefix),
            session_id=result.session_id,
            dossier_id=request.dossier_id,
            final_status=result.status,
            reason_code=result.reason_code,
            iterations=result.iterations,
            terminal_message=run_terminal_message,
            terminal_summary=run_terminal_summary,
            final_freshness_posture=freshness_posture if isinstance(freshness_posture, dict) else None,
            final_freshness_summary=freshness_summary,
            run_artifact_ref=result.run_artifact_ref,
            handoff_packet_ref=handoff_packet_ref,
            handoff_summary=handoff_summary,
            feed_service=feed_service or _RUN_FEED_PERSISTENCE,
        )
    except Exception as exc:
        _LOG.warning(
            "TX_RUN_FEED_WRITE_FAILED ► run_id=%s error_type=%s error=%s",
            request_id_prefix,
            type(exc).__name__,
            str(exc)[:220],
        )
    return result


def _runtime_hitl_state(state: TranscriptEditLoopState) -> dict[str, Any]:
    from .board_observability import compact_emergent_board_run_posture

    _, hitl_read_ledger = transcript_edit_unified_and_closure_read_from_loop_state(state)
    projection = derive_waiting_feedback_projection(
        blocker_registry=state.blocker_registry,
        fallback_prompt_id=state.pending_feedback_prompt_id,
        fallback_decision_key=state.pending_feedback_decision_key,
    )
    tickets = list_external_context_injections(
        hitl_read_ledger,
        type_filter="human_resolution_ticket",
    )
    mission_runtime_summary = derive_mission_runtime_summary(
        decision_ledger=hitl_read_ledger,
        blocker_registry=state.blocker_registry,
        waiting_projection=projection,
    )
    return {
        "used_human_feedback": bool(state.used_human_feedback),
        "feedback_received_count": int(state.feedback_received_count),
        "feedback_consumed_count": int(state.feedback_consumed_count),
        "feedback_stale_count": int(state.feedback_stale_count),
        "feedback_superseded_count": int(state.feedback_superseded_count),
        "mission_runtime_summary": mission_runtime_summary,
        "pending_feedback_prompt_id": projection.get("pending_feedback_prompt_id"),
        "pending_feedback_decision_key": projection.get("pending_feedback_decision_key"),
        "superseded_prompt_ids": sorted(list(state.superseded_feedback_prompt_ids)),
        "hitl_lifecycle_log": list(state.hitl_lifecycle_log),
        "human_resolution_tickets": tickets,
        "source_completeness": str(hitl_read_ledger.get("source_completeness") or "unknown"),
        "source_completeness_reason": hitl_read_ledger.get("source_completeness_reason"),
        "source_limitations": [
            str(v)
            for v in list(hitl_read_ledger.get("source_limitations") or [])
            if str(v).strip()
        ][:12],
        "scope_summaries": dict(hitl_read_ledger.get("scope_summaries") or {}),
        "convention_context": dict(state.convention_context or {}),
        "blocker_registry": registry_snapshot_for_payload(state.blocker_registry),
        "active_blocker": select_primary_blocker(state.blocker_registry),
        "blocker_health": blocker_health_snapshot(registry=state.blocker_registry, decision_ledger=hitl_read_ledger),
        "board_run_posture_compact": compact_emergent_board_run_posture(
            list(state.harness_emergent_board_items or []),
            last_focus_key=state.last_focus_key,
        ),
    }
def _normalized_mode(raw: str | None) -> str:
    return normalized_mode(
        raw,
        {_MODE_OFF, _MODE_AUDIT_ONLY, _MODE_AUDIT_REPAIR, _MODE_AUDIT_REPAIR_PROMOTE},
        _MODE_AUDIT_REPAIR_PROMOTE,
    )
def _normalized_validation_mode(raw: str | None) -> str:
    return normalized_mode(
        raw,
        {_VALIDATION_MODE_OFF, _VALIDATION_MODE_LIVE_HITL},
        _VALIDATION_MODE_OFF,
    )


def _validation_runtime_profile(validation_mode: str) -> dict[str, Any]:
    mode = _normalized_validation_mode(validation_mode)
    if mode == _VALIDATION_MODE_LIVE_HITL:
        return {
            "validation_mode": mode,
            "max_wall_time_seconds": 600,
            "image_verify_max_checks": 1,
            "image_verify_step_timeout_seconds": 90,
            "image_verify_max_attempts_per_check": 1,
            "image_verify_heartbeat_thresholds_seconds": [10, 20, 30, 60],
            "image_verify_heartbeat_every_seconds": 30,
        }
    return {
        "validation_mode": _VALIDATION_MODE_OFF,
        "max_wall_time_seconds": 600,
        "image_verify_max_checks": 4,
        "image_verify_step_timeout_seconds": 240,
        "image_verify_max_attempts_per_check": 2,
        "image_verify_heartbeat_thresholds_seconds": [15, 30, 60],
        "image_verify_heartbeat_every_seconds": 60,
    }


def _should_convert_timeout_to_waiting_feedback(*, reason: str | None, state: TranscriptEditLoopState) -> bool:
    reason_text = str(reason or "").strip().lower()
    if "budget_wall_time_exceeded" not in reason_text:
        return False
    sync_pending_feedback_cache_from_registry(state=state)
    projection = derive_waiting_feedback_projection(
        blocker_registry=state.blocker_registry,
        fallback_prompt_id=state.pending_feedback_prompt_id,
        fallback_decision_key=state.pending_feedback_decision_key,
    )
    return bool(projection.get("waiting_feedback"))


def _read_step_outputs_inline(step_record: dict[str, Any] | None) -> dict[str, Any]:
    return read_step_outputs_inline(step_record)


def _read_str(value: object) -> str | None:
    return read_str(value)


def _read_int(value: object, default: int) -> int:
    return read_int(value, default)


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


def _edit_loop_model(preferred: str | None) -> str:
    del preferred
    return _EDIT_LOOP_LLM_MODEL


def _build_orient_inputs(
    *,
    dossier_id: str | None,
    model: str,
    source_transcript_ref: str | None,
    source_text: str | None,
    candidate_refs: list[str],
    candidate_texts: list[str],
    max_candidates_for_orient: int,
    max_total_hydrated_bytes_for_orient: int,
    max_bytes_per_candidate_for_orient: int | None,
    orient_hydration_selection_strategy: str,
) -> dict[str, Any]:
    inputs: dict[str, Any] = {
        "dossier_id": dossier_id,
        "model": model,
        "max_candidates_for_orient": int(max_candidates_for_orient),
        "max_total_hydrated_bytes": int(max_total_hydrated_bytes_for_orient),
        "selection_strategy": str(orient_hydration_selection_strategy or "first_middle_last"),
    }
    if isinstance(max_bytes_per_candidate_for_orient, int) and max_bytes_per_candidate_for_orient > 0:
        inputs["max_bytes_per_candidate"] = int(max_bytes_per_candidate_for_orient)
    if source_transcript_ref:
        inputs["canonical_ref"] = source_transcript_ref
    elif source_text:
        inputs["source_text"] = source_text

    candidate_ref_pool = [
        ref
        for ref in candidate_refs[:_MAX_CANDIDATES]
        if isinstance(ref, str) and ref.strip()
    ]
    if candidate_ref_pool:
        inputs["candidate_refs"] = candidate_ref_pool
        return inputs

    # Deprecated fallback for callers not yet migrated to candidate refs.
    candidate_pool = [text for text in candidate_texts[:_MAX_CANDIDATES] if isinstance(text, str) and text.strip()]
    while candidate_pool:
        candidate_inputs = dict(inputs)
        candidate_inputs["candidate_texts"] = candidate_pool
        if _kernel_inputs_size_bytes(candidate_inputs) <= _KERNEL_STEP_INPUT_BUDGET_BYTES:
            inputs["candidate_texts"] = candidate_pool
            return inputs
        candidate_pool = candidate_pool[:-1]
    return inputs


def _kernel_inputs_size_bytes(inputs: dict[str, Any]) -> int:
    payload = json.dumps(inputs, sort_keys=True, separators=(",", ":"))
    return len(payload.encode("utf-8"))


def _prioritized_findings_for_planning(*, top_findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return prioritized_findings_for_planning(top_findings=top_findings)


def _viewer_run_id_from_request_prefix(request_id_prefix: str) -> str:
    return viewer_run_id_from_request_prefix(request_id_prefix)


def _build_human_feedback_prompt(
    *,
    decision_ledger: dict[str, Any],
    iteration: int,
) -> dict[str, Any] | None:
    return build_human_feedback_prompt(
        decision_ledger=decision_ledger,
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


# ---------------------------------------------------------------------------
# Display helpers for rich progress emissions
# ---------------------------------------------------------------------------

def _span_to_display_dict(span: dict[str, Any]) -> dict[str, Any]:
    """span_id + text excerpt (120 chars)."""
    text = str(span.get("text") or span.get("content") or "").strip()
    return {
        "span_id": span.get("span_id"),
        "text": text[:120] + ("..." if len(text) > 120 else ""),
    }
