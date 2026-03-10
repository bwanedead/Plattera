from __future__ import annotations

from typing import Any

_RESOLVER_RAW_OUTPUT_EXCERPT_MAX_CHARS = 4000


def _base_payload(
    *,
    iteration: int,
    phase: str,
    message: str,
    latest_refs: dict[str, Any],
    execution_state: str | None = None,
    stream_kind: str = "narration",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "iteration": iteration,
        "phase": phase,
        "message": message,
        "latest_refs": latest_refs,
        "stream_kind": stream_kind,
    }
    if execution_state is not None:
        payload["execution_state"] = execution_state
    return payload


def starting_payload(
    *,
    mode: str,
    candidate_count: int,
    latest_refs: dict[str, Any],
) -> dict[str, Any]:
    return _base_payload(
        iteration=0,
        phase="starting",
        message=(
            f"Starting transcript edit loop ({mode.replace('_', ' ')}). "
            f"{'Loaded ' + str(candidate_count) + ' T0 draft candidate(s). ' if candidate_count > 0 else ''}"
            "Preparing canonical transcript and semantic baseline."
        ),
        latest_refs=latest_refs,
        execution_state="starting",
    )


def preflight_countdown_payload(
    *,
    remaining_seconds: int,
    latest_refs: dict[str, Any],
) -> dict[str, Any]:
    return _base_payload(
        iteration=0,
        phase="preflight_countdown",
        message=f"Preflight countdown: {remaining_seconds}s remaining before transcript-edit API work begins.",
        latest_refs=latest_refs,
        execution_state="waiting",
        stream_kind="ticker",
    )


def ticker_payload(
    *,
    iteration: int,
    phase: str,
    message: str,
    latest_refs: dict[str, Any],
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _base_payload(
        iteration=iteration,
        phase=phase,
        message=message,
        latest_refs=latest_refs,
        execution_state="running",
        stream_kind="ticker",
    )
    if isinstance(detail, dict) and detail:
        payload["detail"] = detail
    return payload


def audit_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    execution_state: str,
) -> dict[str, Any]:
    return _base_payload(
        iteration=iteration,
        phase="audit",
        message=f"Auditing transcript for deterministic errors and mapping-critical issues (iteration {iteration}).",
        latest_refs=latest_refs,
        execution_state=execution_state,
    )


def audit_result_payload(
    *,
    iteration: int,
    finding_count: int,
    error_count: int,
    warning_count: int,
    top_findings_display: list[dict[str, Any]],
    summary_text: str,
    latest_refs: dict[str, Any],
    execution_state: str,
    decision_ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        **_base_payload(
            iteration=iteration,
            phase="audit_result",
            message=(
            f"Found {finding_count} issues ({error_count} errors, {warning_count} warnings)."
            if finding_count > 0
            else "Transcript is clean — no issues found."
            ),
            latest_refs=latest_refs,
            execution_state=execution_state,
        ),
        "detail": {
            "finding_count": finding_count,
            "error_count": error_count,
            "warning_count": warning_count,
            "top_findings": top_findings_display,
            "summary_text": summary_text,
            "decision_ledger": decision_ledger,
        },
    }


def final_verify_retry_payload(*, iteration: int, latest_refs: dict[str, Any]) -> dict[str, Any]:
    return _base_payload(
        iteration=iteration,
        phase="final_verify_retry",
        message="Final image verification found unresolved map-critical uncertainty; re-checking before terminal decision.",
        latest_refs=latest_refs,
        execution_state="retrying",
    )


def stabilize_payload(
    *,
    iteration: int,
    min_iterations_before_complete: int,
    latest_refs: dict[str, Any],
) -> dict[str, Any]:
    return _base_payload(
        iteration=iteration,
        phase="stabilize",
        message=f"Clean audit achieved; running additional stabilization pass ({iteration}/{min_iterations_before_complete}) before terminalizing.",
        latest_refs=latest_refs,
        execution_state="running",
    )


def promote_payload(*, iteration: int, latest_refs: dict[str, Any]) -> dict[str, Any]:
    return _base_payload(
        iteration=iteration,
        phase="promote",
        message="Next, I will run a final image sanity check before promotion.",
        latest_refs=latest_refs,
        execution_state="running",
    )


