"""Shared mechanical subtask trace field names for delegate observability."""

from __future__ import annotations

SUBTASK_TRACE_FIELDS: tuple[str, ...] = (
    "model",
    "prompt_char_count",
    "image_attachment_count",
    "hydration_seconds",
    "prompt_build_seconds",
    "model_call_seconds",
    "output_normalize_seconds",
    "total_seconds",
    "retry_count",
)


def compact_subtask_trace(trace: object) -> dict[str, object] | None:
    if not isinstance(trace, dict):
        return None
    out = {key: trace[key] for key in SUBTASK_TRACE_FIELDS if key in trace}
    return out or None
