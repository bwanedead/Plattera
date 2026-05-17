"""Canonical validation for the user-message-acknowledgment fields of an action plan.

Kept separate from ``action_plan_parser.py`` to preserve that file's hotspot
budget and to keep the user-message channel's parsing rules reviewable in one
place — mirrors ``hitl/request_shape.py`` for the HITL channel.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_MAX_USER_MESSAGE_ID_CHARS = 256
_MAX_USER_MESSAGE_DEFER_REASON_CHARS = 400


def validate_user_message_consumed_ids(raw: Any) -> tuple[str, ...]:
    """Coerce optional list of user-message ids to a clean tuple of strings.

    Raises ``ValueError`` on any malformed entry; the action-plan parser
    converts that into a repairable parse error so the LLM can fix the shape.
    """
    if raw is None:
        return ()
    if isinstance(raw, tuple):
        seq: list[Any] = list(raw)
    elif isinstance(raw, list):
        seq = raw
    else:
        raise ValueError("user_message_consumed_ids must be a JSON array of strings")
    out: list[str] = []
    for x in seq:
        if not isinstance(x, str) or not x.strip():
            raise ValueError("user_message_consumed_ids entries must be non-empty strings")
        s = x.strip()
        if len(s) > _MAX_USER_MESSAGE_ID_CHARS:
            raise ValueError("user_message_consumed_ids entry exceeds length limit")
        out.append(s)
    return tuple(out)


def validate_user_message_defers(raw: Any) -> tuple[dict[str, Any], ...]:
    """Coerce optional list of defer rows to a clean tuple of normalized dicts.

    Each row must be ``{"message_id": <non-empty string>, "reason": <non-empty string>}``.
    Both fields are bounded; longer values are rejected so the agent defers with
    concise reasoning.
    """
    if raw is None:
        return ()
    if isinstance(raw, tuple):
        seq: list[Any] = list(raw)
    elif isinstance(raw, list):
        seq = raw
    else:
        raise ValueError("user_message_defers must be a JSON array of objects")
    out: list[dict[str, Any]] = []
    for row in seq:
        if not isinstance(row, Mapping):
            raise ValueError("user_message_defers entries must be JSON objects")
        mid_raw = row.get("message_id")
        if not isinstance(mid_raw, str) or not mid_raw.strip():
            raise ValueError("user_message_defers.message_id must be a non-empty string")
        mid = mid_raw.strip()
        if len(mid) > _MAX_USER_MESSAGE_ID_CHARS:
            raise ValueError("user_message_defers.message_id exceeds length limit")
        reason_raw = row.get("reason")
        if not isinstance(reason_raw, str) or not reason_raw.strip():
            raise ValueError("user_message_defers.reason must be a non-empty string")
        reason = reason_raw.strip()
        if len(reason) > _MAX_USER_MESSAGE_DEFER_REASON_CHARS:
            raise ValueError("user_message_defers.reason exceeds length limit")
        out.append({"message_id": mid, "reason": reason})
    return tuple(out)
