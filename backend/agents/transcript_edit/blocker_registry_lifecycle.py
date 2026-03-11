from __future__ import annotations

import time
from typing import Any

from .blocker_archetypes import BLOCKER_ARCHETYPE_CATALOG
from .decision_ledger import unresolved_closure_requirements
from .blocker_registry_state import (
    _BLOCKING_CLASS_VALUES,
    _SCOPE_VALUES,
    _blocker_id_for_item,
    _counts_for_rows,
    _emergent_row_priority_key,
    _ensure_registry_shape,
    _find_latest_row_for_decision,
    _normalize_active_blocker,
    _row_from_unresolved_item,
    _row_sort_key,
    _sync_emergent_rows_from_legacy,
)

def apply_proposed_emergent_blocker_updates(
    *,
    registry: dict[str, Any] | None,
    blocker_updates: list[dict[str, Any]] | None,
    fallback_decision_key: str | None = None,
) -> dict[str, Any]:
    working = _ensure_registry_shape(
        registry=registry,
        run_id=None,
        session_id=None,
        source_transcript_ref=None,
    )
    updates = [dict(row) for row in list(blocker_updates or []) if isinstance(row, dict)]
    if not updates:
        return {
            "registry": working,
            "accepted": [],
            "rejected": [{"operation": None, "blocker_id": None, "reason": "empty_blocker_updates"}],
        }
    emergent = working.get("emergent") if isinstance(working.get("emergent"), dict) else {}
    rows = [dict(row) for row in list(emergent.get("rows") or []) if isinstance(row, dict)]
    now = int(time.time())
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, update in enumerate(updates):
        normalized, error = _normalize_proposed_update(
            update=update,
            rows=rows,
            fallback_decision_key=fallback_decision_key,
        )
        operation = str(update.get("operation") or "").strip().lower() or None
        blocker_id = str(update.get("blocker_id") or "").strip() or None
        if error is not None:
            rejected.append(
                {
                    "index": index,
                    "operation": operation,
                    "blocker_id": blocker_id,
                    "reason": error,
                }
            )
            continue
        op = str(normalized.get("operation") or "").strip().lower()
        if op == "add":
            row, error = _apply_emergent_add(normalized=normalized, rows=rows, now=now)
        elif op == "update":
            row, error = _apply_emergent_update(normalized=normalized, rows=rows, now=now)
        elif op == "resolve":
            row, error = _apply_emergent_resolve(normalized=normalized, rows=rows, now=now)
        elif op == "supersede":
            row, error = _apply_emergent_supersede(normalized=normalized, rows=rows, now=now)
        else:
            row, error = None, f"unsupported_operation:{op}"
        if error is not None:
            rejected.append(
                {
                    "index": index,
                    "operation": op,
                    "blocker_id": str(normalized.get("blocker_id") or "").strip() or None,
                    "reason": error,
                }
            )
            continue
        if isinstance(row, dict):
            accepted.append(
                {
                    "index": index,
                    "operation": op,
                    "blocker_id": str(row.get("blocker_id") or "").strip() or None,
                    "blocker_kind": str(row.get("blocker_kind") or "").strip() or None,
                    "blocking_class": str(row.get("blocking_class") or "").strip().lower() or None,
                    "state": str(row.get("state") or "").strip().lower() or None,
                }
            )
    emergent["rows"] = rows[-120:]
    active_row = next(
        (
            row
            for row in rows
            if str(row.get("state") or "").strip().lower() not in {"resolved", "superseded"}
        ),
        None,
    )
    emergent["active_blocker_id"] = str((active_row or {}).get("blocker_id") or "").strip() or None
    emergent["counts"] = _counts_for_rows(rows)
    history = [dict(row) for row in list(emergent.get("history") or []) if isinstance(row, dict)]
    history.append(
        {
            "timestamp_epoch_seconds": now,
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "active_blocker_id": emergent.get("active_blocker_id"),
        }
    )
    emergent["history"] = history[-120:]
    working["emergent"] = emergent
    working["updated_at"] = now
    return {
        "registry": working,
        "accepted": accepted,
        "rejected": rejected,
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
    _sync_emergent_rows_from_legacy(working)
    working["updated_at"] = int(time.time())
    return working

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
    _sync_emergent_rows_from_legacy(working)
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
    _sync_emergent_rows_from_legacy(working)
    working["updated_at"] = int(time.time())
    return working

def mark_feedback_stale(
    *,
    registry: dict[str, Any] | None,
    decision_key: str,
    prompt_id: str | None,
    reason: str,
) -> dict[str, Any]:
    working = _ensure_registry_shape(registry=registry, run_id=None, session_id=None, source_transcript_ref=None)
    row = _find_latest_row_for_decision(rows=list(working.get("rows") or []), decision_key=decision_key)
    if row is None:
        return working
    active_prompt = str(row.get("linked_prompt_id") or "").strip() or None
    stale_prompt = str(prompt_id or "").strip() or None
    if active_prompt and stale_prompt and active_prompt == stale_prompt:
        return working
    row["feedback_status"] = "stale"
    row["last_transition_reason"] = str(reason or "").strip() or "feedback_stale_ignored"
    row["updated_at"] = int(time.time())
    working["counts"] = _counts_for_rows(working["rows"])
    _sync_emergent_rows_from_legacy(working)
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
    blocker_delta: dict[str, Any] | None = None,
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
            "blocker_delta": (
                dict(blocker_delta)
                if isinstance(blocker_delta, dict)
                else {}
            ),
            "timestamp_epoch_seconds": int(time.time()),
        }
    )
    if len(history) > 120:
        del history[:-120]
    working["updated_at"] = int(time.time())
    return working

