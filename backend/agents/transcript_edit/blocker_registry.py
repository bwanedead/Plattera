from __future__ import annotations

import time
from typing import Any

from .decision_ledger import unresolved_closure_requirements

_STATE_VALUES = {
    "open",
    "waiting_feedback",
    "answered_unintegrated",
    "resolved",
    "superseded",
}
_FEEDBACK_STATUS_VALUES = {"none", "pending", "received", "integrated", "stale", "superseded"}
_SCOPE_VALUES = {"in_target", "outside_target", "unknown"}
_ACTION_VALUES = {
    "request_hitl",
    "integrate_feedback",
    "gather_image_evidence",
    "apply_edit_plan",
    "mark_blocked_by_incomplete_source",
}


def initialize_blocker_registry(
    *,
    run_id: str,
    session_id: str,
    source_transcript_ref: str | None,
) -> dict[str, Any]:
    return {
        "version": 1,
        "run_id": str(run_id or "").strip() or None,
        "session_id": str(session_id or "").strip() or None,
        "source_transcript_ref": str(source_transcript_ref or "").strip() or None,
        "source_completeness": "unknown",
        "target_scope_status": "not_attempted",
        "active_blocker_id": None,
        "counts": _counts_empty(),
        "rows": [],
        "history": [],
        "updated_at": int(time.time()),
    }


def sync_registry_from_ledger(
    *,
    registry: dict[str, Any] | None,
    decision_ledger: dict[str, Any] | None,
    run_id: str | None = None,
    session_id: str | None = None,
    source_transcript_ref: str | None = None,
) -> dict[str, Any]:
    working = _ensure_registry_shape(
        registry=registry,
        run_id=run_id,
        session_id=session_id,
        source_transcript_ref=source_transcript_ref,
    )
    ledger = decision_ledger if isinstance(decision_ledger, dict) else {}
    unresolved = [
        row for row in unresolved_closure_requirements(ledger) if isinstance(row, dict)
    ]
    unresolved_ids: set[str] = set()
    by_id = {
        str(row.get("blocker_id") or "").strip(): row
        for row in list(working.get("rows") or [])
        if isinstance(row, dict) and str(row.get("blocker_id") or "").strip()
    }
    rows_out: list[dict[str, Any]] = []
    for item in unresolved:
        blocker_id = _blocker_id_for_item(item)
        unresolved_ids.add(blocker_id)
        previous = by_id.get(blocker_id, {})
        merged = _row_from_unresolved_item(
            item=item,
            prior=previous,
            source_completeness=str(ledger.get("source_completeness") or "unknown").strip().lower(),
            source_limitations=[
                str(v).strip()
                for v in list(ledger.get("source_limitations") or [])
                if str(v).strip()
            ][:8],
        )
        rows_out.append(merged)

    # Keep historical rows and explicitly mark unresolved rows that disappeared as resolved.
    for row in by_id.values():
        if not isinstance(row, dict):
            continue
        blocker_id = str(row.get("blocker_id") or "").strip()
        if not blocker_id or blocker_id in unresolved_ids:
            continue
        state = str(row.get("state") or "").strip().lower()
        if state in {"resolved", "superseded"}:
            rows_out.append(dict(row))
            continue
        resolved = dict(row)
        resolved["state"] = "resolved"
        resolved["feedback_status"] = (
            "integrated"
            if str(row.get("feedback_status") or "").strip().lower() in {"received", "pending", "integrated"}
            else "none"
        )
        resolved["next_valid_actions"] = []
        resolved["last_transition_reason"] = "unresolved_item_cleared_in_ledger"
        resolved["updated_at"] = int(time.time())
        rows_out.append(resolved)

    working["run_id"] = str(run_id or working.get("run_id") or "").strip() or None
    working["session_id"] = str(session_id or working.get("session_id") or "").strip() or None
    if source_transcript_ref:
        working["source_transcript_ref"] = str(source_transcript_ref).strip() or None
    working["source_completeness"] = str(ledger.get("source_completeness") or "unknown").strip().lower() or "unknown"
    scope_summaries = ledger.get("scope_summaries") if isinstance(ledger.get("scope_summaries"), dict) else {}
    working["target_scope_status"] = str((scope_summaries.get("target_scope") or {}).get("scope_closure_state") or "not_attempted")
    rows_out.sort(key=_row_sort_key)
    working["rows"] = rows_out[-80:]
    _normalize_active_blocker(working)
    working["counts"] = _counts_for_rows(working["rows"])
    working["updated_at"] = int(time.time())
    return working


