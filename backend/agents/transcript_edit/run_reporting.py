from __future__ import annotations

from typing import Any


def starting_payload(
    *,
    mode: str,
    candidate_count: int,
    has_disagreements: bool,
    latest_refs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "iteration": 0,
        "phase": "starting",
        "message": (
            f"Starting transcript edit loop ({mode.replace('_', ' ')}). "
            f"{'Analyzing ' + str(candidate_count) + ' draft(s) for consistency. ' if candidate_count > 1 else ''}"
            f"{'Disagreements detected between drafts — will investigate.' if has_disagreements else 'Auditing transcript for errors and mapping-critical issues.'}"
        ),
        "latest_refs": latest_refs,
        "execution_state": "starting",
    }


def audit_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    execution_state: str,
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "phase": "audit",
        "message": f"Auditing transcript for deterministic errors and mapping-critical issues (iteration {iteration}).",
        "latest_refs": latest_refs,
        "execution_state": execution_state,
    }


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
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "phase": "audit_result",
        "message": (
            f"Found {finding_count} issues ({error_count} errors, {warning_count} warnings)."
            if finding_count > 0
            else "Transcript is clean — no issues found."
        ),
        "latest_refs": latest_refs,
        "execution_state": execution_state,
        "detail": {
            "finding_count": finding_count,
            "error_count": error_count,
            "warning_count": warning_count,
            "top_findings": top_findings_display,
            "summary_text": summary_text,
        },
    }


def final_verify_retry_payload(*, iteration: int, latest_refs: dict[str, Any]) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "phase": "final_verify_retry",
        "message": "Final image verification found unresolved map-critical uncertainty; re-checking before terminal decision.",
        "latest_refs": latest_refs,
        "execution_state": "retrying",
    }


def stabilize_payload(
    *,
    iteration: int,
    min_iterations_before_complete: int,
    latest_refs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "phase": "stabilize",
        "message": f"Clean audit achieved; running additional stabilization pass ({iteration}/{min_iterations_before_complete}) before terminalizing.",
        "latest_refs": latest_refs,
        "execution_state": "running",
    }


def promote_payload(*, iteration: int, latest_refs: dict[str, Any]) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "phase": "promote",
        "message": "Next, I will run a final image sanity check before promotion.",
        "latest_refs": latest_refs,
        "execution_state": "running",
    }


def human_feedback_reused_payload(
    *,
    iteration: int,
    sticky_range_selection: int,
    latest_refs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_type": "human_feedback",
        "iteration": iteration,
        "phase": "human_feedback_reused",
        "message": f"Reusing prior human range decision ({sticky_range_selection}) to continue safely.",
        "execution_state": "received",
        "latest_refs": latest_refs,
    }


def human_feedback_needed_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    feedback_prompt: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_type": "human_feedback_needed",
        "iteration": iteration,
        "phase": "human_feedback_needed",
        "message": feedback_prompt.get("line1"),
        "execution_state": "waiting",
        "latest_refs": latest_refs,
        "prompt_id": feedback_prompt.get("prompt_id"),
        "blocking": True,
        "choices": feedback_prompt.get("choices", []),
        "default_choice": feedback_prompt.get("default_choice"),
        "context": feedback_prompt.get("context", {}),
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
        "iteration": iteration,
        "phase": "human_feedback_received",
        "message": "Human feedback received for blocking ambiguity.",
        "execution_state": "received",
        "latest_refs": latest_refs,
        "prompt_id": prompt_id,
        "feedback": feedback_entry,
    }


def open_spans_payload(*, iteration: int, latest_refs: dict[str, Any]) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "phase": "open_spans",
        "message": "Opening localized transcript spans around flagged areas for detailed inspection.",
        "latest_refs": latest_refs,
        "execution_state": "running",
    }


def open_spans_result_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    spans_display: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "phase": "open_spans_result",
        "message": f"Opened {len(spans_display)} text spans for context.",
        "latest_refs": latest_refs,
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
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "phase": "image_verify",
        "message": message,
        "latest_refs": latest_refs,
        "execution_state": "running",
    }


def image_verify_result_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    iv_payload: dict[str, Any],
    iv_results: list[dict[str, Any]],
    iv_confirmed: int,
    iv_rejected: int,
    iv_total: int,
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "phase": "image_verify_result",
        "message": f"Image check: {iv_confirmed} confirmed, {iv_rejected} rejected out of {iv_total} checks.",
        "latest_refs": latest_refs,
        "image_verification": iv_payload,
        "detail": {
            "confirmed": iv_confirmed,
            "rejected": iv_rejected,
            "total": iv_total,
            "results": iv_results,
        },
    }


def plan_payload(*, iteration: int, latest_refs: dict[str, Any]) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "phase": "plan",
        "message": "Building a drift-safe edit plan from verified findings and image evidence.",
        "latest_refs": latest_refs,
        "execution_state": "running",
    }


def plan_result_payload(
    *,
    iteration: int,
    latest_refs: dict[str, Any],
    plan_reason: str,
    op_count: int,
    ops_preview: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "phase": "plan_result",
        "message": f"Edit plan ready ({plan_reason}): {op_count} operations proposed.",
        "latest_refs": latest_refs,
        "execution_state": "running",
        "detail": {
            "plan_reason": plan_reason,
            "op_count": op_count,
            "ops_preview": ops_preview,
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
        "iteration": iteration,
        "phase": "apply_result",
        "message": f"Applied {plan_op_count} edits. Re-auditing transcript.",
        "latest_refs": latest_refs,
        "execution_state": execution_state,
        "detail": {
            "plan_op_count": plan_op_count,
            "ops": ops_display,
        },
    }
