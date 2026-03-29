from __future__ import annotations

from typing import Any


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            out.append(item)
    return out


def as_str(value: Any) -> str | None:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed if trimmed else None
    return None


def as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        parsed = as_str(item)
        if parsed:
            out.append(parsed)
    return out


def first_non_empty(*values: Any) -> str | None:
    for value in values:
        parsed = as_str(value)
        if parsed:
            return parsed
    return None


def bounded_text(value: Any, *, max_chars: int) -> str | None:
    parsed = as_str(value)
    if not parsed:
        return None
    if len(parsed) <= max_chars:
        return parsed
    if max_chars <= 16:
        return parsed[:max_chars]
    return f"{parsed[: max_chars - 14]}...[truncated]"


def source_ref(*, primary: str | None, fallback: str | None, default: str) -> str:
    return first_non_empty(primary, fallback, default) or default


def extract_run_id_from_session(session_id: str | None) -> str | None:
    value = (session_id or "").strip()
    if not value or "::" not in value:
        return None
    return value.rsplit("::", maxsplit=1)[-1] or None

