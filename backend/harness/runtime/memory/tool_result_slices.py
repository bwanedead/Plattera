"""Bounded mechanical excerpts of recent tool results for prompt transport.

The slice builder is a pure drop-only projection of stored
``kernel_step_result_records``. It selects the last ``max_records`` rows by
turn order and copies a handful of mechanical fields plus a bounded excerpt
of each row's ``outputs_for_continuity``. It does not inspect domain content
to decide inclusion, does not rank by semantic relevance, and does not embed
image or binary payloads.

The goal is to make the previous turn's tool output visible to the next LLM
turn without re-adding the raw record dump to default prompts.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

DEFAULT_MAX_RECORDS = 3
DEFAULT_MAX_CHARS_PER_RESULT = 2500
DEFAULT_MAX_TOTAL_CHARS = 7000
_MAX_ARTIFACT_REFS = 16

_BINARY_KEYS = frozenset(
    {
        "image_bytes",
        "image_b64",
        "image_base64",
        "image_evidence",
        "binary",
        "binary_payload",
        "pdf_bytes",
        "bytes",
        "raw_bytes",
    }
)


def _turn_index(row: Mapping[str, Any]) -> int | None:
    try:
        return int(row.get("kernel_turn_index"))
    except (TypeError, ValueError):
        return None


def _strip_binary(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_binary(inner)
            for key, inner in value.items()
            if str(key) not in _BINARY_KEYS
        }
    if isinstance(value, list):
        return [_strip_binary(item) for item in value]
    return value


def _bounded_outputs_excerpt(outputs: Any, *, max_chars: int) -> tuple[Any, bool]:
    """Return a bounded copy of outputs and whether it was truncated."""
    if isinstance(outputs, str):
        if len(outputs) <= max_chars:
            return outputs, False
        return outputs[:max_chars], True
    stripped = _strip_binary(outputs)
    try:
        blob = json.dumps(stripped, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        blob = str(stripped)
    if len(blob) <= max_chars:
        return stripped, False
    return blob[:max_chars], True


def build_recent_tool_result_slices(
    step_result_records: list[dict[str, Any]],
    *,
    max_records: int = DEFAULT_MAX_RECORDS,
    max_chars_per_result: int = DEFAULT_MAX_CHARS_PER_RESULT,
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
) -> list[dict[str, Any]]:
    """Mechanical bounded projection of the most recent tool-result rows.

    Selection is by ``kernel_turn_index`` order only. No semantic ranking.
    Binary/image payload keys are stripped. Each slice is bounded in size
    and the total lane is bounded by ``max_total_chars``.
    """
    if not step_result_records or max_records <= 0:
        return []
    rows: list[Mapping[str, Any]] = [
        row for row in step_result_records if isinstance(row, Mapping)
    ]
    rows.sort(key=lambda r: _turn_index(r) if _turn_index(r) is not None else -1)
    kept = rows[-max_records:]

    slices: list[dict[str, Any]] = []
    total_chars = 0
    for row in kept:
        turn = _turn_index(row)
        if turn is None:
            continue
        outputs = row.get("outputs_for_continuity", {})
        excerpt, excerpt_truncated = _bounded_outputs_excerpt(
            outputs, max_chars=max_chars_per_result
        )
        raw_refs = row.get("artifact_refs") or []
        if isinstance(raw_refs, list):
            artifact_refs = [str(x) for x in raw_refs[:_MAX_ARTIFACT_REFS]]
        else:
            artifact_refs = []
        slice_row: dict[str, Any] = {
            "kernel_turn_index": turn,
            "action_type": row.get("action_type"),
            "execution_state": row.get("execution_state"),
            "execution_reason_code": row.get("execution_reason_code"),
            "result_truncated": bool(row.get("result_truncated", False)),
            "artifact_refs": artifact_refs,
            "outputs_excerpt": excerpt,
            "outputs_excerpt_truncated": bool(excerpt_truncated),
        }
        try:
            row_chars = len(
                json.dumps(slice_row, ensure_ascii=False, default=str)
            )
        except (TypeError, ValueError):
            row_chars = max_chars_per_result
        if slices and total_chars + row_chars > max_total_chars:
            break
        slices.append(slice_row)
        total_chars += row_chars
    return slices
