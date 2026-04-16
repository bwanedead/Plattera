from __future__ import annotations

from typing import Any


def normalize_continuity_journal_entry(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept the exact stored-row wrapper only as a narrow ergonomic alias."""
    keys = set(payload.keys())
    if keys in ({"author_payload"}, {"kernel_turn_index", "author_payload"}):
        author_payload = payload.get("author_payload")
        if isinstance(author_payload, dict) and author_payload:
            return dict(author_payload)
    return payload