def human_feedback_reused_payload(
    *,
    iteration: int,
    decision_key: str,
    selected_value: str,
    latest_refs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_type": "human_feedback",
        **_base_payload(
            iteration=iteration,
            phase="human_feedback_reused",
            message=f"Reusing prior human {decision_key} decision ({selected_value}) to continue safely.",
            latest_refs=latest_refs,
            execution_state="received",
        ),
    }


def human_feedback_needed_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    feedback_prompt: dict[str, Any],
    blocking: bool = False,
    evidence_attempts: dict[str, int] | None = None,
) -> dict[str, Any]:
    attempts = evidence_attempts or {}
    return {
        "event_type": "human_feedback_needed",
        **_base_payload(
            iteration=iteration,
            phase="human_feedback_needed",
            message=feedback_prompt.get("line1"),
            latest_refs=latest_refs,
            execution_state="waiting",
        ),
        "prompt_id": feedback_prompt.get("prompt_id"),
        "blocking": blocking,
        "choices": feedback_prompt.get("choices", []),
        "default_choice": feedback_prompt.get("default_choice"),
        "context": feedback_prompt.get("context", {}),
        "evidence_attempts": {
            "open_spans_count": int(attempts.get("open_spans_count", 0)),
            "image_verify_count": int(attempts.get("image_verify_count", 0)),
            "retrieval_count": int(attempts.get("retrieval_count", 0)),
        },
    }


def human_feedback_received_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    prompt_id: str | None,
    feedback_entry: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_type": "human_feedback",
        **_base_payload(
            iteration=iteration,
            phase="human_feedback_received",
            message="Human feedback received for blocking ambiguity.",
            latest_refs=latest_refs,
            execution_state="received",
        ),
        "prompt_id": prompt_id,
        "feedback": feedback_entry,
    }


def human_feedback_consumed_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    prompt_id: str | None,
    decision_key: str | None,
    selected_value: str | None,
) -> dict[str, Any]:
    value = str(selected_value or "").strip()
    return {
        "event_type": "human_feedback",
        **_base_payload(
            iteration=iteration,
            phase="human_feedback_consumed",
            message=(
                f"Consumed human feedback for {decision_key or 'decision'}"
                + (f": {value}" if value else ".")
            ),
            latest_refs=latest_refs,
            execution_state="received",
        ),
        "prompt_id": prompt_id,
        "decision_key": decision_key,
        "selected_value": selected_value,
    }


def human_resolution_ticket_state_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    ticket_id: str | None,
    decision_key: str | None,
    lifecycle_state: str,
    strength: str | None = None,
    relevance: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    normalized_state = str(lifecycle_state or "").strip().lower() or "unknown"
    return {
        "event_type": "human_resolution_ticket",
        **_base_payload(
            iteration=iteration,
            phase=f"ticket_{normalized_state}",
            message=(
                f"Human-resolution ticket state: {decision_key or 'decision'} -> {normalized_state}."
            ),
            latest_refs=latest_refs,
            execution_state="running",
        ),
        "ticket_id": ticket_id,
        "decision_key": decision_key,
        "lifecycle_state": normalized_state,
        "strength": strength,
        "relevance": relevance,
        "reason": reason,
    }


def human_feedback_stale_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    prompt_id: str | None,
    active_prompt_id: str | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "event_type": "human_feedback",
        **_base_payload(
            iteration=iteration,
            phase="human_feedback_stale",
            message="Feedback received for a stale/superseded prompt and was not consumed.",
            latest_refs=latest_refs,
            execution_state="received",
        ),
        "prompt_id": prompt_id,
        "active_prompt_id": active_prompt_id,
        "reason": reason,
    }


def human_feedback_prompt_superseded_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    superseded_prompt_id: str,
    replacement_prompt_id: str | None,
    decision_key: str | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "event_type": "human_feedback_needed",
        **_base_payload(
            iteration=iteration,
            phase="human_feedback_prompt_superseded",
            message="Superseded pending human-feedback prompt with a newer authoritative prompt.",
            latest_refs=latest_refs,
            execution_state="running",
        ),
        "prompt_id": superseded_prompt_id,
        "replacement_prompt_id": replacement_prompt_id,
        "decision_key": decision_key,
        "reason": reason,
    }


