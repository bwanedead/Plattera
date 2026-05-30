"""Stable refs and bounded records for delegated subtask observations.

Mechanical persistence and hydration only — no semantic authority over delegate output.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .projection import project_subtask_output

DELEGATE_RESULT_REF_PREFIX = "subtask:"
DELEGATE_RESULT_KIND = "delegate_subtask_result"

MAX_STORED_RECORDS = 32
MAX_TASK_CHARS = 400
MAX_RESULT_SERIALIZED_CHARS = 2400
MAX_RECORD_SERIALIZED_CHARS = 4000
MAX_PROMPT_ROWS = 8

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
    }
)
_BINARY_KEY_PARTS = ("b64", "base64", "bytes", "binary")

_REF_SEGMENT_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def is_delegate_result_ref(ref_id: str) -> bool:
    text = str(ref_id or "").strip()
    return text.startswith(DELEGATE_RESULT_REF_PREFIX)


def build_delegate_result_ref_id(
    *,
    turn_index: int,
    alias: str | None,
    action_index: int,
    duplicate_index: int = 1,
) -> str:
    """Build ``subtask:turn{N}:{alias|actionK}`` with optional ``:2`` disambiguation."""
    turn = max(1, int(turn_index))
    segment = _ref_segment(alias, action_index=action_index)
    ref_id = f"{DELEGATE_RESULT_REF_PREFIX}turn{turn}:{segment}"
    if duplicate_index > 1:
        ref_id = f"{ref_id}:{duplicate_index}"
    return ref_id


def build_delegate_result_record(
    *,
    ref_id: str,
    turn_index: int,
    alias: str,
    action_index: int,
    action_inputs: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a bounded delegate result record from execution outputs."""
    projected = project_subtask_output(outputs) or {}
    context_refs = _bounded_str_list(action_inputs.get("context_refs"), limit=8)
    task = _bound_text(str(action_inputs.get("task") or ""), max_chars=MAX_TASK_CHARS)
    result_payload = projected.get("result") if isinstance(projected.get("result"), Mapping) else {}
    stored_alias = _stored_alias(alias, action_index=action_index)
    record: dict[str, Any] = {
        "ref_id": ref_id,
        "kind": DELEGATE_RESULT_KIND,
        "turn_index": int(turn_index),
        "alias": stored_alias,
        "action_index": int(action_index),
        "profile": str(projected.get("profile") or action_inputs.get("profile") or ""),
        "task": task,
        "context_refs": context_refs,
        "status": str(projected.get("status") or outputs.get("status") or "unknown"),
        "result": _sanitize_value(result_payload),
        "created_at_turn": int(turn_index),
    }
    trace = projected.get("subtask_trace")
    if isinstance(trace, Mapping) and trace:
        record["subtask_trace"] = {
            key: trace[key]
            for key in ("model", "prompt_char_count", "image_attachment_count")
            if key in trace
        }
    if projected.get("result_truncated") is True:
        record["result_truncated"] = True
        truncated_fields = projected.get("truncated_fields")
        if isinstance(truncated_fields, list) and truncated_fields:
            record["truncated_fields"] = [_bound_text(str(x)) for x in truncated_fields[:8]]
        original_chars = projected.get("original_result_chars")
        if original_chars is not None:
            try:
                record["original_result_chars"] = int(original_chars)
            except (TypeError, ValueError):
                pass
    errors = projected.get("errors")
    if isinstance(errors, list) and errors:
        record["errors"] = [dict(row) for row in errors[:4] if isinstance(row, Mapping)]
    return _bound_record(record)


def register_delegate_result_record(
    continuity: Any,
    record: Mapping[str, Any],
) -> None:
    """Append one delegate result record to continuity storage (bounded)."""
    rows = list(getattr(continuity, "delegate_subtask_results", None) or [])
    rows.append(dict(record))
    continuity.delegate_subtask_results = rows[-MAX_STORED_RECORDS:]


