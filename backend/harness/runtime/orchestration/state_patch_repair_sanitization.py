"""JSON-native sanitization and strict sizing for state_patch repair fragments.

Mechanical only: strip host/binary keys, omit unsupported values whole, and
measure with allow_nan=False (no default=str). Does not own bundle semantics.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

MAX_FRAGMENT_SERIALIZED_CHARS = 1500
_MAX_LIST_ITEMS = 8
_MAX_STRING_CHARS = 800

_STRIP_FRAGMENT_KEYS = frozenset(
    {
        "b64",
        "bytes",
        "raw_image",
        "raw_image_data",
        "image_bytes",
        "raw_prompt_text",
        "raw_llm_response_text",
        "prompt_text",
        "absolute_path",
        "workspace_root",
        "host_path",
        "file_path",
        "path",
    }
)

# Explicit order: must not depend on frozenset/hash iteration for durable bundles.
PRESERVE_FRAGMENT_KEYS: tuple[str, ...] = (
    "item_id",
    "unit_id",
    "status",
    "determination",
    "determined_value",
    "evidence_refs",
    "evidence_locators",
    "verification_basis",
    "closure_summary",
    "reopen_triggers",
    "summary",
    "title",
    "kind",
    "candidate_values",
    "label",
    "value_kind",
    "next_needed_step",
    "completion_criteria",
    "notes",
    "blocking",
    "requires_hitl",
    "no_further_progress",
    "structure_kind",
    "materiality",
)

# Sentinel: omit unsupported values whole (do not stringify).
_OMIT = object()


def json_chars(value: Any) -> int:
    """Serialized size using strict JSON-native encoding (no default=str)."""
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    )


def safe_json_chars(value: Any) -> int:
    try:
        return json_chars(value)
    except (TypeError, ValueError):
        return 10**9


def should_strip_key(key: str) -> bool:
    return key in _STRIP_FRAGMENT_KEYS or key.endswith("_b64")


def sanitize_fragment(fragment: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    """Return a JSON-native fragment dict and whether anything was omitted/truncated."""
    truncated = False
    out: dict[str, Any] = {}
    for key, value in fragment.items():
        key_text = str(key)
        if should_strip_key(key_text):
            truncated = True
            continue
        sanitized, nested_truncated = sanitize_json_value(value)
        if sanitized is _OMIT:
            truncated = True
            continue
        out[key_text] = sanitized
        if nested_truncated:
            truncated = True

    try:
        over_budget = json_chars(out) > MAX_FRAGMENT_SERIALIZED_CHARS
    except (TypeError, ValueError):
        over_budget = True
        truncated = True
    if over_budget:
        trimmed: dict[str, Any] = {}
        for key in PRESERVE_FRAGMENT_KEYS:
            if key in out:
                trimmed[key] = out[key]
        if not trimmed:
            # Deterministic fallback: sorted key order, not hash iteration.
            for key in sorted(out.keys())[:12]:
                trimmed[key] = out[key]
        out = trimmed
        truncated = True

    try:
        still_over = json_chars(out) > MAX_FRAGMENT_SERIALIZED_CHARS
    except (TypeError, ValueError):
        still_over = True
    if still_over:
        out = truncate_mapping_values(out, max_chars=MAX_FRAGMENT_SERIALIZED_CHARS)
        truncated = True
    return out, truncated


def sanitize_json_value(value: Any) -> tuple[Any, bool]:
    """Return ``(sanitized_value_or__OMIT, truncated)`` for one JSON-native value."""
    if value is None or type(value) is bool:
        return value, False
    if type(value) is int:
        return value, False
    if type(value) is float:
        if not math.isfinite(value):
            return _OMIT, True
        return value, False
    if isinstance(value, str):
        if len(value) > _MAX_STRING_CHARS:
            return value[:_MAX_STRING_CHARS], True
        return value, False
    if isinstance(value, Mapping):
        return sanitize_fragment(value)
    if isinstance(value, list):
        return _sanitize_json_list(value)
    return _OMIT, True


def _sanitize_json_list(value: list[Any]) -> tuple[list[Any], bool]:
    truncated = False
    cleaned: list[Any] = []
    if len(value) > _MAX_LIST_ITEMS:
        truncated = True
    for row in value[:_MAX_LIST_ITEMS]:
        sanitized, nested_truncated = sanitize_json_value(row)
        if sanitized is _OMIT:
            truncated = True
            continue
        cleaned.append(sanitized)
        if nested_truncated:
            truncated = True
    return cleaned, truncated


def truncate_mapping_values(payload: Mapping[str, Any], *, max_chars: int) -> dict[str, Any]:
    out = dict(payload)
    while out:
        try:
            if json_chars(out) <= max_chars:
                break
        except (TypeError, ValueError):
            # Deterministic: drop lexicographically last key when unmeasurable.
            drop_key = sorted(out.keys())[-1]
            del out[drop_key]
            continue
        longest_key = max(out.keys(), key=lambda k: (safe_json_chars(out[k]), k))
        current = out[longest_key]
        if isinstance(current, str) and len(current) > 80:
            out[longest_key] = current[: max(40, len(current) // 2)]
        else:
            del out[longest_key]
    return out