def select_primary_blocker(registry: dict[str, Any] | None) -> dict[str, Any] | None:
    working = _ensure_registry_shape(registry=registry, run_id=None, session_id=None, source_transcript_ref=None)
    candidates = [row for row in list(working.get("rows") or []) if isinstance(row, dict) and _is_operationally_active(row)]
    if not candidates:
        return None
    candidates.sort(key=_row_priority_key)
    return dict(candidates[0])


def link_prompt_to_blocker(
    *,
    registry: dict[str, Any] | None,
    decision_key: str,
    prompt_id: str,
    ticket_id: str | None,
    reason: str,
) -> dict[str, Any]:
    working = _ensure_registry_shape(registry=registry, run_id=None, session_id=None, source_transcript_ref=None)
    row = _find_latest_row_for_decision(
        rows=[r for r in list(working.get("rows") or []) if isinstance(r, dict)],
        decision_key=decision_key,
    )
    if row is None:
        return working
    row["state"] = "waiting_feedback"
    row["linked_prompt_id"] = str(prompt_id or "").strip() or None
    row["linked_ticket_id"] = str(ticket_id or prompt_id or "").strip() or None
    row["feedback_status"] = "pending"
    row["last_transition_reason"] = str(reason or "").strip() or "prompt_issued"
    row["updated_at"] = int(time.time())
    _normalize_active_blocker(working, preferred_blocker_id=str(row.get("blocker_id") or "").strip() or None)
    working["counts"] = _counts_for_rows(working["rows"])
    working["updated_at"] = int(time.time())
    return working


def supersede_prompt_link(
    *,
    registry: dict[str, Any] | None,
    decision_key: str,
    old_prompt_id: str,
    new_prompt_id: str,
    reason: str,
) -> dict[str, Any]:
    working = _ensure_registry_shape(registry=registry, run_id=None, session_id=None, source_transcript_ref=None)
    old_id = str(old_prompt_id or "").strip()
    if old_id:
        for row in list(working.get("rows") or []):
            if not isinstance(row, dict):
                continue
            if str(row.get("decision_key") or "").strip().lower() != str(decision_key or "").strip().lower():
                continue
            if str(row.get("linked_prompt_id") or "").strip() != old_id:
                continue
            row["state"] = "superseded"
            row["feedback_status"] = "superseded"
            row["last_transition_reason"] = str(reason or "").strip() or "prompt_superseded"
            row["updated_at"] = int(time.time())
    return link_prompt_to_blocker(
        registry=working,
        decision_key=decision_key,
        prompt_id=new_prompt_id,
        ticket_id=new_prompt_id,
        reason=reason or "prompt_superseded_reissue",
    )


