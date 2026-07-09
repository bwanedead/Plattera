"""Tests for harness-local OpenAI model context metadata + compaction token heuristics."""

from __future__ import annotations

from services.llm.openai import OpenAIService

from harness.runtime.memory.openai_model_limits import (
    estimate_prompt_tokens_from_chars,
    resolve_context_window_tokens,
)


def test_gpt_5_4_mini_has_explicit_context_and_max_output() -> None:
    m = OpenAIService.models["gpt-5.4-mini"]
    assert m["context_window_tokens"] == 400_000
    assert m["max_output_tokens"] == 128_000


def test_resolve_unknown_model_yields_250k_fallback_flag() -> None:
    cw, used_fb = resolve_context_window_tokens("model-id-absent-from-openai-service-registry")
    assert cw == 250_000
    assert used_fb is True


def test_resolve_known_model_no_fallback() -> None:
    cw, used_fb = resolve_context_window_tokens("gpt-5.4-mini")
    assert cw == 400_000
    assert used_fb is False


def test_resolve_gpt56_terra_and_luna_no_fallback() -> None:
    for model_id in ("gpt-5.6-terra", "gpt-5.6-luna"):
        assert model_id in OpenAIService.models
        cw, used_fb = resolve_context_window_tokens(model_id)
        assert cw == OpenAIService.models[model_id]["context_window_tokens"]
        assert used_fb is False


def test_estimate_prompt_tokens_from_chars_is_documented_heuristic() -> None:
    assert estimate_prompt_tokens_from_chars(400) == 100
