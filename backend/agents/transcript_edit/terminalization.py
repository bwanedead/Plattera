from __future__ import annotations

from typing import Any

from .contracts import TranscriptEditAgentRunResult


def build_run_result(
    *,
    run_artifact_ref: str | None,
    session_id: str,
    iterations: int,
    status: str,
    reason_code: str,
    latest_refs: dict[str, Any],
    review_required: bool,
) -> TranscriptEditAgentRunResult:
    return TranscriptEditAgentRunResult(
        run_artifact_ref=run_artifact_ref,
        session_id=session_id,
        iterations=iterations,
        status=status,
        reason_code=reason_code,
        latest_refs=latest_refs,
        review_required=review_required,
    )


def terminal_message(result: Any) -> str:
    status = getattr(result, "status", "unknown")
    reason = getattr(result, "reason_code", "") or ""
    iterations = getattr(result, "iterations", 0)
    if status == "completed" and "promoted" in reason:
        return f"Transcript clean and promoted for mapping after {iterations} iteration(s)."
    if status == "completed":
        return f"Transcript audit completed after {iterations} iteration(s) — no errors found."
    if status == "needs_review":
        short_reason = reason.replace("tx_agent_", "").replace("_", " ")
        return f"Run finished after {iterations} iteration(s) — needs review ({short_reason})."
    if status == "failed":
        short_reason = reason.replace("tx_", "").replace("_", " ")
        return f"Run failed after {iterations} iteration(s): {short_reason}."
    return f"Run ended with status '{status}' after {iterations} iteration(s)."


def terminal_summary(progress_log: list[dict[str, Any]], result: Any) -> dict[str, Any]:
    first_audit = None
    final_audit = None
    edits_applied = 0
    used_human_feedback = False
    for entry in progress_log:
        if not isinstance(entry, dict):
            continue
        phase = str(entry.get("phase") or "")
        event_type = str(entry.get("event_type") or "")
        detail = entry.get("detail") if isinstance(entry.get("detail"), dict) else {}
        if phase == "audit_result":
            if first_audit is None:
                first_audit = detail
            final_audit = detail
        if phase == "apply_result":
            edits_applied += int(detail.get("plan_op_count") or 0)
        if event_type == "human_feedback" or phase in {"human_feedback_received", "human_feedback_reused"}:
            used_human_feedback = True
    return {
        "status": getattr(result, "status", "unknown"),
        "reason_code": getattr(result, "reason_code", None),
        "iterations": getattr(result, "iterations", None),
        "review_required": bool(getattr(result, "review_required", False)),
        "edits_applied_total": edits_applied,
        "used_human_feedback": used_human_feedback,
        "initial_findings": first_audit or {},
        "final_findings": final_audit or {},
    }
