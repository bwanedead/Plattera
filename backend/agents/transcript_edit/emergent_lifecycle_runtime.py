"""Apply harness emergent work-board lifecycle updates after a resolver iteration (transcript_edit)."""
from __future__ import annotations

from typing import Any

from harness.work_board.lifecycle import (
    compute_emergent_state_after_resolver_move,
    count_tail_resolver_moves,
    edit_plan_has_ops,
    emergent_recency_rank,
    normalize_board_state,
    stamp_harness_lifecycle_domain,
)

from .loop_state import TranscriptEditLoopState
from .work_board_projection import HARNESS_EMERGENT_ITEM_PREFIX


def sync_focused_emergent_item_from_resolver_outcome(
    state: TranscriptEditLoopState,
    *,
    focus_key: str,
    move: str,
    resolver_outcome: dict[str, Any] | None,
    policy_signals: dict[str, Any] | None,
    now_epoch: int | None = None,
) -> dict[str, Any] | None:
    """Update focused emergent row; return compact observability dict if state changed."""
    fk = str(focus_key or "").strip().lower()
    if not fk.startswith(HARNESS_EMERGENT_ITEM_PREFIX):
        return None
    sig = policy_signals if isinstance(policy_signals, dict) else {}
    repeat = bool(sig.get("repeat_without_signal"))
    tail = count_tail_resolver_moves(
        state.continuity_log,
        decision_key=fk,
        move="gather_more_evidence",
    )
    has_ops = edit_plan_has_ops(resolver_outcome if isinstance(resolver_outcome, dict) else None)
    new_items: list[dict[str, Any]] = []
    changed = False
    board_before = ""
    board_after = ""
    transition_reason = ""
    for row in list(state.harness_emergent_board_items or []):
        if not isinstance(row, dict):
            continue
        if str(row.get("item_id") or "").strip().lower() != fk:
            new_items.append(dict(row))
            continue
        cur_before = normalize_board_state(str(row.get("state") or "open"))
        board_before = cur_before
        nxt = compute_emergent_state_after_resolver_move(
            cur_before,
            move,
            repeat_without_signal=repeat,
            consecutive_gather_tail=tail,
            edit_plan_has_ops_flag=has_ops,
        )
        r2 = dict(row)
        if nxt is not None:
            r2["state"] = normalize_board_state(nxt)
            reason_code = f"resolver_move:{str(move or '').strip().lower()[:40]}"
            r2["domain_payload"] = stamp_harness_lifecycle_domain(
                r2.get("domain_payload") if isinstance(r2.get("domain_payload"), dict) else {},
                new_state=r2["state"],
                reason_code=reason_code,
            )
            changed = True
            board_after = str(r2["state"])
            transition_reason = reason_code
        else:
            board_after = cur_before
        new_items.append(r2)
    if not changed:
        return None
    state.harness_emergent_board_items = new_items
    row_for_rank = next(
        (dict(r) for r in new_items if isinstance(r, dict) and str(r.get("item_id") or "").strip().lower() == fk),
        {},
    )
    rec_rank = emergent_recency_rank(row_for_rank, now_epoch=now_epoch) if row_for_rank else None
    life = (
        (row_for_rank.get("domain_payload") or {}).get("harness_lifecycle")
        if isinstance(row_for_rank.get("domain_payload"), dict)
        else {}
    )
    life = life if isinstance(life, dict) else {}
    return {
        "event": "lifecycle_transition",
        "focus_target_kind": "harness_emergent",
        "board_item_id": fk,
        "board_state_before": board_before,
        "board_state_after": board_after,
        "board_transition_reason": transition_reason[:200],
        "board_recency_rank": rec_rank,
        "harness_lifecycle_last_reason": str(life.get("last_transition_reason") or "")[:120] or None,
        "newly_promoted": False,
        "recently_touched": bool(rec_rank is not None and rec_rank == 0),
    }
