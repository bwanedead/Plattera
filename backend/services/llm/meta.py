"""Meta Model API LLM provider (Muse Spark contributor development route).

Canonical transport: OpenAI SDK Responses API against ``https://api.meta.ai/v1``.
Credentials: ``META_MODEL_API_KEY`` only (no generic MODEL_API_KEY fallback).
"""

from __future__ import annotations

import logging
import os
from dataclasses import replace
from typing import Any, Dict, Mapping

from services.llm.base import LLMService

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI

    OPENAI_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - environment without openai
    OpenAI = None  # type: ignore[misc, assignment]
    OPENAI_SDK_AVAILABLE = False

META_DEFAULT_BASE_URL = "https://api.meta.ai/v1"
META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID = "muse-spark-1.2-contributor"

# Phase budgets stay inside the Meta adapter (not harness).
_PHASE_JSON_ACTION_BUDGETS: dict[str, dict[str, Any]] = {
    "choose_action": {
        "min_max_tokens": 32_000,
        "reasoning_effort": "medium",
    },
    "choose_action_repair": {
        "min_max_tokens": 32_000,
        "reasoning_effort": "medium",
    },
}

_DELEGATE_PHASES = frozenset({"delegate_subtask", "delegate"})
_DELEGATE_MAX_OUTPUT_TOKENS = 8_000
# Adapter-local request ceiling only — not a published Meta model maximum.
_OPERATIONAL_MAX_OUTPUT_TOKENS = 32_000


def _get_meta_api_key() -> str | None:
    """Resolve Meta Model API key from META_MODEL_API_KEY only."""
    key = str(os.getenv("META_MODEL_API_KEY") or "").strip()
    return key or None


def _get_meta_base_url() -> str:
    raw = str(os.getenv("META_MODEL_API_BASE_URL") or "").strip()
    return raw or META_DEFAULT_BASE_URL


def _streaming_requested(*, call_opts: Any, kwargs: Mapping[str, Any]) -> bool:
    try:
        from services.llm.call_options import LlmCallOptions
    except ImportError:  # pragma: no cover
        LlmCallOptions = None  # type: ignore[misc, assignment]
    if LlmCallOptions is not None and isinstance(call_opts, LlmCallOptions):
        if bool(getattr(call_opts, "streaming", False)):
            return True
    return bool(kwargs.get("streaming")) or bool(kwargs.get("stream"))


