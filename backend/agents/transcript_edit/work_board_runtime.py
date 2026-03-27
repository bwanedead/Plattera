"""Apply resolver-emitted resolution-item changes to transcript-edit loop state."""
from __future__ import annotations

from typing import Any

from harness.mission_state import apply_resolution_changes

from .loop_state import TranscriptEditLoopState
from .work_board_projection import project_decision_ledger_to_work_board


def apply_work_board_changes_from_resolver(
    *,
    state: TranscriptEditLoopState,
    decision_ledger: dict[str, Any],
    work_board_changes: list[dict[str, Any]],
) -> dict[str, Any]:
    projected = project_decision_ledger_to_work_board(decision_ledger)
    ledger_rows = [dict(x) for x in projected.get("items") or [] if isinstance(x, dict)]
    result = apply_resolution_changes(
        work_board_changes,
        decision_ledger=decision_ledger,
        emergent_items=list(state.harness_emergent_board_items or []),
        context_notes_by_item_id=dict(state.harness_board_context_notes or {}),
        projected_ledgers_items=ledger_rows,
    )
    state.harness_emergent_board_items = list(result.get("emergent_items") or [])
    state.harness_board_context_notes = dict(result.get("context_notes_by_item_id") or {})
    return result
