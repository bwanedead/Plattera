"""Deep-merge helpers for surgical IR draft patches."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def deep_merge_patch(base: Any, patch: Any) -> Any:
    """Deep-merge patch into base: dicts recurse, lists/scalars replace, null clears."""
    if patch is None:
        return None
    if isinstance(patch, Mapping) and isinstance(base, Mapping):
        merged: dict[str, Any] = dict(base)
        for key, value in patch.items():
            if value is None:
                merged[str(key)] = None
            elif isinstance(value, Mapping):
                existing = merged.get(str(key))
                merged[str(key)] = deep_merge_patch(
                    existing if isinstance(existing, Mapping) else {},
                    value,
                )
            else:
                merged[str(key)] = value
        return merged
    if isinstance(patch, Mapping):
        return {str(key): deep_merge_patch(None, value) for key, value in patch.items()}
    return patch
