"""Canonical harness **decision ledger** contract (mission-agnostic organized work).

This is the intended single harness-owned surface for durable work items (including
domain-projected rows and harness-emergent rows). The wire envelope matches
``work_board.v1`` during migration; domain ontology never belongs in harness-native
field semantics—use ``kind`` and ``domain_payload`` only.

See also: ``backend/harness/work_board/contracts.py`` (implementation source).
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
