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
        streaming_supported: bool = True,
        refuse_streaming: bool = False,
        received: list[dict[str, Any]] | None = None,
    ) -> None:
        self.name = name
        self.models = models
        self._available = available
        self._call_log = call_log if call_log is not None else []
        self._streaming_supported = streaming_supported
        self._refuse_streaming = refuse_streaming
        self.received = received if received is not None else []

    def is_available(self) -> bool:
        return self._available

    def supports_streaming(self) -> bool:
        return self._streaming_supported

    def call_text(self, prompt: str, model: str, **kwargs) -> dict[str, Any]:
        from harness.runtime.llm.llm_call_trace import extract_streaming_requested

        streaming = extract_streaming_requested(
            kwargs=kwargs,
            call_options=kwargs.get("call_options"),
        )
        self.received.append(
            {
                "prompt": prompt,
                "model": model,
                "streaming": streaming,
                "call_options": kwargs.get("call_options"),
                "kwargs": dict(kwargs),
            }
        )
        self._call_log.append((self.name, model))
        if self._refuse_streaming and streaming:
            return {
                "success": False,
                "error": "streaming_unsupported",
                "finish_reason": "streaming_unsupported",
                "text": None,
                "model": model,
            }
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


def _streaming_opts(*, phase: str, streaming: bool = True) -> Any:
    from services.llm.call_options import LlmCallOptions

    return LlmCallOptions(output_mode="json_object", phase=phase, streaming=streaming)


def test_streaming_passthrough_when_provider_supports_it() -> None:
    openai = _FakeLLM(
        name="openai",
        models={"gpt-5.6-luna": {"context_window_tokens": 400_000}},
        streaming_supported=True,
        refuse_streaming=False,
    )
    caller = build_provider_model_caller(
        default_model_name="gpt-5.6-luna",
        registry=_registry_with(openai),
    )
    opts = _streaming_opts(phase="choose_action")
    result = caller("prompt", "gpt-5.6-luna", call_options=opts)
    assert result["success"] is True
    assert openai.received[0]["streaming"] is True
    assert openai.received[0]["call_options"] is opts
    trace = result["llm_call_trace"]
    assert trace["streaming_requested"] is True
    assert trace["streaming_supported"] is True
    assert trace["streaming_effective"] is True


def test_streaming_downgraded_when_provider_does_not_support_it() -> None:
    meta = _FakeLLM(
        name="meta",
        models={"muse-spark-1.2-contributor": {"context_window_tokens": 1_048_576}},
        streaming_supported=False,
        refuse_streaming=True,
    )
    caller = build_provider_model_caller(
        default_model_name="muse-spark-1.2-contributor",
        registry=_registry_with(meta),
    )
    opts = _streaming_opts(phase="choose_action")
    result = caller("prompt", "muse-spark-1.2-contributor", call_options=opts, stream=True)
    assert result["success"] is True
    assert result["text"].startswith("from:meta:")
    assert opts.streaming is True
    received = meta.received[0]
    assert received["streaming"] is False
    assert "stream" not in received["kwargs"]
    assert "streaming" not in received["kwargs"]
    assert received["call_options"] is not opts
    assert received["call_options"].streaming is False
    assert received["call_options"].phase == "choose_action"
    assert received["call_options"].output_mode == "json_object"
    trace = result["llm_call_trace"]
    assert trace["streaming_requested"] is True
    assert trace["streaming_supported"] is False
    assert trace["streaming_effective"] is False


def test_streaming_negotiation_covers_parent_repair_and_delegate_phases() -> None:
    meta = _FakeLLM(
        name="meta",
        models={"muse-spark-1.2-contributor": {"context_window_tokens": 1_048_576}},
        streaming_supported=False,
        refuse_streaming=True,
    )
    caller = build_provider_model_caller(
        default_model_name="muse-spark-1.2-contributor",
        registry=_registry_with(meta),
    )
    for phase, role in (
        ("choose_action", "parent"),
        ("choose_action_repair", "repair"),
        ("delegate_subtask", "delegate"),
    ):
        result = caller("p", "muse-spark-1.2-contributor", call_options=_streaming_opts(phase=phase))
        assert result["success"] is True
        assert result["llm_call_trace"]["call_role"] == role
        assert result["llm_call_trace"]["streaming_requested"] is True
        assert result["llm_call_trace"]["streaming_supported"] is False
        assert result["llm_call_trace"]["streaming_effective"] is False
    assert all(row["streaming"] is False for row in meta.received)