def mark_feedback_received(
    *,
    registry: dict[str, Any] | None,
    decision_key: str,
    prompt_id: str | None,
    feedback_value: str | None,
    feedback_note: str | None,
    reason: str,
) -> dict[str, Any]:
    working = _ensure_registry_shape(registry=registry, run_id=None, session_id=None, source_transcript_ref=None)
    row = _find_latest_row_for_decision(rows=list(working.get("rows") or []), decision_key=decision_key)
    if row is None:
        return working
    incoming_prompt = str(prompt_id or "").strip() or None
    linked_prompt = str(row.get("linked_prompt_id") or "").strip() or None
    if linked_prompt and incoming_prompt and linked_prompt != incoming_prompt:
        row["feedback_status"] = "stale"
        row["last_transition_reason"] = "feedback_prompt_mismatch"
    else:
        row["state"] = "answered_unintegrated"
        row["feedback_status"] = "received"
        row["feedback_value"] = str(feedback_value or "").strip() or None
        row["feedback_note"] = str(feedback_note or "").strip() or None
        row["feedback_received_at"] = int(time.time())
        row["last_transition_reason"] = str(reason or "").strip() or "feedback_received"
    row["updated_at"] = int(time.time())
    _normalize_active_blocker(working, preferred_blocker_id=str(row.get("blocker_id") or "").strip() or None)
    working["counts"] = _counts_for_rows(working["rows"])
    working["updated_at"] = int(time.time())
    return working


def append_iteration_recap(
    *,
    registry: dict[str, Any] | None,
    iteration: int,
    active_blocker_id: str | None,
    prior_state: str | None,
    action_attempted: str | None,
    result: str | None,
    new_state: str | None,
    reason: str | None,
) -> dict[str, Any]:
    working = _ensure_registry_shape(registry=registry, run_id=None, session_id=None, source_transcript_ref=None)
    history = working.get("history")
    if not isinstance(history, list):
        history = []
        working["history"] = history
    history.append(
        {
            "iteration": int(iteration),
            "active_blocker_id": str(active_blocker_id or "").strip() or None,
            "prior_state": str(prior_state or "").strip().lower() or None,
            "action_attempted": str(action_attempted or "").strip().lower() or None,
            "result": str(result or "").strip().lower() or None,
            "new_state": str(new_state or "").strip().lower() or None,
            "reason": str(reason or "").strip() or None,
            "counts": dict(working.get("counts") or {}),
            "timestamp_epoch_seconds": int(time.time()),
        }
    )
    if len(history) > 120:
        del history[:-120]
    working["updated_at"] = int(time.time())
    return working


def registry_snapshot_for_payload(registry: dict[str, Any] | None) -> dict[str, Any]:
    working = _ensure_registry_shape(registry=registry, run_id=None, session_id=None, source_transcript_ref=None)
    return {
        "version": int(working.get("version") or 1),
        "run_id": working.get("run_id"),
        "session_id": working.get("session_id"),
        "source_transcript_ref": working.get("source_transcript_ref"),
        "source_completeness": working.get("source_completeness"),
        "target_scope_status": working.get("target_scope_status"),
        "active_blocker_id": working.get("active_blocker_id"),
        "counts": dict(working.get("counts") or {}),
        "rows": [dict(row) for row in list(working.get("rows") or []) if isinstance(row, dict)][:80],
        "history": [dict(row) for row in list(working.get("history") or []) if isinstance(row, dict)][-80:],
        "updated_at": int(working.get("updated_at") or int(time.time())),
    }


def _ensure_registry_shape(
    *,
    registry: dict[str, Any] | None,
    run_id: str | None,
    session_id: str | None,
    source_transcript_ref: str | None,
) -> dict[str, Any]:
    base = initialize_blocker_registry(
        run_id=str(run_id or "").strip() or None,
        session_id=str(session_id or "").strip() or None,
        source_transcript_ref=source_transcript_ref,
    )
    if not isinstance(registry, dict):
        return base
    out = dict(base)
    out["run_id"] = str(registry.get("run_id") or out["run_id"] or "").strip() or None
    out["session_id"] = str(registry.get("session_id") or out["session_id"] or "").strip() or None
    out["source_transcript_ref"] = str(registry.get("source_transcript_ref") or out["source_transcript_ref"] or "").strip() or None
    out["source_completeness"] = str(registry.get("source_completeness") or out["source_completeness"] or "unknown").strip().lower() or "unknown"
    out["target_scope_status"] = str(registry.get("target_scope_status") or out["target_scope_status"] or "not_attempted").strip().lower() or "not_attempted"
    out["active_blocker_id"] = str(registry.get("active_blocker_id") or "").strip() or None
    out["rows"] = [dict(row) for row in list(registry.get("rows") or []) if isinstance(row, dict)][-80:]
    out["history"] = [dict(row) for row in list(registry.get("history") or []) if isinstance(row, dict)][-120:]
    out["counts"] = _counts_for_rows(out["rows"])
    out["updated_at"] = int(registry.get("updated_at") or int(time.time()))
    return out


