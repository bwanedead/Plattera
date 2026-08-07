"""Local provider-neutral model context limits for harness compaction triggers.

Values are read from the canonical service registry model catalog. The harness
does not query providers at runtime for context-window size.

If a loop run uses a model id that has no positive ``context_window_tokens``
in that catalog, ``resolve_context_window_tokens`` returns
``(250_000, True)`` — the second value flags that this is an explicit harness
fallback, not a provider-declared limit.

Metadata lookup works without provider credentials.
"""

from __future__ import annotations

from services.registry import ModelProviderError, get_model_metadata

# Explicit harness fallback when catalog has no usable context_window_tokens.
_FALLBACK_CONTEXT_WINDOW_TOKENS = 250_000


def resolve_context_window_tokens(model_name: str) -> tuple[int, bool]:
    """Return ``(context_window_tokens, used_fallback)``."""
    mid = str(model_name or "").strip()
    try:
        row = get_model_metadata(mid)
    except ModelProviderError:
        return _FALLBACK_CONTEXT_WINDOW_TOKENS, True
    v = row.get("context_window_tokens")
    if isinstance(v, int) and v > 0:
        return v, False
    return _FALLBACK_CONTEXT_WINDOW_TOKENS, True


def estimate_prompt_tokens_from_chars(char_count: int) -> int:
    """Rough token estimate for compaction triggers only (~4 characters per token)."""
    return max(1, int(char_count) // 4)
