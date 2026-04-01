"""Helpers for generic latest reference maps."""

from __future__ import annotations

from typing import Any, Mapping


def normalize_latest_refs(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        name = str(key).strip()
        if name:
            out[name] = value
    return out


def merge_latest_refs(
    existing: Mapping[str, Any] | None,
    incoming: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged = normalize_latest_refs(existing)
    merged.update(normalize_latest_refs(incoming))
    return merged

