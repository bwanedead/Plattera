from __future__ import annotations

from typing import Any

MAX_SPAN_COUNT = 6
MAX_SPAN_TEXT_CHARS = 320
MAX_IMAGE_RESULTS = 8
MAX_IMAGE_OBSERVED_TEXT_CHARS = 180
MAX_RECENT_ATTEMPTS = 6
MAX_ATTEMPT_REASON_CHARS = 120
MAX_FEEDBACK_VALUE_CHARS = 160
MAX_FEEDBACK_NOTE_CHARS = 240
MAX_MEMORY_SUMMARY_CHARS = 420
MAX_EXTERNAL_CONTEXT_INJECTIONS = 6
MAX_EXTERNAL_PAYLOAD_CHARS = 320


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
        max_items=MAX_RECENT_ATTEMPTS,
    )
    bounded_spans = _bounded_span_context(span_context)
    bounded_image = _bounded_image_verification(image_verification_payload=image_verification_payload, decision_key=key)
    bounded_feedback = _bounded_feedback(feedback=feedback, decision_key=key)
    external_injections = _bounded_external_context_injections(
        decision_ledger=decision_ledger,
        decision_key=key,
    )
    return {
        "decision_key": key,
        "ledger_item": ledger_item or {},
        "closure_requirement": closure_requirement,
        "source_transcript_ref": source_transcript_ref,
        "source_transcript_hash": source_transcript_hash,
        "span_context": bounded_spans,
        "image_verification": bounded_image,
        "feedback": bounded_feedback,
        "external_context_injections": external_injections,
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
        matched.append(
            {
                "decision_key": decision_key,
                "move": str(entry.get("move") or "").strip()[:40],
                "outcome": str(entry.get("outcome") or "").strip()[:MAX_ATTEMPT_REASON_CHARS],
                "evidence_kind": str(entry.get("evidence_kind") or "").strip()[:40] or None,
            }
        )
    return matched[-max_items:]


def _memory_summary(recent_attempts: list[dict[str, Any]]) -> str:
    if not recent_attempts:
        return "No recent attempts recorded for this focus item."
    latest = recent_attempts[-1]
    move = str(latest.get("move") or "unknown_move")
    outcome = str(latest.get("outcome") or "unknown_outcome")
    summary = f"Recent focus history: last move={move}, outcome={outcome}, total_recent={len(recent_attempts)}."
    return summary[:MAX_MEMORY_SUMMARY_CHARS]


def _bounded_span_context(span_context: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bounded: list[dict[str, Any]] = []
    for entry in span_context:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or entry.get("content") or "").strip()
        bounded.append(
            {
                "span_id": str(entry.get("span_id") or "").strip() or None,
                "text": text[:MAX_SPAN_TEXT_CHARS],
                "start_char": entry.get("start_char"),
                "end_char": entry.get("end_char"),
            }
        )
        if len(bounded) >= MAX_SPAN_COUNT:
            break
    return bounded


def _bounded_image_verification(
    *,
    image_verification_payload: dict[str, Any],
    decision_key: str,
) -> dict[str, Any]:
    payload = image_verification_payload if isinstance(image_verification_payload, dict) else {}
    out: dict[str, Any] = {
        "decision_key": decision_key,
        "summary": dict(payload.get("summary")) if isinstance(payload.get("summary"), dict) else {},
        "results": [],
    }
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    bounded_results: list[dict[str, Any]] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        bounded_results.append(
            {
                "decision_key": decision_key,
                "check_id": str(row.get("check_id") or "").strip(),
                "status": str(row.get("status") or "").strip().lower(),
                "confidence": str(row.get("confidence") or "").strip().lower(),
                "observed_text": str(row.get("observed_text") or "").strip()[:MAX_IMAGE_OBSERVED_TEXT_CHARS],
            }
        )
        if len(bounded_results) >= MAX_IMAGE_RESULTS:
            break
    out["results"] = bounded_results
    return out


def _bounded_feedback(*, feedback: dict[str, Any] | None, decision_key: str) -> dict[str, Any] | None:
    if not isinstance(feedback, dict):
        return None
    feedback_key = str(feedback.get("decision_key") or decision_key).strip().lower()
    return {
        "decision_key": feedback_key,
        "selected_value": str(feedback.get("selected_value") or "").strip()[:MAX_FEEDBACK_VALUE_CHARS],
        "choice": str(feedback.get("choice") or "").strip()[:MAX_FEEDBACK_VALUE_CHARS] or None,
        "note": str(feedback.get("note") or "").strip()[:MAX_FEEDBACK_NOTE_CHARS] or None,
        "prompt_id": str(feedback.get("prompt_id") or "").strip()[:120] or None,
        "metadata": dict(feedback.get("metadata")) if isinstance(feedback.get("metadata"), dict) else {},
    }


def _bounded_external_context_injections(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str,
) -> list[dict[str, Any]]:
    rows = decision_ledger.get("external_context_injections") if isinstance(decision_ledger, dict) else []
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    key = str(decision_key or "").strip().lower()
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_key = str(row.get("decision_key") or "").strip().lower()
        if key and row_key and row_key != key:
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        payload_summary = {
            "issue_summary": str(payload.get("issue_summary") or "").strip()[:MAX_EXTERNAL_PAYLOAD_CHARS] or None,
            "original_prompt_summary": str(payload.get("original_prompt_summary") or "").strip()[:MAX_EXTERNAL_PAYLOAD_CHARS] or None,
            "selected_choice": str(payload.get("selected_choice") or "").strip()[:MAX_EXTERNAL_PAYLOAD_CHARS] or None,
            "normalized_answer_summary": str(payload.get("normalized_answer_summary") or "").strip()[:MAX_EXTERNAL_PAYLOAD_CHARS] or None,
            "note": str(payload.get("note") or "").strip()[:MAX_EXTERNAL_PAYLOAD_CHARS] or None,
            "alternatives": [
                str(v).strip()[:MAX_EXTERNAL_PAYLOAD_CHARS]
                for v in list(payload.get("alternatives") or [])
                if str(v).strip()
            ][:6],
        }
        out.append(
            {
                "type": str(row.get("type") or "").strip().lower() or None,
                "ticket_id": str(row.get("ticket_id") or "").strip() or None,
                "decision_key": row_key or None,
                "lifecycle_state": str(row.get("lifecycle_state") or "").strip().lower() or None,
                "strength": str(row.get("strength") or "").strip().lower() or None,
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "answered_at": row.get("answered_at"),
                "integrated_at": row.get("integrated_at"),
                "relevance": str(row.get("relevance") or "").strip().lower() or None,
                "payload": payload_summary,
            }
        )
        if len(out) >= MAX_EXTERNAL_CONTEXT_INJECTIONS:
            break
    return out
