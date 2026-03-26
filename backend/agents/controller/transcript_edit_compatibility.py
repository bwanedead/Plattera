"""Transcript-edit compatibility residue for controller contracts.

This module makes the legacy transcript-edit action-id coupling explicit and
bounded. The controller still needs these ids for compatibility, but they are
not core deed-to-IR semantics.
"""

from __future__ import annotations

from agents.transcript_edit.execution_action_ids import (
    TX_APPLY_EDIT_PLAN,
    TX_AUDIT_TRANSCRIPT,
    TX_OPEN_TRANSCRIPT_SPANS,
    TX_ORIENT_AND_BASELINE,
    TX_PROMOTE_TRANSCRIPT_FOR_MAPPING,
    TX_SAVE_TRANSCRIPT_SPAN_SEEDS,
    TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
)


TRANSCRIPT_EDIT_COMPATIBILITY_ACTION_IDS = frozenset(
    {
        TX_AUDIT_TRANSCRIPT,
        TX_OPEN_TRANSCRIPT_SPANS,
        TX_ORIENT_AND_BASELINE,
        TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
        TX_SAVE_TRANSCRIPT_SPAN_SEEDS,
        TX_APPLY_EDIT_PLAN,
        TX_PROMOTE_TRANSCRIPT_FOR_MAPPING,
    }
)