def _row_from_unresolved_item(
    *,
    item: dict[str, Any],
    prior: dict[str, Any],
    source_completeness: str,
    source_limitations: list[str],
) -> dict[str, Any]:
    now = int(time.time())
    closure = item.get("closure_requirement") if isinstance(item.get("closure_requirement"), dict) else {}
    decision_key = str(item.get("key") or "").strip().lower()
    scope_status = _normalize_scope_status(item, closure)
    prior_state = str(prior.get("state") or "").strip().lower()
    state = prior_state if prior_state in _STATE_VALUES else "open"
    if state in {"resolved", "superseded"}:
        # If the unresolved item still exists, reopen unless explicitly waiting for feedback.
        state = "waiting_feedback" if prior_state == "waiting_feedback" else "open"
    feedback_status = str(prior.get("feedback_status") or "").strip().lower()
    if feedback_status not in _FEEDBACK_STATUS_VALUES:
        feedback_status = "none"
    if state == "waiting_feedback":
        feedback_status = "pending"
    elif state == "answered_unintegrated":
        feedback_status = "received"
    elif state in {"resolved"} and feedback_status == "none":
        feedback_status = "integrated"
    if state == "answered_unintegrated":
        default_action = "integrate_feedback"
    else:
        default_action = "gather_image_evidence"
    actions = _normalize_actions(
        prior.get("next_valid_actions")
        if isinstance(prior.get("next_valid_actions"), list)
        else [default_action]
    )
    if state == "waiting_feedback":
        actions = []
    if state in {"open"} and "request_hitl" not in actions:
        actions = _normalize_actions(["request_hitl", *actions])
    if state == "answered_unintegrated":
        actions = _normalize_actions(["integrate_feedback", "apply_edit_plan", *actions])
    blocker_id = _blocker_id_for_item(item)
    row = {
        "blocker_id": blocker_id,
        "decision_key": decision_key,
        "scope_status": scope_status,
        "scope_proof": [str(v).strip().lower() for v in list(item.get("scope_proof") or closure.get("scope_proof") or []) if str(v).strip()][:6],
        "mapping_blocking": bool(item.get("mapping_blocking")),
        "state": state,
        "block_reason": str(closure.get("block_reason") or "").strip().lower() or "ambiguity",
        "required_information": str(closure.get("required_information") or "").strip() or None,
        "minimal_user_action": str(closure.get("minimal_user_action") or "").strip() or None,
        "current_evidence_summary": str(closure.get("attempt_summary") or "").strip() or None,
        "current_selected_value": item.get("selected_value"),
        "candidate_values": [str(v).strip() for v in list(item.get("alternatives") or []) if str(v).strip()][:8],
        "source_completeness": source_completeness,
        "source_limitations": source_limitations[:8],
        "next_valid_actions": actions,
        "linked_ticket_id": str(prior.get("linked_ticket_id") or "").strip() or None,
        "linked_prompt_id": str(prior.get("linked_prompt_id") or "").strip() or None,
        "feedback_status": feedback_status,
        "feedback_value": str(prior.get("feedback_value") or "").strip() or None,
        "feedback_note": str(prior.get("feedback_note") or "").strip() or None,
        "feedback_received_at": prior.get("feedback_received_at"),
        "integration_attempts": int(prior.get("integration_attempts") or 0),
        "last_transition_reason": str(prior.get("last_transition_reason") or "").strip() or "ledger_sync",
        "superseded_by_blocker_id": str(prior.get("superseded_by_blocker_id") or "").strip() or None,
        "created_at": int(prior.get("created_at") or now),
        "updated_at": now,
    }
    return row


