"""Mechanical validation for generic LLM-authored ``hitl_request`` payloads.

The harness does not interpret semantic content; it only checks JSON shapes.
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

_MAX_MESSAGE_CHARS = 16_384
_MAX_CHOICES = 64
_MAX_CONTEXT_JSON_CHARS = 32_768
_MAX_OPAQUE_JSON_CHARS = 32_768
_MAX_PROMPT_ID_CHARS = 256


def normalize_hitl_request(raw: dict[str, Any], *, iteration: int) -> dict[str, Any]:
    """Return a normalized outbound HITL record or raise ``ValueError`` with a short reason."""
    if not isinstance(raw, dict):
        raise ValueError("hitl_request_not_object")
    msg = raw.get("message")
    if not isinstance(msg, str) or not str(msg).strip():
        raise ValueError("hitl_request_message_invalid")
    message = str(msg).strip()
    if len(message) > _MAX_MESSAGE_CHARS:
        message = message[:_MAX_MESSAGE_CHARS]

    ch = raw.get("choices")
    if ch is None:
        choices: list[Any] = []
    elif isinstance(ch, list):
        choices = list(ch)
    else:
        raise ValueError("hitl_request_choices_invalid")
    if len(choices) > _MAX_CHOICES:
        choices = choices[:_MAX_CHOICES]

    ctx = raw.get("context")
    if ctx is None:
        context: dict[str, Any] = {}
    elif isinstance(ctx, dict):
        context = dict(ctx)
    else:
        raise ValueError("hitl_request_context_invalid")

    op = raw.get("opaque_payload")
    if op is None:
        opaque: dict[str, Any] = {}
    elif isinstance(op, dict):
        opaque = dict(op)
    else:
        raise ValueError("hitl_request_opaque_payload_invalid")

    pid_raw = raw.get("prompt_id")
    if pid_raw is None or (isinstance(pid_raw, str) and not str(pid_raw).strip()):
        prompt_id = f"hitl-{uuid4().hex}"
    elif isinstance(pid_raw, str):
        prompt_id = _sanitize_prompt_id(pid_raw)
    else:
        raise ValueError("hitl_request_prompt_id_invalid")

    return {
        "prompt_id": prompt_id,
        "message": message,
        "choices": choices,
        "context": _size_bound_dict(context, _MAX_CONTEXT_JSON_CHARS),
        "opaque_payload": _size_bound_dict(opaque, _MAX_OPAQUE_JSON_CHARS),
        "issued_at_iteration": int(iteration),
    }


def _sanitize_prompt_id(s: str) -> str:
    t = str(s).strip()
    if not t or len(t) > _MAX_PROMPT_ID_CHARS:
        raise ValueError("hitl_request_prompt_id_invalid")
    if not re.match(r"^[\w.\-:+]+$", t):
        raise ValueError("hitl_request_prompt_id_invalid")
    return t


def _size_bound_dict(d: dict[str, Any], max_json_chars: int) -> dict[str, Any]:
    raw = json.dumps(d, ensure_ascii=False, default=str, sort_keys=True)
    if len(raw) <= max_json_chars:
        return d
    return {"_truncated": True, "_prefix": raw[:max_json_chars]}


def validate_hitl_consumed_prompt_ids(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, tuple):
        seq: list[Any] = list(raw)
    elif isinstance(raw, list):
        seq = raw
    else:
        raise ValueError("hitl_consumed_prompt_ids_invalid")
    out: list[str] = []
    for x in seq:
        if not isinstance(x, str) or not x.strip():
            raise ValueError("hitl_consumed_prompt_ids_invalid")
        s = x.strip()
        if len(s) > _MAX_PROMPT_ID_CHARS:
            raise ValueError("hitl_consumed_prompt_ids_invalid")
        out.append(s)
    return tuple(out)
