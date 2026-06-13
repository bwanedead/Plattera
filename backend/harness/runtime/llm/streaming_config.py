"""Resolve disabled-by-default OpenAI streaming for harness LLM calls."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from services.llm.call_options import LlmCallOptions

STREAMING_RUN_CONTEXT_KEYS = ("llm_streaming", "openai_streaming", "streaming")
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})


def _parse_streaming_flag(raw: Any) -> bool | None:
    """Return explicit True/False when set; None when absent or unrecognized."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int) and not isinstance(raw, bool):
        if raw == 0:
            return False
        if raw == 1:
            return True
        return None
    if isinstance(raw, str):
        text = raw.strip().lower()
        if text in _TRUTHY:
            return True
        if text in _FALSY:
            return False
    return None


def resolve_llm_streaming_enabled(run_context: Mapping[str, Any] | None = None) -> bool:
    """Return True when launch/run config or env explicitly enables LLM streaming.

    Run-context values take precedence over ``HARNESS_LLM_STREAMING``. An explicit
    false in launch context disables streaming even when the env var is true.
    """
    if isinstance(run_context, Mapping):
        for key in STREAMING_RUN_CONTEXT_KEYS:
            if key not in run_context:
                continue
            parsed = _parse_streaming_flag(run_context.get(key))
            if parsed is not None:
                return parsed
    env = str(os.environ.get("HARNESS_LLM_STREAMING", "") or "").strip().lower()
    return env in _TRUTHY


def apply_streaming_to_call_options(
    call_options: LlmCallOptions,
    *,
    run_context: Mapping[str, Any] | None = None,
    streaming: bool | None = None,
) -> LlmCallOptions:
    """Enable streaming on call options when run config or override requests it."""
    enabled = (
        bool(streaming)
        if streaming is not None
        else resolve_llm_streaming_enabled(run_context)
    )
    if not enabled:
        return call_options
    return replace(call_options, streaming=True)
