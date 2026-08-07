"""Harness-owned LLM call telemetry (mechanical, provider-agnostic surface)."""

from .llm_call_trace import (
    LLM_CALL_TRACE_FIELDS,
    build_llm_call_trace,
    build_llm_call_trace_from_response,
    collect_llm_call_traces,
    resolve_call_role,
    sanitize_llm_call_trace,
)
from .instrumented_caller import instrument_model_caller
from .provider_model_caller import build_provider_model_caller, ensure_model_provider_ready

__all__ = [
    "LLM_CALL_TRACE_FIELDS",
    "build_llm_call_trace",
    "build_llm_call_trace_from_response",
    "build_provider_model_caller",
    "collect_llm_call_traces",
    "ensure_model_provider_ready",
    "instrument_model_caller",
    "resolve_call_role",
    "sanitize_llm_call_trace",
]
