"""Transitional harness **decision ledger** shim over work-board contracts.

This module remains as compatibility surface during the work-board migration.
Canonical implementation lives in ``backend/harness/work_board/contracts.py``.
Use ``kind`` and ``domain_payload`` for domain-specific payloads; do not treat
this file as the source of new shared-harness doctrine.
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
