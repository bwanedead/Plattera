from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .blocker_registry import append_iteration_recap, blocker_registry_delta
from .focus_runtime import registry_row_for_decision_key
from .loop_runtime import emit_progress
from .run_reporting import ticker_payload


def append_blocker_iteration_recap(
    *,
    registry: dict[str, Any],
    before_registry: dict[str, Any],
    iteration: int,
    active_blocker_id: str | None,
    active_blocker_prior_state: str | None,
    action_attempted: str,
    result: str,
    decision_key: str | None,
    reason: str | None,
    selection_reason_code: str,
    latest_refs: dict[str, Any],
    progress_cb: Callable[[dict[str, Any]], None] | None,
) -> dict[str, Any]:
    row = registry_row_for_decision_key(
        registry=registry,
        decision_key=decision_key,
    )
    new_state = str((row or {}).get("state") or "").strip().lower() or None
    delta = blocker_registry_delta(
        before_registry=before_registry,
        after_registry=registry,
    )
    next_registry = append_iteration_recap(
        registry=registry,
        iteration=iteration,
        active_blocker_id=active_blocker_id,
        prior_state=active_blocker_prior_state,
        action_attempted=action_attempted,
        result=result,
        new_state=new_state,
        reason=reason,
        blocker_delta=delta,
    )
    emit_progress(
        progress_cb,
        ticker_payload(
            iteration=iteration,
            phase="blocker_registry_iteration",
            message=f"Blocker iteration recap: action={action_attempted}, result={result}.",
            latest_refs=latest_refs,
            detail={
                "active_blocker_id": active_blocker_id,
                "prior_state": active_blocker_prior_state,
                "decision_key": str(decision_key or "").strip().lower() or None,
                "new_state": new_state,
                "reason": str(reason or "").strip() or None,
                "counts": dict((next_registry or {}).get("counts") or {}),
                "selection_reason_code": selection_reason_code,
                "blocker_delta": delta,
            },
        ),
    )
    return next_registry
