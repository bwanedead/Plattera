from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.decision_ledger_focus import choose_investigation_focus
from backend.agents.transcript_edit.domain_pack_focus_wiring import (
    choose_investigation_fallback_focus_from_state,
    composite_work_board_from_loop_state,
)
from backend.agents.transcript_edit.loop_state import TranscriptEditLoopState
from backend.agents.transcript_edit.work_board_composite import transcript_edit_composite_work_board


def test_composite_and_fallback_match_inline_assembly() -> None:
    from backend.agents.transcript_edit.decision_ledger import initialize_decision_ledger

    ledger = initialize_decision_ledger()
    st = TranscriptEditLoopState(
        decision_ledger=ledger,
        harness_emergent_board_items=[],
        harness_board_context_notes={},
    )
    inline = transcript_edit_composite_work_board(
        decision_ledger=ledger,
        harness_emergent_board_items=[],
        harness_board_context_notes={},
    )
    assert composite_work_board_from_loop_state(st) == inline
    a = choose_investigation_focus(ledger, work_board=inline) or {}
    b = choose_investigation_fallback_focus_from_state(st)
    assert a == b
