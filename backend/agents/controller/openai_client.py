"""OpenAI-backed NextStepLLMClient implementation for controller loops."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol

from services.llm.openai import OpenAIService

from .controller import IterationDigestClient, NextStepLLMClient

logger = logging.getLogger(__name__)
_MAX_ERROR_MESSAGE_CHARS = 1000
_MISSION_PREFIX = (
    "Mission: convert deed context into a FeatureGraph IR, then run deterministic physics gates "
    "(compile, judge, bundle) and only attempt DECLARE_DONE when claimability is likely ready.\n"
    "Protocol: output exactly one next step via tool call `kernel_step`. Never output prose.\n"
    "Tool discipline:\n"
    "- HYDRATE_DEED: use when deed text ref/excerpt is missing.\n"
    "- OPEN_ARTIFACT: requires one of artifact_ref | artifact_path | corpus_entry_ref.\n"
    "- If inputs.deed_text_artifact_ref exists and you need the deed text, call OPEN_ARTIFACT with "
    "{artifact_ref: inputs.deed_text_artifact_ref}.\n"
    "- DRAFT_IR: draft minimal valid graph first; iterate based on judge gaps.\n"
    "- RETRIEVE_EVIDENCE: optional; requires a non-empty query.\n"
    "- COMPILE/JUDGE: run after IR changes to get deterministic feedback.\n"
    "- BUNDLE: run after compile/judge when preparing completion package.\n"
    "Done semantics: kernel claimability indicates structural readiness; you are semantic arbiter. "
    "DECLARE_DONE must include concise justification with artifact refs and evidence/assumptions.\n"
    "Refs-not-blobs: prefer artifact refs, avoid large inline payloads.\n"
    "FeatureGraph IR cheatsheet (v0):\n"
    "- Shape: {graph_id, nodes[], edges[], metadata{}}.\n"
    "- Node shape: {id, kind, label?, metadata?, one-of: geometry | op_expr | feature_ref}.\n"
    "- kind vocabulary: point, curve, region, frame, constraint, annotation, unknown.\n"
    "- Rule: node content is mutually exclusive (geometry XOR op_expr XOR feature_ref).\n"
    "- Edges: {source_id, target_id, edge_type?}; edge IDs must reference existing nodes.\n"
    "- Prefer op_expr over large coordinate blobs when possible.\n"
    "Micro example 1:\n"
    '{"graph_id":"g_min_1","nodes":[{"id":"start","kind":"point","geometry":{"type":"Point","coordinates":[0.0,0.0]}},{"id":"boundary_curve","kind":"curve","geometry":{"type":"LineString","coordinates":[[0.0,0.0],[100.0,0.0]]}}],"edges":[{"source_id":"start","target_id":"boundary_curve","edge_type":"anchored_to"}],"metadata":{"source":"deed"}}\n'
    "Micro example 2:\n"
    '{"graph_id":"g_min_2","nodes":[{"id":"boundary_curve","kind":"curve","geometry":{"type":"LineString","coordinates":[[0.0,0.0],[10.0,0.0],[10.0,10.0],[0.0,10.0],[0.0,0.0]]}},{"id":"parcel_region","kind":"region","op_expr":{"op_name":"Close","operands":["boundary_curve"]}}],"edges":[{"source_id":"boundary_curve","target_id":"parcel_region","edge_type":"depends_on"}],"metadata":{"source":"deed"}}'
)


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
        mode = os.getenv("AGENT_CONTROLLER_LLM_MODE", "tool_call").strip().lower()
        params: dict[str, Any] = {
            "model": api_model,
            "messages": [
                {
                    "role": "developer",
                    "content": _MISSION_PREFIX,
                },
                {"role": "user", "content": prompt},
            ],
        }
        if mode == "json_object":
            params["response_format"] = {"type": "json_object"}
        else:
            params["tools"] = [schema]
            params["tool_choice"] = {"type": "function", "function": {"name": "kernel_step"}}
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
                for tool_call in tool_calls:
                    function = getattr(tool_call, "function", None)
                    if function is None or getattr(function, "name", None) != "kernel_step":
                        continue
                    raw_args = getattr(function, "arguments", None)
                    if isinstance(raw_args, str) and raw_args.strip():
                        parsed_args = json.loads(raw_args)
                        if isinstance(parsed_args, dict):
                            parsed = parsed_args
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
