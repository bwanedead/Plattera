"""Mechanical normalization for inbound HITL feedback payloads.

Mirrors the outbound ``normalize_hitl_request`` in ``request_shape.py`` but for
the inbound side: bounds adversarial or pathologically large operator/UI
payloads before they enter durable harness state (transport queues, ledger,
trace events, prompt projection, resume snapshots).

Truncation is mechanical and visible — when any field is shortened, a
``_bounds`` block on the returned dict records which fields were truncated, so
downstream consumers (and the model reading prompt projections) cannot mistake
clipped feedback for complete text.

Never interprets feedback meaning.  Never raises — defensive against arbitrary
JSON from the feedback store.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

_MAX_CHOICE_CHARS = 16_384
_MAX_NOTE_CHARS = 16_384
_MAX_METADATA_JSON_CHARS = 32_768
_MAX_PROMPT_ID_CHARS = 256

# Canonical set of admission-time truncation markers.  Only these keys are
# carried forward across re-normalization passes; arbitrary keys in an inbound
# ``_bounds`` block are dropped to keep ledger entries small and predictable.
_ALLOWED_BOUND_KEYS: frozenset[str] = frozenset({
    "prompt_id_truncated",
    "choice_truncated",
    "note_truncated",
    "metadata_truncated",
})


def normalize_hitl_feedback(raw: Any) -> dict[str, Any]:
    """Return a bounded copy of inbound feedback with truncation metadata.

    Sparse on input: only fields actually present in ``raw`` (or already
    normalized) appear in the output.  Recognized keys:

      - ``prompt_id``: string, max 256 chars
      - ``choice``: string (or null), truncated to 16,384 chars
      - ``note``: string (or null), truncated to 16,384 chars
      - ``metadata``: dict, JSON-bounded to 32,768 chars (replaced by stub when over)
      - ``submitted_at_epoch_seconds``: int/float, preserved verbatim
      - ``_bounds``: dict with per-field truncation flags — present iff any
        recognized field was truncated.  Keys: ``prompt_id_truncated``,
        ``choice_truncated``, ``note_truncated``, ``metadata_truncated``.

    Unknown extra fields are dropped — the canonical inbound shape is the union
    of the keys above plus ``_bounds``.  This keeps ledger entries small and
    predictable across feedback-store implementations.
    """
    if not isinstance(raw, Mapping):
        return {}

    out: dict[str, Any] = {}
    bounds: dict[str, bool] = {}

    if "prompt_id" in raw:
        pid_raw = raw.get("prompt_id")
        if isinstance(pid_raw, str):
            s = pid_raw.strip()
            if s:
                if len(s) > _MAX_PROMPT_ID_CHARS:
                    out["prompt_id"] = s[:_MAX_PROMPT_ID_CHARS]
                    bounds["prompt_id_truncated"] = True
                else:
                    out["prompt_id"] = s

    if "choice" in raw:
        choice_raw = raw.get("choice")
        if choice_raw is None:
            out["choice"] = None
        elif isinstance(choice_raw, str):
            if len(choice_raw) > _MAX_CHOICE_CHARS:
                out["choice"] = choice_raw[:_MAX_CHOICE_CHARS]
                bounds["choice_truncated"] = True
            else:
                out["choice"] = choice_raw
        else:
            # Coerce non-string scalars (int/bool/float) by stringifying — the
            # feedback store should not normally send these, but we don't want
            # to drop the answer either.
            coerced = str(choice_raw)
            if len(coerced) > _MAX_CHOICE_CHARS:
                out["choice"] = coerced[:_MAX_CHOICE_CHARS]
                bounds["choice_truncated"] = True
            else:
                out["choice"] = coerced

    if "note" in raw:
        note_raw = raw.get("note")
        if note_raw is None:
            out["note"] = None
        elif isinstance(note_raw, str):
            if len(note_raw) > _MAX_NOTE_CHARS:
                out["note"] = note_raw[:_MAX_NOTE_CHARS]
                bounds["note_truncated"] = True
            else:
                out["note"] = note_raw
        else:
            out["note"] = None  # drop non-string note rather than corrupt the field

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

    if "submitted_at_epoch_seconds" in raw:
        sub = raw.get("submitted_at_epoch_seconds")
        if isinstance(sub, (int, float)) and not isinstance(sub, bool):
            out["submitted_at_epoch_seconds"] = sub

    # Preserve admission-time truncation markers from earlier normalization passes.
    # Without this, defensive re-normalization (e.g. ``record_inbound`` on already-
    # bounded data from ``hitl_poll_feedback_store``) would silently erase the
    # ``_bounds`` block: the second pass sees already-clipped short strings, finds
    # no new truncation, and emits no flags.  Only the canonical marker set is
    # carried forward — arbitrary keys in an adversarial or malformed inbound
    # ``_bounds`` block are dropped so attackers cannot smuggle large or unknown
    # keys into durable ledger state.
    incoming_bounds = raw.get("_bounds")
    if isinstance(incoming_bounds, Mapping):
        for k, v in incoming_bounds.items():
            if k in _ALLOWED_BOUND_KEYS and v is True:
                bounds.setdefault(k, True)

    if bounds:
        out["_bounds"] = bounds

    return out


def _size_bound_metadata(d: dict[str, Any], max_json_chars: int) -> tuple[dict[str, Any], bool]:
    """Bound a metadata dict by JSON char count.

    If the JSON serialization fits, returns ``(d, False)``.  Otherwise returns
    a sentinel stub ``({"_truncated": True, "_prefix": <first N chars>}, True)``
    so callers can still see *what* was sent without unbounded growth.
    """
    try:
        raw = json.dumps(d, ensure_ascii=False, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return ({"_truncated": True, "_prefix": ""}, True)
    if len(raw) <= max_json_chars:
        return (d, False)
    return ({"_truncated": True, "_prefix": raw[:max_json_chars]}, True)