def resolver_invalid_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    reason: str,
    invalid_plan_strikes: int,
    max_invalid_plan_attempts: int,
    exhausted: bool,
    decision_key: str | None = None,
    post_feedback_ticket_state: str | None = None,
    post_feedback_ticket_id: str | None = None,
    validation_error_class: str | None = None,
    raw_output_excerpt: str | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "reason": reason,
        "invalid_plan_strikes": int(invalid_plan_strikes),
        "max_invalid_plan_attempts": int(max_invalid_plan_attempts),
        "exhausted": bool(exhausted),
        "decision_key": decision_key,
        "post_feedback_ticket_state": post_feedback_ticket_state,
        "post_feedback_ticket_id": post_feedback_ticket_id,
        "validation_error_class": validation_error_class,
    }
    excerpt = str(raw_output_excerpt or "").strip()
    if excerpt:
        detail["raw_output_excerpt"] = excerpt[:_RESOLVER_RAW_OUTPUT_EXCERPT_MAX_CHARS]
    return {
        "event_type": "resolver_invalid",
        **_base_payload(
            iteration=iteration,
            phase="resolver_invalid",
            message=(
                "Resolver produced an invalid move payload; retrying."
                if not exhausted
                else "Resolver produced invalid payload repeatedly; retry budget exhausted."
            ),
            latest_refs=latest_refs,
            execution_state="retrying" if not exhausted else "failed",
        ),
        "detail": detail,
    }


def resolver_attempt_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    decision_key: str,
    resolver_attempt_number: int,
    is_repair_attempt: bool,
    ticket_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "event_type": "resolver_attempt",
        **_base_payload(
            iteration=iteration,
            phase="resolver_attempt",
            message=f"Resolver attempt {resolver_attempt_number} for {decision_key}.",
            latest_refs=latest_refs,
            execution_state="running",
        ),
        "detail": {
            "decision_key": decision_key,
            "resolver_attempt_number": int(resolver_attempt_number),
            "is_repair_attempt": bool(is_repair_attempt),
            "ticket_snapshot": dict(ticket_snapshot) if isinstance(ticket_snapshot, dict) else None,
        },
    }


def resolver_outcome_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    decision_key: str,
    move: str | None,
    result_category: str,
    reason: str | None,
    resolver_attempt_number: int,
    is_repair_attempt: bool,
    ticket_snapshot: dict[str, Any] | None = None,
    validation_error_class: str | None = None,
    raw_output_excerpt: str | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "decision_key": decision_key,
        "move": move,
        "result_category": result_category,
        "reason": reason,
        "resolver_attempt_number": int(resolver_attempt_number),
        "is_repair_attempt": bool(is_repair_attempt),
        "ticket_snapshot": dict(ticket_snapshot) if isinstance(ticket_snapshot, dict) else None,
        "validation_error_class": validation_error_class,
    }
    excerpt = str(raw_output_excerpt or "").strip()
    if excerpt:
        detail["raw_output_excerpt"] = excerpt[:_RESOLVER_RAW_OUTPUT_EXCERPT_MAX_CHARS]
    return {
        "event_type": "resolver_outcome",
        **_base_payload(
            iteration=iteration,
            phase="resolver_outcome",
            message=f"Resolver outcome for {decision_key}: {result_category}.",
            latest_refs=latest_refs,
            execution_state="running",
        ),
        "detail": detail,
    }


