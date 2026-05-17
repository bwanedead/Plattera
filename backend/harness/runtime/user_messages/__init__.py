"""Generic harness-owned user-to-agent message channel.

Mirrors the HITL exchange pattern but operates in the opposite direction:
HITL is agent-initiated (agent asks human, human answers); user messages are
user-initiated (operator/tester/UI/API injects a message into a running or
resumable run, agent receives it as durable context on the next turn).

Strictly harness mechanics — durable ledger, bounded text, resume persistence,
prompt projection, trace events, action-plan consumption acknowledgment.  The
harness preserves exact user text and accounts for delivery/consumption status;
the agent (and its domain) interpret the message and decide what state changes
to make.  No deterministic "truth override" or domain-specific repair logic
lives here.
"""

from __future__ import annotations

from .ledger import (
    UserMessageStatus,
    build_prompt_user_message_view,
    clamp_ledger as clamp_user_message_ledger,
    count_deferred,
    count_pending as count_pending_user_messages,
    count_consumed as count_consumed_user_messages,
    get_message,
    make_message_id,
    mark_consumed as mark_user_messages_consumed,
    mark_deferred as mark_user_messages_deferred,
    record_inbound as record_user_message_inbound,
    render_user_message_audit_view,
    validate_stored_user_message,
)
from .message_shape import normalize_user_message

__all__ = [
    "UserMessageStatus",
    "build_prompt_user_message_view",
    "clamp_user_message_ledger",
    "count_consumed_user_messages",
    "count_deferred",
    "count_pending_user_messages",
    "get_message",
    "make_message_id",
    "mark_user_messages_consumed",
    "mark_user_messages_deferred",
    "normalize_user_message",
    "record_user_message_inbound",
    "render_user_message_audit_view",
    "validate_stored_user_message",
]
