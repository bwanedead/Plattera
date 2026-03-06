from __future__ import annotations

from typing import Any

from .contracts import TranscriptEditAgentRunResult
from .decision_ledger import (
    closure_state_from_layers,
    derive_layer_statuses,
    has_unresolved_mapping_blocking_closure,
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
        if decision_ledger is None and isinstance(detail.get("decision_ledger"), dict):
            decision_ledger = detail.get("decision_ledger")
        elif isinstance(detail.get("decision_ledger"), dict):
            decision_ledger = detail.get("decision_ledger")
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
    blocking_unresolved = has_unresolved_mapping_blocking_closure(decision_ledger)
    unresolved_mapping_blocking_items = unresolved_mapping_blocking_requirements(decision_ledger)
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
    pending_feedback_prompt_ids = _pending_feedback_prompt_ids(events=events)
    human_feedback_pending = len(pending_feedback_prompt_ids) > 0
    hitl_state = runtime_hitl_state if isinstance(runtime_hitl_state, dict) else {}
    feedback_received_count = int(hitl_state.get("feedback_received_count") or 0)
    feedback_consumed_count = int(hitl_state.get("feedback_consumed_count") or 0)
    feedback_stale_count = int(hitl_state.get("feedback_stale_count") or 0)
    feedback_superseded_count = int(hitl_state.get("feedback_superseded_count") or 0)
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
    mapping_ready = False
    readiness_blocker: str | None = None
    if promoted:
        mapping_ready = True
    elif result_status == "completed" and validator_clean and not blocking_unresolved:
        mapping_ready = True
    elif reason_code.startswith("tx_agent_final_image_verify_failed"):
        mapping_ready = False
        readiness_blocker = "mapping_critical_image_verification_unresolved"
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
        mapping_ready=mapping_ready,
        unresolved_dependency_items=unresolved_dependency_items,
        unresolved_ambiguity_items=unresolved_ambiguity_items,
        optional_only_remaining=optional_only_remaining,
        human_feedback_pending=human_feedback_pending,
        result_status=result_status,
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
        **layer_statuses,
        "decision_ledger": decision_ledger_with_history,
        "closure_history": closure_history,
        "unresolved_closure_requirements": unresolved_requirements,
        "unresolved_mapping_blocking_closure_requirements": unresolved_mapping_blocking_items,
        "unresolved_dependency_items": unresolved_dependency_items,
        "unresolved_ambiguity_items": unresolved_ambiguity_items,
        "unresolved_optional_items": unresolved_optional_items,
        "optional_only_remaining": optional_only_remaining,
        "human_feedback_pending": human_feedback_pending,
        "pending_feedback_prompt_ids": pending_feedback_prompt_ids,
        "feedback_received_count": feedback_received_count,
        "feedback_consumed_count": feedback_consumed_count,
        "feedback_stale_count": feedback_stale_count,
        "feedback_superseded_count": feedback_superseded_count,
        "superseded_feedback_prompt_ids": superseded_prompt_ids,
        "hitl_lifecycle_log": hitl_lifecycle_log,
        "decision_ledger_summary": (
            decision_ledger.get("summary")
            if isinstance(decision_ledger, dict) and isinstance(decision_ledger.get("summary"), dict)
            else {}
        ),
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


def _terminal_classification(
    *,
    mapping_ready: bool,
    unresolved_dependency_items: list[dict[str, Any]],
    unresolved_ambiguity_items: list[dict[str, Any]],
    optional_only_remaining: bool,
    human_feedback_pending: bool,
    result_status: str,
) -> str:
    if mapping_ready:
        if optional_only_remaining:
            return "optional_quality_remaining_only"
        return "closure_achieved"
    if len(unresolved_dependency_items) > 0:
        return "blocked_dependency_evidence_missing"
    if human_feedback_pending:
        return "blocked_human_feedback_needed"
    if len(unresolved_ambiguity_items) > 0:
        return "blocked_mapping_ambiguity_unresolved"
    if result_status == "failed":
        return "blocked_execution_failed"
    return "blocked_no_safe_autonomous_move"
