from __future__ import annotations

from typing import Any


def derive_waiting_feedback_projection(
    *,
    blocker_registry: dict[str, Any] | None,
    fallback_prompt_id: str | None = None,
    fallback_decision_key: str | None = None,
) -> dict[str, Any]:
    registry = blocker_registry if isinstance(blocker_registry, dict) else {}
    rows = [row for row in list(registry.get("rows") or []) if isinstance(row, dict)]
    active_blocker_id = str(registry.get("active_blocker_id") or "").strip() or None

    waiting_rows = [
        row
        for row in rows
        if str(row.get("state") or "").strip().lower() == "waiting_feedback"
    ]
    waiting_owner = next(
        (
            row
            for row in waiting_rows
            if active_blocker_id
            and str(row.get("blocker_id") or "").strip() == active_blocker_id
        ),
        waiting_rows[0] if waiting_rows else None,
    )

    owner_prompt_id = str((waiting_owner or {}).get("linked_prompt_id") or "").strip() or None
    owner_decision_key = str((waiting_owner or {}).get("decision_key") or "").strip().lower() or None
    has_registry_rows = len(rows) > 0

    prompt_id = owner_prompt_id
    decision_key = owner_decision_key
    if not prompt_id and not has_registry_rows:
        prompt_id = str(fallback_prompt_id or "").strip() or None
    if not decision_key and not has_registry_rows:
        decision_key = str(fallback_decision_key or "").strip().lower() or None

    waiting_feedback = bool(waiting_owner) or (not has_registry_rows and bool(prompt_id))
    return {
        "pending_feedback_prompt_id": prompt_id,
        "pending_feedback_decision_key": decision_key,
        "waiting_feedback": waiting_feedback,
        "resumable": waiting_feedback,
        "waiting_feedback_owner": dict(waiting_owner) if isinstance(waiting_owner, dict) else None,
        "source": "blocker_registry" if has_registry_rows else "compat_fallback",
    }


def sync_pending_feedback_cache_from_registry(*, state: Any) -> None:
    registry = state.blocker_registry if isinstance(getattr(state, "blocker_registry", None), dict) else {}
    projection = derive_waiting_feedback_projection(
        blocker_registry=registry,
        fallback_prompt_id=getattr(state, "pending_feedback_prompt_id", None),
        fallback_decision_key=getattr(state, "pending_feedback_decision_key", None),
    )
    prior_prompt_id = str(getattr(state, "pending_feedback_prompt_id", "") or "").strip() or None
    next_prompt_id = projection.get("pending_feedback_prompt_id")

    state.pending_feedback_prompt_id = next_prompt_id
    state.pending_feedback_decision_key = projection.get("pending_feedback_decision_key")
    if not next_prompt_id:
        state.pending_feedback_prompt = None
        state.pending_feedback_emitted_iteration = None
    elif prior_prompt_id and prior_prompt_id != next_prompt_id:
        # Preserve cache only for the active prompt.
        state.pending_feedback_prompt = None


def should_convert_timeout_to_waiting_feedback(*, reason: str | None, state: Any) -> bool:
    reason_text = str(reason or "").strip().lower()
    if "budget_wall_time_exceeded" not in reason_text:
        return False
    projection = derive_waiting_feedback_projection(
        blocker_registry=(
            state.blocker_registry if isinstance(getattr(state, "blocker_registry", None), dict) else {}
        ),
        fallback_prompt_id=getattr(state, "pending_feedback_prompt_id", None),
        fallback_decision_key=getattr(state, "pending_feedback_decision_key", None),
    )
    return bool(projection.get("waiting_feedback"))
