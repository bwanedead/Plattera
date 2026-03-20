"""Glue: unified harness decision ledger + investigation fallback focus from loop state.

Keeps ``domain_pack.py`` slim; behavior matches passing **native** ``decision_ledger`` plus the
unified envelope to ``choose_investigation_focus`` (required for Phase 14 seed dormancy + composition).
"""
from __future__ import annotations

from typing import Any

from .decision_ledger_adapter import transcript_edit_unified_and_closure_read_from_loop_state
from .decision_ledger_focus import choose_investigation_focus
from .loop_state import TranscriptEditLoopState


def composite_work_board_from_loop_state(state: TranscriptEditLoopState) -> dict[str, Any]:
    unified, _ = transcript_edit_unified_and_closure_read_from_loop_state(state)
    return unified


def choose_investigation_fallback_focus_from_state(state: TranscriptEditLoopState) -> dict[str, Any]:
    unified = composite_work_board_from_loop_state(state)
    return choose_investigation_focus(state.decision_ledger, work_board=unified) or {}
