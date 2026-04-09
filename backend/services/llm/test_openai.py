from __future__ import annotations

from types import SimpleNamespace

from services.llm.call_options import LlmCallOptions
from services.llm.openai import OpenAIService


class _FakeChatCompletions:
    def __init__(self) -> None:
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content='{"ok":true}'),
                )
            ],
            usage=SimpleNamespace(
                total_tokens=42,
                prompt_tokens=21,
                completion_tokens=21,
                reasoning_tokens=5,
            ),
        )


class _FakeClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=_FakeChatCompletions())


def _service_with_fake_client() -> tuple[OpenAIService, _FakeChatCompletions]:
    service = OpenAIService()
    fake_client = _FakeClient()
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
