"""Generic harness work-board contracts (mission-agnostic organized work).

Domain loops project discovered work items onto this board; domain ontology
lives in extension payloads, not in harness-native field semantics.
"""

from __future__ import annotations

from .contracts import (
    WORK_BOARD_VERSION,
    WorkBoardItemState,
    new_work_board,
    work_board_item_dict,
)
from .emergence import (
    apply_work_board_changes,
    evaluate_add_item_promotion,
    normalize_work_board_change,
    normalize_work_board_changes_list,
)
from .recent_iteration_lane import build_recent_iteration_lane

__all__ = [
    "WORK_BOARD_VERSION",
    "WorkBoardItemState",
    "apply_work_board_changes",
    "build_recent_iteration_lane",
    "evaluate_add_item_promotion",
    "new_work_board",
    "normalize_work_board_change",
    "normalize_work_board_changes_list",
    "work_board_item_dict",
]
