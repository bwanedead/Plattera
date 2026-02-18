"""OpenAI-backed NextStepLLMClient implementation for controller loops."""

from __future__ import annotations

import json
from typing import Any, Protocol

from services.llm.openai import OpenAIService

from .controller import NextStepLLMClient


class _OpenAIServiceLike(Protocol):
    client: Any
    models: dict[str, dict[str, Any]]

    def is_available(self) -> bool: ...


class OpenAINextStepClient(NextStepLLMClient):
    """Strict JSON-schema step proposal client using OpenAI chat completions."""

    def __init__(self, service: _OpenAIServiceLike | None = None) -> None:
        self._service = service or OpenAIService()

    def propose_next_step(
        self,
        *,
        model: str,
        schema: dict[str, object],
        prompt: str,
    ) -> dict[str, object]:
        if not self._service.is_available():
            return {
                "success": False,
                "error": "openai_service_unavailable",
                "model": model,
            }
        client = getattr(self._service, "client", None)
        if client is None:
            return {
                "success": False,
                "error": "openai_client_missing",
                "model": model,
            }

        api_model = self._resolve_api_model_name(model)
        params: dict[str, Any] = {
            "model": api_model,
            "messages": [
                {
                    "role": "developer",
                    "content": (
                        "Return exactly one JSON object matching the provided schema. "
                        "No markdown and no extra prose."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "next_step_proposal",
                    "schema": schema,
                    "strict": True,
                },
            },
        }
        if "gpt-5" in api_model or "o4-mini" in api_model:
            params["max_completion_tokens"] = int(self._default_max_tokens(model))
            if "gpt-5" in api_model:
                params["reasoning_effort"] = "medium"
        else:
            params["temperature"] = 0
            params["max_tokens"] = int(self._default_max_tokens(model))

        try:
            completion = client.chat.completions.create(**params)
            message = completion.choices[0].message if completion.choices else None
            content = message.content if message is not None else None
            if not isinstance(content, str) or not content.strip():
                return {
                    "success": False,
                    "error": "openai_empty_response",
                    "model": model,
                }
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                return {
                    "success": False,
                    "error": "openai_non_object_json",
                    "text": content,
                    "model": model,
                }
            total_tokens = 0
            if getattr(completion, "usage", None) is not None:
                total_tokens = int(getattr(completion.usage, "total_tokens", 0) or 0)
            return {
                "success": True,
                "structured_data": parsed,
                "text": content,
                "tokens_used": total_tokens,
                "model": model,
            }
        except Exception as exc:
            return {
                "success": False,
                "error": f"openai_next_step_failed:{exc}",
                "model": model,
            }

    def _resolve_api_model_name(self, model: str) -> str:
        model_info = self._service.models.get(model, {})
        api_name = model_info.get("api_model_name")
        if isinstance(api_name, str) and api_name:
            return api_name
        return model

    def _default_max_tokens(self, model: str) -> int:
        model_info = self._service.models.get(model, {})
        raw = model_info.get("default_max_tokens", 4000)
        try:
            return max(256, int(raw))
        except Exception:
            return 4000

