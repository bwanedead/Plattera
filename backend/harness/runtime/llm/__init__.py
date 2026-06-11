"""Harness-owned LLM call telemetry (mechanical, provider-agnostic surface)."""

from .llm_call_trace import (
    LLM_CALL_TRACE_FIELDS,
    build_llm_call_trace,
    build_llm_call_trace_from_response,
    collect_llm_call_traces,
    resolve_call_role,
    sanitize_llm_call_trace,
)
from .instrumented_caller import instrument_openai_model_caller

__all__ = [
    "LLM_CALL_TRACE_FIELDS",
    "build_llm_call_trace",
    "build_llm_call_trace_from_response",
    "collect_llm_call_traces",
    "instrument_openai_model_caller",
    "resolve_call_role",
    "sanitize_llm_call_trace",
]
