"""Mechanical normalization for inbound user-to-agent message payloads.

Mirrors ``runtime/hitl/feedback_shape.py`` in shape and intent: bounds
adversarial or pathologically large payloads at admission so the user message
never floods ledger state, resume snapshots, trace events, prompt projection,
or audit rendering.

Truncation is mechanical and visible — when any field is shortened a
``_bounds`` block on the returned dict records which fields were truncated,
so downstream consumers (and the model reading prompt projections) cannot
mistake clipped text for complete user input.

Never interprets message meaning.  Never raises — defensive against arbitrary
payloads from the CLI/UI/API.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

_MAX_MESSAGE_ID_CHARS = 256
_MAX_SOURCE_CHARS = 64
_MAX_TEXT_CHARS = 8_192
_MAX_METADATA_JSON_CHARS = 32_768
_MAX_DEFER_REASON_CHARS = 400

# Canonical set of admission-time truncation markers.  Only these keys are
# carried forward across re-normalization passes; arbitrary keys in an inbound
# ``_bounds`` block are dropped to keep ledger entries small and predictable.
USER_MESSAGE_BOUND_KEYS: frozenset[str] = frozenset({
    "message_id_truncated",
    "source_truncated",
    "text_truncated",
    "metadata_truncated",
})


def normalize_user_message(raw: Any) -> dict[str, Any]:
    """Return a bounded copy of an inbound user message with truncation metadata.

    Sparse on input: only fields present in ``raw`` (or already normalized)
    appear in the output.  Recognized keys:

      - ``message_id``: string, max 256 chars
      - ``created_at_epoch_seconds``: int/float, preserved verbatim
      - ``source``: string, max 64 chars (cli|viewer|tester|api or similar)
      - ``text``: string, truncated to 8,192 chars (the meat of the message)
      - ``metadata``: dict, JSON-bounded to 32,768 chars (stub if over)
      - ``_bounds``: dict with per-field truncation flags — present iff any
        recognized field was truncated.

    Unknown fields are dropped — the canonical inbound shape is the union of
    the keys above plus ``_bounds``.
    """
    if not isinstance(raw, Mapping):
        return {}

    out: dict[str, Any] = {}
    bounds: dict[str, bool] = {}

    if "message_id" in raw:
        mid_raw = raw.get("message_id")
        if isinstance(mid_raw, str):
            s = mid_raw.strip()
            if s:
                if len(s) > _MAX_MESSAGE_ID_CHARS:
                    out["message_id"] = s[:_MAX_MESSAGE_ID_CHARS]
                    bounds["message_id_truncated"] = True
                else:
                    out["message_id"] = s

    if "created_at_epoch_seconds" in raw:
        ts = raw.get("created_at_epoch_seconds")
        if isinstance(ts, (int, float)) and not isinstance(ts, bool):
            out["created_at_epoch_seconds"] = ts

    if "source" in raw:
        src_raw = raw.get("source")
        if isinstance(src_raw, str):
            s = src_raw.strip()
            if s:
                if len(s) > _MAX_SOURCE_CHARS:
                    out["source"] = s[:_MAX_SOURCE_CHARS]
                    bounds["source_truncated"] = True
                else:
                    out["source"] = s

    if "text" in raw:
        text_raw = raw.get("text")
        if text_raw is None:
            out["text"] = ""
        elif isinstance(text_raw, str):
            if len(text_raw) > _MAX_TEXT_CHARS:
                out["text"] = text_raw[:_MAX_TEXT_CHARS]
                bounds["text_truncated"] = True
            else:
                out["text"] = text_raw
        else:
            # Coerce non-string scalars by stringifying — do not silently drop
            # the user's message.  Truncate the coerced form just in case.
            coerced = str(text_raw)
            if len(coerced) > _MAX_TEXT_CHARS:
                out["text"] = coerced[:_MAX_TEXT_CHARS]
                bounds["text_truncated"] = True
            else:
                out["text"] = coerced

    if "metadata" in raw:
        metadata_raw = raw.get("metadata")
        if metadata_raw is None:
            out["metadata"] = {}
        elif isinstance(metadata_raw, Mapping):
            bounded, was_truncated = _size_bound_metadata(dict(metadata_raw), _MAX_METADATA_JSON_CHARS)
            out["metadata"] = bounded
            if was_truncated:
                bounds["metadata_truncated"] = True
        else:
            out["metadata"] = {}

    # Preserve any admission-time truncation markers from earlier normalization
    # passes (defensive re-normalization at storage time, etc.).
    incoming_bounds = raw.get("_bounds")
    if isinstance(incoming_bounds, Mapping):
        for k, v in incoming_bounds.items():
            if k in USER_MESSAGE_BOUND_KEYS and v is True:
                bounds.setdefault(k, True)

    if bounds:
        out["_bounds"] = bounds

    return out


def clamp_defer_reason(value: Any) -> str | None:
    """Return a bounded defer reason string, or None when empty/invalid."""
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    if len(s) > _MAX_DEFER_REASON_CHARS:
        return s[:_MAX_DEFER_REASON_CHARS]
    return s


def _size_bound_metadata(d: dict[str, Any], max_json_chars: int) -> tuple[dict[str, Any], bool]:
    """Bound a metadata dict by JSON char count.  Mirrors feedback_shape."""
    try:
        raw = json.dumps(d, ensure_ascii=False, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return ({"_truncated": True, "_prefix": ""}, True)
    if len(raw) <= max_json_chars:
        return (d, False)
    return ({"_truncated": True, "_prefix": raw[:max_json_chars]}, True)
