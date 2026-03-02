from __future__ import annotations

import hashlib
import json
from typing import Any
import re
from datetime import datetime, timezone
from collections.abc import Callable
import time
from uuid import uuid4

from agent_kernel.models import (
    ActionType,
    KernelBudgets,
    KernelGoal,
    KernelSessionStartRequest,
    KernelStepRequest,
    StepExecutionState,
)
from agent_kernel.session import KernelSessionManager
from transcript_edit.persistence import TranscriptionEditPersistenceService
from services.agent_viewer import feedback_store

from .contracts import TranscriptEditAgentRunRequest, TranscriptEditAgentRunResult
from .planner import TranscriptEditPlanPlanner
from .span_seeds import build_transcript_span_seeds_artifact, load_transcript_text_for_seeds

_MODE_OFF = "off"
_MODE_AUDIT_ONLY = "audit_only"
_MODE_AUDIT_REPAIR = "audit_then_repair"
_MODE_AUDIT_REPAIR_PROMOTE = "audit_then_repair_then_promote"


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
    last_reason = "tx_agent_not_started"
    disagreement_hints = _candidate_disagreement_hints(request.candidate_texts)
    mapping_focus = _mapping_priority_focus(disagreement_hints=disagreement_hints)

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
                "message": "Audited transcript for deterministic findings.",
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
        disagreement_findings = _critical_disagreement_findings(disagreement_hints)
        if disagreement_findings:
            top_findings = [*top_findings, *disagreement_findings]
            findings_summary = _merge_findings_summary_with_disagreement(
                findings_summary=findings_summary,
                disagreement_findings=disagreement_findings,
            )
        planning_findings = _prioritized_findings_for_planning(top_findings=top_findings)
        blocking_warning_present = _has_blocking_warnings(top_findings)

        finding_signature = _finding_signature(summary=findings_summary, findings=top_findings)
        if previous_finding_signature is not None and finding_signature == previous_finding_signature:
            no_progress_streak += 1
        else:
            no_progress_streak = 0
        previous_finding_signature = finding_signature

        if error_count <= 0 and not blocking_warning_present:
            if (
                request.dossier_id
                and current_transcript_ref
                and source_transcript_hash
                and error_count <= 0
            ):
                span_seeds_ref = _emit_transcript_span_seeds(
                    persistence=tx_persistence,
                    dossier_id=request.dossier_id,
                    source_transcript_ref=current_transcript_ref,
                    source_transcript_hash=source_transcript_hash,
                )
                if span_seeds_ref:
                    latest_refs["tx_span_seeds_ref"] = {"artifact_path": span_seeds_ref}
            should_promote = (
                mode == _MODE_AUDIT_REPAIR_PROMOTE
                and request.auto_promote
                and not applied_non_normalization
                and not applied_requires_review
                and error_count <= 0
            )
            if should_promote and current_transcript_ref:
                final_verify = _final_image_sanity_pass_before_promote(
                    session_manager=session_manager,
                    session_id=session_id,
                    iteration=iterations,
                    dossier_id=request.dossier_id,
                    source_transcript_ref=current_transcript_ref,
                    source_image_refs=request.source_image_refs,
                    model=_vision_verify_model(request.model),
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
                return _result(
                    start=start,
                    session_id=session_id,
                    iterations=iterations,
                    status="completed",
                    reason="tx_agent_clean_promoted",
                    latest_refs=latest_refs,
                    review_required=False,
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
        viewer_run_id = _viewer_run_id_from_request_prefix(request_id_prefix)
        if blocking_warning_present and request.hitl_enabled and viewer_run_id.startswith("tx_agent_"):
            feedback_prompt = _build_human_feedback_prompt(
                disagreement_hints=disagreement_hints,
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
                if selected_number is not None and current_transcript_ref and source_transcript_hash:
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
                "phase": "open_spans",
                "message": "Opened localized transcript spans for planning context.",
                "latest_refs": latest_refs,
            },
        )
        image_verification = _verify_mapping_critical_with_image(
            session_manager=session_manager,
            session_id=session_id,
            iteration=iterations,
            dossier_id=request.dossier_id,
            source_transcript_ref=current_transcript_ref,
            top_findings=planning_findings,
            disagreement_hints=disagreement_hints,
            source_image_refs=request.source_image_refs,
            model=_vision_verify_model(request.model),
        )
        if image_verification:
            latest_refs = image_verification.get("latest_refs", latest_refs)
            _emit_progress(
                progress_cb,
                {
                    "iteration": iterations,
                    "phase": "image_verify",
                    "message": "Ran image-backed verification on mapping-critical findings.",
                    "latest_refs": latest_refs,
                    "image_verification": image_verification.get("payload"),
                },
            )
        manual_plan = manual_plan_override or (request.edit_plan if isinstance(request.edit_plan, dict) else None)
        consensus_plan_payload = None
        if manual_plan is None:
            consensus_plan_payload = _build_deterministic_consensus_plan(
                source_transcript_ref=current_transcript_ref,
                source_transcript_hash=source_transcript_hash,
                disagreement_hints=disagreement_hints,
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
            try:
                plan, plan_reason, raw_plan_text = planner_client.propose_plan(
                    model=request.model,
                    source_transcript_ref=current_transcript_ref,
                    source_transcript_hash=source_transcript_hash,
                    findings_summary=findings_summary,
                    top_findings=_coerce_findings(planning_findings),
                    span_context=span_context,
                    image_verification=image_verification.get("payload") if isinstance(image_verification, dict) else {},
                    candidate_disagreement_hints=disagreement_hints,
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
        apply = _step(
            session_manager=session_manager,
            session_id=session_id,
            prefix="tx_apply",
            iteration=iterations,
            action_type=ActionType.TX_APPLY_EDIT_PLAN,
            inputs={"dossier_id": request.dossier_id, "edit_plan": plan_payload},
        )
        latest_refs = apply.dashboard.latest_refs.model_dump(mode="json")
        _emit_progress(
            progress_cb,
            {
                "iteration": iterations,
                "phase": "apply",
                "message": "Applied transcript edit plan and persisted updated artifacts.",
                "latest_refs": latest_refs,
                "execution_state": str(apply.execution_state.value),
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
        if manual_plan is None:
            invalid_plan_strikes = 0
        last_reason = plan_reason if plan_reason else "tx_apply_completed"
        if raw_plan_text:
            _ = raw_plan_text  # retain variable for debugging parity without expanding artifacts

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
    if progress_cb is None:
        return
    try:
        progress_cb(payload)
    except Exception:
        return


def _step(
    *,
    session_manager: KernelSessionManager,
    session_id: str,
    prefix: str,
    iteration: int,
    action_type: ActionType,
    inputs: dict[str, Any],
):
    return session_manager.step(
        KernelStepRequest(
            session_id=session_id,
            idempotency_key=_idempotency_key(prefix, iteration, inputs),
            action_type=action_type,
            inputs=inputs,
        )
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
    spans: list[dict[str, Any]] = []
    for finding in top_findings[:5]:
        if not isinstance(finding, dict):
            continue
        span = finding.get("span")
        if isinstance(span, dict):
            start = span.get("start_char")
            end = span.get("end_char")
            if isinstance(start, int) and isinstance(end, int) and end > start:
                spans.append({"start_char": max(0, start - 100), "end_char": end + 100, "span_id": finding.get("finding_id")})
    if not spans:
        spans = _fallback_spans_for_findings(
            source_transcript_ref=source_transcript_ref,
            top_findings=top_findings,
        )
    step = _step(
        session_manager=session_manager,
        session_id=session_id,
        prefix="tx_open_spans",
        iteration=iteration,
        action_type=ActionType.TX_OPEN_TRANSCRIPT_SPANS,
        inputs={
            "dossier_id": dossier_id,
            "source_transcript_ref": source_transcript_ref,
            "spans": spans,
            "max_chars_per_span": 1400,
            "max_total_chars": 5000,
        },
    )
    if step.execution_state != StepExecutionState.EXECUTED:
        return []
    inline = _read_step_outputs_inline(step.step_record)
    raw_spans = inline.get("spans")
    if isinstance(raw_spans, list):
        return [s for s in raw_spans[:8] if isinstance(s, dict)]
    return []


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
    checks: list[dict[str, Any]] = []
    for finding in top_findings[:6]:
        if not isinstance(finding, dict):
            continue
        finding_type = str(finding.get("finding_type") or "").strip().lower()
        if finding_type not in {"plss_consistency", "bearing_parse", "numeric_unit_sanity", "call_chain_structure"}:
            continue
        check_id = str(finding.get("finding_id") or f"finding_{len(checks) + 1}")
        checks.append(
            {
                "check_id": check_id,
                "query": str(finding.get("message") or "")[:320],
                "expected_text": _first_expected_token_from_message(str(finding.get("message") or "")),
            }
        )
    checks.extend(_image_checks_from_disagreement_hints(disagreement_hints))
    if not checks:
        return {}

    inputs: dict[str, Any] = {
        "dossier_id": dossier_id,
        "source_transcript_ref": source_transcript_ref,
        "checks": checks[:6],
        "model": model,
        "zoom_factor": 2.4,
    }
    if isinstance(source_image_refs, list) and source_image_refs:
        first_image = _read_str(source_image_refs[0])
        if first_image:
            inputs["image_ref"] = first_image

    step = _step(
        session_manager=session_manager,
        session_id=session_id,
        prefix="tx_verify_img",
        iteration=iteration,
        action_type=ActionType.TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
        inputs=inputs,
    )
    latest_refs = step.dashboard.latest_refs.model_dump(mode="json")
    if step.execution_state != StepExecutionState.EXECUTED:
        return {"latest_refs": latest_refs, "payload": {}}
    inline = _read_step_outputs_inline(step.step_record)
    payload = {
        "summary": inline.get("tx_image_verify_summary") if isinstance(inline.get("tx_image_verify_summary"), dict) else {},
        "results": inline.get("tx_image_verify_results") if isinstance(inline.get("tx_image_verify_results"), list) else [],
        "image_path": _read_str(inline.get("tx_image_path")),
    }
    return {"latest_refs": latest_refs, "payload": payload}


def _final_image_sanity_pass_before_promote(
    *,
    session_manager: KernelSessionManager,
    session_id: str,
    iteration: int,
    dossier_id: str | None,
    source_transcript_ref: str,
    source_image_refs: list[str],
    model: str,
) -> dict[str, Any]:
    checks = [
        {
            "check_id": "final_sanity_plss",
            "query": (
                "Read the deed image and report the key PLSS location tokens exactly as written "
                "(township, range, section if present)."
            ),
            "expected_text": None,
        },
        {
            "check_id": "final_sanity_distance",
            "query": (
                "Report the principal tie distance in feet from the point-of-beginning tie language if present."
            ),
            "expected_text": None,
        },
        {
            "check_id": "final_sanity_acreage",
            "query": "Report acreage value(s) stated for parcel descriptions if present.",
            "expected_text": None,
        },
    ]
    inputs: dict[str, Any] = {
        "dossier_id": dossier_id,
        "source_transcript_ref": source_transcript_ref,
        "checks": checks,
        "model": model,
        "zoom_factor": 2.4,
    }
    if isinstance(source_image_refs, list) and source_image_refs:
        first_image = _read_str(source_image_refs[0])
        if first_image:
            inputs["image_ref"] = first_image

    step = _step(
        session_manager=session_manager,
        session_id=session_id,
        prefix="tx_final_verify",
        iteration=iteration,
        action_type=ActionType.TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
        inputs=inputs,
    )
    latest_refs = step.dashboard.latest_refs.model_dump(mode="json")
    if step.execution_state != StepExecutionState.EXECUTED:
        refusal_code = step.refusal.reason_code if step.refusal is not None else "tx_agent_final_image_verify_refused"
        return {"passed": False, "reason": f"tx_agent_final_image_verify_failed:{refusal_code}", "latest_refs": latest_refs}

    inline = _read_step_outputs_inline(step.step_record)
    summary = inline.get("tx_image_verify_summary") if isinstance(inline.get("tx_image_verify_summary"), dict) else {}
    mismatch_count = _read_int(summary.get("mismatch_count"), 0) if isinstance(summary, dict) else 0
    unclear_count = _read_int(summary.get("unclear_count"), 0) if isinstance(summary, dict) else 0
    total_checks = _read_int(summary.get("total_checks"), 0) if isinstance(summary, dict) else 0
    if total_checks <= 0:
        return {"passed": False, "reason": "tx_agent_final_image_verify_failed:no_checks", "latest_refs": latest_refs}
    if mismatch_count > 0:
        return {"passed": False, "reason": "tx_agent_final_image_verify_failed:mismatch", "latest_refs": latest_refs}
    if unclear_count > 0:
        return {"passed": False, "reason": "tx_agent_final_image_verify_failed:unclear", "latest_refs": latest_refs}
    return {"passed": True, "reason": "ok", "latest_refs": latest_refs}


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
    value = (raw or "").strip().lower()
    if value in {_MODE_OFF, _MODE_AUDIT_ONLY, _MODE_AUDIT_REPAIR, _MODE_AUDIT_REPAIR_PROMOTE}:
        return value
    return _MODE_AUDIT_REPAIR_PROMOTE


def _idempotency_key(prefix: str, iteration: int, inputs: dict[str, Any]) -> str:
    canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{iteration:02d}-{digest}"


def _read_step_outputs_inline(step_record: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(step_record, dict):
        return {}
    outputs_inline = step_record.get("outputs_inline")
    if isinstance(outputs_inline, dict):
        return outputs_inline
    return {}


def _read_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _read_int(value: object, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _coerce_findings(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in values[:12]:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "finding_id": item.get("finding_id"),
                "finding_type": item.get("finding_type"),
                "severity": item.get("severity"),
                "message": item.get("message"),
                "section_id": item.get("section_id"),
                "span": item.get("span"),
            }
        )
    return out


def _finding_signature(*, summary: dict[str, Any], findings: list[dict[str, Any]]) -> str:
    payload = {
        "summary": summary,
        "findings": [
            {
                "finding_id": f.get("finding_id"),
                "severity": f.get("severity"),
                "finding_type": f.get("finding_type"),
            }
            for f in findings[:8]
            if isinstance(f, dict)
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _max_change_class_from_plan(plan: dict[str, Any]) -> str:
    ops = plan.get("ops")
    if not isinstance(ops, list):
        return "normalization"
    rank = {"normalization": 0, "semantic": 1, "structural": 2}
    highest = 0
    for op in ops:
        if not isinstance(op, dict):
            continue
        cc = str(op.get("change_class") or "").strip().lower()
        highest = max(highest, rank.get(cc, 0))
    for key, value in rank.items():
        if value == highest:
            return key
    return "normalization"


def _plan_has_review_required(plan: dict[str, Any]) -> bool:
    flags = plan.get("global_flags")
    if isinstance(flags, dict) and bool(flags.get("review_required")):
        return True
    ops = plan.get("ops")
    if isinstance(ops, list):
        for op in ops:
            if isinstance(op, dict) and bool(op.get("review_required")):
                return True
    return False


def _plan_has_no_ops(plan: dict[str, Any]) -> bool:
    ops = plan.get("ops")
    if not isinstance(ops, list):
        return True
    return len([op for op in ops if isinstance(op, dict)]) == 0


def _read_str_from_latest_refs(latest_refs: dict[str, Any], key: str) -> str | None:
    value = latest_refs.get(key)
    if isinstance(value, dict):
        path = value.get("artifact_path")
        return _read_str(path)
    return _read_str(value)


def _emit_transcript_span_seeds(
    *,
    persistence: TranscriptionEditPersistenceService,
    dossier_id: str,
    source_transcript_ref: str,
    source_transcript_hash: str,
) -> str | None:
    transcript_text = load_transcript_text_for_seeds(source_transcript_ref)
    if not transcript_text:
        return None
    artifact = build_transcript_span_seeds_artifact(
        dossier_id=dossier_id,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
        transcript_text=transcript_text,
    )
    if not artifact.seeds:
        return None
    try:
        return persistence.save_transcript_span_seeds(dossier_id=dossier_id, artifact=artifact)
    except Exception:
        # Seeds are advisory only; failure here must not fail the controller loop.
        return None


def _has_blocking_warnings(top_findings: list[dict[str, Any]]) -> bool:
    blocking_types = {"plss_consistency", "call_chain_structure"}
    blocking_ids = {
        "plss_range_conflict_001",
        "plss_township_conflict_001",
        "candidate_disagreement_range_conflict_001",
        "candidate_disagreement_tie_distance_conflict_001",
    }
    for finding in top_findings:
        if not isinstance(finding, dict):
            continue
        severity = str(finding.get("severity") or "").strip().lower()
        if severity != "warning":
            continue
        ftype = str(finding.get("finding_type") or "").strip().lower()
        fid = str(finding.get("finding_id") or "").strip().lower()
        if ftype in blocking_types or fid in blocking_ids:
            return True
    return False


def _fallback_spans_for_findings(
    *,
    source_transcript_ref: str,
    top_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    text = load_transcript_text_for_seeds(source_transcript_ref)
    if not text:
        return []
    spans: list[dict[str, Any]] = []
    text_len = len(text)
    window = 1400

    def _add_window(center: int, span_id: str) -> None:
        start = max(0, center - (window // 2))
        end = min(text_len, start + window)
        if end <= start:
            return
        for existing in spans:
            if int(existing["start_char"]) == start and int(existing["end_char"]) == end:
                return
        spans.append({"start_char": start, "end_char": end, "span_id": span_id})

    _add_window(0, "fallback_head")
    _add_window(text_len, "fallback_tail")

    search_terms: list[tuple[str, str]] = []
    for finding in top_findings[:8]:
        if not isinstance(finding, dict):
            continue
        ftype = str(finding.get("finding_type") or "").strip().lower()
        if ftype == "plss_consistency":
            search_terms.extend([
                ("Range seventy-four (74) West", "finding_plss_r74"),
                ("Range seventy-five (75) West", "finding_plss_r75"),
                ("Township Fourteen (14) North", "finding_plss_t14"),
            ])
        elif ftype == "bearing_parse":
            search_terms.extend([
                ("N. 4°00' W., 1638 feet", "finding_bearing_tie"),
                ("thence N.", "finding_bearing_thence"),
                ("to the point of beginning", "finding_bearing_closure"),
            ])
        elif ftype == "numeric_unit_sanity":
            search_terms.extend([
                ("1.4 acres", "finding_acreage_14"),
                ("1.9 acres", "finding_acreage_19"),
                ("1638 feet", "finding_distance_1638"),
            ])
        message = str(finding.get("message") or "")
        for literal in _extract_numeric_literals(message):
            search_terms.append((literal, f"finding_literal_{literal[:24]}"))

    for term, sid in search_terms:
        idx = text.find(term)
        if idx >= 0:
            _add_window(idx, sid)

    return spans[:8]


def _candidate_disagreement_hints(candidate_texts: list[str]) -> dict[str, Any]:
    if not isinstance(candidate_texts, list) or len(candidate_texts) <= 1:
        return {}
    ranges: dict[str, int] = {}
    acreages: dict[str, int] = {}
    tie_distances: dict[str, int] = {}
    bearings: dict[str, int] = {}
    range_patterns = [
        re.compile(r"\brange[^()]{0,60}\((\d{1,3})\)\s*(west|east)\b", re.IGNORECASE),
        re.compile(r"\br\s*\.?\s*(\d{1,3})\s*([we])\b", re.IGNORECASE),
    ]
    acreage_pattern = re.compile(r"\b(\d+(?:\.\d+)?)\s*acres?\b", re.IGNORECASE)
    distance_pattern = re.compile(r"\b(\d{2,5}(?:\.\d+)?)\s*(?:ft|feet)\b", re.IGNORECASE)
    bearing_pattern = re.compile(r"\b[NS]\.?\s*\d{1,3}(?:\s*°\s*\d{1,2})?\s*(?:[EW]\.?|east|west)\b", re.IGNORECASE)

    def _inc(bucket: dict[str, int], key: str) -> None:
        bucket[key] = bucket.get(key, 0) + 1

    for text in candidate_texts[:10]:
        if not isinstance(text, str):
            continue
        for pat in range_patterns:
            for m in pat.finditer(text):
                number = m.group(1)
                direction = m.group(2).lower()
                direction = "w" if direction.startswith("w") else "e"
                _inc(ranges, f"r{number}{direction}")
        for m in acreage_pattern.finditer(text):
            _inc(acreages, m.group(1))
        for m in distance_pattern.finditer(text):
            _inc(tie_distances, m.group(1))
        for m in bearing_pattern.finditer(text):
            _inc(bearings, re.sub(r"\s+", " ", m.group(0).strip().lower()))

    def _sorted_counts(bucket: dict[str, int]) -> list[dict[str, Any]]:
        return [
            {"value": key, "count": count}
            for key, count in sorted(bucket.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
        ]

    return {
        "candidate_count": len(candidate_texts[:10]),
        "range_values": _sorted_counts(ranges),
        "acreage_values": _sorted_counts(acreages),
        "distance_values": _sorted_counts(tie_distances),
        "bearing_values": _sorted_counts(bearings),
    }


def _extract_numeric_literals(message: str) -> list[str]:
    out: list[str] = []
    if not isinstance(message, str):
        return out
    for token in re.findall(r"\b\d{1,5}(?:\.\d+)?\b", message):
        out.append(token)
    return out[:6]


def _image_checks_from_disagreement_hints(disagreement_hints: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if not isinstance(disagreement_hints, dict):
        return checks
    range_values = disagreement_hints.get("range_values")
    if isinstance(range_values, list) and len(range_values) > 1:
        checks.append(
            {
                "check_id": "image_check_range_tokens",
                "query": (
                    "Read the deed and list all explicit range numbers shown near township/section clauses. "
                    "Include both if more than one appears."
                ),
                "expected_text": None,
            }
        )
    distance_values = disagreement_hints.get("distance_values")
    if isinstance(distance_values, list) and len(distance_values) > 1:
        checks.append(
            {
                "check_id": "image_check_tie_distance",
                "query": (
                    "What is the numeric distance in feet in the clause containing 'Northwest corner bears ... feet distant'? "
                    "Return the exact number."
                ),
                "expected_text": None,
            }
        )
    acreage_values = disagreement_hints.get("acreage_values")
    if isinstance(acreage_values, list) and len(acreage_values) > 1:
        checks.append(
            {
                "check_id": "image_check_acreage",
                "query": (
                    "What acreage value is stated for the first parcel near 'containing ... acres'? "
                    "Return the exact number."
                ),
                "expected_text": None,
            }
        )
    return checks[:4]


def _image_numeric_signals(image_verification: dict[str, Any]) -> dict[str, str | None]:
    out: dict[str, str | None] = {
        "tie_distance": None,
        "tie_distance_strength": None,
        "acreage": None,
        "acreage_strength": None,
    }
    if not isinstance(image_verification, dict):
        return out
    raw_results = image_verification.get("results")
    if not isinstance(raw_results, list):
        return out
    for item in raw_results[:12]:
        if not isinstance(item, dict):
            continue
        check_id = str(item.get("check_id") or "").strip().lower()
        confidence = str(item.get("confidence") or "").strip().lower()
        observed = str(item.get("observed_text") or "")
        numbers = re.findall(r"\b\d{1,5}(?:\.\d+)?\b", observed)
        if check_id == "image_check_tie_distance" and confidence == "high":
            numeric = _first_numeric_like(numbers, minimum=500.0)
            if numeric:
                out["tie_distance"] = numeric
                out["tie_distance_strength"] = confidence
        if check_id == "image_check_acreage" and confidence in {"medium", "high"}:
            numeric = _first_numeric_like(numbers, minimum=0.1, maximum=1000.0)
            if numeric:
                out["acreage"] = numeric
                out["acreage_strength"] = confidence
    return out


def _first_numeric_like(
    values: list[str],
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> str | None:
    for raw in values:
        try:
            value = float(raw)
        except Exception:
            continue
        if minimum is not None and value < minimum:
            continue
        if maximum is not None and value > maximum:
            continue
        return raw
    return None


def _first_expected_token_from_message(message: str) -> str | None:
    if not isinstance(message, str):
        return None
    token_match = re.search(r"'([^']{1,80})'", message)
    if token_match:
        return token_match.group(1)
    number_match = re.search(r"\b\d{1,5}(?:\.\d+)?\b", message)
    if number_match:
        return number_match.group(0)
    return None


def _vision_verify_model(preferred: str) -> str:
    normalized = str(preferred or "").strip().lower()
    if normalized in {"gpt-o4-mini", "gpt-4o", "o3"}:
        return normalized
    return "gpt-o4-mini"


def _prioritized_findings_for_planning(*, top_findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(top_findings, list):
        return []
    rank = {
        "plss_consistency": 0,
        "call_chain_structure": 1,
        "bearing_parse": 2,
        "numeric_unit_sanity": 3,
    }
    normalized: list[dict[str, Any]] = [finding for finding in top_findings if isinstance(finding, dict)]
    normalized.sort(key=lambda finding: rank.get(str(finding.get("finding_type") or "").strip().lower(), 9))
    return normalized[:12]


def _viewer_run_id_from_request_prefix(request_id_prefix: str) -> str:
    value = str(request_id_prefix or "").strip()
    if value.startswith("tx-agent-"):
        return value[len("tx-agent-") :]
    return value


def _build_human_feedback_prompt(
    *,
    disagreement_hints: dict[str, Any],
    top_findings: list[dict[str, Any]],
    iteration: int,
) -> dict[str, Any] | None:
    if not isinstance(disagreement_hints, dict):
        return None
    range_values = disagreement_hints.get("range_values")
    if not (isinstance(range_values, list) and len(range_values) > 1):
        return None
    options: list[str] = []
    for item in range_values[:4]:
        if not isinstance(item, dict):
            continue
        token = str(item.get("value") or "").strip().lower()
        m = re.match(r"r(\d{1,3})([we])$", token)
        if not m:
            continue
        num = m.group(1)
        direction = "West" if m.group(2) == "w" else "East"
        options.append(f"Range {num} {direction}")
    options = [opt for opt in options if opt]
    if len(options) < 2:
        return None
    top_message = ""
    for finding in top_findings:
        if not isinstance(finding, dict):
            continue
        msg = str(finding.get("message") or "").strip()
        if msg:
            top_message = msg[:180]
            break
    return {
        "prompt_id": f"hitl_range_{iteration}_{uuid4().hex[:8]}",
        "line1": "Confirm range token for this deed",
        "line2": "Image/text checks disagree on range values; promotion is blocked pending your choice.",
        "choices": options[:4],
        "default_choice": options[0],
        "context": {"top_finding": top_message, "range_values": range_values[:4]},
    }


def _wait_for_feedback_response(
    *,
    run_id: str,
    prompt_id: str,
    timeout_seconds: int,
    poll_interval_seconds: int,
) -> dict[str, Any] | None:
    deadline = time.time() + max(1, int(timeout_seconds))
    while time.time() < deadline:
        entry = feedback_store.first_matching_prompt_entry(
            loop_kind="transcript_edit",
            run_id=run_id,
            prompt_id=prompt_id,
        )
        if isinstance(entry, dict):
            return entry
        time.sleep(max(1, int(poll_interval_seconds)))
    return None


def _range_number_from_feedback(feedback_entry: dict[str, Any]) -> int | None:
    if not isinstance(feedback_entry, dict):
        return None
    choice = str(feedback_entry.get("choice") or "").strip()
    note = str(feedback_entry.get("note") or "").strip()
    for text in (choice, note):
        m = re.search(r"\b(\d{1,3})\b", text)
        if not m:
            continue
        try:
            num = int(m.group(1))
        except Exception:
            continue
        if 1 <= num <= 200:
            return num
    return None


def _build_range_feedback_plan(
    *,
    source_transcript_ref: str,
    source_transcript_hash: str,
    selected_number: int,
) -> dict[str, Any] | None:
    text = load_transcript_text_for_seeds(source_transcript_ref)
    if not text:
        return None
    ops: list[dict[str, Any]] = []
    pattern = re.compile(r"\bRange\b[^()\n]{0,80}\((\d{1,3})\)\s*(West|East)\b", re.IGNORECASE)
    for idx, m in enumerate(pattern.finditer(text)):
        current = m.group(1)
        direction = m.group(2)
        try:
            current_num = int(current)
        except Exception:
            continue
        if current_num == selected_number:
            continue
        ops.append(
            {
                "op_id": f"hitl-range-{idx+1}",
                "op_type": "replace_span",
                "change_class": "semantic",
                "confidence": "medium",
                "review_required": True,
                "reason": "Human selected range token to resolve blocking conflict.",
                "evidence_refs": [],
                "target": {
                    "locator_type": "offsets",
                    "start_char": int(m.start(1)),
                    "end_char": int(m.end(1)),
                },
                "expected_old": {"old_excerpt": str(current)},
                "new_text": str(selected_number),
            }
        )
        if len(ops) >= 2:
            break
    if not ops:
        return None
    return {
        "plan_version": "edit_plan_v0",
        "source_transcript_ref": source_transcript_ref,
        "source_transcript_hash": source_transcript_hash,
        "plan_id": f"hitl-range-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "summary": "Apply human-selected range token to resolve blocking conflict.",
        "ops": ops,
        "global_flags": {
            "review_required": True,
            "rationale": "Human-guided semantic correction.",
        },
    }


def _mapping_priority_focus(disagreement_hints: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(disagreement_hints, dict):
        return {}
    return {
        "mapping_critical_fields": [
            "plss",
            "tie_to_corner_distance",
            "bearings",
            "call_chain_closure",
            "acreage",
        ],
        "disagreement_snapshot": {
            "range_values": disagreement_hints.get("range_values") or [],
            "distance_values": disagreement_hints.get("distance_values") or [],
            "bearing_values": disagreement_hints.get("bearing_values") or [],
            "acreage_values": disagreement_hints.get("acreage_values") or [],
        },
    }


def _critical_disagreement_findings(disagreement_hints: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not isinstance(disagreement_hints, dict):
        return findings
    ranges = disagreement_hints.get("range_values")
    if isinstance(ranges, list) and len(ranges) > 1:
        values = [str(item.get("value")) for item in ranges[:4] if isinstance(item, dict) and item.get("value")]
        if values:
            findings.append(
                {
                    "finding_id": "candidate_disagreement_range_conflict_001",
                    "finding_type": "plss_consistency",
                    "severity": "warning",
                    "message": f"Redundancy drafts disagree on range tokens: {', '.join(values)}",
                    "section_id": None,
                    "span": None,
                }
            )

    distances = disagreement_hints.get("distance_values")
    if isinstance(distances, list) and len(distances) > 1:
        critical = [item for item in distances[:6] if isinstance(item, dict) and _is_critical_tie_distance(item.get("value"))]
        if len(critical) > 1:
            values = [str(item.get("value")) for item in critical[:4] if item.get("value")]
            findings.append(
                {
                    "finding_id": "candidate_disagreement_tie_distance_conflict_001",
                    "finding_type": "numeric_unit_sanity",
                    "severity": "warning",
                    "message": f"Redundancy drafts disagree on tie distances: {', '.join(values)}",
                    "section_id": None,
                    "span": None,
                }
            )
    return findings


def _build_deterministic_consensus_plan(
    *,
    source_transcript_ref: str,
    source_transcript_hash: str,
    disagreement_hints: dict[str, Any],
    image_verification: dict[str, Any],
    top_findings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(disagreement_hints, dict):
        return None
    if not isinstance(top_findings, list):
        return None
    text = load_transcript_text_for_seeds(source_transcript_ref)
    if not text:
        return None

    has_plss_conflict = any(
        isinstance(f, dict)
        and str(f.get("finding_type") or "").strip().lower() == "plss_consistency"
        for f in top_findings
    )
    if has_plss_conflict:
        # PLSS conflicts are too semantic/ambiguous for deterministic auto-correction.
        return None

    image_numeric = _image_numeric_signals(image_verification)
    ops: list[dict[str, Any]] = []
    distance_op = _deterministic_numeric_replace_op(
        text=text,
        bucket=disagreement_hints.get("distance_values"),
        value_regex=r"\b(\d{3,5}(?:\.\d+)?)\s*(feet|ft)\b",
        value_guard=_is_critical_tie_distance,
        op_id="auto-distance-1",
        reason="Image-guided consensus indicates a likely OCR error in mapping-critical tie distance.",
        preferred_value=image_numeric.get("tie_distance"),
        preferred_strength=image_numeric.get("tie_distance_strength"),
    )
    if distance_op:
        ops.append(distance_op)

    acreage_op = _deterministic_numeric_replace_op(
        text=text,
        bucket=disagreement_hints.get("acreage_values"),
        value_regex=r"\b(\d+(?:\.\d+)?)\s*(acres?)\b",
        value_guard=lambda _: True,
        op_id="auto-acreage-1",
        reason="Image-guided consensus indicates a likely OCR error in acreage value.",
        preferred_value=image_numeric.get("acreage"),
        preferred_strength=image_numeric.get("acreage_strength"),
    )
    if acreage_op:
        ops.append(acreage_op)

    if not ops:
        return None
    plan = {
        "plan_version": "edit_plan_v0",
        "source_transcript_ref": source_transcript_ref,
        "source_transcript_hash": source_transcript_hash,
        "plan_id": f"det-consensus-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "summary": "Deterministic redundancy-consensus correction for mapping-critical numeric fields.",
        "ops": ops[:3],
        "global_flags": {
            "review_required": True,
            "rationale": "Auto-applied from redundancy consensus; semantic review is required before promotion.",
        },
    }
    return plan


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
    dominant_value: str | None = None
    if preferred_value and preferred_strength == "high":
        dominant_value = str(preferred_value)
    else:
        winner = _dominant_bucket_value(bucket)
        if winner is None:
            return None
        dominant_value, dominant_count, total = winner
        if total < 3 or dominant_count < max(2, total - 1):
            return None
    if dominant_value is None:
        return None
    if not value_guard(dominant_value):
        return None
    pattern = re.compile(value_regex, re.IGNORECASE)
    for match in pattern.finditer(text):
        current_value = str(match.group(1))
        unit = str(match.group(2))
        if current_value == dominant_value:
            continue
        old_excerpt = match.group(0)
        new_excerpt = f"{dominant_value} {unit}"
        return {
            "op_id": op_id,
            "op_type": "replace_span",
            "change_class": "semantic",
            "confidence": "medium",
            "review_required": True,
            "reason": reason,
            "evidence_refs": [],
            "target": {
                "locator_type": "offsets",
                "start_char": int(match.start()),
                "end_char": int(match.end()),
            },
            "expected_old": {"old_excerpt": old_excerpt},
            "new_text": new_excerpt,
        }
    return None


def _dominant_bucket_value(bucket: Any) -> tuple[str, int, int] | None:
    if not isinstance(bucket, list):
        return None
    parsed: list[tuple[str, int]] = []
    for item in bucket[:8]:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        count = item.get("count")
        if value is None:
            continue
        try:
            count_i = int(count)
        except Exception:
            continue
        parsed.append((str(value), count_i))
    if len(parsed) < 2:
        return None
    total = sum(max(0, c) for _, c in parsed)
    parsed.sort(key=lambda kv: (-kv[1], kv[0]))
    return parsed[0][0], parsed[0][1], total


def _merge_findings_summary_with_disagreement(
    *,
    findings_summary: dict[str, Any],
    disagreement_findings: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = dict(findings_summary) if isinstance(findings_summary, dict) else {}
    total = int(summary.get("total") or 0)
    warnings = int(summary.get("warnings") or 0)
    errors = int(summary.get("errors") or 0)
    infos = int(summary.get("infos") or 0)
    for finding in disagreement_findings:
        severity = str(finding.get("severity") or "").strip().lower()
        total += 1
        if severity == "warning":
            warnings += 1
        elif severity == "error":
            errors += 1
        elif severity == "info":
            infos += 1
    summary["total"] = total
    summary["warnings"] = warnings
    summary["errors"] = errors
    summary["infos"] = infos
    return summary


def _is_critical_tie_distance(value: Any) -> bool:
    try:
        number = float(str(value))
    except Exception:
        return False
    return number >= 900.0
