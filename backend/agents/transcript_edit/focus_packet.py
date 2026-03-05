from __future__ import annotations

from typing import Any


def build_focus_packet(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str | None,
    source_transcript_ref: str | None,
    source_transcript_hash: str,
    span_context: list[dict[str, Any]],
    image_verification_payload: dict[str, Any],
    feedback: dict[str, Any] | None,
    continuity_log: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    key = str(decision_key or "").strip().lower()
    ledger_item = _ledger_item_for_key(decision_ledger=decision_ledger, decision_key=key)
    closure_requirement = (
        dict(ledger_item.get("closure_requirement"))
        if isinstance(ledger_item, dict) and isinstance(ledger_item.get("closure_requirement"), dict)
        else {}
    )
    attempts = _recent_attempts_for_key(
        continuity_log=continuity_log or [],
        decision_key=key,
        max_items=6,
    )
    return {
        "decision_key": key,
        "ledger_item": ledger_item or {},
        "closure_requirement": closure_requirement,
        "source_transcript_ref": source_transcript_ref,
        "source_transcript_hash": source_transcript_hash,
        "span_context": [s for s in span_context[:8] if isinstance(s, dict)],
        "image_verification": image_verification_payload if isinstance(image_verification_payload, dict) else {},
        "feedback": feedback if isinstance(feedback, dict) else None,
        "recent_attempts": attempts,
        "memory_summary": _memory_summary(attempts),
    }


def _ledger_item_for_key(*, decision_ledger: dict[str, Any], decision_key: str) -> dict[str, Any] | None:
    if not decision_key:
        return None
    items = decision_ledger.get("items") if isinstance(decision_ledger, dict) else []
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("key") or "").strip().lower() == decision_key:
            return dict(item)
    return None


def _recent_attempts_for_key(
    *,
    continuity_log: list[dict[str, Any]],
    decision_key: str,
    max_items: int,
) -> list[dict[str, Any]]:
    if not decision_key:
        return []
    matched: list[dict[str, Any]] = []
    for entry in continuity_log:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("decision_key") or "").strip().lower() != decision_key:
            continue
        matched.append(dict(entry))
    return matched[-max_items:]


def _memory_summary(recent_attempts: list[dict[str, Any]]) -> str:
    if not recent_attempts:
        return "No recent attempts recorded for this focus item."
    latest = recent_attempts[-1]
    move = str(latest.get("move") or "unknown_move")
    outcome = str(latest.get("outcome") or "unknown_outcome")
    return f"Recent focus history: last move={move}, outcome={outcome}, total_recent={len(recent_attempts)}."
