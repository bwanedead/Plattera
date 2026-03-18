from __future__ import annotations

from typing import Any

from .contracts import TranscriptEditAgentRunResult
from .decision_ledger import (
    closure_state_from_layers,
    derive_layer_statuses,
    has_unresolved_target_scope_mapping_blocking_closure,
    scope_summaries_from_ledger,
    unresolved_outside_target_scope_mapping_blocking_requirements,
    unresolved_target_scope_mapping_blocking_requirements,
    unresolved_mapping_blocking_requirements,
    unresolved_closure_requirements,
)
from .terminal_classification import (
    _eligible_for_scoped_success,
    _run_is_healthy_for_scoped_success,
    _scope_proof_for_unresolved_item,
    _scope_status_for_unresolved_item,
    _terminal_classification,
)
from .terminal_history import (
    _attach_closure_history,
    _build_closure_history,
    _latest_freshness_posture,
    _latest_image_verify_observability,
    _merge_terminal_events,
    _pending_feedback_prompt_ids,
)
from .terminal_hitl import _post_feedback_ticket_seam
from .terminal_summary import _final_decision_rationale
from .state_projection import derive_waiting_feedback_projection

def build_run_result(
    *,
    run_artifact_ref: str | None,
    session_id: str,
    iterations: int,
    status: str,
    reason_code: str,
    latest_refs: dict[str, Any],
    review_required: bool,
    runtime_hitl_state: dict[str, Any] | None = None,
) -> TranscriptEditAgentRunResult:
    return TranscriptEditAgentRunResult(
        run_artifact_ref=run_artifact_ref,
        session_id=session_id,
        iterations=iterations,
        status=status,
        reason_code=reason_code,
        latest_refs=latest_refs,
        review_required=review_required,
        runtime_hitl_state=runtime_hitl_state if isinstance(runtime_hitl_state, dict) else None,
    )

def terminal_message(result: Any) -> str:
    status = getattr(result, "status", "unknown")
    reason = getattr(result, "reason_code", "") or ""
    iterations = getattr(result, "iterations", 0)
    if status == "needs_review" and reason.startswith("tx_agent_final_image_verify_failed"):
        return (
            f"Transcript is validator-clean but not mapping-ready after {iterations} iteration(s) "
            "because mapping-critical image verification is unresolved."
        )
    if status == "completed" and "promoted" in reason:
        return f"Transcript clean and promoted for mapping after {iterations} iteration(s)."
    if status == "completed":
        return f"Transcript audit completed after {iterations} iteration(s) — no errors found."
    if status == "needs_review":
        short_reason = reason.replace("tx_agent_", "").replace("_", " ")
        if reason.startswith("tx_agent_no_safe_plan_for_findings"):
            return (
                f"Run paused for review after {iterations} iteration(s): "
                "no safe edit plan remains for unresolved findings."
            )
        if reason.startswith("tx_agent_closure_requirements_unresolved"):
            return (
                f"Run paused after {iterations} iteration(s): "
                "closure requirements are still unresolved."
            )
        return f"Run paused for review after {iterations} iteration(s) ({short_reason})."
    if status == "failed":
        short_reason = reason.replace("tx_", "").replace("_", " ")
        return f"Run failed after {iterations} iteration(s): {short_reason}."
    return f"Run ended with status '{status}' after {iterations} iteration(s)."

