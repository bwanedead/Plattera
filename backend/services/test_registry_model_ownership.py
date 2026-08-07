"""Tests for credential-independent LLM model ownership in ServiceRegistry."""

from __future__ import annotations

from typing import Any

import pytest

from services.llm.base import LLMService
from services.registry import (
    ModelProviderError,
    ServiceRegistry,
    get_model_metadata,
    get_provider_name_for_model,
    get_available_llm_service_for_model,
    reset_registry_for_tests,
)


class _FakeLLM(LLMService):
    def __init__(
        self,
        *,
        name: str,
        models: dict[str, dict[str, Any]],
        available: bool,
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
        return {"success": True, "text": f"{self.name}:{model}", "model": model}

    def call_vision(self, prompt: str, image_data: str, model: str, **kwargs) -> dict[str, Any]:
        return self.call_text(prompt, model, **kwargs)


@pytest.fixture
def isolated_global_registry():
    """Reset the process-global registry before and after mutating tests."""
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


def test_openai_model_metadata_resolves_without_api_key(
    monkeypatch, isolated_global_registry
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("services.llm.openai._get_openai_api_key", lambda: None)
    from services.registry import get_registry

    reg = get_registry()
    meta = reg.get_model_metadata("gpt-5.6-luna")
    assert meta["context_window_tokens"] > 0
    assert reg.get_provider_name_for_model("gpt-5.6-luna") == "openai"
    with pytest.raises(ModelProviderError) as raised:
        reg.get_available_llm_service_for_model("gpt-5.6-luna")
    assert raised.value.reason_code == "model_provider_unavailable"
    assert "gpt-5.6-luna" not in reg.get_all_models()


def test_known_unavailable_model_stays_out_of_available_listing() -> None:
    """Catalog knowledge must remain distinct from user-facing availability."""
    reg = ServiceRegistry(discover=False)
    reg.accept_llm_service(
        _FakeLLM(
            name="alpha",
            models={"alpha-model": {"context_window_tokens": 10_000}},
            available=False,
        )
    )
    assert reg.get_model_metadata("alpha-model")["context_window_tokens"] == 10_000
    assert reg.get_provider_name_for_model("alpha-model") == "alpha"
    with pytest.raises(ModelProviderError) as unavailable:
        reg.get_available_llm_service_for_model("alpha-model")
    assert unavailable.value.reason_code == "model_provider_unavailable"
    assert "alpha-model" not in reg.get_all_models()
    assert reg.get_service_info()["llm_services"] == {}
    assert reg.get_service_info()["total_models"] == 0


def test_unknown_model_distinct_from_unavailable_provider() -> None:
    reg = ServiceRegistry(discover=False)
    reg.accept_llm_service(
        _FakeLLM(
            name="alpha",
            models={"alpha-model": {"context_window_tokens": 10_000}},
            available=False,
        )
    )
    with pytest.raises(ModelProviderError) as unknown:
        reg.get_model_metadata("totally-unknown-model")
    assert unknown.value.reason_code == "model_provider_not_found"

    with pytest.raises(ModelProviderError) as unavailable:
        reg.get_available_llm_service_for_model("alpha-model")
    assert unavailable.value.reason_code == "model_provider_unavailable"
    assert reg.get_provider_name_for_model("alpha-model") == "alpha"


def test_duplicate_model_ownership_rejected_and_absent_from_listing() -> None:
    reg = ServiceRegistry(discover=False)
    reg.accept_llm_service(
        _FakeLLM(
            name="alpha",
            models={"shared-model": {"context_window_tokens": 1}},
            available=True,
        )
    )
    reg.accept_llm_service(
        _FakeLLM(
            name="beta",
            models={"shared-model": {"context_window_tokens": 2}},
            available=True,
        )
    )
    with pytest.raises(ModelProviderError) as raised:
        reg.get_provider_name_for_model("shared-model")
    assert raised.value.reason_code == "model_provider_ambiguous"
    with pytest.raises(ModelProviderError) as raised_meta:
        reg.get_model_metadata("shared-model")
    assert raised_meta.value.reason_code == "model_provider_ambiguous"
    assert "shared-model" not in reg.get_all_models()


def test_available_model_appears_in_get_all_models() -> None:
    reg = ServiceRegistry(discover=False)
    reg.accept_llm_service(
        _FakeLLM(
            name="omega",
            models={"omega-1": {"context_window_tokens": 99}},
            available=True,
        )
    )
    listed = reg.get_all_models()
    assert "omega-1" in listed
    assert listed["omega-1"]["service_name"] == "omega"
    info = reg.get_service_info()
    assert info["llm_services"]["omega"]["available"] is True
    assert "omega-1" in info["llm_services"]["omega"]["models"]


def test_module_level_resolution_helpers_use_canonical_registry(
    monkeypatch, isolated_global_registry
) -> None:
    reg = ServiceRegistry(discover=False)
    reg.accept_llm_service(
        _FakeLLM(
            name="omega",
            models={"omega-1": {"context_window_tokens": 99}},
            available=True,
        )
    )
    monkeypatch.setattr("services.registry._registry", reg)
    assert get_provider_name_for_model("omega-1") == "omega"
    assert get_model_metadata("omega-1")["context_window_tokens"] == 99
    assert get_available_llm_service_for_model("omega-1").name == "omega"