def resolver_move_gate_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    decision_key: str,
    move: str,
    gate_outcome: str,
    gate_reason: str,
    ticket_snapshot: dict[str, Any] | None = None,
    normalize_reason: str | None = None,
    evidence_request_kind: str | None = None,
    evidence_request_mode: str | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "decision_key": decision_key,
        "move": move,
        "gate_outcome": gate_outcome,
        "gate_reason": gate_reason,
        "ticket_snapshot": dict(ticket_snapshot) if isinstance(ticket_snapshot, dict) else None,
    }
    if str(normalize_reason or "").strip():
        detail["normalize_reason"] = str(normalize_reason or "").strip()
    if str(evidence_request_kind or "").strip():
        detail["evidence_request_kind"] = str(evidence_request_kind or "").strip().lower()
    if str(evidence_request_mode or "").strip():
        detail["evidence_request_mode"] = str(evidence_request_mode or "").strip().lower()
    return {
        "event_type": "resolver_move_gate",
        **_base_payload(
            iteration=iteration,
            phase="resolver_move_gate",
            message=f"Runtime move gate for {decision_key}: {gate_outcome} ({gate_reason}).",
            latest_refs=latest_refs,
            execution_state="running",
        ),
        "detail": detail,
    }


def open_spans_payload(*, iteration: int, latest_refs: dict[str, Any]) -> dict[str, Any]:
    return _base_payload(
        iteration=iteration,
        phase="open_spans",
        message="Opening localized transcript spans around flagged areas for detailed inspection.",
        latest_refs=latest_refs,
        execution_state="running",
    )


def investigation_baseline_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    conflict_map: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        **_base_payload(
            iteration=iteration,
            phase="investigation_baseline",
            message="Running baseline investigation to self-reconcile cross-draft conflicts before any HITL escalation.",
            latest_refs=latest_refs,
            execution_state="running",
        ),
        "detail": {
            "conflict_count": len(conflict_map),
            "conflict_map": conflict_map,
        },
    }


def investigation_baseline_result_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    evidence_attempts: list[dict[str, Any]],
    residual_blockers: list[dict[str, Any]],
    mapping_blocking_count: int,
    optional_count: int,
    next_recommended_action: str,
    decision_ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        **_base_payload(
            iteration=iteration,
            phase="investigation_baseline_result",
            message=(
                "Baseline investigation complete. "
                f"Residual blockers: {len(residual_blockers)} "
                f"({mapping_blocking_count} mapping-blocking, {optional_count} optional)."
            ),
            latest_refs=latest_refs,
            execution_state="running",
        ),
        "detail": {
            "evidence_attempts": evidence_attempts,
            "residual_blockers": residual_blockers,
            "mapping_blocking_count": mapping_blocking_count,
            "optional_count": optional_count,
            "next_recommended_action": next_recommended_action,
            "decision_ledger": decision_ledger,
        },
    }


def open_spans_result_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    spans_display: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        **_base_payload(
            iteration=iteration,
            phase="open_spans_result",
            message=f"Opened {len(spans_display)} text spans for context.",
            latest_refs=latest_refs,
        ),
        "detail": {
            "span_count": len(spans_display),
            "spans": spans_display,
        },
    }


def image_verify_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    message: str,
    decision_key: str | None = None,
    evidence_kind: str = "image_verify",
) -> dict[str, Any]:
    payload = _base_payload(
        iteration=iteration,
        phase="image_verify",
        message=message,
        latest_refs=latest_refs,
        execution_state="running",
    )
    payload["detail"] = {
        "decision_key": decision_key,
        "evidence_kind": evidence_kind,
    }
    return payload


