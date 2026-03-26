"""Compatibility decision-ledger package.

Canonical shared-state naming now lives under ``harness.mission_state``.
This package remains a secondary compatibility surface for the legacy
organized-work wire shape and helper re-exports.
"""
from __future__ import annotations

from harness.work_board import (
    apply_work_board_changes,
    build_recent_iteration_lane,
    evaluate_add_item_promotion,
    normalize_work_board_change,
    normalize_work_board_changes_list,
)
from harness.work_board.contracts import WORK_BOARD_VERSION

from .contracts import (
    DECISION_LEDGER_ENVELOPE_VERSION,
    DecisionLedgerItemState,
    decision_ledger_item_dict,
    new_decision_ledger,
)

__all__ = [
    "DECISION_LEDGER_ENVELOPE_VERSION",
    "DecisionLedgerItemState",
    "WORK_BOARD_VERSION",
    "apply_work_board_changes",
    "build_recent_iteration_lane",
    "decision_ledger_item_dict",
    "evaluate_add_item_promotion",
    "new_decision_ledger",
    "normalize_work_board_change",
    "normalize_work_board_changes_list",
]


def envelope_is_unified_decision_ledger(obj: object) -> bool:
    """True if ``obj`` is a versioned harness ledger envelope (items list present)."""
    if not isinstance(obj, dict):
        return False
    if str(obj.get("schema_version") or "") != WORK_BOARD_VERSION:
        return False
    return isinstance(obj.get("items"), list)
