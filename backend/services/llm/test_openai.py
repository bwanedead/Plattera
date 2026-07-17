from __future__ import annotations

import time
from types import SimpleNamespace

from services.llm.call_options import LlmCallOptions
from services.llm.openai import OpenAIService, _requested_service_tier_from_kwargs


class _FakeChatCompletions:
    def __init__(
        self,
        *,
        finish_reason: str = "stop",
        content: str | None = '{"ok":true}',
        model_name: str = "gpt-5.4-mini",
        usage: SimpleNamespace | None = None,
    ) -> None:
        self.last_kwargs = None
        self._finish_reason = finish_reason
        self._content = content
        self._model_name = model_name
        self._usage = usage or SimpleNamespace(
            total_tokens=42,
            prompt_tokens=21,
            completion_tokens=21,
            reasoning_tokens=5,
        )

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason=self._finish_reason,
                    message=SimpleNamespace(content=self._content),
                )
            ],
            usage=self._usage,
            model=self._model_name,
        )


class _FakeStreamChunk:
    def __init__(
        self,
        *,
        content: str | None = None,
        finish_reason: str | None = None,
        usage: SimpleNamespace | None = None,
        chunk_id: str = "resp_stream_1",
        model_name: str = "gpt-5.4-mini",
    ) -> None:
        delta = SimpleNamespace(content=content)
        self.choices = [SimpleNamespace(delta=delta, finish_reason=finish_reason)]
        self.usage = usage
        self.id = chunk_id
        self.model = model_name


class _FakeStreamingChatCompletions:
    def __init__(self, chunks: list[_FakeStreamChunk] | None = None) -> None:
        self.last_kwargs = None
        self._chunks = chunks or [
            _FakeStreamChunk(content='{"ok":'),
            _FakeStreamChunk(content="true}"),
            _FakeStreamChunk(
                finish_reason="stop",
                usage=SimpleNamespace(
                    total_tokens=42,
                    prompt_tokens=21,
                    completion_tokens=21,
                    reasoning_tokens=5,
                ),
            ),
        ]

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return iter(self._chunks)


class _FakeClient:
    def __init__(self, completions: _FakeChatCompletions | _FakeStreamingChatCompletions | None = None) -> None:
        self.chat = SimpleNamespace(completions=completions or _FakeChatCompletions())


def _service_with_fake_client(
    completions: _FakeChatCompletions | None = None,
) -> tuple[OpenAIService, _FakeChatCompletions]:
    service = OpenAIService()
    fake_client = _FakeClient(completions=completions)
    service.client = fake_client
    return service, fake_client.chat.completions


def test_call_text_uses_expanded_budget_for_choose_action_json_phase() -> None:
    service, completions = _service_with_fake_client()

    result = service.call_text(
        "prompt",
        "gpt-5.4-mini",
        call_options=LlmCallOptions(output_mode="json_object", phase="choose_action"),
    )

    assert result["success"] is True
    assert completions.last_kwargs is not None
    assert completions.last_kwargs["response_format"] == {"type": "json_object"}
    assert completions.last_kwargs["max_completion_tokens"] == 32_000
    assert completions.last_kwargs["reasoning_effort"] == "medium"


def test_gpt54_model_entry_exists_in_registry() -> None:
    """gpt-5.4 (full, not mini) must be a registered model for the default runner to resolve it."""
    assert "gpt-5.4" in OpenAIService.models
    entry = OpenAIService.models["gpt-5.4"]
    assert entry["provider"] == "openai"
    assert entry.get("api_model_name") == "gpt-5.4"
    # mini must still exist as an explicit override option
    assert "gpt-5.4-mini" in OpenAIService.models


def test_gpt56_terra_and_luna_registered_with_exact_api_names() -> None:
    for model_id, expected_name, cost_tier in (
        ("gpt-5.6-terra", "GPT-5.6 Terra", "standard"),
        ("gpt-5.6-luna", "GPT-5.6 Luna", "budget"),
    ):
        assert model_id in OpenAIService.models
        entry = OpenAIService.models[model_id]
        assert entry["name"] == expected_name
        assert entry["provider"] == "openai"
        assert entry["cost_tier"] == cost_tier
        assert entry.get("api_model_name") == model_id
        assert entry.get("verification_required") is False
        assert entry.get("default_max_tokens") == 16000
        assert "text" in entry["capabilities"]
        assert "vision" in entry["capabilities"]
    # gpt-5.4 remains a supported explicit/historical registry option.
    assert "gpt-5.4" in OpenAIService.models


