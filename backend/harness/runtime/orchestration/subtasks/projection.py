"""Bounded parent/audit projections for delegated subtask results."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import DELEGATE_SUBTASK_ACTION_TYPE

_MAX_TEXT = 240
_MAX_LIST_ITEMS = 4


def project_subtask_output(outputs: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Project one normalized subtask output without raw prompt/media payloads."""

    if not isinstance(outputs, Mapping):
        return None
    if str(outputs.get("action_type") or "") != DELEGATE_SUBTASK_ACTION_TYPE:
        return None
    result = outputs.get("result")
    result_map = dict(result) if isinstance(result, Mapping) else {}
    out: dict[str, Any] = {
        "subtask_id": _short(outputs.get("subtask_id")),
        "profile": _short(outputs.get("profile")),
        "status": _short(outputs.get("status")),
        "input_refs": _bounded_list(outputs.get("input_refs"), limit=8),
        "result": {
            "reading": _nullable_short(result_map.get("reading")),
            "ambiguity": _short(result_map.get("ambiguity")),
            "observations": _bounded_list(result_map.get("observations"), limit=_MAX_LIST_ITEMS),
            "limits": _bounded_list(result_map.get("limits"), limit=_MAX_LIST_ITEMS),
        },
    }
    errors = outputs.get("errors")
    if isinstance(errors, (list, tuple)) and errors:
        out["errors"] = [
            {
                "reason_code": _short(row.get("reason_code") or row.get("code"))
                if isinstance(row, Mapping)
                else _short(row),
                "message": _short(row.get("message")) if isinstance(row, Mapping) else "",
            }
            for row in errors[:_MAX_LIST_ITEMS]
            if row is not None
        ]
    trace = outputs.get("subtask_trace")
    if isinstance(trace, Mapping):
        out["subtask_trace"] = {
            key: trace[key]
            for key in ("model", "prompt_char_count", "image_attachment_count")
            if key in trace
        }
    return out


def project_subtask_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
    if str(row.get("action_type") or "") != DELEGATE_SUBTASK_ACTION_TYPE:
        return None
    outputs = row.get("outputs_excerpt")
    if not isinstance(outputs, Mapping):
        return None
    return project_subtask_output(outputs)


def task_excerpt(action_inputs: Mapping[str, Any] | None) -> str:
    if not isinstance(action_inputs, Mapping):
        return ""
    return _short(action_inputs.get("task"))


def _short(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) <= _MAX_TEXT:
        return text
    return text[:_MAX_TEXT]


def _nullable_short(value: Any) -> str | None:
    if value is None:
        return None
    return _short(value)


def _bounded_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [_short(item) for item in value[:limit] if str(item or "").strip()]
