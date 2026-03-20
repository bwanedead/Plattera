"""Board-informed tie-break helpers for ledger-primary focus selection.

Used after ledger-primary sort keys; when ledger/board parity is broken, board
signals are not used for ordering. Global focus ordering (including emergent vs
ledger) is owned by ``decision_ledger_focus.choose_investigation_focus``.
"""
from __future__ import annotations

from typing import Any

from harness.work_board.lifecycle import emergent_recency_rank

from .work_board_read import board_materiality, board_state, ledger_board_parity

_BOARD_STATE_URGENCY: dict[str, int] = {
    "blocked": 0,
    "investigating": 1,
    "open": 2,
    "narrowed": 3,
    "resolved": 4,
}


def board_focus_sort_suffix(
    decision_key: str,
    ledger_item: dict[str, Any],
    board_item: dict[str, Any] | None,
) -> tuple[int, int, int]:
    """Tie-break key appended after ledger-primary sort keys (lower tuple is better)."""
    parity = ledger_board_parity(decision_key, ledger_item, board_item)
    parity_ok = bool(parity.get("identity_aligned")) and bool(parity.get("posture_aligned"))
    if not parity_ok:
        return (1, 0, 0)
    mat = board_materiality(board_item) or "low"
    mat_rank = 0 if mat == "high" else 1
    st = board_state(board_item) or ""
    state_urgency = _BOARD_STATE_URGENCY.get(st, 5)
    return (0, mat_rank, state_urgency)


def ledger_discovery_focus_sort_suffix(
    ledger_item: dict[str, Any],
    board_item: dict[str, Any] | None,
) -> tuple[int, int, int]:
    """Tie-break for discovery-native rows: do not apply ledger/board parity mismatch penalty.

    Seed checklist rows can drift from projection briefly; discovery-first rows must not be
    buried solely because parity checks are stricter than the material closure signal.
    """
    if not isinstance(board_item, dict):
        return (0, 1, 0)
    mat = board_materiality(board_item) or "low"
    mat_rank = 0 if mat == "high" else 1
    st = board_state(board_item) or ""
    state_urgency = _BOARD_STATE_URGENCY.get(st, 5)
    return (0, mat_rank, state_urgency)


def emergent_board_sort_suffix(
    board_row: dict[str, Any],
    *,
    now_epoch: int | None = None,
) -> tuple[int, int, int, int]:
    """Tie-break for harness-emergent board rows (no ledger parity; board-native only)."""
    rec = emergent_recency_rank(board_row, now_epoch=now_epoch)
    mat = board_materiality(board_row) or "low"
    mat_rank = 0 if mat == "high" else 1 if mat == "medium" else 2
    st = board_state(board_row) or ""
    return (rec, 0, mat_rank, _BOARD_STATE_URGENCY.get(st, 5))
