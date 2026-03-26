"""Compatibility harness **decision ledger** shim over the legacy work-board wire shape.

New shared-state doctrine lives in ``harness.mission_state``. This package is
kept as a secondary compatibility surface for existing call sites and wire
shapes; it should not become the place where the canonical mission-state model
is redefined.
"""
from __future__ import annotations

from harness.work_board.contracts import (
    MAX_BOARD_CONTEXT_NOTES_PER_ITEM,
    MAX_CONTEXT_NOTE_BODY_CHARS,
    MAX_CONTEXT_NOTE_INTENT_CHARS,
    MAX_EMERGENT_PROPOSALS_PER_RESOLVER,
    MAX_EMERGENT_REASON_CHARS,
    MAX_EMERGENT_TITLE_CHARS,
    WORK_BOARD_VERSION as DECISION_LEDGER_ENVELOPE_VERSION,
    WorkBoardItemState as DecisionLedgerItemState,
    new_work_board as new_decision_ledger,
    work_board_item_dict as decision_ledger_item_dict,
)

__all__ = [
    "DECISION_LEDGER_ENVELOPE_VERSION",
    "DecisionLedgerItemState",
    "MAX_BOARD_CONTEXT_NOTES_PER_ITEM",
    "MAX_CONTEXT_NOTE_BODY_CHARS",
    "MAX_CONTEXT_NOTE_INTENT_CHARS",
    "MAX_EMERGENT_PROPOSALS_PER_RESOLVER",
    "MAX_EMERGENT_REASON_CHARS",
    "MAX_EMERGENT_TITLE_CHARS",
    "decision_ledger_item_dict",
    "new_decision_ledger",
]
