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
    initialize_decision_ledger,
    ledger_snapshot_for_payload,
    unresolved_closure_requirements,
    update_ledger_from_orient_baseline,
    update_ledger_from_iteration,
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
from .result_policy import (
    max_iterations_decision,
)
from .terminalization import build_run_result
from .run_reporting import (
    audit_payload,
    audit_result_payload,
    investigation_baseline_result_payload,
    preflight_countdown_payload,
    starting_payload,
)
from .planner import TranscriptEditPlanPlanner

_MODE_OFF = "off"
_MODE_AUDIT_ONLY = "audit_only"
_MODE_AUDIT_REPAIR = "audit_then_repair"
_MODE_AUDIT_REPAIR_PROMOTE = "audit_then_repair_then_promote"
_EDIT_LOOP_LLM_MODEL = "gpt-5.2"
_KERNEL_STEP_INPUT_BUDGET_BYTES = 4096
_LOG = logging.getLogger(__name__)


def run_transcript_edit_controller_loop(
    *,
    session_manager: KernelSessionManager,
    request: TranscriptEditAgentRunRequest,
    request_id_prefix: str,
    planner: TranscriptEditPlanPlanner | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    startup_countdown_seconds: int = 0,
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
    planner_client = planner or TranscriptEditPlanPlanner()
    tx_persistence = TranscriptionEditPersistenceService()
    state = TranscriptEditLoopState(
        latest_refs=start.dashboard.latest_refs.model_dump(mode="json") if start.dashboard else {},
        current_transcript_ref=request.source_transcript_ref,
        decision_ledger=initialize_decision_ledger(),
    )
    candidate_count = len(request.candidate_texts) if request.candidate_texts else 0
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
        return _result(
            start=start,
            session_id=session_id,
            iterations=0,
            status="failed",
            reason=reason,
            latest_refs=state.latest_refs,
            review_required=True,
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
        candidate_texts=request.candidate_texts,
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
        return _result(
            start=start,
            session_id=session_id,
            iterations=0,
            status="needs_review",
            reason=reason,
            latest_refs=state.latest_refs,
            review_required=True,
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
    baseline_unresolved = unresolved_closure_requirements(state.decision_ledger)
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
            return _result(
                start=start,
                session_id=session_id,
                iterations=iterations,
                status="failed",
                reason=reason,
                latest_refs=state.latest_refs,
                review_required=True,
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
        state.decision_ledger = update_ledger_from_iteration(
            ledger=state.decision_ledger,
            findings=top_findings,
        )
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
        if state.previous_finding_signature is not None and current_finding_signature == state.previous_finding_signature:
            state.no_progress_streak += 1
        else:
            state.no_progress_streak = 0
        state.previous_finding_signature = current_finding_signature

        if error_count <= 0 and not blocking_warning_present:
            has_open_closure = bool(unresolved_closure_requirements(state.decision_ledger))
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
            return _result(
                start=start,
                session_id=session_id,
                iterations=iterations,
                status=decision.status,
                reason=decision.reason_code,
                latest_refs=state.latest_refs,
                review_required=decision.review_required,
            )

        if mode == _MODE_AUDIT_ONLY:
            return _result(
                start=start,
                session_id=session_id,
                iterations=iterations,
                status="needs_review",
                reason="tx_agent_audit_only_findings_present",
                latest_refs=state.latest_refs,
                review_required=True,
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
            blocking_warning_present=blocking_warning_present,
            progress_cb=progress_cb,
            model=loop_model,
        )
        if decision is not None:
            return _result(
                start=start,
                session_id=session_id,
                iterations=iterations,
                status=decision.status,
                reason=decision.reason_code,
                latest_refs=state.latest_refs,
                review_required=decision.review_required,
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
    return _result(
        start=start,
        session_id=session_id,
        iterations=iterations,
        status=terminal_decision.status,
        reason=terminal_decision.reason_code,
        latest_refs=state.latest_refs,
        review_required=terminal_decision.review_required,
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
) -> TranscriptEditAgentRunResult:
    return build_run_result(
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
    candidate_texts: list[str],
) -> dict[str, Any]:
    # Keep orient inputs below kernel step payload limit by trimming candidates first.
    inputs: dict[str, Any] = {
        "dossier_id": dossier_id,
        "model": model,
    }
    if source_transcript_ref:
        inputs["source_transcript_ref"] = source_transcript_ref
    elif source_text:
        inputs["source_text"] = source_text
    candidate_pool = [text for text in candidate_texts[:10] if isinstance(text, str) and text.strip()]
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


