from __future__ import annotations

from typing import Any

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

def _max_iteration(events: list[dict[str, Any]]) -> int:
    max_it = 0
    for entry in events:
        if not isinstance(entry, dict):
            continue
        value = entry.get("iteration")
        if isinstance(value, int) and value > max_it:
            max_it = value
    return max_it
