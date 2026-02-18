from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.controller.openai_client import OpenAINextStepClient


class _FakeChatCompletions:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error

    def create(self, **kwargs) -> Any:
        del kwargs
        if self._error is not None:
            raise self._error
        return self._response


class _FakeOpenAIClient:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.chat = SimpleNamespace(completions=_FakeChatCompletions(response=response, error=error))


class _FakeService:
    def __init__(
        self,
        *,
        available: bool,
        client: Any = None,
    ) -> None:
        self._available = available
        self.client = client
        self.models = {"gpt-5-mini": {"api_model_name": "gpt-5-mini", "default_max_tokens": 12000}}

    def is_available(self) -> bool:
        return self._available


def test_openai_next_step_client_returns_structured_data_on_success() -> None:
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"action_type":"declare_done","idempotency_key":"k1","inputs":{},"why":"x","declare_done":{"artifact_refs":{},"evidence_links":[],"accepted_deviations":[]}}'))],
        usage=SimpleNamespace(total_tokens=42),
    )
    service = _FakeService(available=True, client=_FakeOpenAIClient(response=completion))
    client = OpenAINextStepClient(service=service)

    result = client.propose_next_step(
        model="gpt-5-mini",
        schema={"type": "object", "properties": {}, "required": []},
        prompt="propose step",
    )

    assert result["success"] is True
    assert result["structured_data"]["idempotency_key"] == "k1"
    assert result["tokens_used"] == 42


def test_openai_next_step_client_reports_unavailable_service() -> None:
    service = _FakeService(available=False, client=None)
    client = OpenAINextStepClient(service=service)

    result = client.propose_next_step(
        model="gpt-5-mini",
        schema={"type": "object", "properties": {}, "required": []},
        prompt="propose step",
    )

    assert result["success"] is False
    assert result["error"] == "openai_service_unavailable"


def test_openai_next_step_client_reports_runtime_failure() -> None:
    service = _FakeService(
        available=True,
        client=_FakeOpenAIClient(error=RuntimeError("boom")),
    )
    client = OpenAINextStepClient(service=service)

    result = client.propose_next_step(
        model="gpt-5-mini",
        schema={"type": "object", "properties": {}, "required": []},
        prompt="propose step",
    )

    assert result["success"] is False
    assert str(result["error"]).startswith("openai_next_step_failed:")