def test_call_text_uses_max_completion_tokens_for_gpt56_terra_and_luna() -> None:
    for model_id in ("gpt-5.6-terra", "gpt-5.6-luna"):
        service, completions = _service_with_fake_client(
            _FakeChatCompletions(model_name=model_id)
        )
        result = service.call_text("prompt", model_id)
        assert result["success"] is True
        assert completions.last_kwargs is not None
        assert "max_completion_tokens" in completions.last_kwargs
        assert "max_tokens" not in completions.last_kwargs
        assert completions.last_kwargs["max_completion_tokens"] == 16_000


def test_call_text_expanded_budget_for_gpt56_choose_action_phase() -> None:
    service, completions = _service_with_fake_client(
        _FakeChatCompletions(model_name="gpt-5.6-terra")
    )
    result = service.call_text(
        "prompt",
        "gpt-5.6-terra",
        call_options=LlmCallOptions(output_mode="json_object", phase="choose_action"),
    )
    assert result["success"] is True
    assert completions.last_kwargs["max_completion_tokens"] == 32_000
    assert completions.last_kwargs["reasoning_effort"] == "medium"


def test_call_structured_pydantic_accepts_gpt56_family_models() -> None:
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }
    for model_id in ("gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.4", "gpt-5.4-mini"):
        service, completions = _service_with_fake_client(
            _FakeChatCompletions(model_name=model_id, content='{"ok": true}')
        )
        result = service.call_structured_pydantic(
            "prompt",
            "input",
            model_id,
            schema=schema,
        )
        assert "Invalid GPT-5 model" not in str(result.get("error") or "")
        assert completions.last_kwargs is not None
        assert completions.last_kwargs["model"] == model_id
        assert "max_completion_tokens" in completions.last_kwargs
        assert "max_tokens" not in completions.last_kwargs


def test_call_text_keeps_default_budget_for_non_action_phase() -> None:
    service, completions = _service_with_fake_client()

    result = service.call_text(
        "prompt",
        "gpt-5.4-mini",
        call_options=LlmCallOptions(output_mode="json_object", phase="consensus"),
    )

    assert result["success"] is True
    assert completions.last_kwargs is not None
    assert completions.last_kwargs["max_completion_tokens"] == 16_000
    assert completions.last_kwargs["reasoning_effort"] == "high"


def test_call_text_truncation_preserves_provider_metadata_and_partial_text() -> None:
    service, _ = _service_with_fake_client(
        _FakeChatCompletions(
            finish_reason="length",
            content='{"partial": true',
            usage=SimpleNamespace(
                total_tokens=32000,
                prompt_tokens=12000,
                completion_tokens=20000,
                reasoning_tokens=7000,
            ),
        )
    )

    result = service.call_text("prompt", "gpt-5.4-mini")

    assert result["success"] is False
    assert result["error"] == "OpenAI returned truncated response (finish_reason: length)"
    assert result["text"] == '{"partial": true'
    assert result["finish_reason"] == "length"
    assert result["usage"] == {
        "prompt_tokens": 12000,
        "completion_tokens": 20000,
        "reasoning_tokens": 7000,
        "total_tokens": 32000,
        "cached_input_tokens": None,
    }
    assert result["char_count"] == len('{"partial": true')
    assert result["model"] == "gpt-5.4-mini"
    assert result["provider_model"] == "gpt-5.4-mini"
    assert result["api_model"] == "gpt-5.4-mini"


def test_call_text_content_filter_preserves_usage_metadata() -> None:
    service, _ = _service_with_fake_client(
        _FakeChatCompletions(
            finish_reason="content_filter",
            content=None,
            usage=SimpleNamespace(
                total_tokens=99,
                prompt_tokens=44,
                completion_tokens=55,
                reasoning_tokens=None,
            ),
        )
    )

    result = service.call_text("prompt", "gpt-5.4-mini")

    assert result["success"] is False
    assert result["finish_reason"] == "content_filter"
    assert result["usage"] == {
        "prompt_tokens": 44,
        "completion_tokens": 55,
        "reasoning_tokens": None,
        "total_tokens": 99,
        "cached_input_tokens": None,
    }
    assert result["text"] is None
    assert result["char_count"] == 0


