"""Glue: unified harness decision ledger + continuity-first focus from loop state.

Keeps ``domain_pack.py`` slim while preserving the native/unified read seam for startup continuity.
"""
from __future__ import annotations

from typing import Any

from .decision_ledger_adapter import transcript_edit_unified_and_closure_read_from_loop_state
from .llm_startup_understanding import select_startup_focus_key
from .loop_state import TranscriptEditLoopState


def composite_work_board_from_loop_state(state: TranscriptEditLoopState) -> dict[str, Any]:
    unified, _ = transcript_edit_unified_and_closure_read_from_loop_state(state)
    return unified


def choose_investigation_fallback_focus_from_state(state: TranscriptEditLoopState) -> dict[str, Any]:
    selected_focus_key = (
        str(state.last_focus_key or "").strip().lower()
        or select_startup_focus_key(
            last_focus_key=state.last_focus_key,
            startup=(
                dict(state.llm_startup_understanding)
                if isinstance(state.llm_startup_understanding, dict)
                else None
            ),
        )
    )
    if not selected_focus_key:
        return {}
    focus_source = "continuity" if str(state.last_focus_key or "").strip() else "startup_understanding"
    return {
        "decision_key": selected_focus_key,
        "focus_source": focus_source,
        "focus_reason_code": "continuity_preserved" if focus_source == "continuity" else "startup_understanding",
    }
