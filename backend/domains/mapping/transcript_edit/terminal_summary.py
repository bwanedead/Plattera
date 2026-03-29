from __future__ import annotations

from typing import Any

from .terminal_classification import (
    _next_action_for_terminal_classification,
    _scope_status_for_unresolved_item,
)
from .terminal_history import _last_progress_reason, _latest_freshness_posture, _max_iteration
from .terminal_hitl import _hitl_feedback_state_summary

def _final_decision_rationale(
    *,
    events: list[dict[str, Any]],
    result_status: str,
    reason_code: str,
    terminal_classification: str,
    mapping_ready: bool,
    scoped_success_eligible: bool,
    run_healthy: bool,
    closure_state: str,
    mechanical_severity_clear: bool,
    human_feedback_pending: bool,
    unresolved_mapping_blocking_items: list[dict[str, Any]],
    unresolved_dependency_items: list[dict[str, Any]],
    unresolved_ambiguity_items: list[dict[str, Any]],
    unresolved_target_scope_items: list[dict[str, Any]],
    unresolved_outside_target_scope_items: list[dict[str, Any]],
    unresolved_unknown_scope_items: list[dict[str, Any]],
    unresolved_optional_items: list[dict[str, Any]],
    edits_applied: int,
    feedback_received_count: int,
    feedback_consumed_count: int,
    feedback_stale_count: int,
    feedback_superseded_count: int,
    pending_feedback_prompt_ids: list[str],
    final_freshness_posture: dict[str, Any] | None,
    terminal_message_fn,
) -> dict[str, Any]:
    summary_blockers = _summarize_unresolved_items(unresolved_mapping_blocking_items, limit=8)
    summary_optional = _summarize_unresolved_items(unresolved_optional_items, limit=6)
    attempts = _attempts_summary(
        events=events,
        edits_applied=edits_applied,
        feedback_received_count=feedback_received_count,
        feedback_consumed_count=feedback_consumed_count,
        feedback_stale_count=feedback_stale_count,
        feedback_superseded_count=feedback_superseded_count,
    )
    progress_reason = _last_progress_reason(events)
    closure_not_reached_reason = None
    if result_status != "completed" or not mapping_ready:
        closure_not_reached_reason = _closure_not_reached_reason(
            terminal_classification=terminal_classification,
            reason_code=reason_code,
            human_feedback_pending=human_feedback_pending,
            unresolved_mapping_blocking_count=len(unresolved_mapping_blocking_items),
        )
    return {
        "decision_statement": terminal_message_fn(
            type(
                "_ResultView",
                (),
                {
                    "status": result_status,
                    "reason_code": reason_code,
                    "iterations": _max_iteration(events),
                },
            )
        ),
        "result_status": result_status,
        "reason_code": reason_code or None,
        "terminal_classification": terminal_classification,
        "mapping_ready": bool(mapping_ready),
        "closure_state": closure_state,
        "mechanical_severity_clear": bool(mechanical_severity_clear),
        "run_healthy_for_scoped_success": bool(run_healthy),
        "scoped_success_eligible": bool(scoped_success_eligible),
        "why_this_decision": _decision_why_text(
            result_status=result_status,
            terminal_classification=terminal_classification,
            reason_code=reason_code,
            mapping_ready=mapping_ready,
            unresolved_mapping_blocking_count=len(unresolved_mapping_blocking_items),
            progress_reason=progress_reason,
        ),
        "freshness_posture_summary": _freshness_posture_summary(final_freshness_posture),
        "closure_not_reached_reason": closure_not_reached_reason,
        "blocking_items_count": int(len(unresolved_mapping_blocking_items)),
        "blocking_items_summary": summary_blockers,
        "blocking_breakdown": {
            "dependency_count": int(len(unresolved_dependency_items)),
            "ambiguity_count": int(len(unresolved_ambiguity_items)),
            "target_scope_count": int(len(unresolved_target_scope_items)),
            "outside_target_scope_count": int(len(unresolved_outside_target_scope_items)),
            "unknown_scope_count": int(len(unresolved_unknown_scope_items)),
            "optional_unresolved_count": int(len(unresolved_optional_items)),
        },
        "optional_items_summary": summary_optional,
        "what_was_tried": attempts,
        "hitl_feedback_state": _hitl_feedback_state_summary(
            feedback_received_count=feedback_received_count,
            feedback_consumed_count=feedback_consumed_count,
            feedback_stale_count=feedback_stale_count,
            feedback_superseded_count=feedback_superseded_count,
            pending_feedback_prompt_ids=pending_feedback_prompt_ids,
            unresolved_mapping_blocking_items=unresolved_mapping_blocking_items,
        ),
        "pending_feedback_prompt_ids": [str(v) for v in pending_feedback_prompt_ids if str(v).strip()],
        "next_action": _next_action_for_terminal_classification(
            terminal_classification=terminal_classification,
            human_feedback_pending=human_feedback_pending,
        ),
    }

