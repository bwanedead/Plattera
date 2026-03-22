from __future__ import annotations

from typing import Any

def _terminal_classification(
    *,
    reason_code: str,
    mapping_ready: bool,
    scoped_success_eligible: bool,
    run_healthy: bool,
    target_scope_status: str,
    source_completeness: str,
    unresolved_outside_target_scope_items: list[dict[str, Any]],
    unresolved_dependency_items: list[dict[str, Any]],
    unresolved_ambiguity_items: list[dict[str, Any]],
    unresolved_ambiguity_target_scope_items: list[dict[str, Any]],
    optional_only_remaining: bool,
    human_feedback_pending: bool,
    result_status: str,
    blocker_counts: dict[str, Any] | None = None,
    active_blocker: dict[str, Any] | None = None,
) -> str:
    if str(result_status or "").strip().lower() == "failed":
        counts = dict(blocker_counts or {})
        waiting_feedback_count = int(counts.get("waiting_feedback") or 0)
        if (
            "budget_wall_time_exceeded" in str(reason_code or "").strip().lower()
            and (human_feedback_pending or waiting_feedback_count > 0)
        ):
            return "blocked_waiting_feedback_timeout"
        return "blocked_execution_failed"
    counts = dict(blocker_counts or {})
    waiting_feedback_count = int(counts.get("waiting_feedback") or 0)
    answered_unintegrated_count = int(counts.get("answered_unintegrated") or 0)
    active_scope = str((active_blocker or {}).get("scope_status") or "").strip().lower()
    active_state = str((active_blocker or {}).get("state") or "").strip().lower()
    scoped_incomplete_source = bool(
        scoped_success_eligible
        and run_healthy
        and target_scope_status == "achieved"
        and source_completeness in {"partial_truncated", "partial_missing_context"}
        and len(unresolved_outside_target_scope_items) > 0
    )
    if scoped_incomplete_source:
        if result_status == "completed":
            return "target_scope_complete_with_incomplete_source_context"
        return "partial_success_incomplete_source"
    if mapping_ready:
        if optional_only_remaining:
            return "optional_quality_remaining_only"
        return "closure_achieved"
    if len(unresolved_dependency_items) > 0:
        return "blocked_dependency_evidence_missing"
    if str(reason_code or "").startswith("tx_agent_post_feedback_resolver_invalid_exhausted:"):
        return "blocked_post_feedback_resolver_invalid"
    if str(reason_code or "").startswith(
        (
            "tx_agent_post_feedback_plan_invalid_exhausted:",
            "tx_agent_plan_invalid_exhausted:",
        )
    ):
        return "blocked_post_feedback_plan_invalid"
    if human_feedback_pending:
        return "blocked_human_feedback_needed"
    if len(unresolved_ambiguity_target_scope_items) > 0:
        return "blocked_target_scope_ambiguity"
    if len(unresolved_ambiguity_items) > 0:
        return "blocked_mapping_ambiguity_unresolved"
    has_registry_counts = len(counts) > 0
    if has_registry_counts and waiting_feedback_count > 0:
        return "blocked_waiting_feedback"
    if has_registry_counts and answered_unintegrated_count > 0:
        return "blocked_answered_unintegrated_no_safe_plan"
    if has_registry_counts and active_state == "open" and active_scope in {"in_target", "unknown"}:
        return "blocked_target_scope_open"
    return "blocked_no_safe_autonomous_move"

def _scope_status_for_unresolved_item(item: dict[str, Any]) -> str:
    requirement = item.get("closure_requirement") if isinstance(item.get("closure_requirement"), dict) else {}
    raw_status = str(requirement.get("scope_status") or item.get("scope_status") or "").strip().lower()
    if raw_status in {"in_target", "outside_target", "unknown"}:
        return raw_status
    raw_scope_id = str(item.get("scope_id") or "").strip().lower()
    if raw_scope_id == "target_scope":
        return "in_target"
    if raw_scope_id == "outside_target_scope":
        return "outside_target"
    return "unknown"

def _scope_proof_for_unresolved_item(item: dict[str, Any]) -> list[str]:
    requirement = item.get("closure_requirement") if isinstance(item.get("closure_requirement"), dict) else {}
    rows = [
        str(v).strip().lower()
        for v in list(requirement.get("scope_proof") or item.get("scope_proof") or [])
        if str(v).strip()
    ]
    out: list[str] = []
    for code in rows:
        if code not in {
            "explicit_outside_target_text",
            "source_truncation_boundary",
            "image_confirms_post_target_cutoff",
            "operator_marked_outside_target",
        }:
            continue
        if code in out:
            continue
        out.append(code)
    return out[:6]

def _run_is_healthy_for_scoped_success(*, result_status: str, reason_code: str) -> bool:
    status = str(result_status or "").strip().lower()
    reason = str(reason_code or "").strip().lower()
    if status == "failed":
        return False
    unhealthy_prefixes = (
        "tx_agent_post_feedback_resolver_invalid_exhausted",
        "tx_agent_plan_invalid_exhausted",
        "tx_audit_refused",
        "tx_pre_audit_refused",
        "tx_orient_baseline_refused",
        "tx_apply_refused",
        "tx_promote_refused",
        "tx_agent_execution_failed",
    )
    return not any(reason.startswith(prefix) for prefix in unhealthy_prefixes)

def _eligible_for_scoped_success(
    *,
    run_healthy: bool,
    in_target_unresolved_count: int,
    unknown_scope_unresolved_count: int,
    mechanical_severity_clear: bool,
    target_scope_status: str,
    source_completeness: str,
    outside_target_proved_count: int,
) -> bool:
    if not run_healthy:
        return False
    if not mechanical_severity_clear:
        return False
    if int(in_target_unresolved_count) > 0:
        return False
    if int(unknown_scope_unresolved_count) > 0:
        return False
    if str(target_scope_status or "").strip().lower() != "achieved":
        return False
    if str(source_completeness or "").strip().lower() not in {"partial_truncated", "partial_missing_context"}:
        return False
    if int(outside_target_proved_count) <= 0:
        return False
    return True

def _next_action_for_terminal_classification(*, terminal_classification: str, human_feedback_pending: bool) -> str:
    if human_feedback_pending or terminal_classification in {
        "blocked_human_feedback_needed",
        "blocked_waiting_feedback",
        "blocked_waiting_feedback_timeout",
    }:
        return "Provide feedback to the active prompt and resume the run."
    if terminal_classification == "blocked_answered_unintegrated_no_safe_plan":
        return "Review returned feedback integration constraints and provide refined guidance or corrected source evidence."
    if terminal_classification == "blocked_dependency_evidence_missing":
        return "Provide missing dependency evidence/source material, then resume."
    if terminal_classification in {"blocked_target_scope_ambiguity", "blocked_mapping_ambiguity_unresolved"}:
        return "Provide explicit disambiguation (or corrected source text), then rerun."
    if terminal_classification in {"blocked_post_feedback_resolver_invalid", "blocked_post_feedback_plan_invalid"}:
        return "Inspect resolver diagnostics and repair move-contract/prompting before rerun."
    if terminal_classification in {"closure_achieved", "target_scope_complete_with_incomplete_source_context"}:
        return "Proceed to downstream mapping workflow."
    return "Review terminal blockers and rerun with additional evidence or operator input."
