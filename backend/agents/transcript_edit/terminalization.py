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
    waiting_feedback_owner = next(
        (
            row
            for row in blocker_rows
            if str(row.get("state") or "").strip().lower() == "waiting_feedback"
        ),
        None,
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
    runtime_pending_prompt_id = str(hitl_state.get("pending_feedback_prompt_id") or "").strip()
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
    )
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
        "final_decision_rationale": final_decision_rationale,
        "initial_findings": first_audit or {},
        "final_findings": final_audit or {},
    }


def _build_closure_history(*, progress_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history_by_key: dict[str, list[dict[str, Any]]] = {}
    last_state_by_key: dict[str, str] = {}
    for entry in progress_log:
        if not isinstance(entry, dict):
            continue
        phase = str(entry.get("phase") or "")
        timestamp = entry.get("timestamp_epoch_seconds")
        detail = entry.get("detail") if isinstance(entry.get("detail"), dict) else {}
        ledger = detail.get("decision_ledger")
        if not isinstance(ledger, dict):
            continue
        items = ledger.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            state = str(item.get("state") or "unknown")
            if last_state_by_key.get(key) == state:
                continue
            last_state_by_key[key] = state
            evidence_refs = item.get("evidence_refs") if isinstance(item.get("evidence_refs"), list) else []
            evidence_ref = str(evidence_refs[-1]) if evidence_refs else None
            history_by_key.setdefault(key, []).append(
                {
                    "timestamp_epoch_seconds": timestamp,
                    "action": phase or "state_update",
                    "outcome": state,
                    "evidence_ref": evidence_ref,
                }
            )
    out: list[dict[str, Any]] = []
    for key in sorted(history_by_key.keys()):
        out.append({"decision_key": key, "events": history_by_key[key]})
    return out


def _attach_closure_history(*, decision_ledger: dict[str, Any], closure_history: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(decision_ledger, dict):
        return {}
    out = dict(decision_ledger)
    items = out.get("items")
    if not isinstance(items, list):
        return out
    events_by_key: dict[str, list[dict[str, Any]]] = {}
    for item in closure_history:
        if not isinstance(item, dict):
            continue
        key = str(item.get("decision_key") or "")
        events = item.get("events")
        if key and isinstance(events, list):
            events_by_key[key] = [e for e in events if isinstance(e, dict)]
    updated_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        copy_item = dict(item)
        key = str(copy_item.get("key") or "")
        copy_item["closure_history"] = events_by_key.get(key, [])
        updated_items.append(copy_item)
    out["items"] = updated_items
    return out


def _pending_feedback_prompt_ids(*, events: list[dict[str, Any]]) -> list[str]:
    needed: list[str] = []
    answered: set[str] = set()
    superseded: set[str] = set()
    for entry in events:
        if not isinstance(entry, dict):
            continue
        event_type = str(entry.get("event_type") or "").strip().lower()
        phase = str(entry.get("phase") or "").strip().lower()
        prompt_id = str(entry.get("prompt_id") or "").strip()
        if event_type == "human_feedback_needed" and prompt_id:
            needed.append(prompt_id)
            continue
        if phase in {"human_feedback_received", "human_feedback_reused", "human_feedback_consumed"} and prompt_id:
            answered.add(prompt_id)
        if phase == "human_feedback_prompt_superseded" and prompt_id:
            superseded.add(prompt_id)
    pending = [pid for pid in needed if pid not in answered and pid not in superseded]
    deduped: list[str] = []
    seen: set[str] = set()
    for pid in pending:
        if pid in seen:
            continue
        seen.add(pid)
        deduped.append(pid)
    return deduped


def _merge_terminal_events(
    *,
    progress_log: list[dict[str, Any]],
    critical_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for entry in [*(progress_log or []), *(critical_events or [])]:
        if not isinstance(entry, dict):
            continue
        key = "|".join(
            [
                str(entry.get("timestamp_epoch_seconds") or ""),
                str(entry.get("iteration") or ""),
                str(entry.get("phase") or ""),
                str(entry.get("event_type") or ""),
                str(entry.get("prompt_id") or ""),
                str(entry.get("message") or "")[:120],
            ]
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        merged.append(entry)
    return merged


def _latest_image_verify_observability(*, events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for entry in reversed(events):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("phase") or "").strip().lower() != "image_verify":
            continue
        detail = entry.get("detail") if isinstance(entry.get("detail"), dict) else {}
        return {
            "phase": "image_verify",
            "message": str(entry.get("message") or "").strip() or None,
            "detail": dict(detail),
            "timestamp_epoch_seconds": entry.get("timestamp_epoch_seconds"),
            "iteration": entry.get("iteration"),
        }
    return None


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
    target_validator_clean: bool,
    target_scope_status: str,
    source_completeness: str,
    outside_target_proved_count: int,
) -> bool:
    if not run_healthy:
        return False
    if not target_validator_clean:
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


def _post_feedback_ticket_seam(*, human_resolution_tickets: list[dict[str, Any]]) -> tuple[str | None, dict[str, Any] | None]:
    if not human_resolution_tickets:
        return None, None
    rows = [dict(row) for row in human_resolution_tickets if isinstance(row, dict)]
    if not rows:
        return None, None
    rows.sort(key=lambda row: int(row.get("updated_at") or row.get("created_at") or 0), reverse=True)
    preferred_order = {
        "integration_attempted_failed": 0,
        "answered_unintegrated": 1,
        "integrated": 2,
        "superseded": 3,
        "stale": 4,
        "issued_waiting_feedback": 5,
    }
    rows.sort(key=lambda row: preferred_order.get(str(row.get("lifecycle_state") or "").strip().lower(), 99))
    top = rows[0]
    state = str(top.get("lifecycle_state") or "").strip().lower() or None
    snapshot = {
        "ticket_id": str(top.get("ticket_id") or "").strip() or None,
        "ticket_state": state,
        "ticket_decision_key": str(top.get("decision_key") or "").strip().lower() or None,
        "ticket_strength": str(top.get("strength") or "").strip().lower() or None,
        "answered_at": top.get("answered_at"),
        "integrated_at": top.get("integrated_at"),
        "updated_at": top.get("updated_at"),
    }
    return state, snapshot


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
    validator_clean: bool,
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
        "decision_statement": terminal_message(
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
        "validator_clean": bool(validator_clean),
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


def _last_progress_reason(events: list[dict[str, Any]]) -> str | None:
    for entry in reversed(events):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("phase") or "").strip().lower() != "progress_evaluation":
            continue
        detail = entry.get("detail") if isinstance(entry.get("detail"), dict) else {}
        reason = str(detail.get("progress_reason") or "").strip()
        if reason:
            return reason
    return None


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


def _max_iteration(events: list[dict[str, Any]]) -> int:
    max_it = 0
    for entry in events:
        if not isinstance(entry, dict):
            continue
        value = entry.get("iteration")
        if isinstance(value, int) and value > max_it:
            max_it = value
    return max_it


def _hitl_feedback_state_summary(
    *,
    feedback_received_count: int,
    feedback_consumed_count: int,
    feedback_stale_count: int,
    feedback_superseded_count: int,
    pending_feedback_prompt_ids: list[str],
    unresolved_mapping_blocking_items: list[dict[str, Any]],
) -> dict[str, Any]:
    provided = int(feedback_received_count) > 0
    consumed = int(feedback_consumed_count) > 0
    pending = len([str(v) for v in pending_feedback_prompt_ids if str(v).strip()]) > 0
    integrated_status = "unknown"
    if consumed and len(unresolved_mapping_blocking_items) == 0:
        integrated_status = "consumed_and_blocker_cleared"
    elif consumed and len(unresolved_mapping_blocking_items) > 0:
        integrated_status = "consumed_but_blockers_remain"
    elif provided and not consumed:
        integrated_status = "provided_not_consumed"
    elif pending:
        integrated_status = "awaiting_feedback"
    return {
        "hitl_feedback_provided": bool(provided),
        "hitl_feedback_consumed": bool(consumed),
        "hitl_feedback_pending": bool(pending),
        "consumed_definition": (
            "Consumed means the runtime matched a pending prompt response, normalized it, "
            "accepted it into loop state, and used it in focus-cycle decision processing."
        ),
        "integration_status": integrated_status,
        "feedback_received_count": int(feedback_received_count),
        "feedback_consumed_count": int(feedback_consumed_count),
        "feedback_stale_count": int(feedback_stale_count),
        "feedback_superseded_count": int(feedback_superseded_count),
    }
