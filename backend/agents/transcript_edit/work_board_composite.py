"""Backward-compat name for the unified transcript-edit harness decision ledger envelope."""
from __future__ import annotations

from typing import Any

from .decision_ledger_adapter import build_transcript_edit_unified_decision_ledger


def transcript_edit_composite_work_board(
    *,
    decision_ledger: dict[str, Any],
    harness_emergent_board_items: list[dict[str, Any]] | None = None,
    harness_board_context_notes: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Deprecated name: use :func:`build_transcript_edit_unified_decision_ledger`."""
    return build_transcript_edit_unified_decision_ledger(
        decision_ledger=decision_ledger,
        harness_emergent_board_items=harness_emergent_board_items,
        harness_board_context_notes=harness_board_context_notes,
    )
