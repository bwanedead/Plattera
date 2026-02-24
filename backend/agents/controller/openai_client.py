"""OpenAI-backed NextStepLLMClient implementation for controller loops."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol

from services.llm.openai import OpenAIService

from .controller import IterationDigestClient, NextStepLLMClient
from .tool_specs import ToolSpec

logger = logging.getLogger(__name__)
_MAX_ERROR_MESSAGE_CHARS = 1000


class _OpenAIServiceLike(Protocol):
    client: Any
    models: dict[str, dict[str, Any]]

    def is_available(self) -> bool: ...


class OpenAINextStepClient(NextStepLLMClient):
    """Tool-calling step proposal client using OpenAI chat completions."""

    def __init__(self, service: _OpenAIServiceLike | None = None) -> None:
        self._service = service or OpenAIService()

    def propose_next_step(
        self,
        *,
        model: str,
        tools: list[ToolSpec],
        tool_choice_name: str | None,
        developer_message: str,
        user_message: str,
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
        mode = os.getenv("AGENT_CONTROLLER_LLM_MODE", "tool_call").strip().lower()
        params: dict[str, Any] = {
            "model": api_model,
            "messages": [
                {
                    "role": "developer",
                    "content": developer_message,
                },
                {"role": "user", "content": user_message},
            ],
        }
        if mode == "json_object":
            params["response_format"] = {"type": "json_object"}
        else:
            params["tools"] = [self._to_openai_tool(tool) for tool in tools]
            if tool_choice_name:
                params["tool_choice"] = {"type": "function", "function": {"name": tool_choice_name}}
            else:
                params["tool_choice"] = "required"
            params["parallel_tool_calls"] = False
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
            parsed: dict[str, object] | None = None
            content = message.content if message is not None else None

            tool_calls = getattr(message, "tool_calls", None) if message is not None else None
            if isinstance(tool_calls, list):
                allowed_tool_names = {tool.name for tool in tools}
                for tool_call in tool_calls:
                    function = getattr(tool_call, "function", None)
                    tool_name = getattr(function, "name", None) if function is not None else None
                    if function is None or not isinstance(tool_name, str):
                        continue
                    if tool_choice_name and tool_name != tool_choice_name:
                        continue
                    if allowed_tool_names and tool_name not in allowed_tool_names:
                        continue
                    raw_args = getattr(function, "arguments", None)
                    if isinstance(raw_args, str) and raw_args.strip():
                        parsed_args = json.loads(raw_args)
                        if isinstance(parsed_args, dict):
                            parsed = self._tool_call_to_kernel_step_payload(tool_name=tool_name, parsed_args=parsed_args)
                            break
                if parsed is None and mode != "json_object":
                    return {
                        "success": False,
                        "error": "openai_missing_kernel_step_tool_call",
                        "model": model,
                        "api_model": api_model,
                    }

            if parsed is None:
                if not isinstance(content, str) or not content.strip():
                    return {
                        "success": False,
                        "error": "openai_empty_response",
                        "model": model,
                    }
                parsed_any = json.loads(content)
                if not isinstance(parsed_any, dict):
                    return {
                        "success": False,
                        "error": "openai_non_object_json",
                        "text": content,
                        "model": model,
                    }
                parsed = parsed_any
            total_tokens = 0
            if getattr(completion, "usage", None) is not None:
                total_tokens = int(getattr(completion.usage, "total_tokens", 0) or 0)
            return {
                "success": True,
                "structured_data": parsed,
                "text": content if isinstance(content, str) else "",
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

    def _to_openai_tool(self, tool: ToolSpec) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters_schema,
            },
        }

    def _tool_call_to_kernel_step_payload(
        self,
        *,
        tool_name: str,
        parsed_args: dict[str, object],
    ) -> dict[str, object]:
        if tool_name == "kernel_step":
            return parsed_args
        common_keys = {"why", "semantic_ready", "notes", "retrieval_intent", "declare_done", "iteration_summary", "idempotency_key"}
        payload: dict[str, object] = {
            "action_type": tool_name,
            "args": {},
            "why": str(parsed_args.get("why") or f"{tool_name}"),
            "idempotency_key": str(parsed_args.get("idempotency_key") or f"toolcall-{tool_name}"),
        }
        for key in ("semantic_ready", "notes", "retrieval_intent", "declare_done", "iteration_summary"):
            if key in parsed_args:
                payload[key] = parsed_args[key]
        args: dict[str, object] = {}
        for key, value in parsed_args.items():
            if key in common_keys:
                continue
            args[key] = value
        payload["args"] = args
        return payload

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
            "json_schema": bool(
                isinstance(params.get("response_format"), dict)
                and params.get("response_format", {}).get("type") == "json_schema"
            ),
            "json_object": bool(
                isinstance(params.get("response_format"), dict)
                and params.get("response_format", {}).get("type") == "json_object"
            ),
            "tool_calling": bool(params.get("tools")),
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


class OpenAIIterationDigestClient(IterationDigestClient):
    """Cheap JSON-mode summarizer for bounded iteration digests (GPT-5 mini by default)."""

    def __init__(self, service: _OpenAIServiceLike | None = None) -> None:
        self._service = service or OpenAIService()

    def summarize_iteration_digest(
        self,
        *,
        payload: dict[str, object],
        model: str = "gpt-5-mini",
    ) -> dict[str, object]:
        if not self._service.is_available() or getattr(self._service, "client", None) is None:
            return {"success": False, "error": "openai_service_unavailable"}
        client = self._service.client
        api_model = self._resolve_api_model_name(model)
        prompt = (
            "Return a compact JSON iteration digest only. "
            "Keep it under ~2KB. Keys: iter,result,proposed,failure,correction,progress,notes. "
            "notes max 3 short strings. "
            f"Input JSON: {json.dumps(payload, ensure_ascii=True, sort_keys=True)}"
        )
        params: dict[str, Any] = {
            "model": api_model,
            "messages": [
                {"role": "developer", "content": "Summarize controller iteration outcomes into a tiny JSON digest."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        if "gpt-5" in api_model:
            params["max_completion_tokens"] = 800
            params["reasoning_effort"] = "low"
        else:
            params["max_tokens"] = 800
            params["temperature"] = 0
        try:
            completion = client.chat.completions.create(**params)
            message = completion.choices[0].message if completion.choices else None
            content = message.content if message is not None else None
            if not isinstance(content, str) or not content.strip():
                return {"success": False, "error": "empty_digest_response"}
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                return {"success": False, "error": "digest_not_json_object"}
            return {"success": True, "digest": parsed}
        except Exception as exc:
            logger.warning("openai_iteration_digest_failed %s", type(exc).__name__)
            return {"success": False, "error": "openai_iteration_digest_failed"}

    def _resolve_api_model_name(self, model: str) -> str:
        model_info = self._service.models.get(model, {})
        api_name = model_info.get("api_model_name")
        if isinstance(api_name, str) and api_name:
            return api_name
        return model
