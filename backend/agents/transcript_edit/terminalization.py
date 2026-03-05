from __future__ import annotations

from typing import Any

from .contracts import TranscriptEditAgentRunResult
from .decision_ledger import (
    closure_state_from_layers,
    derive_layer_statuses,
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


def terminal_summary(progress_log: list[dict[str, Any]], result: Any) -> dict[str, Any]:
    first_audit = None
    final_audit = None
    edits_applied = 0
    used_human_feedback = False
    decision_ledger = None
    for entry in progress_log:
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
        if event_type == "human_feedback" or phase in {"human_feedback_received", "human_feedback_reused"}:
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
    blocking_unresolved = any(bool(item.get("blocking")) for item in unresolved_requirements if isinstance(item, dict))
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
        **layer_statuses,
        "decision_ledger": decision_ledger_with_history,
        "closure_history": closure_history,
        "unresolved_closure_requirements": unresolved_requirements,
        "unresolved_optional_items": unresolved_optional_items,
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