def _normalize_proposed_update(
    *,
    update: dict[str, Any],
    rows: list[dict[str, Any]],
    fallback_decision_key: str | None,
) -> tuple[dict[str, Any], str | None]:
    operation = str(update.get("operation") or "").strip().lower()
    if operation not in {"add", "update", "resolve", "supersede"}:
        return {}, "invalid_operation"
    blocker_id = str(update.get("blocker_id") or "").strip() or None
    blocker_kind = str(update.get("blocker_kind") or "").strip().lower() or None
    blocking_class = str(update.get("blocking_class") or "").strip().lower() or None
    scope_status = str(update.get("scope_status") or "").strip().lower() or None
    if scope_status not in _SCOPE_VALUES and scope_status is not None:
        return {}, "invalid_scope_status"
    reason = str(update.get("reason") or "").strip()
    evidence_summary = str(update.get("evidence_summary") or "").strip() or None
    resolution_condition = str(update.get("resolution_condition") or "").strip() or None
    title = str(update.get("title") or "").strip() or None
    source_impact = str(update.get("source_completeness_impact") or "").strip().lower() or "none"
    if source_impact not in {"none", "source_incomplete", "source_occluded", "unknown"}:
        return {}, "invalid_source_completeness_impact"
    candidate_values = [
        str(value).strip()
        for value in list(update.get("candidate_values") or [])
        if str(value).strip()
    ][:10]
    next_valid_actions = [
        str(value).strip().lower()
        for value in list(update.get("next_valid_actions") or [])
        if str(value).strip()
    ][:10]
    legacy_decision_key = (
        str(update.get("legacy_decision_key") or fallback_decision_key or "").strip().lower() or None
    )
    supersedes_blocker_id = str(update.get("supersedes_blocker_id") or "").strip() or None
    duplicate_rationale = str(update.get("duplicate_rationale") or "").strip() or None
    if operation == "add":
        if not blocker_kind:
            return {}, "missing_blocker_kind_for_add"
        kind_error = _validate_blocker_kind(blocker_kind=blocker_kind)
        if kind_error is not None:
            return {}, kind_error
        if not title:
            return {}, "missing_title_for_add"
        if not blocking_class or blocking_class not in _BLOCKING_CLASS_VALUES:
            return {}, "invalid_blocking_class_for_add"
        if not reason:
            return {}, "missing_reason_for_add"
    if operation == "update":
        if not blocker_id:
            return {}, "missing_blocker_id_for_update"
        if _find_emergent_row(rows=rows, blocker_id=blocker_id) is None:
            return {}, "update_target_blocker_not_found"
        if blocking_class is not None and blocking_class not in _BLOCKING_CLASS_VALUES:
            return {}, "invalid_blocking_class_for_update"
        if blocker_kind is not None:
            kind_error = _validate_blocker_kind(blocker_kind=blocker_kind)
            if kind_error is not None:
                return {}, kind_error
    if operation == "resolve":
        if not blocker_id:
            return {}, "missing_blocker_id_for_resolve"
        target = _find_emergent_row(rows=rows, blocker_id=blocker_id)
        if target is None:
            return {}, "resolve_target_blocker_not_found"
        if str(target.get("state") or "").strip().lower() in {"resolved", "superseded"}:
            return {}, "resolve_target_not_active"
    if operation == "supersede":
        if not blocker_id:
            return {}, "missing_blocker_id_for_supersede"
        if not supersedes_blocker_id:
            return {}, "missing_supersedes_blocker_id"
        if blocker_id == supersedes_blocker_id:
            return {}, "supersede_self_conflict"
        source_row = _find_emergent_row(rows=rows, blocker_id=blocker_id)
        old_row = _find_emergent_row(rows=rows, blocker_id=supersedes_blocker_id)
        if source_row is None or old_row is None:
            return {}, "supersede_target_blocker_not_found"
    return {
        "operation": operation,
        "blocker_id": blocker_id,
        "blocker_kind": blocker_kind,
        "title": title,
        "blocking_class": blocking_class,
        "reason": reason or None,
        "evidence_summary": evidence_summary,
        "candidate_values": candidate_values,
        "resolution_condition": resolution_condition,
        "next_valid_actions": next_valid_actions,
        "source_completeness_impact": source_impact,
        "scope_status": scope_status or "unknown",
        "supersedes_blocker_id": supersedes_blocker_id,
        "legacy_decision_key": legacy_decision_key,
        "duplicate_rationale": duplicate_rationale,
        "linked_ticket_id": str(update.get("linked_ticket_id") or "").strip() or None,
    }, None

