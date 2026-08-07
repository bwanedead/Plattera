"""Tests for harness-local provider-neutral model context metadata."""

from __future__ import annotations

import pytest

from services.llm.openai import OpenAIService
from services.registry import ServiceRegistry, reset_registry_for_tests

from harness.runtime.memory.model_limits import (
    estimate_prompt_tokens_from_chars,
    resolve_context_window_tokens,
)


@pytest.fixture
def isolated_global_registry():
    """Reset the process-global registry before and after mutating tests."""
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


def test_gpt_5_4_mini_has_explicit_context_and_max_output() -> None:
    m = OpenAIService.models["gpt-5.4-mini"]
    assert m["context_window_tokens"] == 400_000
    assert m["max_output_tokens"] == 128_000


def test_resolve_unknown_model_yields_250k_fallback_flag() -> None:
    cw, used_fb = resolve_context_window_tokens("model-id-absent-from-service-registry")
    assert cw == 250_000
    assert used_fb is True


def test_resolve_known_model_no_fallback_without_credentials(
    monkeypatch, isolated_global_registry
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("services.llm.openai._get_openai_api_key", lambda: None)
    cw, used_fb = resolve_context_window_tokens("gpt-5.4-mini")
    assert cw == 400_000
    assert used_fb is False


def test_resolve_gpt56_terra_and_luna_no_fallback(isolated_global_registry) -> None:
    for model_id in ("gpt-5.6-terra", "gpt-5.6-luna"):
        assert model_id in OpenAIService.models
        cw, used_fb = resolve_context_window_tokens(model_id)
        assert cw == OpenAIService.models[model_id]["context_window_tokens"]
        assert used_fb is False


def test_estimate_prompt_tokens_from_chars_is_documented_heuristic() -> None:
    assert estimate_prompt_tokens_from_chars(400) == 100


def test_known_model_limits_via_registry_catalog_without_available_service(
    monkeypatch, isolated_global_registry
) -> None:
    from services.llm.base import LLMService

    class Declared(LLMService):
        name = "openai"
        models = {"gpt-5.4-mini": {"context_window_tokens": 400_000}}

        def is_available(self) -> bool:
            return False

        def call_text(self, prompt: str, model: str, **kwargs):
            raise AssertionError("must not call")

        def call_vision(self, prompt: str, image_data: str, model: str, **kwargs):
            raise AssertionError("must not call")

    reg = ServiceRegistry(discover=False)
    reg.accept_llm_service(Declared())
    monkeypatch.setattr("services.registry._registry", reg)
    cw, used_fb = resolve_context_window_tokens("gpt-5.4-mini")
    assert cw == 400_000
    assert used_fb is False
