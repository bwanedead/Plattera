from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from .blocker_registry import (
    link_prompt_to_blocker,
    mark_feedback_received,
    mark_feedback_stale,
    supersede_prompt_link,
)
from .decision_ledger import (
    list_external_context_injections,
    mark_human_resolution_ticket_state,
    upsert_human_resolution_ticket,
)
from .hitl_feedback import (
    feedback_entry_signature,
    list_feedback_entries,
    normalize_feedback_response,
    poll_feedback_response,
)
from .loop_runtime import emit_progress
from .loop_state import TranscriptEditLoopState
from .state_projection import (
    derive_waiting_feedback_projection,
    sync_pending_feedback_cache_from_registry,
)
from .run_reporting import (
    human_feedback_consumed_payload,
    human_feedback_prompt_superseded_payload,
    human_feedback_received_payload,
    human_feedback_stale_payload,
    human_resolution_ticket_state_payload,
    ticker_payload,
)


def normalize_feedback_selected_value(*, decision_key: str, selected_value: str) -> str:
    key = str(decision_key or "").strip().lower()
    value = str(selected_value or "").strip().lower()
    if not value:
        return ""
    if key in {"range", "township", "section", "tie_distance"}:
        import re

        match = re.search(r"\b(\d{1,4})\b", value)
        if match:
            return f"{key}:{match.group(1)}"
    return f"{key}:{value}"


def stable_feedback_confirmation_count(
    *,
    hitl_lifecycle_log: list[dict[str, Any]],
    decision_key: str | None,
    selected_value: str | None,
) -> int:
    key = str(decision_key or "").strip().lower()
    normalized_target = normalize_feedback_selected_value(
        decision_key=key,
        selected_value=str(selected_value or ""),
    )
    if not key or not normalized_target:
        return 0
    count = 0
    for entry in reversed(hitl_lifecycle_log):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("phase") or "").strip().lower() != "human_feedback_consumed":
            continue
        entry_key = str(entry.get("decision_key") or "").strip().lower()
        if entry_key != key:
            continue
        entry_value = normalize_feedback_selected_value(
            decision_key=key,
            selected_value=str(entry.get("selected_value") or ""),
        )
        if entry_value == normalized_target:
            count += 1
            continue
        break
    return count


def latest_human_resolution_ticket(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str | None,
    lifecycle_states: set[str],
) -> dict[str, Any] | None:
    rows = list_external_context_injections(
        decision_ledger,
        decision_key=str(decision_key or "").strip().lower(),
        type_filter="human_resolution_ticket",
        lifecycle_states={str(v).strip().lower() for v in lifecycle_states if str(v).strip()},
    )
    if not rows:
        return None
    rows.sort(key=lambda row: int(row.get("updated_at") or row.get("created_at") or 0), reverse=True)
    return dict(rows[0]) if isinstance(rows[0], dict) else None


def feedback_payload_from_ticket(
    *,
    answered_ticket: dict[str, Any] | None,
    decision_key: str | None,
) -> dict[str, Any] | None:
    if not isinstance(answered_ticket, dict):
        return None
    payload = answered_ticket.get("payload") if isinstance(answered_ticket.get("payload"), dict) else {}
    selected_value = (
        str(payload.get("normalized_answer_summary") or "").strip()
        or str(payload.get("selected_choice") or "").strip()
    )
    if not selected_value:
        return None
    key = str(answered_ticket.get("decision_key") or decision_key or "").strip().lower()
    if not key:
        return None
    return {
        "decision_key": key,
        "selected_value": selected_value,
        "choice": str(payload.get("selected_choice") or "").strip() or None,
        "note": str(payload.get("note") or "").strip() or None,
        "prompt_id": str(answered_ticket.get("ticket_id") or "").strip() or None,
        "metadata": {"ticket_id": str(answered_ticket.get("ticket_id") or "").strip() or None},
    }


def feedback_payload_from_registry_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    decision_key = str(row.get("decision_key") or "").strip().lower()
    selected_value = str(row.get("feedback_value") or "").strip()
    if not decision_key or not selected_value:
        return None
    return {
        "decision_key": decision_key,
        "selected_value": selected_value,
        "choice": None,
        "note": str(row.get("feedback_note") or "").strip() or None,
        "prompt_id": str(row.get("linked_prompt_id") or "").strip() or None,
        "metadata": {
            "source": "blocker_registry",
            "blocker_id": str(row.get("blocker_id") or "").strip() or None,
        },
    }


