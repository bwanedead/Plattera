"""Bounded work-board note + lifecycle context for the active focus item (transcript_edit)."""
from __future__ import annotations

from typing import Any

from .decision_ledger_closure import unresolved_mapping_blocking_requirements
from .decision_ledger_scope import _ensure_ledger_shape
from .decision_ledger_focus import focus_authority_audit

MAX_FOCUS_NOTE_BODY = 200
MAX_LINKED_HINTS = 2
MAX_NOTES_ON_FOCUS = 3
MAX_LIFECYCLE_SUMMARY_CHARS = 200
_RECENT_TOUCH_SECONDS = 900
_NEW_PROMO_SECONDS = 900


def _row_by_item_id(work_board: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    iid = str(item_id or "").strip()
    if not iid:
        return None
    for row in list(work_board.get("items") or []):
        if isinstance(row, dict) and str(row.get("item_id") or "").strip() == iid:
            return dict(row)
    return None


def _mapping_blocking_by_key(decision_ledger: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _ensure_ledger_shape(decision_ledger if isinstance(decision_ledger, dict) else {})
    return {
        str(item.get("key") or ""): item
        for item in unresolved_mapping_blocking_requirements(normalized)
        if isinstance(item, dict)
    }


def build_work_board_focus_context_bundle(
    *,
    decision_key: str,
    focus_target_kind: str,
    active_work_item: dict[str, Any] | None,
    work_board: dict[str, Any],
    decision_ledger: dict[str, Any] | None = None,
    now_epoch: int | None = None,
) -> dict[str, Any]:
    """Focused notes (bounded), optional linked dependency notes, lifecycle posture (no full-board dump)."""
    key = str(decision_key or "").strip().lower()
    row = active_work_item if isinstance(active_work_item, dict) else None
    if not row and key:
        row = _row_by_item_id(work_board, key)

    focused_notes: list[dict[str, Any]] = []
    if isinstance(row, dict):
        for n in list(row.get("context_notes") or [])[:MAX_NOTES_ON_FOCUS]:
            if not isinstance(n, dict):
                continue
            body = str(n.get("body") or "").strip()[:MAX_FOCUS_NOTE_BODY]
            if not body:
                continue
            focused_notes.append(
                {
                    "body": body,
                    "intent": str(n.get("intent") or "").strip()[:64] or None,
                    "non_canonical": True,
                }
            )

    linked: list[dict[str, Any]] = []
    if isinstance(row, dict):
        for dep in list(row.get("dependencies") or [])[:8]:
            did = str(dep or "").strip()
            if not did or did == key:
                continue
            other = _row_by_item_id(work_board, did)
            if not isinstance(other, dict):
                continue
            notes = [n for n in list(other.get("context_notes") or []) if isinstance(n, dict)]
            if not notes:
                continue
            n0 = notes[0]
            body = str(n0.get("body") or "").strip()[:MAX_FOCUS_NOTE_BODY]
            if body:
                linked.append(
                    {
                        "item_id": did,
                        "body": body,
                        "intent": str(n0.get("intent") or "").strip()[:64] or None,
                        "non_canonical": True,
                    }
                )
            if len(linked) >= MAX_LINKED_HINTS:
                break

    dp = row.get("domain_payload") if isinstance(row, dict) and isinstance(row.get("domain_payload"), dict) else {}
    life = dp.get("harness_lifecycle") if isinstance(dp.get("harness_lifecycle"), dict) else {}
    bstate = str(row.get("state") or "").strip().lower() if isinstance(row, dict) else ""
    rc = str(row.get("resolution_condition") or "").strip()[:160] if isinstance(row, dict) else ""

    open_summary = ""
    if isinstance(row, dict):
        if bstate in {"resolved", "superseded"}:
            open_summary = "Board row is terminal; no further open work on this item."
        elif rc:
            open_summary = f"Open until: {rc}"
        elif bstate:
            open_summary = f"Open work item (board_state={bstate})."
        else:
            open_summary = "Open work item."

    recency_signal: dict[str, Any] | None = None
    newly_promoted = False
    recently_touched = False
    if now_epoch is not None and isinstance(row, dict):
        ts = int(now_epoch)
        la = int(life.get("last_event_at_epoch") or life.get("last_transition_at_epoch") or 0)
        cr = int(life.get("created_at_epoch") or 0)
        if la:
            recency_signal = {"seconds_since_last_board_event": max(0, ts - la)}
            recently_touched = max(0, ts - la) <= _RECENT_TOUCH_SECONDS
        elif cr:
            recency_signal = {"seconds_since_promoted": max(0, ts - cr)}
        if cr:
            newly_promoted = max(0, ts - cr) <= _NEW_PROMO_SECONDS

    mbk = _mapping_blocking_by_key(decision_ledger if isinstance(decision_ledger, dict) else None)
    auth = focus_authority_audit(mapping_blocking_by_key=mbk, winner=None)
    board_authority_mode = str(auth.get("mode") or "")

    ltr = str(life.get("last_transition_reason") or "").strip()
    lifecycle_transition_summary = None
    if ltr and bstate:
        lifecycle_transition_summary = f"{ltr[:80]} → state={bstate}"[:MAX_LIFECYCLE_SUMMARY_CHARS]

    return {
        "schema_version": "work_board_focus_context.v1",
        "focus_target_kind": str(focus_target_kind or "").strip() or "ledger_decision",
        "board_item_id": key or None,
        "board_authority_mode": board_authority_mode or None,
        "board_authority": auth,
        "newly_promoted": bool(newly_promoted),
        "recently_touched": bool(recently_touched),
        "lifecycle_transition_summary": lifecycle_transition_summary,
        "board_lifecycle": {
            "board_state": bstate or None,
            "harness_lifecycle": dict(life) if life else {},
            "resolution_condition_excerpt": rc or None,
        },
        "focused_context_notes": focused_notes,
        "linked_context_note_hints": linked,
        "open_work_summary": open_summary[:280] if open_summary else None,
        "recency_signal": recency_signal,
    }