def test_call_text_empty_response_preserves_provider_envelope_fields() -> None:
    service, _ = _service_with_fake_client(
        _FakeChatCompletions(
            finish_reason="stop",
            content="",
            usage=SimpleNamespace(
                total_tokens=17,
                prompt_tokens=10,
                completion_tokens=7,
                reasoning_tokens=1,
            ),
        )
    )

    result = service.call_text("prompt", "gpt-5.4-mini")

    assert result["success"] is False
    assert result["error"] == "OpenAI returned empty text response"
    assert result["finish_reason"] == "stop"
    assert result["usage"] == {
        "prompt_tokens": 10,
        "completion_tokens": 7,
        "reasoning_tokens": 1,
        "total_tokens": 17,
        "cached_input_tokens": None,
    }
    assert result["char_count"] == 0


def test_usage_payload_reads_nested_completion_reasoning_tokens() -> None:
    usage = OpenAIService._usage_payload(
        SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=50,
                completion_tokens=20,
                total_tokens=70,
                reasoning_tokens=None,
                completion_tokens_details=SimpleNamespace(reasoning_tokens=15),
            )
        )
    )
    assert usage == {
        "prompt_tokens": 50,
        "completion_tokens": 20,
        "reasoning_tokens": 15,
        "total_tokens": 70,
        "cached_input_tokens": None,
    }


def test_call_text_echoes_requested_service_tier_from_call_options() -> None:
    service, _ = _service_with_fake_client(_FakeChatCompletions())
    result = service.call_text(
        "prompt",
        "gpt-5.4-mini",
        call_options=LlmCallOptions(output_mode="json_object", service_tier="flex"),
    )
    assert result["success"] is True
    assert result["service_tier_requested"] == "flex"


def test_requested_service_tier_from_kwargs_prefers_call_options() -> None:
    opts = LlmCallOptions(service_tier="priority")
    assert _requested_service_tier_from_kwargs({"service_tier": "flex"}, call_opts=opts) == "priority"


def test_call_text_non_streaming_default_unchanged() -> None:
    service, completions = _service_with_fake_client()
    result = service.call_text("prompt", "gpt-5.4-mini")
    assert result["success"] is True
    assert completions.last_kwargs is not None
    assert "stream" not in completions.last_kwargs
    assert result.get("streaming_requested") is not True


def test_call_text_streaming_opt_in_aggregates_text() -> None:
    service, completions = _service_with_fake_client(_FakeStreamingChatCompletions())
    result = service.call_text(
        "prompt",
        "gpt-5.4-mini",
        call_options=LlmCallOptions(output_mode="json_object", phase="choose_action", streaming=True),
    )
    assert result["success"] is True
    assert result["text"] == '{"ok":true}'
    assert result["streaming_requested"] is True
    assert completions.last_kwargs is not None
    assert completions.last_kwargs["stream"] is True
    assert completions.last_kwargs["stream_options"] == {"include_usage": True}
    assert result["usage"]["prompt_tokens"] == 21
    assert result["first_response_event_at_epoch_seconds"] is not None


def test_call_text_streaming_records_first_event_timing() -> None:
    class _DelayedStreamingCompletions(_FakeStreamingChatCompletions):
        def create(self, **kwargs):
            self.last_kwargs = kwargs

            def _iter():
                time.sleep(0.02)
                yield _FakeStreamChunk(content="hi")
                time.sleep(0.03)
                yield _FakeStreamChunk(
                    finish_reason="stop",
                    usage=SimpleNamespace(
                        total_tokens=10,
                        prompt_tokens=4,
                        completion_tokens=6,
                        reasoning_tokens=None,
                    ),
                )

            return _iter()

    service, _ = _service_with_fake_client(_DelayedStreamingCompletions())
    started = time.time()
    result = service.call_text(
        "prompt",
        "gpt-5.4-mini",
        call_options=LlmCallOptions(streaming=True),
    )
    assert result["success"] is True
    assert result["text"] == "hi"
    first = float(result["first_response_event_at_epoch_seconds"])
    finished = float(result["response_finished_at_epoch_seconds"])
    assert first >= started
    assert finished - first >= 0.02


def test_call_text_streaming_without_usage_records_reason() -> None:
    service, _ = _service_with_fake_client(
        _FakeStreamingChatCompletions(
            chunks=[
                _FakeStreamChunk(content="partial"),
                _FakeStreamChunk(finish_reason="stop"),
            ]
        )
    )
    result = service.call_text(
        "prompt",
        "gpt-5.4-mini",
        call_options=LlmCallOptions(streaming=True),
    )
    assert result["success"] is True
    assert result["usage_unavailable_reason"] == "streaming_usage_not_returned"
