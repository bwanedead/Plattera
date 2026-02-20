"""OpenAI-backed NextStepLLMClient implementation for controller loops."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from services.llm.openai import OpenAIService

from .controller import NextStepLLMClient

logger = logging.getLogger(__name__)
_MAX_ERROR_MESSAGE_CHARS = 1000


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
            error_payload = self._extract_openai_error_payload(
                exc,
                model=model,
                api_model=api_model,
                params=params,
            )
            try:
                logger.error(
                    "openai_next_step_error %s",
                    json.dumps(error_payload, ensure_ascii=True),
                )
            except Exception:
                logger.error("openai_next_step_error")
            return error_payload

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

    def _extract_openai_error_payload(
        self,
        exc: Exception,
        *,
        model: str,
        api_model: str,
        params: dict[str, Any],
    ) -> dict[str, object]:
        response = getattr(exc, "response", None)
        error_obj = getattr(exc, "error", None)
        body = getattr(exc, "body", None)

        http_status = (
            getattr(exc, "status_code", None)
            or getattr(response, "status_code", None)
            or getattr(exc, "status", None)
        )
        response_header_request_id = None
        if hasattr(response, "headers"):
            try:
                response_header_request_id = getattr(response, "headers", {}).get("x-request-id")
            except Exception:
                response_header_request_id = None
        request_id = (
            getattr(exc, "request_id", None)
            or getattr(response, "request_id", None)
            or response_header_request_id
        )

        error_type = None
        error_message = None
        error_param = None
        error_code = None
        if isinstance(error_obj, dict):
            error_type = error_obj.get("type")
            error_message = error_obj.get("message")
            error_param = error_obj.get("param")
            error_code = error_obj.get("code")
        elif hasattr(error_obj, "get"):
            try:
                error_type = error_obj.get("type")
                error_message = error_obj.get("message")
                error_param = error_obj.get("param")
                error_code = error_obj.get("code")
            except Exception:
                pass
        if error_message is None and isinstance(body, dict):
            body_error = body.get("error")
            if isinstance(body_error, dict):
                error_type = error_type or body_error.get("type")
                error_message = body_error.get("message")
                error_param = error_param or body_error.get("param")
                error_code = error_code or body_error.get("code")
        if error_message is None:
            error_message = str(exc)

        request_flags: dict[str, object] = {
            "json_schema": bool(params.get("response_format")),
            "reasoning_effort": params.get("reasoning_effort"),
            "max_completion_tokens": params.get("max_completion_tokens"),
            "max_tokens": params.get("max_tokens"),
            "temperature": params.get("temperature"),
        }

        return {
            "success": False,
            "error": "openai_bad_request" if http_status == 400 else "openai_next_step_failed",
            "http_status": http_status,
            "openai_request_id": request_id,
            "error_type": error_type,
            "error_message": str(error_message)[:_MAX_ERROR_MESSAGE_CHARS],
            "error_param": error_param,
            "error_code": error_code,
            "model": model,
            "api_model": api_model,
            "request_flags": request_flags,
        }
