"""Wrap harness model callers with generic OpenAI call trace emission."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from services.llm.call_options import LlmCallOptions

from .llm_call_trace import (
    build_llm_call_trace,
    build_llm_call_trace_from_response,
    extract_service_tier_requested,
    resolve_call_role,
)

TextModelCaller = Callable[..., Mapping[str, Any] | str]


def instrument_openai_model_caller(
    caller: TextModelCaller,
    *,
    provider: str = "openai",
    streaming_supported: bool = True,
) -> TextModelCaller:
    """Attach ``llm_call_trace`` to mapping responses and exception objects.

    Mapping responses receive an embedded ``llm_call_trace`` field. Exceptions
    raised by the inner caller receive ``exc.llm_call_trace``. Plain ``str``
    responses are returned unchanged, so audit surfaces cannot collect a trace
    unless the caller is upgraded to return a mapping envelope.
    """

    def _wrapped(prompt: str, model: str, **kwargs: Any) -> Mapping[str, Any] | str:
        started = time.time()
        call_opts = kwargs.get("call_options")
        phase = _phase_from_call_options(call_opts) or kwargs.get("phase")
        call_role = resolve_call_role(phase=phase)
        call_name = str(phase or "unknown")
        prompt_chars = len(prompt or "")
        try:
            result = caller(prompt, model, **kwargs)
            finished = time.time()
            trace = build_llm_call_trace_from_response(
                raw_response=result,
                call_role=call_role,
                call_name=call_name,
                model=model,
                prompt_char_count=prompt_chars,
                started_at_epoch_seconds=started,
                finished_at_epoch_seconds=finished,
                streaming_requested=False,
                streaming_supported=streaming_supported,
                service_tier_requested=extract_service_tier_requested(
                    kwargs=kwargs,
                    call_options=call_opts,
                    raw_response=result if isinstance(result, Mapping) else None,
                ),
            )
            trace["provider"] = provider
            if isinstance(result, Mapping):
                merged = dict(result)
                merged["llm_call_trace"] = trace
                return merged
            return result
        except Exception as exc:
            finished = time.time()
            trace = build_llm_call_trace(
                provider=provider,
                call_role=call_role,
                call_name=call_name,
                model=model,
                started_at_epoch_seconds=started,
                finished_at_epoch_seconds=finished,
                prompt_char_count=prompt_chars,
                streaming_requested=False,
                streaming_supported=streaming_supported,
                service_tier_requested=extract_service_tier_requested(
                    kwargs=kwargs,
                    call_options=call_opts,
                ),
                error_type=type(exc).__name__,
                error_message_preview=str(exc),
            )
            setattr(exc, "llm_call_trace", trace)
            raise

    return _wrapped


def extract_trace_from_exception(exc: BaseException) -> dict[str, Any] | None:
    """Read a trace previously attached by :func:`instrument_openai_model_caller`."""
    trace = getattr(exc, "llm_call_trace", None)
    if isinstance(trace, Mapping):
        return dict(trace)
    return None


def _phase_from_call_options(call_opts: object | None) -> str | None:
    if isinstance(call_opts, LlmCallOptions):
        phase = call_opts.phase
        return str(phase).strip() if phase else None
    return None
