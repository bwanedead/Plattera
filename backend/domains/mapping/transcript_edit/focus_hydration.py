from __future__ import annotations

from typing import Any

from .focus_runtime import baseline_residual_from_unresolved, recent_image_evidence_attempt_count
from .work_board_read import board_is_mapping_blocking, board_materiality, board_state, generic_knowns_snapshot

MAX_RECENT_ATTEMPTS = 6
MAX_MEMORY_SUMMARY_CHARS = 420
MAX_IMAGE_ATTEMPTS_WINDOW = 8


def build_focus_support_state(
    *,
    decision_key: str,
    focus_source: str = "domain_pack_focus",
    focus_target_kind: str | None = None,
    active_item_id: str | None = None,
    last_focus_key: str | None = None,
    active_emergent_blocker: dict[str, Any] | None = None,
    ledger_item: dict[str, Any],
    closure_requirement: dict[str, Any],
    recent_attempts: list[dict[str, Any]],
    span_context: list[dict[str, Any]],
    image_verification: dict[str, Any],
    visual_evidence: dict[str, Any],
    feedback: dict[str, Any] | None,
    source_completeness: str,
    evidence_repeat_guard: dict[str, dict[str, Any]],
    evidence_signal_counter: int,
    board_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item_context = _item_context(
        decision_key=decision_key,
        ledger_item=ledger_item,
        closure_requirement=closure_requirement,
        recent_attempts=recent_attempts,
        memory_summary=_memory_summary(recent_attempts),
        source_completeness=source_completeness,
        board_item=board_item,
    )
    continuity_context = _continuity_context(
        decision_key=decision_key,
        focus_source=focus_source,
        focus_target_kind=focus_target_kind,
        active_item_id=active_item_id,
        last_focus_key=last_focus_key,
        active_emergent_blocker=active_emergent_blocker,
        recent_attempts=recent_attempts,
    )
    evidence_context = _evidence_context(
        decision_key=decision_key,
        recent_attempts=recent_attempts,
        span_context=span_context,
        image_verification=image_verification,
        visual_evidence=visual_evidence,
        feedback=feedback,
        source_completeness=source_completeness,
        evidence_repeat_guard=evidence_repeat_guard,
        evidence_signal_counter=evidence_signal_counter,
    )
    blocker_posture = _blocker_posture(
        decision_key=decision_key,
        closure_requirement=closure_requirement,
        recent_attempts=recent_attempts,
        evidence_context=evidence_context,
        evidence_repeat_guard=evidence_repeat_guard,
        evidence_signal_counter=evidence_signal_counter,
    )
    unresolved_questions = _unresolved_questions(closure_requirement)
    return {
        "investigation_brief": item_context,
        "item_context": item_context,
        "continuity_context": continuity_context,
        "evidence_context": evidence_context,
        "item_history": item_context.get("recent_attempts") if isinstance(item_context, dict) else [],
        "unresolved_questions": unresolved_questions,
        "blocker_posture": blocker_posture,
    }


def _item_context(
    *,
    decision_key: str,
    ledger_item: dict[str, Any],
    closure_requirement: dict[str, Any],
    recent_attempts: list[dict[str, Any]],
    memory_summary: str,
    source_completeness: str,
    board_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    residual = baseline_residual_from_unresolved(ledger_item) if ledger_item else {}
    open_questions = _unresolved_questions(closure_requirement)
    knowns = {
        "decision_key": decision_key,
        "state": str(ledger_item.get("state") or "unknown").strip().lower() or "unknown",
        "blocking": bool(ledger_item.get("blocking")),
        "mapping_blocking": bool(closure_requirement.get("mapping_blocking")),
        "scope_status": str(closure_requirement.get("scope_status") or "unknown").strip().lower() or "unknown",
        "selected_value": str(ledger_item.get("selected_value") or "").strip() or None,
        "alternatives": [
            str(value).strip()
            for value in list(ledger_item.get("alternatives") or [])
            if str(value).strip()
        ][:6],
        "evidence_refs": [
            str(value).strip()
            for value in list(ledger_item.get("evidence_refs") or [])
            if str(value).strip()
        ][:6],
    }
    if residual:
        knowns["residual"] = residual
    gwb = generic_knowns_snapshot(board_item) if isinstance(board_item, dict) else None
    if gwb:
        knowns["generic_work_board"] = gwb
    return {
        "role": "sticky_note",
        "purpose": "current_case_understanding",
        "source_completeness": source_completeness,
        "knowns": knowns,
        "open_questions": open_questions,
        "recent_attempts": recent_attempts[-MAX_RECENT_ATTEMPTS:],
        "memory_summary": memory_summary[:MAX_MEMORY_SUMMARY_CHARS],
        "editable": True,
        "canonical": False,
    }


def _continuity_context(
    *,
    decision_key: str,
    focus_source: str,
    focus_target_kind: str | None,
    active_item_id: str | None,
    last_focus_key: str | None,
    active_emergent_blocker: dict[str, Any] | None,
    recent_attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    resolved_active_item_id = str(active_item_id or decision_key or "").strip().lower() or None
    resolved_last_focus_key = str(last_focus_key or "").strip().lower() or None
    return {
        "role": "continuity_context",
        "purpose": "active_item_continuity",
        "active_item_id": resolved_active_item_id,
        "last_focus_key": resolved_last_focus_key,
        "focus_source": str(focus_source or "").strip().lower() or None,
        "focus_target_kind": str(focus_target_kind or "").strip().lower() or None,
        "recent_attempt_count": len(recent_attempts[-MAX_RECENT_ATTEMPTS:]),
        "active_emergent_blocker_id": (
            str((active_emergent_blocker or {}).get("blocker_id") or "").strip() or None
        ),
        "reopen_suggested": bool(resolved_last_focus_key and resolved_last_focus_key != resolved_active_item_id),
    }


def _evidence_context(
    *,
    decision_key: str,
    recent_attempts: list[dict[str, Any]],
    span_context: list[dict[str, Any]],
    image_verification: dict[str, Any],
    visual_evidence: dict[str, Any],
    feedback: dict[str, Any] | None,
    source_completeness: str,
    evidence_repeat_guard: dict[str, dict[str, Any]],
    evidence_signal_counter: int,
) -> dict[str, Any]:
    recent_image_attempts = recent_image_evidence_attempt_count(
        continuity_log=recent_attempts,
        decision_key=decision_key,
        window=MAX_IMAGE_ATTEMPTS_WINDOW,
    )
    repeat_signature = f"{str(decision_key or '').strip().lower()}|repeat"
    repeat_entry = evidence_repeat_guard.get(repeat_signature) if isinstance(evidence_repeat_guard, dict) else {}
    return {
        "role": "evidence_context",
        "purpose": "bounded_evidence_surface",
        "span_context": span_context[:6],
        "image_verification": dict(image_verification) if isinstance(image_verification, dict) else {},
        "visual_evidence": dict(visual_evidence) if isinstance(visual_evidence, dict) else {},
        "feedback": dict(feedback) if isinstance(feedback, dict) else None,
        "source_completeness": str(source_completeness or "unknown").strip().lower() or "unknown",
        "evidence_repeat_budget": int((repeat_entry or {}).get("count") or 0) if isinstance(repeat_entry, dict) else 0,
        "evidence_signal_counter": int(evidence_signal_counter or 0),
        "recent_image_attempts": int(recent_image_attempts or 0),
    }


def _blocker_posture(
    *,
    decision_key: str,
    closure_requirement: dict[str, Any],
    recent_attempts: list[dict[str, Any]],
    evidence_context: dict[str, Any],
    evidence_repeat_guard: dict[str, dict[str, Any]],
    evidence_signal_counter: int,
) -> dict[str, Any]:
    mapping_blocking = bool(closure_requirement.get("mapping_blocking"))
    source_state = str(evidence_context.get("source_completeness") or "unknown").strip().lower() or "unknown"
    recent_image_attempts = int(evidence_context.get("recent_image_attempts") or 0)
    repeat_entry = evidence_repeat_guard.get(f"{str(decision_key or '').strip().lower()}|repeat") if isinstance(evidence_repeat_guard, dict) else {}
    last_signal_counter = int((repeat_entry or {}).get("last_signal_counter") or 0) if isinstance(repeat_entry, dict) else 0
    current_signal_counter = int(evidence_signal_counter or 0)
    has_fresh_signal = bool(current_signal_counter > last_signal_counter or evidence_context.get("feedback"))
    cached_context_present = bool(
        evidence_context.get("span_context")
        or (evidence_context.get("image_verification") or {}).get("results")
        or evidence_context.get("visual_evidence")
        or evidence_context.get("feedback")
    )
    if mapping_blocking and source_state in {"unknown", "partial", "partial_truncated", "partial_missing_context"}:
        understanding_strength = "weak"
    elif mapping_blocking and (has_fresh_signal or cached_context_present):
        understanding_strength = "moderate"
    elif mapping_blocking:
        understanding_strength = "moderate"
    else:
        understanding_strength = "narrow"
    return {
        "decision_key": decision_key,
        "understanding_strength": understanding_strength,
        "needs_orientation": understanding_strength == "weak" and not bool(recent_attempts),
        "needs_inventory": understanding_strength == "weak" or (mapping_blocking and not has_fresh_signal),
        "has_new_signal": has_fresh_signal,
        "has_fresh_signal": has_fresh_signal,
        "cached_context_present": cached_context_present,
        "repeat_without_signal": bool(recent_image_attempts >= 2 and not has_fresh_signal),
        "recent_image_attempts": recent_image_attempts,
        "source_completeness": source_state,
        "current_signal_counter": current_signal_counter,
        "last_signal_counter": last_signal_counter,
    }


def _unresolved_questions(closure_requirement: dict[str, Any]) -> list[str]:
    open_questions = [
        str(closure_requirement.get("required_information") or "").strip(),
        str(closure_requirement.get("minimal_user_action") or "").strip(),
    ]
    return [question for question in open_questions if question]


def _memory_summary(recent_attempts: list[dict[str, Any]]) -> str:
    if not recent_attempts:
        return "No recent attempts recorded for this focus item."
    latest = recent_attempts[-1]
    move = str(latest.get("move") or "unknown_move")
    outcome = str(latest.get("outcome") or "unknown_outcome")
    summary = f"Recent focus history: last move={move}, outcome={outcome}, total_recent={len(recent_attempts)}."
    return summary[:MAX_MEMORY_SUMMARY_CHARS]
