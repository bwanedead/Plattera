from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.controller.openai_client import OpenAINextStepClient
from backend.agents.controller.tool_specs import ToolSpec


def _kernel_step_tool() -> ToolSpec:
    return ToolSpec(
        name="kernel_step",
        description="Propose exactly one next kernel action.",
        parameters_schema={"type": "object"},
    )


class _FakeChatCompletions:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.last_kwargs: dict[str, Any] | None = None

    def create(self, **kwargs) -> Any:
        self.last_kwargs = kwargs
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
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            function=SimpleNamespace(
                                name="kernel_step",
                                arguments='{"action_type":"declare_done","idempotency_key":"k1","args":{},"why":"x","declare_done":{"artifact_refs":{},"evidence_links":[],"accepted_deviations":[]}}',
                            )
                        )
                    ],
                )
            )
        ],
        usage=SimpleNamespace(total_tokens=42),
    )
    fake_client = _FakeOpenAIClient(response=completion)
    service = _FakeService(available=True, client=fake_client)
    client = OpenAINextStepClient(service=service)

    result = client.propose_next_step(
        model="gpt-5-mini",
        tools=[_kernel_step_tool()],
        tool_choice_name="kernel_step",
        developer_message="DEV MSG",
        user_message="USER MSG",
    )

    assert result["success"] is True
    assert result["structured_data"]["idempotency_key"] == "k1"
    assert result["tokens_used"] == 42
    sent = fake_client.chat.completions.last_kwargs
    assert isinstance(sent, dict)
    assert sent.get("tool_choice") == {"type": "function", "function": {"name": "kernel_step"}}
    tools = sent.get("tools")
    assert isinstance(tools, list)
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "kernel_step"
    assert tools[0]["function"]["parameters"] == {"type": "object"}
    messages = sent.get("messages")
    assert isinstance(messages, list)
    assert messages[0]["role"] == "developer"
    assert messages[0]["content"] == "DEV MSG"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "USER MSG"


def test_openai_next_step_client_reports_unavailable_service() -> None:
    service = _FakeService(available=False, client=None)
    client = OpenAINextStepClient(service=service)

    result = client.propose_next_step(
        model="gpt-5-mini",
        tools=[_kernel_step_tool()],
        tool_choice_name="kernel_step",
        developer_message="DEV",
        user_message="USER",
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
        tools=[_kernel_step_tool()],
        tool_choice_name="kernel_step",
        developer_message="DEV",
        user_message="USER",
    )

    assert result["success"] is False
    assert result["error"] == "openai_next_step_failed"
    assert result["model"] == "gpt-5-mini"
    assert result["api_model"] == "gpt-5-mini"
    assert "request_flags" in result


def test_openai_next_step_client_reports_missing_kernel_step_tool_call() -> None:
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[]))],
        usage=SimpleNamespace(total_tokens=7),
    )
    service = _FakeService(available=True, client=_FakeOpenAIClient(response=completion))
    client = OpenAINextStepClient(service=service)

    result = client.propose_next_step(
        model="gpt-5-mini",
        tools=[_kernel_step_tool()],
        tool_choice_name="kernel_step",
        developer_message="DEV",
        user_message="USER",
    )

    assert result["success"] is False
    assert result["error"] == "openai_missing_kernel_step_tool_call"


def test_openai_next_step_client_maps_action_tool_call_to_kernel_step_payload() -> None:
    completion = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            function=SimpleNamespace(
                                name="draft_ir",
                                arguments='{"dossier_id":"D1","graph":{"graph_id":"g1","nodes":[{"id":"n1","kind":"point","geometry":{"type":"Point","coordinates":[0,0]}}],"edges":[],"metadata":{"source":"deed"}},"why":"draft now","display_delta":"Starting a first parcel draft from the deed calls."}',
                            )
                        )
                    ],
                )
            )
        ],
        usage=SimpleNamespace(total_tokens=12),
    )
    service = _FakeService(available=True, client=_FakeOpenAIClient(response=completion))
    client = OpenAINextStepClient(service=service)

    result = client.propose_next_step(
        model="gpt-5-mini",
        tools=[
            ToolSpec(
                name="draft_ir",
                description="draft_ir",
                parameters_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            )
        ],
        tool_choice_name=None,
        developer_message="DEV",
        user_message="USER",
    )

    assert result["success"] is True
    payload = result["structured_data"]
    assert payload["action_type"] == "draft_ir"
    assert isinstance(payload["args"], dict)
    assert payload["args"]["dossier_id"] == "D1"
    assert isinstance(payload["args"]["graph"], dict)
    assert payload["display_delta"] == "Starting a first parcel draft from the deed calls."
