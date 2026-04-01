"""Opaque action identifiers for harness execution."""

from __future__ import annotations

ActionId = str


def normalize_action_id(raw: object) -> ActionId:
    value = str(raw).strip() if raw is not None else ""
    if not value:
        raise ValueError("action_id_required")
    return value

