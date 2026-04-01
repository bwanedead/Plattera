"""Shared coercion helpers for run-summary inspection (wire-agnostic)."""

from __future__ import annotations

from typing import Any

from ...terminal_taxonomy import TerminalClass


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _event_kind(event: dict[str, Any]) -> str | None:
    return _first_non_empty(_as_str(event.get("event_kind")), _as_str(event.get("event_type")))


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _as_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _as_str(item)
        if not text or text in out:
            continue
        out.append(text)
    return out


def _as_terminal_class(value: Any) -> TerminalClass | None:
    text = _as_str(value)
    if text in {"completed", "blocked", "waiting_human", "waiting_evidence", "exhausted", "failed"}:
        return text  # type: ignore[return-value]
    return None


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        text = _as_str(value)
        if text:
            return text
    return None
