"""Glue: unified harness decision ledger + investigation fallback focus from loop state.

Keeps ``domain_pack.py`` slim; behavior matches inlining the unified ledger builder +
``choose_investigation_focus`` on that envelope.
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
    return choose_investigation_focus(unified) or {}