def ticket_lifecycle_snapshot_for_key(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str | None,
) -> list[dict[str, Any]]:
    rows = list_external_context_injections(
        decision_ledger,
        decision_key=str(decision_key or "").strip().lower(),
        type_filter="human_resolution_ticket",
    )
    out: list[dict[str, Any]] = []
    for row in rows[:6]:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "ticket_id": str(row.get("ticket_id") or "").strip() or None,
                "decision_key": str(row.get("decision_key") or "").strip().lower() or None,
                "lifecycle_state": str(row.get("lifecycle_state") or "").strip().lower() or None,
                "strength": str(row.get("strength") or "").strip().lower() or None,
                "updated_at": row.get("updated_at"),
            }
        )
    return out


def active_ticket_snapshot(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str | None,
) -> dict[str, Any] | None:
    ticket = latest_human_resolution_ticket(
        decision_ledger=decision_ledger,
        decision_key=decision_key,
        lifecycle_states={"answered_unintegrated", "integration_attempted_failed", "integrated"},
    )
    if not isinstance(ticket, dict):
        return None
    return {
        "ticket_id": str(ticket.get("ticket_id") or "").strip() or None,
        "ticket_state": str(ticket.get("lifecycle_state") or "").strip().lower() or None,
        "ticket_strength": str(ticket.get("strength") or "").strip().lower() or None,
        "ticket_decision_key": str(ticket.get("decision_key") or "").strip().lower() or None,
        "answered_at": ticket.get("answered_at"),
        "integrated_at": ticket.get("integrated_at"),
        "injected_count": len(
            list_external_context_injections(
                decision_ledger,
                decision_key=str(decision_key or "").strip().lower(),
                type_filter="human_resolution_ticket",
            )
        ),
    }


def append_hitl_lifecycle_event(
    *,
    state: TranscriptEditLoopState,
    event: dict[str, Any],
) -> None:
    if not isinstance(event, dict):
        return
    state.hitl_lifecycle_log.append(event)
    if len(state.hitl_lifecycle_log) > 120:
        state.hitl_lifecycle_log = state.hitl_lifecycle_log[-120:]


def emit_ticket_lifecycle_transition(
    *,
    state: TranscriptEditLoopState,
    iterations: int,
    latest_refs: dict[str, Any],
    progress_cb: Callable[[dict[str, Any]], None] | None,
    ticket_id: str | None,
    decision_key: str | None,
    lifecycle_state: str,
    strength: str | None = "binding",
    relevance: str | None = None,
    reason: str | None = None,
) -> None:
    if not str(ticket_id or "").strip():
        return
    append_hitl_lifecycle_event(
        state=state,
        event={
            "iteration": iterations,
            "phase": f"ticket_{str(lifecycle_state or '').strip().lower() or 'unknown'}",
            "event_type": "human_resolution_ticket",
            "ticket_id": str(ticket_id or "").strip() or None,
            "decision_key": str(decision_key or "").strip().lower() or None,
            "lifecycle_state": str(lifecycle_state or "").strip().lower() or None,
            "strength": str(strength or "").strip().lower() or None,
            "relevance": str(relevance or "").strip().lower() or None,
            "reason": str(reason or "").strip() or None,
        },
    )
    emit_progress(
        progress_cb,
        human_resolution_ticket_state_payload(
            iteration=iterations,
            latest_refs=latest_refs,
            ticket_id=str(ticket_id or "").strip() or None,
            decision_key=str(decision_key or "").strip().lower() or None,
            lifecycle_state=str(lifecycle_state or "").strip().lower() or "unknown",
            strength=str(strength or "").strip().lower() or None,
            relevance=str(relevance or "").strip().lower() or None,
            reason=str(reason or "").strip() or None,
        ),
    )