def image_verify_progress_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    decision_key: str | None,
    evidence_kind: str,
    check_id: str,
    check_decision_key: str | None,
    llm_call_seq: int,
    phase_attempt: int,
    stage: str,
    elapsed_seconds: int | None = None,
    wait_reason: str | None = None,
    phase_started_at_epoch_seconds: int | None = None,
    timeout_seconds: int | None = None,
    max_attempts_per_check: int | None = None,
    check_index: int | None = None,
    check_total: int | None = None,
    diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if stage == "running":
        message = f"Image check started ({check_id})."
    elif stage == "completed":
        message = f"Image check completed ({check_id})."
    elif stage == "retrying":
        message = f"Image check retrying ({check_id}), attempt {phase_attempt}."
    elif stage == "timeout":
        message = f"Image check timed out ({check_id}) after {int(elapsed_seconds or 0)}s."
    elif stage == "failed":
        message = f"Image check failed ({check_id})."
    elif stage == "long_running":
        message = f"Image check long-running ({check_id}) at {int(elapsed_seconds or 0)}s."
    else:
        message = f"Image check waiting ({check_id}) at {int(elapsed_seconds or 0)}s."
    payload = _base_payload(
        iteration=iteration,
        phase="image_verify",
        message=message,
        latest_refs=latest_refs,
        execution_state="running",
        stream_kind="ticker",
    )
    payload["detail"] = {
        "decision_key": decision_key,
        "evidence_kind": evidence_kind,
        "check_id": check_id,
        "check_decision_key": check_decision_key,
        "focus_coherent": (
            bool(decision_key and check_decision_key)
            and str(decision_key).strip().lower() == str(check_decision_key).strip().lower()
        ) if decision_key and check_decision_key else None,
        "llm_call_seq": int(llm_call_seq),
        "phase_attempt": int(phase_attempt),
        "stage": stage,
        "elapsed_seconds": int(elapsed_seconds or 0),
        "wait_reason": str(wait_reason or "").strip().lower() or None,
        "phase_started_at_epoch_seconds": int(phase_started_at_epoch_seconds or 0) or None,
        "timeout_seconds": int(timeout_seconds or 0) or None,
        "max_attempts_per_check": int(max_attempts_per_check or 0) or None,
        "check_index": int(check_index or 0) or None,
        "check_total": int(check_total or 0) or None,
    }
    if isinstance(diagnostic, dict) and diagnostic:
        payload["detail"]["diagnostic"] = diagnostic
    return payload


def image_verify_result_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    iv_payload: dict[str, Any],
    iv_results: list[dict[str, Any]],
    iv_confirmed: int,
    iv_rejected: int,
    iv_total: int,
    decision_ledger: dict[str, Any] | None = None,
    decision_key: str | None = None,
    evidence_kind: str = "image_verify",
    llm_call_seq_end: int | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evidence_regions = (
        iv_payload.get("image_evidence_regions")
        if isinstance(iv_payload, dict) and isinstance(iv_payload.get("image_evidence_regions"), list)
        else []
    )
    return {
        **_base_payload(
            iteration=iteration,
            phase="image_verify_result",
            message=f"Image check: {iv_confirmed} confirmed, {iv_rejected} rejected out of {iv_total} checks.",
            latest_refs=latest_refs,
        ),
        "image_verification": iv_payload,
        "detail": {
            "confirmed": iv_confirmed,
            "rejected": iv_rejected,
            "total": iv_total,
            "results": iv_results,
            "decision_key": decision_key,
            "evidence_kind": evidence_kind,
            "llm_call_seq_end": llm_call_seq_end,
            "diagnostics": [d for d in list(diagnostics or []) if isinstance(d, dict)][:8],
            "image_evidence_regions": [item for item in evidence_regions if isinstance(item, dict)][:8],
            "decision_ledger": decision_ledger,
        },
    }


def plan_payload(*, iteration: int, latest_refs: dict[str, Any]) -> dict[str, Any]:
    return _base_payload(
        iteration=iteration,
        phase="plan",
        message="Building a drift-safe edit plan from verified findings and image evidence.",
        latest_refs=latest_refs,
        execution_state="running",
    )


def plan_result_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    plan_reason: str,
    op_count: int,
    ops_preview: list[dict[str, Any]],
    ticket_lifecycle_snapshot: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    snapshot = [dict(row) for row in list(ticket_lifecycle_snapshot or []) if isinstance(row, dict)][:6]
    return {
        **_base_payload(
            iteration=iteration,
            phase="plan_result",
            message=f"Edit plan ready ({plan_reason}): {op_count} operations proposed.",
            latest_refs=latest_refs,
            execution_state="running",
        ),
        "detail": {
            "plan_reason": plan_reason,
            "op_count": op_count,
            "ops_preview": ops_preview,
            "ticket_lifecycle_snapshot": snapshot,
        },
    }


def apply_result_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    execution_state: str,
    plan_op_count: int,
    ops_display: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        **_base_payload(
            iteration=iteration,
            phase="apply_result",
            message=f"Applied {plan_op_count} edits. Re-auditing transcript.",
            latest_refs=latest_refs,
            execution_state=execution_state,
        ),
        "detail": {
            "plan_op_count": plan_op_count,
            "ops": ops_display,
        },
    }
