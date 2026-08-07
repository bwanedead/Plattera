"""Tests for provider-neutral harness model caller."""

from __future__ import annotations

from typing import Any

import pytest

from harness.runtime.llm.provider_model_caller import (
    build_provider_model_caller,
    ensure_model_provider_ready,
)
from services.llm.base import LLMService
from services.registry import ModelProviderError, ServiceRegistry


class _FakeLLM(LLMService):
    def __init__(
        self,
        *,
        name: str,
        models: dict[str, dict[str, Any]],
        available: bool = True,
        call_log: list[tuple[str, str]] | None = None,
    ) -> None:
        self.name = name
        self.models = models
        self._available = available
        self._call_log = call_log if call_log is not None else []

    def is_available(self) -> bool:
        return self._available

    def call_text(self, prompt: str, model: str, **kwargs) -> dict[str, Any]:
        self._call_log.append((self.name, model))
        return {"success": True, "text": f"from:{self.name}:{model}", "model": model}

    def call_vision(self, prompt: str, image_data: str, model: str, **kwargs) -> dict[str, Any]:
        return self.call_text(prompt, model, **kwargs)


def _registry_with(*services: LLMService) -> ServiceRegistry:
    reg = ServiceRegistry(discover=False)
    for service in services:
        reg.accept_llm_service(service)
    return reg


def test_openai_owned_model_routes_to_openai_fake() -> None:
    log: list[tuple[str, str]] = []
    openai = _FakeLLM(
        name="openai",
        models={"gpt-5.6-luna": {"context_window_tokens": 400_000}},
        call_log=log,
    )
    other = _FakeLLM(
        name="other",
        models={"other-model": {"context_window_tokens": 8_000}},
        call_log=log,
    )
    caller = build_provider_model_caller(
        default_model_name="gpt-5.6-luna",
        registry=_registry_with(openai, other),
    )
    result = caller("prompt", "gpt-5.6-luna")
    assert result["text"] == "from:openai:gpt-5.6-luna"
    assert result["llm_call_trace"]["provider"] == "openai"
    assert log == [("openai", "gpt-5.6-luna")]


def test_effective_model_resolved_per_call_with_blank_fallback() -> None:
    log: list[tuple[str, str]] = []
    reg = _registry_with(
        _FakeLLM(
            name="openai",
            models={
                "gpt-5.6-luna": {"context_window_tokens": 400_000},
                "gpt-5.4-mini": {"context_window_tokens": 400_000},
            },
            call_log=log,
        )
    )
    caller = build_provider_model_caller(default_model_name="gpt-5.6-luna", registry=reg)
    caller("p1", "")
    caller("p2", "gpt-5.4-mini")
    assert log == [("openai", "gpt-5.6-luna"), ("openai", "gpt-5.4-mini")]


def test_second_provider_model_routes_to_its_own_service() -> None:
    log: list[tuple[str, str]] = []
    reg = _registry_with(
        _FakeLLM(
            name="openai",
            models={"gpt-5.6-luna": {"context_window_tokens": 400_000}},
            call_log=log,
        ),
        _FakeLLM(
            name="meta",
            models={"meta-llama-test": {"context_window_tokens": 128_000}},
            call_log=log,
        ),
    )
    caller = build_provider_model_caller(default_model_name="gpt-5.6-luna", registry=reg)
    parent = caller("parent prompt", "gpt-5.6-luna")
    delegate = caller("delegate prompt", "meta-llama-test")
    assert parent["llm_call_trace"]["provider"] == "openai"
    assert delegate["llm_call_trace"]["provider"] == "meta"
    assert log == [("openai", "gpt-5.6-luna"), ("meta", "meta-llama-test")]


def test_parent_and_delegate_models_through_one_caller() -> None:
    log: list[tuple[str, str]] = []
    reg = _registry_with(
        _FakeLLM(
            name="openai",
            models={"parent-model": {"context_window_tokens": 10}},
            call_log=log,
        ),
        _FakeLLM(
            name="alt",
            models={"delegate-model": {"context_window_tokens": 10}},
            call_log=log,
        ),
    )
    caller = build_provider_model_caller(default_model_name="parent-model", registry=reg)
    assert caller("a", "parent-model")["text"].startswith("from:openai:")
    assert caller("b", "delegate-model")["text"].startswith("from:alt:")
    assert [entry[0] for entry in log] == ["openai", "alt"]


def test_unknown_and_unavailable_fail_clearly() -> None:
    reg = _registry_with(
        _FakeLLM(
            name="openai",
            models={"gpt-5.6-luna": {"context_window_tokens": 400_000}},
            available=False,
        )
    )
    caller = build_provider_model_caller(default_model_name="gpt-5.6-luna", registry=reg)
    with pytest.raises(ModelProviderError) as unknown:
        caller("p", "no-such-model")
    assert unknown.value.reason_code == "model_provider_not_found"
    with pytest.raises(ModelProviderError) as unavailable:
        caller("p", "gpt-5.6-luna")
    assert unavailable.value.reason_code == "model_provider_unavailable"


def test_ensure_model_provider_ready_before_loop() -> None:
    reg = _registry_with(
        _FakeLLM(
            name="openai",
            models={"gpt-5.6-luna": {"context_window_tokens": 400_000}},
            available=False,
        )
    )
    with pytest.raises(ModelProviderError) as raised:
        ensure_model_provider_ready("gpt-5.6-luna", registry=reg)
    assert raised.value.reason_code == "model_provider_unavailable"
