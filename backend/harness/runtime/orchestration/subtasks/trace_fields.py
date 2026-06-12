"""Shared mechanical subtask trace field names for delegate observability."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from harness.runtime.llm.llm_call_trace import sanitize_llm_call_trace

# ``total_seconds`` and ``wall_seconds`` are the same end-to-end delegate wall clock
# (perf_counter span). Both are kept: ``wall_seconds`` is explicit; ``total_seconds``
# preserves backward compatibility for older readers.
SUBTASK_TRACE_FIELDS: tuple[str, ...] = (
    "model",
    "prompt_char_count",
    "image_attachment_count",
    "hydration_seconds",
    "prompt_build_seconds",
    "model_call_seconds",
    "output_normalize_seconds",
    "started_at_epoch_seconds",
    "finished_at_epoch_seconds",
    "wall_seconds",
    "total_seconds",
    "retry_count",
)

PROMPT_SUBTASK_TRACE_FIELDS: tuple[str, ...] = (
    "wall_seconds",
    "model_call_seconds",
    "retry_count",
    "prompt_char_count",
    "image_attachment_count",
)

_IMAGE_REF_TRACE_KEYS: tuple[str, ...] = (
    "ref_id",
    "width_height",
    "size_bytes",
    "mime_type",
    "media_type",
)

_STRIP_IMAGE_REF_KEYS = frozenset(
    {
        "b64",
        "base64",
        "bytes",
        "binary",
        "raw_image",
        "raw_image_data",
        "image_bytes",
        "absolute_path",
        "path",
        "data",
    }
)
_MAX_IMAGE_REFS = 8


def build_subtask_trace(
    *,
    model: str | None = None,
    prompt_char_count: int | None = None,
    image_attachment_count: int | None = None,
    image_refs: Sequence[Mapping[str, Any]] | None = None,
    hydration_seconds: float | None = None,
    prompt_build_seconds: float | None = None,
    model_call_seconds: float | None = None,
    output_normalize_seconds: float | None = None,
    started_at_epoch_seconds: float | None = None,
    finished_at_epoch_seconds: float | None = None,
    wall_seconds: float | None = None,
    retry_count: int = 0,
    llm_call_trace: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a bounded mechanical subtask trace dict."""
    trace: dict[str, Any] = {}
    if model:
        trace["model"] = str(model)
    if prompt_char_count is not None:
        trace["prompt_char_count"] = int(prompt_char_count)
    if image_attachment_count is not None:
        trace["image_attachment_count"] = int(image_attachment_count)
    compact_refs = compact_image_refs_for_trace(image_refs)
    if compact_refs:
        trace["image_refs"] = compact_refs
    for key, value in (
        ("hydration_seconds", hydration_seconds),
        ("prompt_build_seconds", prompt_build_seconds),
        ("model_call_seconds", model_call_seconds),
        ("output_normalize_seconds", output_normalize_seconds),
        ("started_at_epoch_seconds", started_at_epoch_seconds),
        ("finished_at_epoch_seconds", finished_at_epoch_seconds),
        ("wall_seconds", wall_seconds),
        ("total_seconds", wall_seconds),
        ("retry_count", retry_count),
    ):
        if value is not None:
            trace[key] = _round_seconds(value) if key.endswith("_seconds") else value
    if isinstance(llm_call_trace, Mapping):
        compact_llm = sanitize_llm_call_trace(llm_call_trace)
        if compact_llm:
            trace["llm_call_trace"] = compact_llm
    return trace


def compact_image_refs_for_trace(
    image_rows: Sequence[Mapping[str, Any]] | object | None,
) -> list[dict[str, Any]]:
    """Compact image metadata for trace surfaces — no paths, b64, or raw bytes."""
    if not isinstance(image_rows, Sequence) or isinstance(image_rows, (str, bytes)):
        return []
    out: list[dict[str, Any]] = []
    for row in image_rows:
        if not isinstance(row, Mapping):
            continue
        compact = _compact_image_ref_row(row)
        if compact:
            out.append(compact)
        if len(out) >= _MAX_IMAGE_REFS:
            break
    return out


def compact_subtask_trace(trace: object) -> dict[str, object] | None:
    if not isinstance(trace, dict):
        return None
    out = {key: trace[key] for key in SUBTASK_TRACE_FIELDS if key in trace}
    image_refs = compact_image_refs_for_trace(trace.get("image_refs"))
    if image_refs:
        out["image_refs"] = image_refs
    llm_trace = trace.get("llm_call_trace")
    if isinstance(llm_trace, Mapping):
        compact_llm = sanitize_llm_call_trace(llm_trace)
        if compact_llm:
            out["llm_call_trace"] = compact_llm
    return out or None


