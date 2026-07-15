"""Opaque prompt carry-forward lane for structured retry context.

Domain/tool code authors ``outputs.prompt_carry_forward.payload``. The harness
transports it opaquely, bounds it mechanically, and projects it as a dedicated
structured field — never via JSON-prefix truncation of ``outputs_excerpt``.

Harness does not inspect payload field names or domain semantics.

Budget contract (mechanical):
- Dedicated object bound: ``DEFAULT_MAX_PROMPT_CARRY_FORWARD_CHARS``.
- Prompt slice collection bound: ``DEFAULT_MAX_TOTAL_CHARS`` in
  ``tool_result_slices`` is a hard combined cap on the compact-serialized
  emitted collection (base content + carry-forward), including JSON list
  brackets and inter-row commas. Carry is all-or-nothing: if the full object
  cannot fit the remaining combined budget, emit ``prompt_carry_forward_omitted``
  with reason ``prompt_budget`` rather than a partial object.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

PROMPT_CARRY_FORWARD_KEY = "prompt_carry_forward"
PROMPT_CARRY_FORWARD_SCHEMA_VERSION = "prompt_carry_forward.v1"
PROMPT_CARRY_FORWARD_OMITTED_KEY = "prompt_carry_forward_omitted"

# Dedicated mechanical bound for the structured object (serialized JSON chars).
DEFAULT_MAX_PROMPT_CARRY_FORWARD_CHARS = 8000


def wrap_prompt_carry_forward(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Domain helper: build the opaque envelope around an authored payload."""
    return {
        "schema_version": PROMPT_CARRY_FORWARD_SCHEMA_VERSION,
        "payload": dict(payload),
    }


def peel_prompt_carry_forward(
    outputs: Mapping[str, Any],
) -> tuple[Any | None, dict[str, Any]]:
    """Split ``prompt_carry_forward`` from other outputs without interpreting it.

    Also strips a prior ``prompt_carry_forward_omitted`` marker from the remainder
    so storage/projection can re-author a single authoritative lane.
    """
    remainder = {
        key: value
        for key, value in outputs.items()
        if str(key) not in {PROMPT_CARRY_FORWARD_KEY, PROMPT_CARRY_FORWARD_OMITTED_KEY}
    }
    return outputs.get(PROMPT_CARRY_FORWARD_KEY), remainder


def _serialize_len(value: Any) -> int | None:
    try:
        return len(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))
    except (TypeError, ValueError):
        return None


def _normalized_envelope(raw: Any) -> dict[str, Any] | None:
    """Accept only a structured object with schema_version + mapping payload."""
    if not isinstance(raw, Mapping):
        return None
    schema = str(raw.get("schema_version") or "").strip()
    payload = raw.get("payload")
    if not schema or not isinstance(payload, Mapping):
        return None
    return {
        "schema_version": schema,
        "payload": dict(payload),
    }


def project_prompt_carry_forward(
    outputs: Any,
    *,
    max_chars: int = DEFAULT_MAX_PROMPT_CARRY_FORWARD_CHARS,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Project carry-forward for prompt slices.

    Returns ``(carry_forward, omitted_marker)``. At most one is non-None.
    Oversized payloads are omitted entirely — never prefix-truncated into a
    partial structured object. A storage-authored omission marker is passed
    through when the carry object itself is absent.
    """
    if not isinstance(outputs, Mapping):
        return None, None
    raw = outputs.get(PROMPT_CARRY_FORWARD_KEY)
    if raw is None:
        existing_omitted = outputs.get(PROMPT_CARRY_FORWARD_OMITTED_KEY)
        if isinstance(existing_omitted, Mapping) and existing_omitted:
            return None, dict(existing_omitted)
        return None, None
    envelope = _normalized_envelope(raw)
    if envelope is None:
        return None, {
            "reason": "invalid_shape",
            "detail": "prompt_carry_forward must be an object with schema_version and payload object",
        }
    size = _serialize_len(envelope)
    if size is None:
        return None, {
            "reason": "unserializable",
            "detail": "prompt_carry_forward could not be serialized for bounding",
        }
    if size > max_chars:
        return None, {
            "reason": "oversized",
            "char_length": size,
            "max_chars": max_chars,
        }
    return envelope, None


def bound_prompt_carry_forward_for_storage(
    raw: Any,
    *,
    max_chars: int = DEFAULT_MAX_PROMPT_CARRY_FORWARD_CHARS,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Bound a raw carry-forward value for continuity storage.

    Returns ``(carry_forward, omitted_marker)``. When ``raw`` is absent, both are
    None. When ``raw`` is present but invalid/oversized, returns an explicit
    omission marker rather than silently dropping the lane.
    """
    if raw is None:
        return None, None
    return project_prompt_carry_forward(
        {PROMPT_CARRY_FORWARD_KEY: raw},
        max_chars=max_chars,
    )


def attach_prompt_carry_forward_fields(
    target: dict[str, Any],
    *,
    carry_forward: dict[str, Any] | None,
    omitted: dict[str, Any] | None,
) -> None:
    """Attach the dedicated projection keys (mutates ``target``)."""
    if carry_forward is not None:
        target[PROMPT_CARRY_FORWARD_KEY] = carry_forward
        target.pop(PROMPT_CARRY_FORWARD_OMITTED_KEY, None)
        return
    if omitted is not None:
        target[PROMPT_CARRY_FORWARD_OMITTED_KEY] = dict(omitted)
        target.pop(PROMPT_CARRY_FORWARD_KEY, None)


def omit_prompt_carry_forward_for_budget(
    slice_row: dict[str, Any],
    *,
    remaining_chars: int,
) -> dict[str, Any]:
    """Replace an over-budget carry object with an explicit omission marker."""
    existing = slice_row.get(PROMPT_CARRY_FORWARD_KEY)
    char_length = _serialize_len(existing)
    omitted: dict[str, Any] = {
        "reason": "prompt_budget",
        "remaining_chars": int(remaining_chars),
    }
    if char_length is not None:
        omitted["char_length"] = char_length
    attach_prompt_carry_forward_fields(
        slice_row,
        carry_forward=None,
        omitted=omitted,
    )
    return omitted