def _summarize_unresolved_items(items: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        closure = item.get("closure_requirement") if isinstance(item.get("closure_requirement"), dict) else {}
        out.append(
            {
                "key": str(item.get("key") or "").strip() or None,
                "state": str(item.get("state") or "").strip() or None,
                "scope_status": _scope_status_for_unresolved_item(item),
                "block_reason": str(closure.get("block_reason") or "").strip() or None,
                "required_information": str(closure.get("required_information") or "").strip() or None,
                "minimal_user_action": str(closure.get("minimal_user_action") or "").strip() or None,
                "evidence_refs": [
                    str(v)
                    for v in list(item.get("evidence_refs") or closure.get("evidence_refs") or [])
                    if str(v).strip()
                ][:6],
            }
        )
        if len(out) >= max(1, int(limit)):
            break
    return out

def _attempts_summary(
    *,
    events: list[dict[str, Any]],
    edits_applied: int,
    feedback_received_count: int,
    feedback_consumed_count: int,
    feedback_stale_count: int,
    feedback_superseded_count: int,
) -> dict[str, Any]:
    phase_counts: dict[str, int] = {
        "audit_result": 0,
        "open_spans": 0,
        "image_verify": 0,
        "plan_result": 0,
        "apply_result": 0,
        "resolver_attempt": 0,
    }
    for entry in events:
        if not isinstance(entry, dict):
            continue
        phase = str(entry.get("phase") or "").strip().lower()
        if phase in phase_counts:
            phase_counts[phase] += 1
    return {
        "audit_passes": int(phase_counts["audit_result"]),
        "open_spans_attempts": int(phase_counts["open_spans"]),
        "image_verify_attempts": int(phase_counts["image_verify"]),
        "resolver_attempts": int(phase_counts["resolver_attempt"]),
        "plan_attempts": int(phase_counts["plan_result"]),
        "apply_attempts": int(phase_counts["apply_result"]),
        "edits_applied_total": int(edits_applied),
        "feedback_received_count": int(feedback_received_count),
        "feedback_consumed_count": int(feedback_consumed_count),
        "feedback_stale_count": int(feedback_stale_count),
        "feedback_superseded_count": int(feedback_superseded_count),
    }

def _decision_why_text(
    *,
    result_status: str,
    terminal_classification: str,
    reason_code: str,
    mapping_ready: bool,
    unresolved_mapping_blocking_count: int,
    progress_reason: str | None,
) -> str:
    if mapping_ready and result_status == "completed":
        return (
            "Run ended as completed because mapping readiness gates were satisfied and no target-scope "
            "mapping-blocking closure requirements remained."
        )
    reason_bits = [f"classification={terminal_classification}"]
    if reason_code:
        reason_bits.append(f"reason_code={reason_code}")
    reason_bits.append(f"unresolved_mapping_blockers={int(unresolved_mapping_blocking_count)}")
    if progress_reason:
        reason_bits.append(f"last_progress_reason={progress_reason}")
    return "Run ended without full closure because " + ", ".join(reason_bits) + "."


def _freshness_posture_summary(final_freshness_posture: dict[str, Any] | None) -> str | None:
    posture = final_freshness_posture if isinstance(final_freshness_posture, dict) else {}
    if not posture:
        return None
    if bool(posture.get("repeat_without_signal")):
        return "Run ended after repeated no-signal evidence pressure."
    if bool(posture.get("has_fresh_signal")):
        return "Run ended with fresh signal supporting the final bounded decision."
    if bool(posture.get("cached_context_present")):
        return "Run ended with cached context present but no fresh narrowing signal."
    return "Run ended without a clear freshness posture."

def _closure_not_reached_reason(
    *,
    terminal_classification: str,
    reason_code: str,
    human_feedback_pending: bool,
    unresolved_mapping_blocking_count: int,
) -> str:
    if human_feedback_pending or terminal_classification in {"blocked_waiting_feedback", "blocked_waiting_feedback_timeout"}:
        return "Pending human feedback remained unresolved at terminalization."
    if terminal_classification == "blocked_answered_unintegrated_no_safe_plan":
        return "Returned human feedback was present but no safe integration path cleared the blocker."
    if terminal_classification == "blocked_target_scope_open":
        return "A target-scope mapping blocker remained open at terminalization."
    if terminal_classification == "blocked_dependency_evidence_missing":
        return "Required dependency evidence was unavailable, so closure gates remained blocked."
    if terminal_classification == "blocked_post_feedback_plan_invalid":
        return "Post-feedback plan payloads remained invalid after bounded retries."
    if terminal_classification in {"blocked_target_scope_ambiguity", "blocked_mapping_ambiguity_unresolved"}:
        return "Ambiguity remained unresolved after bounded autonomous attempts."
    if reason_code.startswith("tx_agent_no_progress:"):
        return "Loop exhausted no-progress tolerance without material blocker-state change."
    if reason_code:
        return f"Closure not reached due to terminal reason code: {reason_code}."
    return f"Closure not reached; unresolved mapping-blocking requirements={int(unresolved_mapping_blocking_count)}."
