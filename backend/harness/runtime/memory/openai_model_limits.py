"""Local OpenAI model context limits for harness compaction triggers.

Values are read from ``OpenAIService.models`` (``services.llm.openai``). The
harness does not query providers at runtime for context-window size.

If a loop run uses a model id that has no positive ``context_window_tokens``
in that registry, ``resolve_context_window_tokens`` returns
``(250_000, True)`` — the second value flags that this is an explicit harness
fallback, not a provider-declared limit.
"""

from __future__ import annotations

# Explicit harness fallback when registry has no usable context_window_tokens.
_FALLBACK_CONTEXT_WINDOW_TOKENS = 250_000


def resolve_context_window_tokens(model_name: str) -> tuple[int, bool]:
    """Return ``(context_window_tokens, used_fallback)``."""
    from services.llm.openai import OpenAIService

    row = OpenAIService.models.get(str(model_name or "").strip()) or {}
    v = row.get("context_window_tokens")
    if isinstance(v, int) and v > 0:
        return v, False
    return _FALLBACK_CONTEXT_WINDOW_TOKENS, True


def estimate_prompt_tokens_from_chars(char_count: int) -> int:
    """Rough token estimate for compaction triggers only (~4 characters per token)."""
    return max(1, int(char_count) // 4)
