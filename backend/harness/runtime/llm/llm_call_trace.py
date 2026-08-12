"""Generic harness-owned LLM call trace builder and extraction helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

_MAX_ERROR_PREVIEW_CHARS = 240

LLM_CALL_TRACE_FIELDS: tuple[str, ...] = (
    "provider",
    "call_role",
    "call_name",
    "model",
    "started_at_epoch_seconds",
    "finished_at_epoch_seconds",
    "wall_seconds",
    "first_response_event_at_epoch_seconds",
    "time_to_first_response_event_seconds",
    "response_stream_seconds",
    "provider_wait_seconds",
    "prompt_char_count",
    "response_char_count",
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "total_tokens",
    "service_tier_requested",
    "service_tier_returned",
    "response_id",
    "request_id",
    "streaming_requested",
    "streaming_supported",
    "streaming_effective",
    "usage_unavailable_reason",
    "max_retries_configured",
    "retry_count_observed",
    "timeout_configured_seconds",
    "error_type",
    "error_message_preview",
)

_CALL_ROLES = frozenset({"parent", "delegate", "subagent", "repair", "unknown"})

_STRIP_TRACE_KEYS = frozenset(
    {
        "b64",
        "base64",
        "bytes",
        "binary",
        "raw_prompt_text",
        "raw_llm_response_text",
        "prompt_text",
        "prompt",
        "raw_response",
        "absolute_path",
        "path",
        "image_bytes",
        "raw_image",
        "raw_image_data",
    }
)


def resolve_call_role(*, phase: str | None = None, explicit: str | None = None) -> str:
    """Map observability phase labels to generic call roles."""
    role = str(explicit or "").strip().lower()
    if role in _CALL_ROLES:
        return role
    label = str(phase or "").strip().lower()
    if not label:
        return "unknown"
    if label == "delegate_subtask" or label.startswith("delegate"):
        return "delegate"
    if "repair" in label:
        return "repair"
    if label in {"continuity_compaction"}:
        return "subagent"
    if label.startswith("choose_action") or label.startswith("kernel"):
        return "parent"
    return "unknown"


def extract_response_text(raw: Any) -> str:
    """Best-effort bounded response text extraction for char counts."""
    if isinstance(raw, str):
        return raw
    if not isinstance(raw, Mapping):
        return ""
    for key in ("text", "content", "output_text"):
        value = raw.get(key)
        if isinstance(value, str):
            return value
    error = raw.get("error")
    if isinstance(error, str):
        return error
    return ""


def extract_usage_fields(raw: Mapping[str, Any] | None) -> dict[str, int | None]:
    """Normalize provider usage payloads into trace token fields."""
    if not isinstance(raw, Mapping):
        return {
            "input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "reasoning_tokens": None,
            "total_tokens": None,
        }
    usage = raw.get("usage")
    if not isinstance(usage, Mapping):
        return {
            "input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "reasoning_tokens": None,
            "total_tokens": None,
        }
    cached = usage.get("cached_input_tokens")
    if cached is None:
        details = usage.get("prompt_tokens_details")
        if isinstance(details, Mapping):
            cached = details.get("cached_tokens")
    reasoning = usage.get("reasoning_tokens")
    if reasoning is None:
        completion_details = usage.get("completion_tokens_details")
        if isinstance(completion_details, Mapping):
            reasoning = completion_details.get("reasoning_tokens")
    return {
        "input_tokens": _coerce_int(usage.get("prompt_tokens")),
        "cached_input_tokens": _coerce_int(cached),
        "output_tokens": _coerce_int(usage.get("completion_tokens")),
        "reasoning_tokens": _coerce_int(reasoning),
        "total_tokens": _coerce_int(usage.get("total_tokens")),
    }


def extract_streaming_requested(
    *,
    kwargs: Mapping[str, Any] | None = None,
    call_options: object | None = None,
    raw_response: Mapping[str, Any] | None = None,
) -> bool:
    """Best-effort streaming flag from call options, kwargs, or provider echo."""
    try:
        from services.llm.call_options import LlmCallOptions
    except ImportError:
        LlmCallOptions = None  # type: ignore[misc, assignment]
    if LlmCallOptions is not None and isinstance(call_options, LlmCallOptions):
        if bool(getattr(call_options, "streaming", False)):
            return True
    if isinstance(kwargs, Mapping):
        for key in ("streaming", "stream"):
            if bool(kwargs.get(key)):
                return True
    if isinstance(raw_response, Mapping):
        if bool(raw_response.get("streaming_requested")):
            return True
    return False


def extract_service_tier_requested(
    *,
    kwargs: Mapping[str, Any] | None = None,
    call_options: object | None = None,
    raw_response: Mapping[str, Any] | None = None,
) -> str | None:
    """Best-effort requested service tier for trace surfaces."""
    try:
        from services.llm.call_options import LlmCallOptions
    except ImportError:
        LlmCallOptions = None  # type: ignore[misc, assignment]
    if LlmCallOptions is not None and isinstance(call_options, LlmCallOptions):
        tier = getattr(call_options, "service_tier", None)
        if isinstance(tier, str) and tier.strip():
            return tier.strip()
    if isinstance(kwargs, Mapping):
        raw = kwargs.get("service_tier")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    if isinstance(raw_response, Mapping):
        echoed = raw_response.get("service_tier_requested")
        if isinstance(echoed, str) and echoed.strip():
            return echoed.strip()
    return None


def build_llm_call_trace(
    *,
    provider: str = "unknown",
    call_role: str,
    call_name: str,
    model: str | None,
    started_at_epoch_seconds: float,
    finished_at_epoch_seconds: float,
    prompt_char_count: int,
    response_char_count: int = 0,
    input_tokens: int | None = None,
    cached_input_tokens: int | None = None,
    output_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    total_tokens: int | None = None,
    service_tier_requested: str | None = None,
    service_tier_returned: str | None = None,
    response_id: str | None = None,
    request_id: str | None = None,
    streaming_requested: bool = False,
    streaming_supported: bool = True,
    streaming_effective: bool | None = None,
    max_retries_configured: int | None = None,
    retry_count_observed: int | None = None,
    timeout_configured_seconds: float | None = None,
    error_type: str | None = None,
    error_message_preview: str | None = None,
    first_response_event_at_epoch_seconds: float | None = None,
    usage_unavailable_reason: str | None = None,
) -> dict[str, Any]:
    """Build a compact serializable LLM call trace record."""
    role = str(call_role or "unknown").strip().lower()
    if role not in _CALL_ROLES:
        role = "unknown"
    wall = max(0.0, float(finished_at_epoch_seconds) - float(started_at_epoch_seconds))
    trace: dict[str, Any] = {
        "provider": str(provider or "unknown"),
        "call_role": role,
        "call_name": _bound_text(call_name, 120) or "unknown",
        "model": _bound_text(model, 120) or None,
        "started_at_epoch_seconds": round(float(started_at_epoch_seconds), 3),
        "finished_at_epoch_seconds": round(float(finished_at_epoch_seconds), 3),
        "wall_seconds": round(wall, 3),
        "prompt_char_count": max(0, int(prompt_char_count)),
        "response_char_count": max(0, int(response_char_count)),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "service_tier_requested": service_tier_requested,
        "service_tier_returned": service_tier_returned,
        "response_id": _bound_text(response_id, 120) or None,
        "request_id": _bound_text(request_id, 120) or None,
        "streaming_requested": bool(streaming_requested),
        "streaming_supported": bool(streaming_supported),
        "streaming_effective": (
            bool(streaming_effective)
            if streaming_effective is not None
            else bool(streaming_requested) and bool(streaming_supported)
        ),
        "max_retries_configured": max_retries_configured,
        "retry_count_observed": retry_count_observed,
        "timeout_configured_seconds": timeout_configured_seconds,
        "error_type": _bound_text(error_type, 80) or None,
        "error_message_preview": _bound_text(error_message_preview, _MAX_ERROR_PREVIEW_CHARS) or None,
        "usage_unavailable_reason": _bound_text(usage_unavailable_reason, 120) or None,
    }
    _apply_phase_timing_fields(
        trace,
        started_at_epoch_seconds=started_at_epoch_seconds,
        finished_at_epoch_seconds=finished_at_epoch_seconds,
        streaming_effective=(
            bool(streaming_effective)
            if streaming_effective is not None
            else bool(streaming_requested) and bool(streaming_supported)
        ),
        first_response_event_at_epoch_seconds=first_response_event_at_epoch_seconds,
    )
    return sanitize_llm_call_trace(trace)


def build_llm_call_trace_from_response(
    *,
    raw_response: Any,
    call_role: str,
    call_name: str,
    model: str | None,
    prompt_char_count: int,
    started_at_epoch_seconds: float,
    finished_at_epoch_seconds: float,
    streaming_requested: bool = False,
    streaming_supported: bool = True,
    streaming_effective: bool | None = None,
    service_tier_requested: str | None = None,
    max_retries_configured: int | None = None,
    retry_count_observed: int | None = None,
    timeout_configured_seconds: float | None = None,
    error_type: str | None = None,
    error_message_preview: str | None = None,
) -> dict[str, Any]:
    """Build a trace from a provider response mapping or exception context."""
    response_map = raw_response if isinstance(raw_response, Mapping) else {}
    embedded = response_map.get("llm_call_trace")
    if isinstance(embedded, Mapping):
        merged = sanitize_llm_call_trace(embedded)
        if merged.get("call_role") in (None, "", "unknown"):
            merged["call_role"] = resolve_call_role(phase=call_name, explicit=call_role)
        if not merged.get("call_name"):
            merged["call_name"] = _bound_text(call_name, 120) or "unknown"
        if merged.get("prompt_char_count") in (None, 0):
            merged["prompt_char_count"] = max(0, int(prompt_char_count))
        return merged

    response_text = extract_response_text(raw_response)
    usage = extract_usage_fields(response_map)
    provider_model = response_map.get("provider_model") or response_map.get("api_model") or response_map.get("model")
    resolved_model = _bound_text(provider_model or model, 120) or None
    provider_error = response_map.get("error")
    if error_message_preview is None and isinstance(provider_error, str) and provider_error.strip():
        error_message_preview = provider_error
    if error_type is None and not bool(response_map.get("success", True)):
        error_type = "provider_failure"

    resolved_streaming = streaming_requested or extract_streaming_requested(raw_response=response_map)
    effective = (
        bool(streaming_effective)
        if streaming_effective is not None
        else bool(resolved_streaming) and bool(streaming_supported)
    )
    first_event = _coerce_float(response_map.get("first_response_event_at_epoch_seconds"))

    return build_llm_call_trace(
        call_role=call_role,
        call_name=call_name,
        model=resolved_model,
        started_at_epoch_seconds=started_at_epoch_seconds,
        finished_at_epoch_seconds=finished_at_epoch_seconds,
        prompt_char_count=prompt_char_count,
        response_char_count=len(response_text),
        input_tokens=usage["input_tokens"],
        cached_input_tokens=usage["cached_input_tokens"],
        output_tokens=usage["output_tokens"],
        reasoning_tokens=usage["reasoning_tokens"],
        total_tokens=usage["total_tokens"],
        service_tier_requested=service_tier_requested
        or extract_service_tier_requested(raw_response=response_map),
        service_tier_returned=_optional_str(response_map.get("service_tier_returned")),
        response_id=_optional_str(response_map.get("response_id")),
        request_id=_optional_str(response_map.get("request_id")),
        streaming_requested=resolved_streaming,
        streaming_supported=streaming_supported,
        streaming_effective=effective,
        first_response_event_at_epoch_seconds=first_event,
        usage_unavailable_reason=_optional_str(response_map.get("usage_unavailable_reason")),
        max_retries_configured=(
            _coerce_int(response_map.get("max_retries_configured"))
            if response_map.get("max_retries_configured") is not None
            else max_retries_configured
        ),
        retry_count_observed=(
            _coerce_int(response_map.get("retry_count_observed"))
            if response_map.get("retry_count_observed") is not None
            else retry_count_observed
        ),
        timeout_configured_seconds=(
            _coerce_float(response_map.get("timeout_configured_seconds"))
            if response_map.get("timeout_configured_seconds") is not None
            else timeout_configured_seconds
        ),
        error_type=error_type,
        error_message_preview=error_message_preview,
    )


def collect_llm_call_traces(
    *,
    raw_response: Any = None,
    repair_records: Sequence[Mapping[str, Any]] | None = None,
    extra_traces: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Collect ordered parent/repair traces for one turn audit record."""
    traces: list[dict[str, Any]] = []
    if isinstance(raw_response, Mapping):
        embedded = raw_response.get("llm_call_trace")
        if isinstance(embedded, Mapping):
            traces.append(sanitize_llm_call_trace(embedded))
    if isinstance(repair_records, Sequence):
        for record in repair_records:
            if not isinstance(record, Mapping):
                continue
            embedded = record.get("llm_call_trace")
            if isinstance(embedded, Mapping):
                traces.append(sanitize_llm_call_trace(embedded))
    if isinstance(extra_traces, Sequence):
        for row in extra_traces:
            if isinstance(row, Mapping):
                traces.append(sanitize_llm_call_trace(row))
    return traces