def compact_subtask_trace_for_prompt(trace: object) -> dict[str, object] | None:
    if not isinstance(trace, dict):
        return None
    out = {key: trace[key] for key in PROMPT_SUBTASK_TRACE_FIELDS if key in trace}
    if "wall_seconds" not in out and trace.get("total_seconds") is not None:
        out["wall_seconds"] = trace["total_seconds"]
    return out or None


def format_delegate_trace_timing_parts(trace: Mapping[str, Any]) -> list[str]:
    """Mechanical timing fragments for timeline surfaces — no semantic labels."""
    parts: list[str] = []
    wall = trace.get("wall_seconds")
    if wall is None:
        wall = trace.get("total_seconds")
    if wall is not None:
        parts.append(f"wall={wall}s")
    if trace.get("model_call_seconds") is not None:
        parts.append(f"model={trace['model_call_seconds']}s")
    if trace.get("retry_count") is not None:
        parts.append(f"retries={trace['retry_count']}")
    if trace.get("prompt_char_count") is not None:
        parts.append(f"prompt_chars={trace['prompt_char_count']}")
    if trace.get("image_attachment_count") is not None:
        parts.append(f"images={trace['image_attachment_count']}")
    llm_trace = trace.get("llm_call_trace")
    if isinstance(llm_trace, Mapping):
        parts.extend(_llm_trace_timing_token_parts(llm_trace))
    image_refs = trace.get("image_refs")
    if isinstance(image_refs, list):
        for row in image_refs[:4]:
            if not isinstance(row, Mapping):
                continue
            ref_id = str(row.get("ref_id") or "").strip()
            if not ref_id:
                continue
            detail_parts: list[str] = []
            width_height = row.get("width_height")
            if width_height is not None:
                detail_parts.append(f"size={width_height}")
            size_bytes = row.get("size_bytes")
            if size_bytes is not None:
                detail_parts.append(f"bytes={size_bytes}")
            mime = row.get("mime_type") or row.get("media_type")
            if mime:
                detail_parts.append(f"mime={mime}")
            suffix = f" ({', '.join(detail_parts)})" if detail_parts else ""
            parts.append(f"image_ref={ref_id}{suffix}")
    return parts


def _compact_image_ref_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
    ref_id = str(row.get("ref_id") or row.get("ref") or "").strip()
    if not ref_id:
        return None
    if any(part in ref_id for part in ("://", "\\", "/")) and not ref_id.startswith(
        ("image:", "artifact:", "subtask:", "t0:")
    ):
        return None
    out: dict[str, Any] = {"ref_id": ref_id}
    width_height = row.get("width_height")
    if width_height is not None:
        out["width_height"] = width_height
    size_bytes = row.get("size_bytes")
    if size_bytes is not None:
        try:
            out["size_bytes"] = int(size_bytes)
        except (TypeError, ValueError):
            pass
    mime_type = row.get("mime_type") or row.get("media_type")
    if isinstance(mime_type, str) and mime_type.strip():
        out["mime_type"] = mime_type.strip()
    if len(out) == 1:
        return out
    return {key: out[key] for key in _IMAGE_REF_TRACE_KEYS if key in out}


def _llm_trace_timing_token_parts(trace: Mapping[str, Any]) -> list[str]:
    parts: list[str] = []
    if trace.get("input_tokens") is not None:
        parts.append(f"tokens=input={trace['input_tokens']}")
    if trace.get("cached_input_tokens") is not None:
        parts.append(f"cached={trace['cached_input_tokens']}")
    if trace.get("output_tokens") is not None:
        parts.append(f"output={trace['output_tokens']}")
    if trace.get("reasoning_tokens") is not None:
        parts.append(f"reasoning={trace['reasoning_tokens']}")
    retries = trace.get("retry_count_observed")
    if retries is not None:
        parts.append(f"retries={retries}")
    elif trace.get("max_retries_configured") is not None:
        parts.append("retries=?")
    if trace.get("streaming_requested") is not None:
        parts.append(f"streaming={str(bool(trace['streaming_requested'])).lower()}")
    if trace.get("provider_wait_seconds") is not None:
        parts.append(f"provider_wait={trace['provider_wait_seconds']}s")
    if trace.get("response_stream_seconds") is not None:
        parts.append(f"response_stream={trace['response_stream_seconds']}s")
    return parts


def _round_seconds(value: Any) -> float:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return 0.0
