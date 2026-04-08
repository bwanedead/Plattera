"""Central JSON normalization for audit payloads.

All audit paths must funnel through ``audit_jsonable`` before any ``json.dumps`` call
so that runtime objects (dataclasses, Pydantic models, enums, Paths, sets) never reach
the serializer raw.  Unknown objects degrade to a safe ``repr_fallback`` dict rather
than raising.
"""

from __future__ import annotations

import dataclasses
import enum
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def audit_jsonable(value: Any) -> Any:
    """Recursively convert *value* to a JSON-serializable form.

    Handles:
    - ``None``, bool, int, float, str  → unchanged
    - Pydantic ``BaseModel``           → ``model_dump(mode="json")``
    - ``dataclass`` instances          → ``dataclasses.asdict()``
    - ``enum.Enum``                    → ``.value``
    - ``pathlib.Path``                 → ``str()``
    - ``Mapping``                      → ``{str(k): audit_jsonable(v), …}``
    - list / tuple                     → ``[audit_jsonable(item), …]``
    - set / frozenset                  → sorted list
    - already-JSON-safe primitives     → unchanged
    - everything else                  → ``{"repr_fallback": repr(value)}``
    """
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    # Pydantic models (must come before Mapping check — BaseModel is not a Mapping).
    if hasattr(value, "model_dump") and callable(value.model_dump):
        try:
            return audit_jsonable(value.model_dump(mode="json"))
        except Exception as exc:
            return {"repr_fallback": repr(value), "serialization_error": str(exc)}
    # Dataclasses (instances only, not the class itself).
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        try:
            return audit_jsonable(dataclasses.asdict(value))
        except Exception as exc:
            return {"repr_fallback": repr(value), "serialization_error": str(exc)}
    # Enums.
    if isinstance(value, enum.Enum):
        return value.value
    # Paths.
    if isinstance(value, Path):
        return str(value)
    # Mappings (dict, OrderedDict, etc.).
    if isinstance(value, Mapping):
        return {str(k): audit_jsonable(v) for k, v in value.items()}
    # Sequences.
    if isinstance(value, (list, tuple)):
        return [audit_jsonable(item) for item in value]
    # Sets.
    if isinstance(value, (set, frozenset)):
        return [audit_jsonable(item) for item in sorted(value, key=str)]
    # Last resort: test for direct JSON-serializability then fall back to repr.
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return {"repr_fallback": repr(value)}