def set_pending_feedback_prompt(
    *,
    state: TranscriptEditLoopState,
    feedback_prompt: dict[str, Any],
    decision_key: str,
    supersession_reason: str,
    iterations: int,
    latest_refs: dict[str, Any],
    progress_cb: Callable[[dict[str, Any]], None] | None,
    emit_ticket_lifecycle_transition_fn,
) -> None:
    sync_pending_feedback_cache_from_registry(state=state)
    new_prompt_id = str(feedback_prompt.get("prompt_id") or "").strip() or None
    old_prompt_id = str(state.pending_feedback_prompt_id or "").strip() or None
    if old_prompt_id and new_prompt_id and old_prompt_id != new_prompt_id:
        state.feedback_superseded_count += 1
        state.superseded_feedback_prompt_ids.add(old_prompt_id)
        state.decision_ledger = mark_human_resolution_ticket_state(
            ledger=state.decision_ledger,
            ticket_id=old_prompt_id,
            decision_key=decision_key,
            lifecycle_state="superseded",
            relevance="inactive",
        )
        emit_ticket_lifecycle_transition_fn(
            ticket_id=old_prompt_id,
            decision_key=decision_key,
            lifecycle_state="superseded",
            relevance="inactive",
            reason=supersession_reason,
        )
        superseded_event = {
            "iteration": iterations,
            "phase": "human_feedback_prompt_superseded",
            "event_type": "human_feedback_needed",
            "prompt_id": old_prompt_id,
            "replacement_prompt_id": new_prompt_id,
            "decision_key": decision_key,
            "reason": supersession_reason,
        }
        append_hitl_lifecycle_event(state=state, event=superseded_event)
        emit_progress(
            progress_cb,
            human_feedback_prompt_superseded_payload(
                iteration=iterations,
                latest_refs=latest_refs,
                superseded_prompt_id=old_prompt_id,
                replacement_prompt_id=new_prompt_id,
                decision_key=decision_key or None,
                reason=supersession_reason,
            ),
        )
        state.blocker_registry = supersede_prompt_link(
            registry=state.blocker_registry,
            decision_key=decision_key,
            old_prompt_id=old_prompt_id,
            new_prompt_id=new_prompt_id,
            reason=supersession_reason,
        )
    state.pending_feedback_prompt_id = new_prompt_id
    state.pending_feedback_prompt = feedback_prompt if isinstance(feedback_prompt, dict) else None
    state.pending_feedback_decision_key = decision_key or None
    state.pending_feedback_emitted_iteration = iterations
    if new_prompt_id:
        state.decision_ledger = upsert_human_resolution_ticket(
            ledger=state.decision_ledger,
            ticket_id=new_prompt_id,
            decision_key=decision_key,
            lifecycle_state="issued_waiting_feedback",
            strength="binding",
            payload={
                "issue_summary": str(feedback_prompt.get("line1") or "").strip(),
                "original_prompt_summary": str(feedback_prompt.get("line2") or "").strip(),
                "selected_choice": None,
                "normalized_answer_summary": None,
                "note": None,
                "alternatives": [
                    str(v).strip()
                    for v in list(feedback_prompt.get("choices") or [])
                    if str(v).strip()
                ][:6],
            },
            relevance="active",
        )
        state.blocker_registry = link_prompt_to_blocker(
            registry=state.blocker_registry,
            decision_key=decision_key,
            prompt_id=new_prompt_id,
            ticket_id=new_prompt_id,
            reason="hitl_prompt_issued",
        )
        sync_pending_feedback_cache_from_registry(state=state)
    append_hitl_lifecycle_event(
        state=state,
        event={
            "iteration": iterations,
            "phase": "human_feedback_needed",
            "event_type": "human_feedback_needed",
            "prompt_id": new_prompt_id,
            "decision_key": decision_key or None,
        },
    )


