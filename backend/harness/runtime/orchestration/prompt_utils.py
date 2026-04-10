"""Shared serialization utilities for kernel prompt assembly."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any


def jsonable(value: Any) -> Any:
    """Recursively convert a value to a JSON-serializable form."""
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump(mode="python"))  # type: ignore[call-arg]
    if dataclasses.is_dataclass(value):
        return jsonable(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): jsonable(raw_value) for key, raw_value in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, set):
        return [jsonable(item) for item in sorted(value, key=str)]
    return value
