"""Mechanical lifecycle transport for harness-emergent resolution items."""
from __future__ import annotations

import time
from typing import Any

TERMINAL_RESOLUTION_ITEM_STATES = frozenset({"resolved", "superseded"})
EMERGENT_RESOLUTION_ITEM_PREFIX = "harness:emergent:"

_VALID_STATES = frozenset(
    {
        "open",
        "investigating",
        "narrowed",
        "blocked",
        "waiting_human",
        "waiting_evidence",
        "answered_pending_integration",
        "resolved",
        "superseded",
    }
)


def normalize_resolution_item_state(raw: str | None) -> str:
    state = str(raw or "open").strip().lower()[:64]
    return state if state in _VALID_STATES else "open"


def count_tail_resolver_moves(
    continuity_log: list[dict[str, Any]] | None,
    *,
    decision_key: str,
    move: str,
    max_scan: int = 24,
) -> int:
    key = str(decision_key or "").strip().lower()
    normalized_move = str(move or "").strip().lower()
    if not key or not normalized_move:
        return 0
    count = 0
    for row in reversed(list(continuity_log or [])[-max_scan:]):
        if not isinstance(row, dict):
            continue
        if str(row.get("decision_key") or "").strip().lower() != key:
            break
        if str(row.get("move") or "").strip().lower() != normalized_move:
            break
        count += 1
    return count


def edit_plan_has_ops(resolver_outcome: dict[str, Any] | None) -> bool:
    if not isinstance(resolver_outcome, dict):
        return False
    plan = resolver_outcome.get("edit_plan")
    if not isinstance(plan, dict):
        return False
    ops = plan.get("ops")
    return isinstance(ops, list) and len(ops) > 0


def compute_emergent_state_after_resolver_move(
    current_state: str,
    resolver_move: str,
    *,
    repeat_without_signal: bool,
    consecutive_gather_tail: int,
    edit_plan_has_ops_flag: bool,
) -> str | None:
    current = normalize_resolution_item_state(current_state)
    move = str(resolver_move or "").strip().lower()
    _ = repeat_without_signal
    _ = consecutive_gather_tail
    if current in TERMINAL_RESOLUTION_ITEM_STATES:
        return None

    if move == "mark_resolved_no_edit":
        return "resolved"
    if move == "mark_blocked":
        return "blocked"
    if move == "request_human_feedback":
        return "waiting_human" if current != "waiting_human" else None
    if move == "gather_more_evidence":
        if current == "open":
            return "investigating"
        return None
    if move == "apply_edit_plan":
        if edit_plan_has_ops_flag and current not in TERMINAL_RESOLUTION_ITEM_STATES:
            return "narrowed"
        return None
    return None


def is_allowed_manual_emergent_transition(old_state: str, new_state: str) -> bool:
    old = normalize_resolution_item_state(old_state)
    new = normalize_resolution_item_state(new_state)
    if old in TERMINAL_RESOLUTION_ITEM_STATES:
        return False
    if new == old:
        return True
    if new == "superseded":
        return True
    if new == "resolved":
        return old in {"open", "investigating", "narrowed", "blocked", "waiting_human", "waiting_evidence"}
    if new == "blocked":
        return old in {"open", "investigating", "waiting_human", "narrowed"}
    if new == "investigating":
        return old in {"open", "blocked", "waiting_human", "narrowed"}
    return False


def stamp_harness_lifecycle_domain(
    domain_payload: dict[str, Any] | None,
    *,
    new_state: str,
    reason_code: str,
    now_epoch: int | None = None,
) -> dict[str, Any]:
    timestamp = int(now_epoch if now_epoch is not None else time.time())
    base = dict(domain_payload) if isinstance(domain_payload, dict) else {}
    previous = dict(base.get("harness_lifecycle")) if isinstance(base.get("harness_lifecycle"), dict) else {}
    created = int(previous.get("created_at_epoch") or timestamp)
    base["harness_lifecycle"] = {
        **previous,
        "created_at_epoch": created,
        "last_event_at_epoch": timestamp,
        "last_transition_at_epoch": timestamp,
        "last_transition_reason": str(reason_code or "").strip()[:120] or "lifecycle",
        "board_state": normalize_resolution_item_state(new_state),
    }
    return base


def emergent_recency_rank(
    row: dict[str, Any],
    *,
    now_epoch: int | None = None,
    recent_seconds: int = 900,
    stale_seconds: int = 86400,
) -> int:
    timestamp = int(now_epoch if now_epoch is not None else time.time())
    domain_payload = row.get("domain_payload") if isinstance(row.get("domain_payload"), dict) else {}
    lifecycle = domain_payload.get("harness_lifecycle") if isinstance(domain_payload.get("harness_lifecycle"), dict) else {}
    last_event = int(
        lifecycle.get("last_event_at_epoch")
        or lifecycle.get("last_transition_at_epoch")
        or lifecycle.get("created_at_epoch")
        or 0
    )
    if not last_event:
        return 2
    age = max(0, timestamp - last_event)
    if age <= recent_seconds:
        return 0
    if age <= stale_seconds:
        return 1
    return 2