def _apply_emergent_add(
    *,
    normalized: dict[str, Any],
    rows: list[dict[str, Any]],
    now: int,
) -> tuple[dict[str, Any] | None, str | None]:
    blocker_kind = str(normalized.get("blocker_kind") or "").strip().lower()
    title = str(normalized.get("title") or "").strip()
    duplicate = _find_duplicate_emergent(rows=rows, blocker_kind=blocker_kind, title=title)
    if duplicate is not None and not str(normalized.get("duplicate_rationale") or "").strip():
        return None, "duplicate_add_without_rationale"
    blocker_id = str(normalized.get("blocker_id") or "").strip()
    if blocker_id:
        if _find_emergent_row(rows=rows, blocker_id=blocker_id) is not None:
            return None, "add_blocker_id_already_exists"
    else:
        blocker_id = _generate_emergent_blocker_id(rows=rows, blocker_kind=blocker_kind)
    row = {
        "blocker_id": blocker_id,
        "blocker_kind": blocker_kind,
        "title": title,
        "blocking_class": str(normalized.get("blocking_class") or "").strip().lower(),
        "state": "open",
        "reason": str(normalized.get("reason") or "").strip() or None,
        "evidence_summary": normalized.get("evidence_summary"),
        "candidate_values": list(normalized.get("candidate_values") or []),
        "resolution_condition": normalized.get("resolution_condition"),
        "next_valid_actions": list(normalized.get("next_valid_actions") or []),
        "scope_status": str(normalized.get("scope_status") or "unknown").strip().lower() or "unknown",
        "source_completeness_impact": str(normalized.get("source_completeness_impact") or "none").strip().lower() or "none",
        "linked_ticket_id": normalized.get("linked_ticket_id"),
        "legacy_blocker_id": None,
        "legacy_decision_key": normalized.get("legacy_decision_key"),
        "created_at": now,
        "updated_at": now,
    }
    rows.append(row)
    return dict(row), None

def _apply_emergent_update(
    *,
    normalized: dict[str, Any],
    rows: list[dict[str, Any]],
    now: int,
) -> tuple[dict[str, Any] | None, str | None]:
    blocker_id = str(normalized.get("blocker_id") or "").strip()
    row = _find_emergent_row(rows=rows, blocker_id=blocker_id)
    if row is None:
        return None, "update_target_blocker_not_found"
    state = str(row.get("state") or "").strip().lower()
    if state in {"resolved", "superseded"}:
        return None, "update_target_not_active"
    fields_changed = 0
    for key in [
        "blocker_kind",
        "title",
        "blocking_class",
        "reason",
        "evidence_summary",
        "resolution_condition",
        "scope_status",
        "source_completeness_impact",
        "linked_ticket_id",
        "legacy_decision_key",
    ]:
        value = normalized.get(key)
        if value in {None, ""}:
            continue
        if row.get(key) == value:
            continue
        row[key] = value
        fields_changed += 1
    for key in ["candidate_values", "next_valid_actions"]:
        value = normalized.get(key)
        if not isinstance(value, list) or not value:
            continue
        row[key] = list(value)
        fields_changed += 1
    if fields_changed <= 0:
        return None, "update_no_mutation_fields"
    row["updated_at"] = now
    return dict(row), None