def test_muse_parent_downgraded_openai_delegate_streams() -> None:
    muse = "muse-spark-1.2-contributor"
    luna = "gpt-5.6-luna"
    openai = _FakeLLM(
        name="openai",
        models={luna: {"context_window_tokens": 400_000}},
        streaming_supported=True,
    )
    meta = _FakeLLM(
        name="meta",
        models={muse: {"context_window_tokens": 1_048_576}},
        streaming_supported=False,
        refuse_streaming=True,
    )
    caller = build_provider_model_caller(default_model_name=muse, registry=_registry_with(openai, meta))
    parent = caller("parent", muse, call_options=_streaming_opts(phase="choose_action"))
    delegate = caller("delegate", luna, call_options=_streaming_opts(phase="delegate_subtask"))
    assert parent["llm_call_trace"]["provider"] == "meta"
    assert parent["llm_call_trace"]["streaming_requested"] is True
    assert parent["llm_call_trace"]["streaming_supported"] is False
    assert parent["llm_call_trace"]["streaming_effective"] is False
    assert meta.received[0]["streaming"] is False
    assert delegate["llm_call_trace"]["provider"] == "openai"
    assert delegate["llm_call_trace"]["streaming_requested"] is True
    assert delegate["llm_call_trace"]["streaming_supported"] is True
    assert delegate["llm_call_trace"]["streaming_effective"] is True
    assert openai.received[0]["streaming"] is True


def test_openai_parent_streams_muse_delegate_downgraded() -> None:
    muse = "muse-spark-1.2-contributor"
    luna = "gpt-5.6-luna"
    openai = _FakeLLM(
        name="openai",
        models={luna: {"context_window_tokens": 400_000}},
        streaming_supported=True,
    )
    meta = _FakeLLM(
        name="meta",
        models={muse: {"context_window_tokens": 1_048_576}},
        streaming_supported=False,
        refuse_streaming=True,
    )
    caller = build_provider_model_caller(default_model_name=luna, registry=_registry_with(openai, meta))
    parent = caller("parent", luna, call_options=_streaming_opts(phase="choose_action"))
    delegate = caller("delegate", muse, call_options=_streaming_opts(phase="delegate_subtask"))
    assert parent["llm_call_trace"]["streaming_effective"] is True
    assert openai.received[0]["streaming"] is True
    assert delegate["llm_call_trace"]["provider"] == "meta"
    assert delegate["llm_call_trace"]["streaming_requested"] is True
    assert delegate["llm_call_trace"]["streaming_effective"] is False
    assert meta.received[0]["streaming"] is False


def test_streaming_disabled_neither_provider_streams() -> None:
    muse = "muse-spark-1.2-contributor"
    luna = "gpt-5.6-luna"
    openai = _FakeLLM(
        name="openai",
        models={luna: {"context_window_tokens": 400_000}},
        streaming_supported=True,
    )
    meta = _FakeLLM(
        name="meta",
        models={muse: {"context_window_tokens": 1_048_576}},
        streaming_supported=False,
        refuse_streaming=True,
    )
    caller = build_provider_model_caller(default_model_name=luna, registry=_registry_with(openai, meta))
    parent = caller("p", luna, call_options=_streaming_opts(phase="choose_action", streaming=False))
    delegate = caller("d", muse, call_options=_streaming_opts(phase="delegate_subtask", streaming=False))
    assert parent["llm_call_trace"]["streaming_requested"] is False
    assert parent["llm_call_trace"]["streaming_effective"] is False
    assert delegate["llm_call_trace"]["streaming_requested"] is False
    assert delegate["llm_call_trace"]["streaming_effective"] is False
    assert openai.received[0]["streaming"] is False
    assert meta.received[0]["streaming"] is False