def drain_pending_feedback(
    *,
    state: TranscriptEditLoopState,
    checkpoint_label: str,
    viewer_run_id: str,
    iterations: int,
    latest_refs: dict[str, Any],
    progress_cb: Callable[[dict[str, Any]], None] | None,
    append_blocker_iteration_recap_fn,
    emit_ticket_lifecycle_transition_fn,
    list_feedback_entries_fn=list_feedback_entries,
    poll_feedback_response_fn=poll_feedback_response,
    feedback_entry_signature_fn=feedback_entry_signature,
    normalize_feedback_response_fn=normalize_feedback_response,
) -> dict[str, Any] | None:
    sync_pending_feedback_cache_from_registry(state=state)
    projection = derive_waiting_feedback_projection(
        blocker_registry=state.blocker_registry,
        fallback_prompt_id=state.pending_feedback_prompt_id,
        fallback_decision_key=state.pending_feedback_decision_key,
    )
    if not projection.get("pending_feedback_prompt_id"):
        return None
    pending_prompt_id = str(projection.get("pending_feedback_prompt_id") or "").strip()
    all_entries = list_feedback_entries_fn(run_id=viewer_run_id)
    if all_entries:
        for entry in all_entries:
            signature = feedback_entry_signature_fn(entry)
            if signature in state.feedback_entry_seen_keys:
                continue
            entry_prompt_id = str(entry.get("prompt_id") or "").strip()
            if not entry_prompt_id:
                continue
            if entry_prompt_id == pending_prompt_id:
                continue
            state.feedback_entry_seen_keys.add(signature)
            state.feedback_stale_count += 1
            stale_decision_key = (
                str(entry.get("metadata", {}).get("decision_key") or "").strip().lower()
                if isinstance(entry.get("metadata"), dict)
                else ""
            ) or str(state.pending_feedback_decision_key or "").strip().lower()
            stale_reason = (
                "superseded_prompt_reply"
                if entry_prompt_id in state.superseded_feedback_prompt_ids
                else "stale_prompt_reply"
            )
            if entry_prompt_id and stale_decision_key:
                state.decision_ledger = mark_human_resolution_ticket_state(
                    ledger=state.decision_ledger,
                    ticket_id=entry_prompt_id,
                    decision_key=stale_decision_key,
                    lifecycle_state="stale",
                    relevance="inactive",
                )
                emit_ticket_lifecycle_transition_fn(
                    ticket_id=entry_prompt_id,
                    decision_key=stale_decision_key,
                    lifecycle_state="stale",
                    relevance="inactive",
                    reason="stale_prompt_reply",
                )
                state.blocker_registry = mark_feedback_stale(
                    registry=state.blocker_registry,
                    decision_key=stale_decision_key,
                    prompt_id=entry_prompt_id,
                    reason=stale_reason,
                )
                sync_pending_feedback_cache_from_registry(state=state)
            stale_event = {
                "iteration": iterations,
                "phase": "human_feedback_stale",
                "event_type": "human_feedback",
                "prompt_id": entry_prompt_id,
                "active_prompt_id": pending_prompt_id,
                "reason": stale_reason,
            }
            append_hitl_lifecycle_event(state=state, event=stale_event)
            emit_progress(
                progress_cb,
                human_feedback_stale_payload(
                    iteration=iterations,
                    latest_refs=latest_refs,
                    prompt_id=entry_prompt_id,
                    active_prompt_id=pending_prompt_id,
                    reason=stale_reason,
                ),
            )
            append_blocker_iteration_recap_fn(
                action_attempted="consume_feedback",
                result="feedback_stale_ignored",
                decision_key=stale_decision_key,
                reason=stale_reason,
            )
    feedback_entry = poll_feedback_response_fn(
        run_id=viewer_run_id,
        prompt_id=pending_prompt_id,
    )
    if feedback_entry is None:
        return None
    signature = feedback_entry_signature_fn(feedback_entry)
    if signature in state.feedback_entry_seen_keys:
        return None
    state.feedback_entry_seen_keys.add(signature)
    state.feedback_received_count += 1
    append_hitl_lifecycle_event(
        state=state,
        event={
            "iteration": iterations,
            "phase": "human_feedback_received",
            "event_type": "human_feedback",
            "prompt_id": pending_prompt_id,
            "decision_key": state.pending_feedback_decision_key,
        },
    )
    emit_progress(
        progress_cb,
        human_feedback_received_payload(
            iteration=iterations,
            latest_refs=latest_refs,
            prompt_id=pending_prompt_id,
            feedback_entry=feedback_entry,
        ),
    )
    normalized_feedback = normalize_feedback_response_fn(
        feedback_entry=feedback_entry,
        prompt_id=pending_prompt_id,
        prompt_context=state.pending_feedback_prompt,
    )
    if not isinstance(normalized_feedback, dict):
        state.feedback_stale_count += 1
        state.blocker_registry = mark_feedback_stale(
            registry=state.blocker_registry,
            decision_key=str(state.pending_feedback_decision_key or "").strip().lower(),
            prompt_id=pending_prompt_id,
            reason="invalid_feedback_payload",
        )
        sync_pending_feedback_cache_from_registry(state=state)
        append_hitl_lifecycle_event(
            state=state,
            event={
                "iteration": iterations,
                "phase": "human_feedback_stale",
                "event_type": "human_feedback",
                "prompt_id": pending_prompt_id,
                "active_prompt_id": pending_prompt_id,
                "reason": "invalid_feedback_payload",
            },
        )
        emit_progress(
            progress_cb,
            human_feedback_stale_payload(
                iteration=iterations,
                latest_refs=latest_refs,
                prompt_id=pending_prompt_id,
                active_prompt_id=pending_prompt_id,
                reason="invalid_feedback_payload",
            ),
        )
        return None
    emit_progress(
        progress_cb,
        ticker_payload(
            iteration=iterations,
            phase="human_feedback_needed",
            message=f"Feedback received at {checkpoint_label}; incorporating into current iteration.",
            latest_refs=latest_refs,
        ),
    )
    active_prompt_context = (
        dict(state.pending_feedback_prompt)
        if isinstance(state.pending_feedback_prompt, dict)
        else {}
    )
    state.used_human_feedback = True
    state.feedback_consumed_count += 1
    state.pending_feedback_prompt_id = None
    state.pending_feedback_prompt = None
    state.pending_feedback_decision_key = None
    state.pending_feedback_emitted_iteration = None
    state.decision_ledger = upsert_human_resolution_ticket(
        ledger=state.decision_ledger,
        ticket_id=pending_prompt_id,
        decision_key=str(normalized_feedback.get("decision_key") or "").strip().lower(),
        lifecycle_state="answered_unintegrated",
        strength="binding",
        payload={
            "issue_summary": str(active_prompt_context.get("line1") or "").strip(),
            "original_prompt_summary": str(active_prompt_context.get("line2") or "").strip(),
            "selected_choice": str(normalized_feedback.get("choice") or "").strip() or None,
            "normalized_answer_summary": str(normalized_feedback.get("selected_value") or "").strip() or None,
            "note": str(normalized_feedback.get("note") or "").strip() or None,
            "alternatives": [
                str(v).strip()
                for v in list(active_prompt_context.get("choices") or [])
                if str(v).strip()
            ][:6],
        },
        answered_at=int(time.time()),
        relevance="active",
    )
    state.blocker_registry = mark_feedback_received(
        registry=state.blocker_registry,
        decision_key=str(normalized_feedback.get("decision_key") or "").strip().lower(),
        prompt_id=pending_prompt_id,
        feedback_value=str(normalized_feedback.get("selected_value") or "").strip() or None,
        feedback_note=str(normalized_feedback.get("note") or "").strip() or None,
        reason="feedback_received_for_pending_prompt",
    )
    sync_pending_feedback_cache_from_registry(state=state)
    emit_ticket_lifecycle_transition_fn(
        ticket_id=pending_prompt_id,
        decision_key=str(normalized_feedback.get("decision_key") or "").strip().lower(),
        lifecycle_state="answered_unintegrated",
        relevance="active",
        reason=checkpoint_label,
    )
    append_hitl_lifecycle_event(
        state=state,
        event={
            "iteration": iterations,
            "phase": "human_feedback_consumed",
            "event_type": "human_feedback",
            "prompt_id": pending_prompt_id,
            "decision_key": normalized_feedback.get("decision_key"),
            "selected_value": normalized_feedback.get("selected_value"),
        },
    )
    emit_progress(
        progress_cb,
        human_feedback_consumed_payload(
            iteration=iterations,
            latest_refs=latest_refs,
            prompt_id=pending_prompt_id,
            decision_key=str(normalized_feedback.get("decision_key") or "").strip() or None,
            selected_value=str(normalized_feedback.get("selected_value") or "").strip() or None,
        ),
    )
    return normalized_feedback


def apply_consumed_feedback(
    *,
    state: TranscriptEditLoopState,
    feedback_payload: dict[str, Any],
) -> dict[str, Any]:
    state.latest_feedback = feedback_payload
    state.evidence_signal_counter += 1
    state.no_progress_streak = 0
    state.last_progress_reason = "human_feedback_consumed"
    return feedback_payload