def sanitize_llm_call_trace(trace: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe trace with only known fields and bounded values."""
    out: dict[str, Any] = {}
    for key in LLM_CALL_TRACE_FIELDS:
        if key not in trace:
            continue
        value = trace[key]
        if key in _STRIP_TRACE_KEYS:
            continue
        if value is None:
            out[key] = None
            continue
        if key.endswith("_seconds") and key != "timeout_configured_seconds":
            out[key] = round(_coerce_float(value) or 0.0, 3)
            continue
        if key.endswith("_tokens") or key in {"max_retries_configured", "retry_count_observed"}:
            out[key] = _coerce_int(value)
            continue
        if key in {"streaming_requested", "streaming_supported", "streaming_effective"}:
            out[key] = bool(value)
            continue
        if isinstance(value, (dict, list, tuple)):
            continue
        out[key] = value
    # Ensure streaming defaults exist for forward-compatible readers.
    if "streaming_requested" not in out:
        out["streaming_requested"] = False
    if "streaming_supported" not in out:
        out["streaming_supported"] = True
    if "streaming_effective" not in out:
        out["streaming_effective"] = bool(out.get("streaming_requested")) and bool(
            out.get("streaming_supported", True)
        )
    return out


def trace_is_json_serializable(trace: Mapping[str, Any]) -> bool:
    """Mechanical guard for tests — trace must json.dumps without raw payloads."""
    payload = sanitize_llm_call_trace(trace)
    text = json.dumps(payload)
    lowered = text.lower()
    for forbidden in ("b64", "base64", "absolute_path", "raw_prompt", "raw_llm_response"):
        if forbidden in lowered:
            return False
    return True


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _bound_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= int(limit):
        return text
    return text[: int(limit)]


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _apply_phase_timing_fields(
    trace: dict[str, Any],
    *,
    started_at_epoch_seconds: float,
    finished_at_epoch_seconds: float,
    streaming_effective: bool,
    first_response_event_at_epoch_seconds: float | None = None,
) -> None:
    """Add first-event timing only when streaming actually occurred."""
    if not streaming_effective or first_response_event_at_epoch_seconds is None:
        return
    first = float(first_response_event_at_epoch_seconds)
    started = float(started_at_epoch_seconds)
    finished = float(finished_at_epoch_seconds)
    wait = max(0.0, first - started)
    stream = max(0.0, finished - first)
    trace["first_response_event_at_epoch_seconds"] = round(first, 3)
    trace["time_to_first_response_event_seconds"] = round(wait, 3)
    trace["provider_wait_seconds"] = round(wait, 3)
    trace["response_stream_seconds"] = round(stream, 3)


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