class MetaModelService(LLMService):
    """Meta Model API provider using the documented Responses wire path."""

    name = "meta"

    # context_window_tokens: Meta Models catalog for muse-spark-1.2-contributor.
    # max_output_tokens omitted: no exact-model published maximum verified for
    # muse-spark-1.2-contributor on a primary Meta catalog surface.
    models = {
        META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID: {
            "name": "Muse Spark 1.2 Contributor",
            "provider": "meta",
            "cost_tier": "contributor",
            "capabilities": ["text", "vision", "reasoning"],
            "description": "Development model using Meta's contributor-data route",
            "verification_required": False,
            "api_model_name": META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID,
            "default_max_tokens": 16_000,
            "context_window_tokens": 1_048_576,
        },
    }

    def __init__(self) -> None:
        self.client = None
        api_key = _get_meta_api_key()
        if OPENAI_SDK_AVAILABLE and api_key:
            self.client = OpenAI(api_key=api_key, base_url=_get_meta_base_url())

    def is_available(self) -> bool:
        return bool(OPENAI_SDK_AVAILABLE and _get_meta_api_key() and self.client is not None)

    def supports_streaming(self) -> bool:
        # Streaming is explicitly unsupported until Meta streaming is aggregated
        # into the canonical final-response envelope.
        return False

    def _api_model_name(self, model: str) -> str:
        info = self.models.get(model, {})
        return str(info.get("api_model_name") or model)

    def _resolve_output_budget(
        self,
        *,
        model: str,
        effective_phase: str | None,
        output_mode: str,
        kwargs: Mapping[str, Any],
    ) -> tuple[int, str | None]:
        model_info = self.models.get(model, {})
        default_max = int(model_info.get("default_max_tokens", 16_000))
        operational_cap = _OPERATIONAL_MAX_OUTPUT_TOKENS
        if "max_tokens" in kwargs and kwargs["max_tokens"] is not None:
            return min(operational_cap, int(kwargs["max_tokens"])), None

        phase = str(effective_phase or "").strip()
        if output_mode == "json_object" and phase in _PHASE_JSON_ACTION_BUDGETS:
            phase_budget = _PHASE_JSON_ACTION_BUDGETS[phase]
            min_max = int(phase_budget["min_max_tokens"])
            tuned = min(operational_cap, max(default_max, min_max))
            return tuned, str(phase_budget.get("reasoning_effort") or "medium")

        if phase in _DELEGATE_PHASES or phase.startswith("delegate"):
            return min(operational_cap, _DELEGATE_MAX_OUTPUT_TOKENS), "medium"

        return min(operational_cap, default_max), "medium"

    def _build_user_input(
        self,
        prompt: str,
        *,
        image_attachments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        for att in image_attachments:
            if not isinstance(att, Mapping):
                continue
            b64 = att.get("b64")
            if not isinstance(b64, str) or not b64.strip():
                continue
            media_type_raw = att.get("media_type")
            if media_type_raw is None:
                media_type = "image/jpeg"
            elif isinstance(media_type_raw, str) and media_type_raw.strip():
                media_type = media_type_raw.strip()
            else:
                continue
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{media_type};base64,{b64.strip()}",
                }
            )
        return [{"role": "user", "content": content}]

    def _build_responses_params(
        self,
        *,
        prompt: str,
        model: str,
        image_attachments: list[dict[str, Any]],
        output_mode: str,
        effective_phase: str | None,
        kwargs: Mapping[str, Any],
    ) -> dict[str, Any]:
        api_model = self._api_model_name(model)
        max_output_tokens, reasoning_effort = self._resolve_output_budget(
            model=model,
            effective_phase=effective_phase,
            output_mode=output_mode,
            kwargs=kwargs,
        )
        params: dict[str, Any] = {
            "model": api_model,
            "input": self._build_user_input(prompt, image_attachments=image_attachments),
            "max_output_tokens": max_output_tokens,
            "store": False,
        }
        if reasoning_effort:
            params["reasoning"] = {"effort": reasoning_effort}
        if output_mode == "json_object":
            # Responses API structured-output surface (not Chat Completions response_format).
            params["text"] = {"format": {"type": "json_object"}}
        return params

    @staticmethod
    def _usage_payload(response: Any) -> dict[str, int | None] | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        input_details = getattr(usage, "input_tokens_details", None)
        output_details = getattr(usage, "output_tokens_details", None)
        cached = None
        if input_details is not None:
            cached = getattr(input_details, "cached_tokens", None)
        reasoning = None
        if output_details is not None:
            reasoning = getattr(output_details, "reasoning_tokens", None)
        return {
            "prompt_tokens": getattr(usage, "input_tokens", None),
            "completion_tokens": getattr(usage, "output_tokens", None),
            "cached_input_tokens": cached,
            "reasoning_tokens": reasoning,
            "total_tokens": getattr(usage, "total_tokens", None),
        }

    @staticmethod
    def _extract_output_text(response: Any) -> str | None:
        text = getattr(response, "output_text", None)
        if isinstance(text, str) and text.strip():
            return text
        # Fallback: walk Responses output items.
        chunks: list[str] = []
        for item in list(getattr(response, "output", None) or []):
            if str(getattr(item, "type", "") or "") != "message":
                continue
            for part in list(getattr(item, "content", None) or []):
                if str(getattr(part, "type", "") or "") in {"output_text", "text"}:
                    value = getattr(part, "text", None)
                    if isinstance(value, str) and value:
                        chunks.append(value)
        if chunks:
            return "".join(chunks)
        return None

    @staticmethod
    def _extract_refusal_text(response: Any) -> str | None:
        for item in list(getattr(response, "output", None) or []):
            for part in list(getattr(item, "content", None) or []):
                part_type = str(getattr(part, "type", "") or "")
                if part_type in {"refusal", "output_refusal"}:
                    refusal_text = getattr(part, "refusal", None) or getattr(part, "text", None)
                    if isinstance(refusal_text, str) and refusal_text.strip():
                        return refusal_text
                    return ""
        return None

    @staticmethod
    def _finish_reason_for_response(response: Any) -> str | None:
        status = str(getattr(response, "status", "") or "").strip() or None
        if status == "completed":
            return "stop"
        if status == "incomplete":
            details = getattr(response, "incomplete_details", None)
            reason = getattr(details, "reason", None) if details is not None else None
            if str(reason or "") in {"max_output_tokens", "length"}:
                return "length"
            return "incomplete"
        if status in {"failed", "cancelled"}:
            return status
        return status

    def _failure_result(
        self,
        *,
        model: str,
        api_model: str,
        error: str,
        response: Any | None = None,
        finish_reason: str | None = None,
        text: str | None = None,
    ) -> Dict[str, Any]:
        usage = self._usage_payload(response) if response is not None else None
        partial = text
        if partial is None and response is not None:
            partial = self._extract_output_text(response)
        char_count = len(partial) if isinstance(partial, str) else 0
        provider_model = None
        if response is not None:
            provider_model = getattr(response, "model", None)
        return {
            "success": False,
            "error": error,
            "text": partial,
            "tokens_used": (usage or {}).get("total_tokens"),
            "model": model,
            "provider_model": provider_model or api_model,
            "api_model": api_model,
            "finish_reason": finish_reason,
            "char_count": char_count,
            "response_id": getattr(response, "id", None) if response is not None else None,
            "usage": usage,
        }

    def call_text(self, prompt: str, model: str, **kwargs) -> Dict[str, Any]:
        # Allow an injected client (tests) even when env credentials are absent.
        if self.client is None:
            return {
                "success": False,
                "error": "Meta Model API provider is not configured.",
                "text": None,
                "model": model,
                "char_count": 0,
            }

        call_opts = kwargs.get("call_options")
        if call_opts is not None:
            image_attachments = list(call_opts.image_attachments or ())
            output_mode = str(getattr(call_opts, "output_mode", "text") or "text")
            effective_phase = getattr(call_opts, "phase", None) or kwargs.get("phase")
        else:
            image_attachments = list(kwargs.get("image_attachments") or [])
            output_mode = "text"
            effective_phase = kwargs.get("phase")

        api_model = self._api_model_name(model)
        if _streaming_requested(call_opts=call_opts, kwargs=kwargs):
            return self._failure_result(
                model=model,
                api_model=api_model,
                error="Meta Model API streaming is not supported by this provider adapter.",
                finish_reason="streaming_unsupported",
            )

        params = self._build_responses_params(
            prompt=prompt,
            model=model,
            image_attachments=image_attachments,
            output_mode=output_mode,
            effective_phase=str(effective_phase) if effective_phase else None,
            kwargs=kwargs,
        )
        phase_label = str(effective_phase or "").strip()
        logger.info(
            "META TEXT CALL ► model=%s max_output_tokens=%s phase=%s",
            model,
            params.get("max_output_tokens"),
            phase_label or "-",
        )

        try:
            response = self.client.responses.create(**params)
        except Exception as exc:
            # Never include request payloads or credentials in failure output.
            return self._failure_result(
                model=model,
                api_model=api_model,
                error=f"Meta Model API request failed: {type(exc).__name__}",
            )

        finish_reason = self._finish_reason_for_response(response)
        usage = self._usage_payload(response)
        text = self._extract_output_text(response)
        status = str(getattr(response, "status", "") or "")

        # Refusal/filter before incomplete/length so incomplete refusals are not
        # misclassified as truncation.
        refusal_text = self._extract_refusal_text(response)
        if refusal_text is not None:
            return self._failure_result(
                model=model,
                api_model=api_model,
                error="Meta refused or filtered the response",
                response=response,
                finish_reason="content_filter",
                text=refusal_text or text,
            )

        if finish_reason == "length":
            logger.warning("META TEXT truncated ► model=%s status=%s", model, status)
            return self._failure_result(
                model=model,
                api_model=api_model,
                error="Meta returned truncated response (max_output_tokens)",
                response=response,
                finish_reason="length",
                text=text,
            )

        if status == "incomplete" or finish_reason == "incomplete":
            incomplete_details = getattr(response, "incomplete_details", None)
            reason = (
                getattr(incomplete_details, "reason", None)
                if incomplete_details is not None
                else None
            )
            reason_label = str(reason).strip() if reason else "unspecified"
            return self._failure_result(
                model=model,
                api_model=api_model,
                error=f"Meta returned incomplete response (reason={reason_label})",
                response=response,
                finish_reason="incomplete",
                text=text,
            )

        if status in {"failed", "cancelled"}:
            return self._failure_result(
                model=model,
                api_model=api_model,
                error=f"Meta response status={status}",
                response=response,
                finish_reason=finish_reason,
                text=text,
            )

        if not text:
            return self._failure_result(
                model=model,
                api_model=api_model,
                error="Meta returned empty text response",
                response=response,
                finish_reason=finish_reason,
            )

        provider_model = getattr(response, "model", None) or api_model
        return {
            "success": True,
            "text": text,
            "tokens_used": (usage or {}).get("total_tokens"),
            "model": model,
            "provider_model": provider_model,
            "api_model": api_model,
            "finish_reason": finish_reason or "stop",
            "char_count": len(text),
            "response_id": getattr(response, "id", None),
            "usage": usage,
        }

    def call_vision(self, prompt: str, image_data: str, model: str, **kwargs) -> Dict[str, Any]:
        """Reuse the canonical multimodal Responses path via call_text."""
        from services.llm.call_options import LlmCallOptions

        if not isinstance(image_data, str) or not image_data.strip():
            return {
                "success": False,
                "error": "Empty or invalid image data provided",
                "text": None,
                "model": model,
                "char_count": 0,
            }

        media_type_kw = kwargs.get("media_type", None)
        if media_type_kw is None:
            media_type = "image/jpeg"
        elif isinstance(media_type_kw, str) and media_type_kw.strip():
            media_type = media_type_kw.strip()
        else:
            return {
                "success": False,
                "error": "Empty or invalid image media_type provided",
                "text": None,
                "model": model,
                "char_count": 0,
            }

        new_attachment = {"b64": image_data.strip(), "media_type": media_type}
        existing = kwargs.get("call_options")
        if isinstance(existing, LlmCallOptions):
            prior = tuple(existing.image_attachments or ())
            call_options = replace(
                existing,
                image_attachments=prior + (new_attachment,),
            )
        else:
            call_options = LlmCallOptions(
                image_attachments=(new_attachment,),
                phase=kwargs.get("phase"),
            )

        next_kwargs = dict(kwargs)
        next_kwargs["call_options"] = call_options
        return self.call_text(prompt, model, **next_kwargs)