def hydrate_delegate_result_refs(
    records: Sequence[Mapping[str, Any]],
    ref_ids: Sequence[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Hydrate ``subtask:*`` refs from stored records without rerunning delegates."""
    by_ref = {
        str(row.get("ref_id") or "").strip(): dict(row)
        for row in records
        if isinstance(row, Mapping) and str(row.get("ref_id") or "").strip()
    }
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for ref_id in ref_ids:
        text = str(ref_id or "").strip()
        if not text:
            errors.append({"ref_id": ref_id, "code": "ref_id_invalid", "message": "ref_id must be non-empty."})
            continue
        if not is_delegate_result_ref(text):
            errors.append(
                {
                    "ref_id": text,
                    "code": "unknown_ref_kind",
                    "message": "Not a delegate result ref.",
                }
            )
            continue
        stored = by_ref.get(text)
        if stored is None:
            errors.append(
                {
                    "ref_id": text,
                    "code": "ref_not_found",
                    "message": "No stored delegate result for this ref.",
                }
            )
            continue
        results.append(build_hydrated_delegate_payload(stored))
    return results, errors


def build_hydrated_delegate_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    """Compact hydrate_artifact_refs-compatible payload for one delegate record."""
    return {
        "ref_id": str(record.get("ref_id") or ""),
        "kind": DELEGATE_RESULT_KIND,
        "summary": build_delegate_result_summary(record),
        "profile": record.get("profile"),
        "task": record.get("task"),
        "context_refs": list(record.get("context_refs") or []),
        "status": record.get("status"),
        "result": dict(record.get("result") or {}),
        "subtask_trace": dict(record.get("subtask_trace") or {}) or None,
        "result_truncated": record.get("result_truncated"),
        "truncated_fields": list(record.get("truncated_fields") or []) or None,
        "errors": list(record.get("errors") or []) or None,
    }


def build_delegate_result_summary(record: Mapping[str, Any]) -> str:
    alias = str(record.get("alias") or "?").strip() or "?"
    status = str(record.get("status") or "?").strip() or "?"
    preview = _first_result_preview(record.get("result"))
    if preview:
        return f"{alias} {status}; {preview}"
    return f"{alias} {status}"


def project_recent_delegate_results_for_prompt(
    records: Sequence[Mapping[str, Any]] | None,
    *,
    current_turn: int,
    hot_refs: frozenset[str] | None = None,
) -> dict[str, Any] | None:
    """Prompt-visible recent delegate result refs (mechanical only)."""
    if not records:
        return None
    hot = hot_refs or frozenset()
    rows: list[dict[str, Any]] = []
    for record in reversed(list(records)):
        if not isinstance(record, Mapping):
            continue
        ref_id = str(record.get("ref_id") or "").strip()
        if not ref_id:
            continue
        try:
            turn = int(record.get("turn_index") or record.get("created_at_turn") or 0)
        except (TypeError, ValueError):
            turn = 0
        age = max(0, int(current_turn) - turn) if turn else 2
        keep_hot = age <= 1 or ref_id in hot
        row = {
            "ref_id": ref_id,
            "alias": record.get("alias"),
            "status": record.get("status"),
            "context_refs": list(record.get("context_refs") or [])[:4],
            "summary": build_delegate_result_summary(record),
        }
        if not keep_hot:
            row["stale"] = True
        rows.append(row)
        if len(rows) >= MAX_PROMPT_ROWS:
            break
    if not rows:
        return None
    return {"items": list(reversed(rows))}


def validate_stored_delegate_result_record(row: Any) -> dict[str, Any] | None:
    """Resume-snapshot validator for one delegate result record."""
    if not isinstance(row, Mapping):
        return None
    ref_id = str(row.get("ref_id") or "").strip()
    if not ref_id or not is_delegate_result_ref(ref_id):
        return None
    if str(row.get("kind") or "") != DELEGATE_RESULT_KIND:
        return None
    try:
        turn_index = int(row.get("turn_index") or row.get("created_at_turn") or 0)
    except (TypeError, ValueError):
        return None
    if turn_index < 0:
        return None
    try:
        action_index = int(row.get("action_index") or 0)
    except (TypeError, ValueError):
        return None
    if action_index < 1:
        return None
    alias = _stored_alias(str(row.get("alias") or ""), action_index=action_index)
    bounded = _bound_record(
        {
            "ref_id": ref_id,
            "kind": DELEGATE_RESULT_KIND,
            "turn_index": turn_index,
            "alias": alias,
            "action_index": action_index,
            "profile": _bound_text(str(row.get("profile") or "")),
            "task": _bound_text(str(row.get("task") or ""), max_chars=MAX_TASK_CHARS),
            "context_refs": _bounded_str_list(row.get("context_refs"), limit=8),
            "status": _bound_text(str(row.get("status") or "unknown")),
            "result": _sanitize_value(row.get("result") if isinstance(row.get("result"), Mapping) else {}),
            "created_at_turn": turn_index,
        }
    )
    trace = row.get("subtask_trace")
    if isinstance(trace, Mapping):
        bounded["subtask_trace"] = {
            key: trace[key]
            for key in ("model", "prompt_char_count", "image_attachment_count")
            if key in trace
        }
    if row.get("result_truncated") is True:
        bounded["result_truncated"] = True
    errors = row.get("errors")
    if isinstance(errors, list) and errors:
        bounded["errors"] = [dict(e) for e in errors[:4] if isinstance(e, Mapping)]
    return bounded


def _ref_segment(alias: str | None, *, action_index: int) -> str:
    return _stored_alias(alias, action_index=action_index)


def _stored_alias(alias: str | None, *, action_index: int) -> str:
    text = str(alias or "").strip()
    if text and _REF_SEGMENT_RE.match(text):
        return text
    return f"action{max(1, int(action_index))}"


def _first_result_preview(result: Any) -> str:
    if not isinstance(result, Mapping) or not result:
        return ""
    for key, value in result.items():
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return f"{key}={_bound_text(value, max_chars=120)}"
        if isinstance(value, (int, float, bool)):
            return f"{key}={value}"
    return ""


def _bound_record(record: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(record)
    result = out.get("result")
    if isinstance(result, Mapping):
        out["result"] = _bound_mapping(result, max_chars=MAX_RESULT_SERIALIZED_CHARS)
    serialized = json.dumps(out, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(serialized) <= MAX_RECORD_SERIALIZED_CHARS:
        return out
    if isinstance(out.get("result"), Mapping):
        out["result"] = _bound_mapping(out["result"], max_chars=max(400, MAX_RESULT_SERIALIZED_CHARS // 2))
    out["record_truncated"] = True
    return out


def _bound_mapping(payload: Mapping[str, Any], *, max_chars: int) -> dict[str, Any]:
    cleaned = _sanitize_value(payload)
    if not isinstance(cleaned, Mapping):
        return {}
    out = dict(cleaned)
    while out and len(json.dumps(out, ensure_ascii=False, default=str)) > max_chars:
        longest_key = max(
            out.keys(),
            key=lambda k: len(json.dumps(out[k], ensure_ascii=False, default=str)),
        )
        current = out[longest_key]
        if isinstance(current, str) and len(current) > 40:
            out[longest_key] = current[: max(20, len(current) // 2)]
        else:
            del out[longest_key]
    return out


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, inner in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if key_text in _STRIP_KEYS or any(part in lowered for part in _BINARY_KEY_PARTS):
                continue
            if isinstance(inner, (bytes, bytearray)):
                continue
            out[key_text] = _sanitize_value(inner)
        return out
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value[:12]]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value[:12]]
    if isinstance(value, str):
        return _bound_text(value)
    return value


def _bounded_str_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(_bound_text(text))
        if len(out) >= limit:
            break
    return out


def _bound_text(value: str, *, max_chars: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars]
