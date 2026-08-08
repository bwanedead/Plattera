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
            models={"muse-spark-1.2-contributor": {"context_window_tokens": 1_048_576}},
            call_log=log,
        ),
    )
    caller = build_provider_model_caller(default_model_name="gpt-5.6-luna", registry=reg)
    parent = caller("parent prompt", "gpt-5.6-luna")
    delegate = caller("delegate prompt", "muse-spark-1.2-contributor")
    assert parent["llm_call_trace"]["provider"] == "openai"
    assert delegate["llm_call_trace"]["provider"] == "meta"
    assert log == [("openai", "gpt-5.6-luna"), ("meta", "muse-spark-1.2-contributor")]


def test_muse_parent_and_openai_delegate_and_inverse() -> None:
    log: list[tuple[str, str]] = []
    muse = "muse-spark-1.2-contributor"
    luna = "gpt-5.6-luna"
    reg = _registry_with(
        _FakeLLM(
            name="openai",
            models={luna: {"context_window_tokens": 400_000}},
            call_log=log,
        ),
        _FakeLLM(
            name="meta",
            models={muse: {"context_window_tokens": 1_048_576}},
            call_log=log,
        ),
    )
    caller = build_provider_model_caller(default_model_name=muse, registry=reg)
    assert caller("p", muse)["llm_call_trace"]["provider"] == "meta"
    assert caller("d", luna)["llm_call_trace"]["provider"] == "openai"
    # Cached wrappers must not cross-wire after switching providers.
    assert caller("p2", muse)["llm_call_trace"]["provider"] == "meta"
    assert log == [("meta", muse), ("openai", luna), ("meta", muse)]

    log.clear()
    caller2 = build_provider_model_caller(default_model_name=luna, registry=reg)
    assert caller2("p", luna)["llm_call_trace"]["provider"] == "openai"
    assert caller2("d", muse)["llm_call_trace"]["provider"] == "meta"
    assert log == [("openai", luna), ("meta", muse)]


def test_image_bearing_delegate_reaches_meta_with_attachment_order() -> None:
    from services.llm.call_options import LlmCallOptions

    captured: list[Any] = []

    class _CaptureMeta(_FakeLLM):
        def call_text(self, prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
            captured.append(kwargs.get("call_options"))
            return super().call_text(prompt, model, **kwargs)

    muse = "muse-spark-1.2-contributor"
    reg = _registry_with(
        _CaptureMeta(
            name="meta",
            models={muse: {"context_window_tokens": 1_048_576}},
        )
    )
    caller = build_provider_model_caller(default_model_name=muse, registry=reg)
    opts = LlmCallOptions(
        image_attachments=(
            {"b64": "ONE", "media_type": "image/png"},
            {"b64": "TWO", "media_type": "image/jpeg"},
        ),
        phase="delegate_subtask",
    )
    result = caller("visual delegate", muse, call_options=opts)
    assert result["llm_call_trace"]["provider"] == "meta"
    assert captured and captured[0] is not None
    atts = list(captured[0].image_attachments)
    assert [a["b64"] for a in atts] == ["ONE", "TWO"]


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
