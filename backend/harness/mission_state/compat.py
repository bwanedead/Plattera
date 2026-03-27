"""Thin compatibility helpers for legacy organized-work envelopes.

These helpers recognize legacy shapes without depending on legacy package exports.
"""
from __future__ import annotations


LEGACY_WORK_BOARD_ENVELOPE_VERSION = "work_board.v1"


def envelope_is_legacy_work_board_envelope(obj: object) -> bool:
    if not isinstance(obj, dict):
        return False
    if str(obj.get("schema_version") or "") != LEGACY_WORK_BOARD_ENVELOPE_VERSION:
        return False
    return isinstance(obj.get("items"), list)
