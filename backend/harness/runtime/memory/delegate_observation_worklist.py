"""Derived worklist of completed delegate observations not cited in durable state.

Exact-string integration scanning only — no semantic atom association or fuzzy matching.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from harness.runtime.orchestration.subtasks.delegate_integration_status import (
    STATUS_REFERENCED_IN_REPAIR_BUNDLE,
    STATUS_REFERENCED_IN_STATE,
    compute_delegate_ref_integration_status,
)
from harness.runtime.orchestration.subtasks.trace_fields import compact_subtask_trace_for_prompt

KIND = "delegate_observation_worklist"
COMPLETED_STATUS = "completed"

MAX_ROWS = 12
MAX_PREVIEW_CHARS = 300
MAX_CONTEXT_REFS = 4
MAX_TASK_PREVIEW_CHARS = 300

_STRIP_KEYS = frozenset(
    {
        "b64",
        "base64",
        "bytes",
        "binary",
        "raw_image",
        "raw_image_data",
        "image_bytes",
        "raw_prompt_text",
        "raw_llm_response_text",
        "prompt_text",
        "prompt",
        "raw_response",
        "absolute_path",
    }
)
_BINARY_KEY_PARTS = ("b64", "base64", "bytes", "binary")
_ABSOLUTE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]|^/")


def build_delegate_observation_worklist(
    *,
    delegate_result_records: Sequence[Mapping[str, Any]] | None,
    mission_state: Mapping[str, Any] | None = None,
    resolution_state: Mapping[str, Any] | None = None,
    repair_bundle: Mapping[str, Any] | None = None,
    current_turn: int = 0,
) -> dict[str, Any]:
    """Return unintegrated completed delegate observations (mechanical exact-ref join)."""
    rows: list[dict[str, Any]] = []
    for record in _sorted_records(delegate_result_records):
        row = _worklist_row_from_record(
            record,
            mission_state=mission_state,
            resolution_state=resolution_state,
            repair_bundle=repair_bundle,
            current_turn=int(current_turn),
        )
        if row is not None:
            rows.append(row)
        if len(rows) >= MAX_ROWS:
            break

    if not rows:
        return {
            "kind": KIND,
            "counts": {"unintegrated_completed": 0},
            "rows": [],
        }

    return {
        "kind": KIND,
        "counts": {"unintegrated_completed": len(rows)},
        "rows": rows,
    }


def _sorted_records(
    records: Sequence[Mapping[str, Any]] | None,
) -> list[Mapping[str, Any]]:
    valid: list[tuple[int, Mapping[str, Any]]] = []
    for record in records or ():
        if not isinstance(record, Mapping):
            continue
        try:
            turn = int(record.get("turn_index") or record.get("created_at_turn") or 0)
        except (TypeError, ValueError):
            turn = 0
        valid.append((turn, record))
    valid.sort(key=lambda item: (-item[0], str(item[1].get("ref_id") or "")))
    return [record for _, record in valid]


def _worklist_row_from_record(
    record: Mapping[str, Any],
    *,
    mission_state: Mapping[str, Any] | None,
    resolution_state: Mapping[str, Any] | None,
    repair_bundle: Mapping[str, Any] | None,
    current_turn: int,
) -> dict[str, Any] | None:
    ref_id = str(record.get("ref_id") or "").strip()
    if not ref_id:
        return None

    status = str(record.get("status") or "").strip().lower()
    if status != COMPLETED_STATUS:
        return None

    try:
        turn_index = int(record.get("turn_index") or record.get("created_at_turn") or 0)
    except (TypeError, ValueError):
        turn_index = 0

    integration = compute_delegate_ref_integration_status(
        ref_id=ref_id,
        record_turn_index=turn_index,
        current_turn=current_turn,
        mission_state=mission_state,
        resolution_state=resolution_state,
        repair_bundle=repair_bundle,
    )
    if integration in (STATUS_REFERENCED_IN_STATE, STATUS_REFERENCED_IN_REPAIR_BUNDLE):
        return None

    result = record.get("result")
    result_map = dict(result) if isinstance(result, Mapping) else {}

    row: dict[str, Any] = {
        "ref_id": ref_id,
        "alias": _bound_text(str(record.get("alias") or "")),
        "turn_index": turn_index,
        "profile": _bound_text(str(record.get("profile") or "")),
        "status": COMPLETED_STATUS,
        "context_refs": _bounded_str_list(record.get("context_refs"), limit=MAX_CONTEXT_REFS),
    }

    task_preview = _bound_text(str(record.get("task") or ""), max_chars=MAX_TASK_PREVIEW_CHARS)
    if task_preview:
        row["task_preview"] = task_preview

    for field, key in (
        ("task_response_preview", "task_response"),
        ("source_visible_text_preview", "source_visible_text"),
        ("ambiguity_preview", "ambiguity"),
        ("limits_preview", "limits"),
    ):
        preview = _preview_from_result(result_map, key=key)
        if preview:
            row[field] = preview

    trace = _compact_trace_for_worklist(record.get("subtask_trace"))
    if trace:
        row["subtask_trace"] = trace

    return _sanitize_row(row)


def _preview_from_result(result: Mapping[str, Any], *, key: str) -> str:
    value = result.get(key)
    if value is None:
        return ""
    if isinstance(value, str):
        return _bound_text(value, max_chars=MAX_PREVIEW_CHARS)
    if isinstance(value, list):
        parts = [_bound_text(str(item), max_chars=80) for item in value[:4] if item is not None]
        joined = "; ".join(part for part in parts if part)
        return _bound_text(joined, max_chars=MAX_PREVIEW_CHARS)
    if isinstance(value, Mapping):
        text = json.dumps(_sanitize_value(value), ensure_ascii=False, default=str)
        return _bound_text(text, max_chars=MAX_PREVIEW_CHARS)
    return _bound_text(str(value), max_chars=MAX_PREVIEW_CHARS)


def _compact_trace_for_worklist(trace: object) -> dict[str, Any] | None:
    if not isinstance(trace, Mapping):
        return None
    out = compact_subtask_trace_for_prompt(trace)
    if out is None:
        return None
    if trace.get("total_seconds") is not None and "total_seconds" not in out:
        out = dict(out)
        out["total_seconds"] = trace["total_seconds"]
    return out


def _bounded_str_list(raw: object, *, limit: int) -> list[str]:
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if not text or text in out:
            continue
        if _ABSOLUTE_PATH_RE.match(text):
            continue
        out.append(_bound_text(text, max_chars=256))
        if len(out) >= limit:
            break
    return out


def _bound_text(text: str, *, max_chars: int = MAX_PREVIEW_CHARS) -> str:
    cleaned = str(text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3] + "..."


def _sanitize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    cleaned = _sanitize_value(dict(row))
    return dict(cleaned) if isinstance(cleaned, Mapping) else {}


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, inner in value.items():
            lowered = str(key).lower()
            if lowered in _STRIP_KEYS:
                continue
            if any(part in lowered for part in _BINARY_KEY_PARTS):
                continue
            if isinstance(inner, str) and _ABSOLUTE_PATH_RE.match(inner.strip()):
                continue
            out[str(key)] = _sanitize_value(inner)
        return out
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value]
    return value
