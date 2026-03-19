"""Generic harness rules for emergent work-board row lifecycle (not domain truth).

Ledger-backed projection rows are owned by domain projection; this module applies
to durable harness-emergent rows (``harness:emergent:*``) only.
"""
from __future__ import annotations

import time
from typing import Any

# Terminal / low-motion states for focus progression (focus layer filters these out).
TERMINAL_STATES = frozenset({"resolved", "superseded"})

# Stable prefix for harness-owned emergent rows (matches transcript_edit projection).
EMERGENT_ITEM_ID_PREFIX = "harness:emergent:"

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


def normalize_board_state(raw: str | None) -> str:
    s = str(raw or "open").strip().lower()[:64]
    return s if s in _VALID_STATES else "open"


def count_tail_resolver_moves(
    continuity_log: list[dict[str, Any]] | None,
    *,
    decision_key: str,
    move: str,
    max_scan: int = 24,
) -> int:
    """Count trailing continuity rows for ``decision_key`` with the same ``move`` (most recent first)."""
    key = str(decision_key or "").strip().lower()
    m = str(move or "").strip().lower()
    if not key or not m:
        return 0
    n = 0
    for row in reversed(list(continuity_log or [])[-max_scan:]):
        if not isinstance(row, dict):
            continue
        if str(row.get("decision_key") or "").strip().lower() != key:
            break
        if str(row.get("move") or "").strip().lower() != m:
            break
        n += 1
    return n


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
    """Return a new board state for an emergent row, or None to leave unchanged."""
    cur = normalize_board_state(current_state)
    move = str(resolver_move or "").strip().lower()
    if cur in TERMINAL_STATES:
        return None

    if move == "mark_resolved_no_edit":
        return "resolved"
    if move == "mark_blocked":
        return "blocked"
    if move == "request_human_feedback":
        return "waiting_human" if cur != "waiting_human" else None

    if move == "gather_more_evidence":
        if cur == "open":
            return "investigating"
        if cur == "investigating" and repeat_without_signal and consecutive_gather_tail >= 2:
            return "blocked"
        return None

    if move == "apply_edit_plan":
        if edit_plan_has_ops_flag and cur not in TERMINAL_STATES:
            return "narrowed"
        return None

    return None


def is_allowed_manual_emergent_transition(old_state: str, new_state: str) -> bool:
    """Validate resolver-proposed ``update_item_state`` jumps (conservative)."""
    old = normalize_board_state(old_state)
    new = normalize_board_state(new_state)
    if old in TERMINAL_STATES:
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
    """Merge lifecycle stamps into ``domain_payload`` (copy)."""
    ts = int(now_epoch if now_epoch is not None else time.time())
    base = dict(domain_payload) if isinstance(domain_payload, dict) else {}
    prev = dict(base.get("harness_lifecycle")) if isinstance(base.get("harness_lifecycle"), dict) else {}
    created = int(prev.get("created_at_epoch") or ts)
    out = {
        **prev,
        "created_at_epoch": created,
        "last_event_at_epoch": ts,
        "last_transition_at_epoch": ts,
        "last_transition_reason": str(reason_code or "").strip()[:120] or "lifecycle",
        "board_state": normalize_board_state(new_state),
    }
    base["harness_lifecycle"] = out
    return base


def emergent_recency_rank(
    row: dict[str, Any],
    *,
    now_epoch: int | None = None,
    recent_seconds: int = 900,
    stale_seconds: int = 86400,
) -> int:
    """Lower is more salient (recently created or touched). Uses ``harness_lifecycle`` stamps."""
    ts = int(now_epoch if now_epoch is not None else time.time())
    dp = row.get("domain_payload") if isinstance(row.get("domain_payload"), dict) else {}
    life = dp.get("harness_lifecycle") if isinstance(dp.get("harness_lifecycle"), dict) else {}
    last_ev = int(life.get("last_event_at_epoch") or life.get("last_transition_at_epoch") or life.get("created_at_epoch") or 0)
    if not last_ev:
        return 2
    age = max(0, ts - last_ev)
    if age <= recent_seconds:
        return 0
    if age <= stale_seconds:
        return 1
    return 2