def _blocker_id_for_item(item: dict[str, Any]) -> str:
    decision_key = str(item.get("key") or "").strip().lower() or "unknown"
    return f"blocker:{decision_key}"


def _normalize_scope_status(item: dict[str, Any], closure: dict[str, Any]) -> str:
    status = str(closure.get("scope_status") or item.get("scope_status") or "").strip().lower()
    if status in _SCOPE_VALUES:
        return status
    scope_id = str(item.get("scope_id") or "").strip().lower()
    if scope_id == "target_scope":
        return "in_target"
    if scope_id == "outside_target_scope":
        return "outside_target"
    return "unknown"


def _normalize_actions(values: list[Any]) -> list[str]:
    out: list[str] = []
    for value in values:
        action = str(value or "").strip().lower()
        if action not in _ACTION_VALUES:
            continue
        if action in out:
            continue
        out.append(action)
    return out[:6]


def _is_operationally_active(row: dict[str, Any]) -> bool:
    return str(row.get("state") or "").strip().lower() not in {"resolved", "superseded"}


def _row_priority_key(row: dict[str, Any]) -> tuple[int, int, int, int]:
    state = str(row.get("state") or "").strip().lower()
    scope = str(row.get("scope_status") or "").strip().lower()
    mapping_blocking = bool(row.get("mapping_blocking"))
    state_rank = {
        "answered_unintegrated": 0,
        "open": 1,
        "waiting_feedback": 2,
    }.get(state, 9)
    scope_rank = {"in_target": 0, "unknown": 1, "outside_target": 2}.get(scope, 3)
    blocking_rank = 0 if mapping_blocking else 1
    updated_rank = -int(row.get("updated_at") or 0)
    return (state_rank, scope_rank, blocking_rank, updated_rank)


def _row_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    active_rank = 0 if _is_operationally_active(row) else 1
    return (active_rank, str(row.get("blocker_id") or ""))


def _find_latest_row_for_decision(*, rows: list[dict[str, Any]], decision_key: str) -> dict[str, Any] | None:
    key = str(decision_key or "").strip().lower()
    matches = [
        row
        for row in rows
        if isinstance(row, dict) and str(row.get("decision_key") or "").strip().lower() == key
    ]
    if not matches:
        return None
    matches.sort(key=lambda row: int(row.get("updated_at") or row.get("created_at") or 0), reverse=True)
    return matches[0]


def _normalize_active_blocker(working: dict[str, Any], preferred_blocker_id: str | None = None) -> None:
    rows = [row for row in list(working.get("rows") or []) if isinstance(row, dict)]
    active = None
    preferred = str(preferred_blocker_id or "").strip()
    if preferred:
        for row in rows:
            if str(row.get("blocker_id") or "").strip() == preferred and _is_operationally_active(row):
                active = preferred
                break
    if active is None:
        candidate = select_primary_blocker(working)
        active = str((candidate or {}).get("blocker_id") or "").strip() or None
    working["active_blocker_id"] = active


def _counts_empty() -> dict[str, int]:
    return {
        "open": 0,
        "waiting_feedback": 0,
        "answered_unintegrated": 0,
        "resolved": 0,
        "superseded": 0,
        "total": 0,
    }


def _counts_for_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = _counts_empty()
    for row in rows:
        if not isinstance(row, dict):
            continue
        state = str(row.get("state") or "").strip().lower()
        if state not in counts:
            continue
        counts[state] = int(counts[state]) + 1
    counts["total"] = sum(
        int(v) for k, v in counts.items() if k != "total"
    )
    return counts
