from __future__ import annotations

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
    starting_payload,
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
    planner_client = planner or TranscriptEditPlanPlanner()
    tx_persistence = TranscriptionEditPersistenceService()
    state = TranscriptEditLoopState(
        latest_refs=start.dashboard.latest_refs.model_dump(mode="json") if start.dashboard else {},
        current_transcript_ref=request.source_transcript_ref,
    )
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
    loop_model = _edit_loop_model(request.model)
    _emit_progress(
        progress_cb,
        starting_payload(
            mode=mode,
            candidate_count=candidate_count,
            has_disagreements=has_disagreements,
            latest_refs=state.latest_refs,
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
        source_transcript_hash = _read_str(inline.get("tx_source_transcript_hash")) or ""
        if not source_transcript_hash:
            source_transcript_hash = _read_str_from_latest_refs(state.latest_refs, "tx_source_transcript_ref") or ""
        effective_disagreement_hints = _resolved_disagreement_hints(
            disagreement_hints=disagreement_hints,
            sticky_range_selection=state.sticky_range_selection,
        )
        mapping_focus = _mapping_priority_focus(disagreement_hints=effective_disagreement_hints)
        disagreement_findings = _critical_disagreement_findings(effective_disagreement_hints)
        # Include disagreement findings on first iteration (to gate obvious cross-draft conflicts),
        # and on later iterations only when the validator still finds issues. This prevents
        # stale disagreement hints from re-triggering HITL after a clean re-audit.
        include_disagreement_findings = bool(disagreement_findings and (finding_count > 0 or iterations == 1 or state.sticky_range_selection is None))
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
            audit_result_payload(
                iteration=iterations,
                finding_count=finding_count,
                error_count=error_count,
                warning_count=warning_count,
                top_findings_display=[finding_to_display_dict(f) for f in top_findings[:6]],
                summary_text=top_findings_summary_text(top_findings),
                latest_refs=state.latest_refs,
                execution_state=str(audit.execution_state.value),
            ),
        )

        current_finding_signature = finding_signature(summary=findings_summary, findings=top_findings)
        if state.previous_finding_signature is not None and current_finding_signature == state.previous_finding_signature:
            state.no_progress_streak += 1
        else:
            state.no_progress_streak = 0
        state.previous_finding_signature = current_finding_signature

        if error_count <= 0 and not blocking_warning_present:
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
                has_disagreements=has_disagreements,
                effective_disagreement_hints=effective_disagreement_hints,
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
            effective_disagreement_hints=effective_disagreement_hints,
            mapping_focus=mapping_focus,
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

def _span_to_display_dict(span: dict[str, Any]) -> dict[str, Any]:
    """span_id + text excerpt (120 chars)."""
    text = str(span.get("text") or span.get("content") or "").strip()
    return {
        "span_id": span.get("span_id"),
        "text": text[:120] + ("..." if len(text) > 120 else ""),
    }


