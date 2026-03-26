"""Compatibility harness work-board surface.

Canonical shared-state naming now lives under ``harness.mission_state``.
Domain loops still project discovered work items through this legacy wire shape
for backward compatibility.
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