def terminal_summary(
    progress_log: list[dict[str, Any]],
    result: Any,
    *,
    critical_events: list[dict[str, Any]] | None = None,
    runtime_hitl_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if runtime_hitl_state is None:
        result_runtime_hitl_state = getattr(result, "runtime_hitl_state", None)
        runtime_hitl_state = (
            result_runtime_hitl_state
            if isinstance(result_runtime_hitl_state, dict)
            else None
        )
    events = _merge_terminal_events(progress_log=progress_log, critical_events=critical_events or [])
    image_verify_observability = _latest_image_verify_observability(events=events)
    runtime_final_freshness_posture = (
        dict((runtime_hitl_state or {}).get("final_freshness_posture"))
        if isinstance((runtime_hitl_state or {}).get("final_freshness_posture"), dict)
        else None
    )
    final_freshness_posture = runtime_final_freshness_posture or _latest_freshness_posture(events=events)
    first_audit = None
    final_audit = None
    edits_applied = 0
    used_human_feedback = bool((runtime_hitl_state or {}).get("used_human_feedback"))
    decision_ledger = None
    for entry in events:
        if not isinstance(entry, dict):
            continue
        phase = str(entry.get("phase") or "")
        event_type = str(entry.get("event_type") or "")
        detail = entry.get("detail") if isinstance(entry.get("detail"), dict) else {}
        detail_ledger = detail.get("decision_ledger") if isinstance(detail.get("decision_ledger"), dict) else None
        if isinstance(detail_ledger, dict):
            has_items = isinstance(detail_ledger.get("items"), list) and len(detail_ledger.get("items") or []) > 0
            has_summary = isinstance(detail_ledger.get("summary"), dict) and len(detail_ledger.get("summary") or {}) > 0
            if has_items or has_summary:
                decision_ledger = detail_ledger
        if phase == "audit_result":
            if first_audit is None:
                first_audit = detail
            final_audit = detail
        if phase == "apply_result":
            edits_applied += int(detail.get("plan_op_count") or 0)
        if event_type == "human_feedback" or phase in {"human_feedback_received", "human_feedback_reused", "human_feedback_consumed"}:
            used_human_feedback = True
    result_status = str(getattr(result, "status", "unknown"))
    reason_code = str(getattr(result, "reason_code", "") or "")
    final_error_count = int((final_audit or {}).get("error_count") or 0) if isinstance(final_audit, dict) else 0
    validator_clean = final_error_count <= 0
    promoted = result_status == "completed" and "promoted" in reason_code
    unresolved_requirements = (
        unresolved_closure_requirements(decision_ledger)
        if isinstance(decision_ledger, dict) and isinstance(decision_ledger.get("items"), list)
        else []
    )
    unresolved_optional_items = [
        item for item in unresolved_requirements if isinstance(item, dict) and not bool(item.get("mapping_blocking"))
    ]
    source_completeness = (
        str(decision_ledger.get("source_completeness") or "unknown").strip().lower()
        if isinstance(decision_ledger, dict)
        else "unknown"
    )
    source_completeness_reason = (
        str(decision_ledger.get("source_completeness_reason") or "").strip() or None
        if isinstance(decision_ledger, dict)
        else None
    )
    source_limitations = (
        [str(v) for v in list(decision_ledger.get("source_limitations") or []) if str(v).strip()][:12]
        if isinstance(decision_ledger, dict)
        else []
    )
    blocking_unresolved = has_unresolved_target_scope_mapping_blocking_closure(decision_ledger)
    unresolved_mapping_blocking_items = unresolved_mapping_blocking_requirements(decision_ledger)
    unresolved_target_scope_items = unresolved_target_scope_mapping_blocking_requirements(decision_ledger)
    unresolved_outside_target_scope_items = unresolved_outside_target_scope_mapping_blocking_requirements(decision_ledger)
    unresolved_dependency_items = [
        item
        for item in unresolved_mapping_blocking_items
        if isinstance(item, dict)
        and isinstance(item.get("closure_requirement"), dict)
        and str((item.get("closure_requirement") or {}).get("block_reason") or "").strip().lower() == "dependency"
    ]
    unresolved_ambiguity_items = [
        item for item in unresolved_mapping_blocking_items if item not in unresolved_dependency_items
    ]
    unresolved_ambiguity_target_scope_items = [
        item
        for item in unresolved_target_scope_items
        if item in unresolved_ambiguity_items
    ]
    unresolved_unknown_scope_items = [
        item
        for item in unresolved_mapping_blocking_items
        if _scope_status_for_unresolved_item(item) == "unknown"
    ]
    unresolved_in_target_scope_items = [
        item
        for item in unresolved_mapping_blocking_items
        if _scope_status_for_unresolved_item(item) == "in_target"
    ]
    unresolved_outside_target_scope_items_with_proof = [
        item
        for item in unresolved_outside_target_scope_items
        if len(_scope_proof_for_unresolved_item(item)) > 0
    ]
    pending_feedback_prompt_ids = _pending_feedback_prompt_ids(events=events)
    human_feedback_pending = len(pending_feedback_prompt_ids) > 0
    hitl_state = runtime_hitl_state if isinstance(runtime_hitl_state, dict) else {}
    blocker_registry = (
        dict(hitl_state.get("blocker_registry"))
        if isinstance(hitl_state.get("blocker_registry"), dict)
        else {}
    )
    blocker_rows = [
        dict(row)
        for row in list(blocker_registry.get("rows") or [])
        if isinstance(row, dict)
    ]
    blocker_counts = (
        dict(blocker_registry.get("counts") or {})
        if isinstance(blocker_registry.get("counts"), dict)
        else {}
    )
    active_blocker_id = str(blocker_registry.get("active_blocker_id") or "").strip() or None
    active_blocker = next(
        (
            row
            for row in blocker_rows
            if str(row.get("blocker_id") or "").strip() == str(active_blocker_id or "").strip()
        ),
        None,
    )
    waiting_projection = derive_waiting_feedback_projection(
        blocker_registry=blocker_registry,
        fallback_prompt_id=str(hitl_state.get("pending_feedback_prompt_id") or "").strip() or None,
        fallback_decision_key=str(hitl_state.get("pending_feedback_decision_key") or "").strip().lower() or None,
    )
    waiting_feedback_owner = (
        dict(waiting_projection.get("waiting_feedback_owner"))
        if isinstance(waiting_projection.get("waiting_feedback_owner"), dict)
        else None
    )
    answered_unintegrated_owner = next(
        (
            row
            for row in blocker_rows
            if str(row.get("state") or "").strip().lower() == "answered_unintegrated"
        ),
        None,
    )
    feedback_received_count = int(hitl_state.get("feedback_received_count") or 0)
    feedback_consumed_count = int(hitl_state.get("feedback_consumed_count") or 0)
    feedback_stale_count = int(hitl_state.get("feedback_stale_count") or 0)
    feedback_superseded_count = int(hitl_state.get("feedback_superseded_count") or 0)
    human_resolution_tickets = (
        [dict(row) for row in list(hitl_state.get("human_resolution_tickets") or []) if isinstance(row, dict)][-40:]
        if isinstance(hitl_state, dict)
        else []
    )
    answered_unintegrated_ticket_count = sum(
        1
        for row in human_resolution_tickets
        if str(row.get("lifecycle_state") or "").strip().lower() == "answered_unintegrated"
    )
    integration_failed_ticket_count = sum(
        1
        for row in human_resolution_tickets
        if str(row.get("lifecycle_state") or "").strip().lower() == "integration_attempted_failed"
    )
    integrated_ticket_count = sum(
        1
        for row in human_resolution_tickets
        if str(row.get("lifecycle_state") or "").strip().lower() == "integrated"
    )
    seam_state, seam_snapshot = _post_feedback_ticket_seam(human_resolution_tickets=human_resolution_tickets)
    superseded_prompt_ids = (
        [str(v) for v in list(hitl_state.get("superseded_prompt_ids") or []) if str(v).strip()]
        if isinstance(hitl_state, dict)
        else []
    )
    hitl_lifecycle_log = (
        [evt for evt in list(hitl_state.get("hitl_lifecycle_log") or []) if isinstance(evt, dict)][-80:]
        if isinstance(hitl_state, dict)
        else []
    )
    runtime_pending_prompt_id = str(waiting_projection.get("pending_feedback_prompt_id") or "").strip()
    if runtime_pending_prompt_id and runtime_pending_prompt_id not in pending_feedback_prompt_ids:
        pending_feedback_prompt_ids.append(runtime_pending_prompt_id)
        human_feedback_pending = True
    optional_only_remaining = bool(
        len(unresolved_optional_items) > 0
        and len(unresolved_mapping_blocking_items) == 0
    )
    scope_summaries = scope_summaries_from_ledger(decision_ledger if isinstance(decision_ledger, dict) else None)
    target_scope_status = str((scope_summaries.get("target_scope") or {}).get("scope_closure_state") or "not_attempted")
    outside_target_scope_status = str((scope_summaries.get("outside_target_scope") or {}).get("scope_closure_state") or "not_attempted")
    unknown_scope_status = str((scope_summaries.get("unknown_scope") or {}).get("scope_closure_state") or "not_attempted")
    run_healthy = _run_is_healthy_for_scoped_success(
        result_status=result_status,
        reason_code=reason_code,
    )
    scoped_success_eligible = _eligible_for_scoped_success(
        run_healthy=run_healthy,
        in_target_unresolved_count=len(unresolved_in_target_scope_items),
        unknown_scope_unresolved_count=len(unresolved_unknown_scope_items),
        target_validator_clean=validator_clean,
        target_scope_status=target_scope_status,
        source_completeness=source_completeness,
        outside_target_proved_count=len(unresolved_outside_target_scope_items_with_proof),
    )
    mapping_ready = False
    readiness_blocker: str | None = None
    if promoted:
        mapping_ready = True
    elif result_status == "completed" and validator_clean and not blocking_unresolved:
        mapping_ready = True
    elif reason_code.startswith("tx_agent_final_image_verify_failed"):
        mapping_ready = False
        readiness_blocker = "mapping_critical_image_verification_unresolved"
    if not mapping_ready and scoped_success_eligible and result_status == "completed":
        mapping_ready = True
        readiness_blocker = None
    layer_statuses = derive_layer_statuses(
        mapping_ready=mapping_ready,
        validator_clean=validator_clean,
        readiness_blocker=readiness_blocker,
    )
    closure_state = closure_state_from_layers(layer_statuses)
    closure_history = _build_closure_history(progress_log=progress_log)
    decision_ledger_with_history = _attach_closure_history(
        decision_ledger=decision_ledger if isinstance(decision_ledger, dict) else {},
        closure_history=closure_history,
    )
    terminal_classification = _terminal_classification(
        reason_code=reason_code,
        mapping_ready=mapping_ready,
        scoped_success_eligible=scoped_success_eligible,
        run_healthy=run_healthy,
        target_scope_status=target_scope_status,
        source_completeness=source_completeness,
        unresolved_outside_target_scope_items=unresolved_outside_target_scope_items_with_proof,
        unresolved_dependency_items=unresolved_dependency_items,
        unresolved_ambiguity_items=unresolved_ambiguity_items,
        unresolved_ambiguity_target_scope_items=unresolved_ambiguity_target_scope_items,
        optional_only_remaining=optional_only_remaining,
        human_feedback_pending=human_feedback_pending,
        result_status=result_status,
        blocker_counts=blocker_counts,
        active_blocker=active_blocker,
    )
    last_blocker_transition = (
        next(
            (
                dict(row)
                for row in reversed(list(blocker_registry.get("history") or []))
                if isinstance(row, dict)
            ),
            None,
        )
        if isinstance(blocker_registry, dict)
        else None
    )
    actionable_returned_feedback_pending_integration = int((blocker_counts or {}).get("answered_unintegrated") or 0) > 0
    final_decision_rationale = _final_decision_rationale(
        events=events,
        result_status=result_status,
        reason_code=reason_code,
        terminal_classification=terminal_classification,
        mapping_ready=mapping_ready,
        scoped_success_eligible=scoped_success_eligible,
        run_healthy=run_healthy,
        closure_state=closure_state,
        validator_clean=validator_clean,
        human_feedback_pending=human_feedback_pending,
        unresolved_mapping_blocking_items=unresolved_mapping_blocking_items,
        unresolved_dependency_items=unresolved_dependency_items,
        unresolved_ambiguity_items=unresolved_ambiguity_items,
        unresolved_target_scope_items=unresolved_target_scope_items,
        unresolved_outside_target_scope_items=unresolved_outside_target_scope_items_with_proof,
        unresolved_unknown_scope_items=unresolved_unknown_scope_items,
        unresolved_optional_items=unresolved_optional_items,
        edits_applied=edits_applied,
        feedback_received_count=feedback_received_count,
        feedback_consumed_count=feedback_consumed_count,
        feedback_stale_count=feedback_stale_count,
        feedback_superseded_count=feedback_superseded_count,
        pending_feedback_prompt_ids=pending_feedback_prompt_ids,
        final_freshness_posture=final_freshness_posture,
        terminal_message_fn=terminal_message,
    )
    final_freshness_summary = final_decision_rationale.get("freshness_posture_summary")
    return {
        "status": result_status,
        "reason_code": reason_code or None,
        "iterations": getattr(result, "iterations", None),
        "review_required": bool(getattr(result, "review_required", False)),
        "edits_applied_total": edits_applied,
        "used_human_feedback": used_human_feedback,
        "validator_clean": validator_clean,
        "mapping_ready": mapping_ready,
        "promoted": promoted,
        "readiness_blocker": readiness_blocker,
        "closure_state": closure_state,
        "terminal_classification": terminal_classification,
        "source_completeness": source_completeness,
        "source_completeness_reason": source_completeness_reason,
        "source_limitations": source_limitations,
        "scope_summaries": scope_summaries,
        "scope_summary": {
            "in_target_unresolved_mapping_blockers": len(unresolved_in_target_scope_items),
            "unknown_scope_unresolved_mapping_blockers": len(unresolved_unknown_scope_items),
            "outside_target_unresolved_mapping_blockers": len(unresolved_outside_target_scope_items_with_proof),
        },
        "target_scope_status": target_scope_status,
        "outside_target_scope_status": outside_target_scope_status,
        "unknown_scope_status": unknown_scope_status,
        "scoped_success_eligible": scoped_success_eligible,
        "run_healthy_for_scoped_success": run_healthy,
        **layer_statuses,
        "decision_ledger": decision_ledger_with_history,
        "closure_history": closure_history,
        "unresolved_closure_requirements": unresolved_requirements,
        "unresolved_mapping_blocking_closure_requirements": unresolved_mapping_blocking_items,
        "unresolved_dependency_items": unresolved_dependency_items,
        "unresolved_ambiguity_items": unresolved_ambiguity_items,
        "unresolved_target_scope_items": unresolved_target_scope_items,
        "unresolved_outside_target_scope_items": unresolved_outside_target_scope_items,
        "unresolved_unknown_scope_items": unresolved_unknown_scope_items,
        "outside_target_items_with_scope_proof": [
            {
                **item,
                "scope_proof": _scope_proof_for_unresolved_item(item),
            }
            for item in unresolved_outside_target_scope_items_with_proof
            if isinstance(item, dict)
        ],
        "unresolved_by_scope": {
            "target_scope": unresolved_in_target_scope_items,
            "outside_target_scope": unresolved_outside_target_scope_items_with_proof,
            "unknown_scope": unresolved_unknown_scope_items,
        },
        "unresolved_optional_items": unresolved_optional_items,
        "optional_only_remaining": optional_only_remaining,
        "human_feedback_pending": human_feedback_pending,
        "pending_feedback_prompt_ids": pending_feedback_prompt_ids,
        "feedback_received_count": feedback_received_count,
        "feedback_consumed_count": feedback_consumed_count,
        "feedback_stale_count": feedback_stale_count,
        "feedback_superseded_count": feedback_superseded_count,
        "answered_unintegrated_ticket_count": int(answered_unintegrated_ticket_count),
        "integration_failed_ticket_count": int(integration_failed_ticket_count),
        "integrated_ticket_count": int(integrated_ticket_count),
        "post_feedback_ticket_seam_state": seam_state,
        "post_feedback_ticket_snapshot": seam_snapshot,
        "superseded_feedback_prompt_ids": superseded_prompt_ids,
        "human_resolution_tickets": human_resolution_tickets,
        "hitl_lifecycle_log": hitl_lifecycle_log,
        "blocker_registry": blocker_registry,
        "blocker_registry_counts": blocker_counts,
        "active_blocker_id": active_blocker_id,
        "active_blocker": active_blocker,
        "waiting_feedback_owner": waiting_feedback_owner,
        "answered_unintegrated_owner": answered_unintegrated_owner,
        "last_blocker_transition": last_blocker_transition,
        "actionable_returned_feedback_pending_integration": actionable_returned_feedback_pending_integration,
        "decision_ledger_summary": (
            decision_ledger.get("summary")
            if isinstance(decision_ledger, dict) and isinstance(decision_ledger.get("summary"), dict)
            else {}
        ),
        "image_verify_observability": image_verify_observability,
        "final_freshness_posture": final_freshness_posture,
        "final_freshness_summary": final_freshness_summary,
        "final_decision_rationale": final_decision_rationale,
        "initial_findings": first_audit or {},
        "final_findings": final_audit or {},
    }