def _apply_emergent_resolve(
    *,
    normalized: dict[str, Any],
    rows: list[dict[str, Any]],
    now: int,
) -> tuple[dict[str, Any] | None, str | None]:
    blocker_id = str(normalized.get("blocker_id") or "").strip()
    row = _find_emergent_row(rows=rows, blocker_id=blocker_id)
    if row is None:
        return None, "resolve_target_blocker_not_found"
    state = str(row.get("state") or "").strip().lower()
    if state in {"resolved", "superseded"}:
        return None, "resolve_target_not_active"
    row["state"] = "resolved"
    if str(normalized.get("reason") or "").strip():
        row["reason"] = str(normalized.get("reason") or "").strip()
    row["updated_at"] = now
    return dict(row), None

def _apply_emergent_supersede(
    *,
    normalized: dict[str, Any],
    rows: list[dict[str, Any]],
    now: int,
) -> tuple[dict[str, Any] | None, str | None]:
    blocker_id = str(normalized.get("blocker_id") or "").strip()
    supersedes = str(normalized.get("supersedes_blocker_id") or "").strip()
    source = _find_emergent_row(rows=rows, blocker_id=blocker_id)
    target = _find_emergent_row(rows=rows, blocker_id=supersedes)
    if source is None or target is None:
        return None, "supersede_target_blocker_not_found"
    existing_superseder = str(target.get("superseded_by_blocker_id") or "").strip()
    if existing_superseder and existing_superseder != blocker_id:
        return None, "supersede_lineage_conflict"
    target_state = str(target.get("state") or "").strip().lower()
    if target_state in {"resolved", "superseded"}:
        return None, "supersede_target_not_active"
    target["state"] = "superseded"
    target["superseded_by_blocker_id"] = blocker_id
    target["updated_at"] = now
    if str(normalized.get("reason") or "").strip():
        source["reason"] = str(normalized.get("reason") or "").strip()
    source["updated_at"] = now
    return dict(source), None

def _find_emergent_row(*, rows: list[dict[str, Any]], blocker_id: str) -> dict[str, Any] | None:
    target = str(blocker_id or "").strip()
    if not target:
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("blocker_id") or "").strip() == target:
            return row
    return None

def _find_duplicate_emergent(
    *,
    rows: list[dict[str, Any]],
    blocker_kind: str,
    title: str,
) -> dict[str, Any] | None:
    normalized_kind = str(blocker_kind or "").strip().lower()
    normalized_title = str(title or "").strip().lower()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("state") or "").strip().lower() in {"resolved", "superseded"}:
            continue
        if str(row.get("blocker_kind") or "").strip().lower() != normalized_kind:
            continue
        if str(row.get("title") or "").strip().lower() != normalized_title:
            continue
        return row
    return None

def _generate_emergent_blocker_id(*, rows: list[dict[str, Any]], blocker_kind: str) -> str:
    base = str(blocker_kind or "custom").replace(":", "_").replace(" ", "_")
    base = "".join(ch for ch in base if ch.isalnum() or ch in {"_", "-"}).strip("_") or "custom"
    taken = {
        str(row.get("blocker_id") or "").strip()
        for row in rows
        if isinstance(row, dict) and str(row.get("blocker_id") or "").strip()
    }
    for idx in range(1, 1000):
        candidate = f"emergent:agent:{base}:{idx}"
        if candidate not in taken:
            return candidate
    return f"emergent:agent:{base}:{int(time.time())}"

def _validate_blocker_kind(*, blocker_kind: str) -> str | None:
    kind = str(blocker_kind or "").strip().lower()
    known_archetypes = {
        str(row.get("archetype_id") or "").strip().lower()
        for row in BLOCKER_ARCHETYPE_CATALOG
        if isinstance(row, dict) and str(row.get("archetype_id") or "").strip()
    }
    if kind in known_archetypes:
        return None
    if not kind.startswith("custom:"):
        return "invalid_blocker_kind_not_archetype_or_custom"
    suffix = kind.split("custom:", 1)[1].strip()
    if not suffix:
        return "invalid_custom_blocker_kind"
    if len(suffix) > 64:
        return "invalid_custom_blocker_kind"
    if any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_:-" for ch in suffix):
        return "invalid_custom_blocker_kind"
    return None
