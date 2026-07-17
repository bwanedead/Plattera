"""
OpenAI LLM Provider
Drop this file in services/llm/ and OpenAI models will automatically appear

🔴 CRITICAL REDUNDANCY IMPLEMENTATION DOCUMENTATION 🔴
=====================================================

THIS MODULE IS THE FINAL LINK IN THE CHAIN - PRESERVE ALL WIRING BELOW 🔴

CRITICAL INTEGRATION POINTS:
1. Pipeline calls: service.process_image_with_text()
2. This method wraps: call_vision()
3. call_vision() formats data for OpenAI API
4. OpenAI API returns text content
5. process_image_with_text() standardizes response

CRITICAL API WIRING:
- OpenAI vision API expects: data:image/jpeg;base64,{base64_string}
- Pipeline provides: clean base64 string (no prefix)
- This service adds: data URI prefix in call_vision()
- OpenAI returns: text content in response.choices[0].message.content

CRITICAL RESPONSE FORMAT:
process_image_with_text() MUST return:
{
    "success": True,
    "extracted_text": "...",  # CRITICAL: Frontend dependency
    "tokens_used": 6561,
    "model_used": "gpt-4o",
    "service_type": "llm",
    "confidence_score": 1.0,
    "metadata": {...}
}

ENHANCEMENT SAFETY RULES:
- NEVER change process_image_with_text() signature
- NEVER modify "extracted_text" field mapping
- NEVER change data URI prefix format
- ALWAYS preserve response standardization
- ALWAYS maintain backward compatibility

REDUNDANCY IMPLEMENTATION SAFETY RULES:
======================================

✅ SAFE FOR REDUNDANCY:
- process_image_with_text() is THREAD-SAFE for parallel calls
- call_vision() can be called multiple times simultaneously
- Response format is consistent across all calls
- Error handling is robust for individual call failures

❌ DO NOT MODIFY FOR REDUNDANCY:
- process_image_with_text() method signature
- call_vision() method signature  
- Response format structure
- Error handling patterns
- Data URI formatting logic

CRITICAL REDUNDANCY REQUIREMENTS:
================================
1. Service MUST handle multiple parallel calls to process_image_with_text()
2. Each call MUST be independent (no shared state)
3. Response format MUST be identical across all calls
4. Error handling MUST work for individual call failures
5. Token counting MUST be accurate for each call

THREADING SAFETY VERIFICATION:
=============================
- OpenAI client is thread-safe ✓
- No shared mutable state in methods ✓
- Each call creates independent request ✓
- Response processing is stateless ✓

TESTING CHECKPOINTS:
===================
After redundancy implementation, verify:
1. Single calls still work unchanged
2. Multiple parallel calls work correctly
3. Error handling works for individual failures
4. Token counting is accurate across calls
5. Response format remains consistent
"""
import os
import base64
import json
from types import SimpleNamespace
from typing import Dict, Any, List, Optional, Union
from services.llm.base import LLMService
from pydantic import BaseModel
import time
import logging
import random
from pathlib import Path
from config.paths import backend_root

try:
    import keyring
except ImportError:
    keyring = None

logger = logging.getLogger(__name__)

# Only import if available
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


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

# Remove the hardcoded Pydantic models (lines 103-133)
# class ParcelOrigin(BaseModel):  # DELETE THESE
# class ParcelLeg(BaseModel):     # DELETE THESE  
# class PlatteraParcel(BaseModel): # DELETE THESE

def _get_openai_api_key():
    """Retrieve OpenAI API key from OS keyring, falling back to env, with diagnostics.

    This is intentionally verbose so that frozen EXE runs make it obvious whether
    OpenAI failed due to missing keyring/env vs missing package.
    """
    if keyring is not None:
        try:
            key = keyring.get_password("plattera", "openai_api_key")
            if key:
                logger.debug("OPENAI_KEY ► resolved from keyring")
                return key
        except Exception as e:
            logger.warning(f"OPENAI_KEY ► keyring error: {e}")

    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        logger.debug("OPENAI_KEY ► resolved from environment")
        return env_key

    logger.warning("OPENAI_KEY ► not found in keyring or environment")
    return None

def _streaming_requested_from_kwargs(kwargs: Dict[str, Any], *, call_opts: Any = None) -> bool:
    """Read disabled-by-default streaming flag from call options or kwargs."""
    try:
        from services.llm.call_options import LlmCallOptions
    except ImportError:
        LlmCallOptions = None  # type: ignore[misc, assignment]
    if LlmCallOptions is not None and isinstance(call_opts, LlmCallOptions):
        if bool(getattr(call_opts, "streaming", False)):
            return True
    if bool(kwargs.get("streaming")) or bool(kwargs.get("stream")):
        return True
    return False


def _requested_service_tier_from_kwargs(kwargs: Dict[str, Any], *, call_opts: Any = None) -> str | None:
    """Read a requested service tier for telemetry without changing API defaults."""
    try:
        from services.llm.call_options import LlmCallOptions
    except ImportError:
        LlmCallOptions = None  # type: ignore[misc, assignment]
    if LlmCallOptions is not None and isinstance(call_opts, LlmCallOptions):
        tier = getattr(call_opts, "service_tier", None)
        if isinstance(tier, str) and tier.strip():
            return tier.strip()
    raw = kwargs.get("service_tier")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


class OpenAIService(LLMService):
    """OpenAI LLM service provider"""
    
    name = "openai"
    
    # context_window_tokens / max_output_tokens: local metadata for harness compaction and budgeting.
    # Not queried from the API at runtime. Models omitted here still work: harness uses a fixed fallback
    # (see harness.runtime.memory.openai_model_limits).
    models = {
        "gpt-4o": {
            "name": "GPT-4o",
            "provider": "openai",
            "cost_tier": "standard",
            "capabilities": ["vision", "text"],
            "description": "Most reliable for structured outputs and vision tasks",
            "verification_required": False,
            "context_window_tokens": 128_000,
            "max_output_tokens": 16_384,
        },
        "gpt-o4-mini": {
            "name": "GPT-o4-mini",
            "provider": "openai",
            "cost_tier": "budget",
            "capabilities": ["vision", "text"],
            "description": "Lightweight, fast model with reasoning capabilities",
            "verification_required": False,
            "api_model_name": "o4-mini-2025-04-16",
            "default_max_tokens": 16000,
            "context_window_tokens": 200_000,
            "max_output_tokens": 100_000,
        },
        "o3": {
            "name": "o3", 
            "provider": "openai",
            "cost_tier": "premium",
            "capabilities": ["vision", "text", "reasoning"],
            "description": "Most advanced reasoning model with highest accuracy",
            "verification_required": True,
            "context_window_tokens": 200_000,
            "max_output_tokens": 100_000,
        },
        "gpt-4": {
            "name": "GPT-4",
            "provider": "openai", 
            "cost_tier": "standard",
            "capabilities": ["text"],
            "description": "High-quality text processing model",
            "verification_required": False,
            "context_window_tokens": 8_192,
            "max_output_tokens": 8_192,
        },
        "gpt-5": {
            "name": "GPT-5",
            "provider": "openai",
            "cost_tier": "standard",
            "capabilities": ["text"],
            "description": "General GPT-5 model suitable for structured outputs",
            "verification_required": False,
            "api_model_name": "gpt-5",
            "context_window_tokens": 400_000,
            "max_output_tokens": 128_000,
        },
        "gpt-5-mini": {
            "name": "GPT-5 Mini",
            "provider": "openai",
            "cost_tier": "budget",
            "capabilities": ["text"],
            "description": "Fast, lightweight model for structured extraction (text-only)",
            "verification_required": False,
            "api_model_name": "gpt-5-mini",
            "context_window_tokens": 400_000,
            "max_output_tokens": 128_000,
        },
        "gpt-5.4": {
            "name": "GPT-5.4",
            "provider": "openai",
            "cost_tier": "standard",
            "capabilities": ["text", "vision"],
            "description": "Full GPT-5.4 model for live harness runs (stronger default than mini)",
            "verification_required": False,
            "api_model_name": "gpt-5.4",
            "default_max_tokens": 16000,
            "context_window_tokens": 400_000,
            "max_output_tokens": 128_000,
        },
        "gpt-5.4-mini": {
            "name": "GPT-5.4 Mini",
            "provider": "openai",
            "cost_tier": "budget",
            "capabilities": ["text", "vision"],
            "description": "Successor mini model for agent/harness overrides (text + image input per OpenAI)",
            "verification_required": False,
            "api_model_name": "gpt-5.4-mini",
            "default_max_tokens": 16000,
            "context_window_tokens": 400_000,
            "max_output_tokens": 128_000,
        },
        # GPT-5.6 Terra/Luna: Luna is the harness default; Terra is the stronger explicit override.
        # context_window_tokens / max_output_tokens match gpt-5.4 until an official OpenAI
        # model card is wired here; public preview listings report larger Terra windows.
        "gpt-5.6-terra": {
            "name": "GPT-5.6 Terra",
            "provider": "openai",
            "cost_tier": "standard",
            "capabilities": ["text", "vision"],
            "description": "Stronger GPT-5.6 model for explicit harness overrides",
            "verification_required": False,
            "api_model_name": "gpt-5.6-terra",
            "default_max_tokens": 16000,
            "context_window_tokens": 400_000,
            "max_output_tokens": 128_000,
        },
        "gpt-5.6-luna": {
            "name": "GPT-5.6 Luna",
            "provider": "openai",
            "cost_tier": "budget",
            "capabilities": ["text", "vision"],
            "description": "Budget GPT-5.6 model used as the harness default",
            "verification_required": False,
            "api_model_name": "gpt-5.6-luna",
            "default_max_tokens": 16000,
            "context_window_tokens": 400_000,
            "max_output_tokens": 128_000,
        },
        "gpt-5.2": {
            "name": "GPT-5.2",
            "provider": "openai",
            "cost_tier": "standard",
            "capabilities": ["text"],
            "description": "Controller default model for agent-loop step proposals",
            "verification_required": False,
            "api_model_name": "gpt-5.2",
            "default_max_tokens": 16000,
            "context_window_tokens": 400_000,
            "max_output_tokens": 128_000,
        },
        "gpt-5-nano": {
            "name": "GPT-5 Nano",
            "provider": "openai",
            "cost_tier": "budget",
            "capabilities": ["text"],
            "description": "Ultra-lightweight model for fast structured extraction (text-only)",
            "verification_required": False,
            "api_model_name": "gpt-5-nano",
            "context_window_tokens": 400_000,
            "max_output_tokens": 32_768,
        }
    }

    # Extend models with consensus-specific aliases (non-breaking additions)
    models.update({
        "gpt-5-consensus": {
            "name": "GPT-5 (Consensus)",
            "provider": "openai",
            "cost_tier": "standard",
            "capabilities": ["text"],
            "description": "Profile for LLM consensus generation (free-text)",
            "verification_required": False,
            "api_model_name": "gpt-5",
            "default_max_tokens": 16000,
            "context_window_tokens": 400_000,
            "max_output_tokens": 128_000,
        },
        "gpt-5-mini-consensus": {
            "name": "GPT-5 Mini (Consensus)",
            "provider": "openai",
            "cost_tier": "budget",
            "capabilities": ["text"],
            "description": "Profile for LLM consensus generation (balanced speed/quality)",
            "verification_required": False,
            "api_model_name": "gpt-5-mini",
            "default_max_tokens": 12000,
            "context_window_tokens": 400_000,
            "max_output_tokens": 128_000,
        },
        "gpt-5-nano-consensus": {
            "name": "GPT-5 Nano (Consensus)",
            "provider": "openai",
            "cost_tier": "budget",
            "capabilities": ["text"],
            "description": "Profile for LLM consensus generation (speed/cost optimized)",
            "verification_required": False,
            "api_model_name": "gpt-5-nano",
            "default_max_tokens": 8000,
            "context_window_tokens": 400_000,
            "max_output_tokens": 32_768,
        }
    })
    
    def __init__(self):
        self.client = None
        api_key = _get_openai_api_key()
        if OPENAI_AVAILABLE and api_key:
            self.client = OpenAI(api_key=api_key)
    
    def is_available(self) -> bool:
        """Check if OpenAI is available and configured"""
        return OPENAI_AVAILABLE and (_get_openai_api_key() is not None)
    
    def _get_api_model_name(self, model: str) -> str:
        """Get the actual API model name (some models have different display vs API names)"""
        model_info = self.models.get(model, {})
        return model_info.get("api_model_name", model)

    def _resolve_text_call_budget(
        self,
        *,
        model: str,
        api_model_name: str,
        effective_phase: str | None,
        output_mode: str,
        kwargs: dict[str, Any],
    ) -> tuple[int, str | None]:
        """Resolve phase-sensitive output budget / reasoning settings for text calls.

        choose_action-style JSON responses are mechanically small, but the prompt can be
        large and reasoning-token heavy. Give those phases a larger completion budget and
        avoid wasting it on maximum reasoning effort.
        """
        model_info = self.models.get(model, {})
        default_max = int(model_info.get("default_max_tokens", 4000))
        if "max_tokens" in kwargs and kwargs["max_tokens"] is not None:
            return int(kwargs["max_tokens"]), None

        if output_mode == "json_object" and effective_phase in _PHASE_JSON_ACTION_BUDGETS:
            phase_budget = _PHASE_JSON_ACTION_BUDGETS[effective_phase]
            provider_cap = int(model_info.get("max_output_tokens", default_max))
            min_max = int(phase_budget["min_max_tokens"])
            tuned_max = min(provider_cap, max(default_max, min_max))
            return tuned_max, str(phase_budget.get("reasoning_effort") or "medium")

        if ("o4-mini" in api_model_name) or ("gpt-5-mini" in api_model_name) or ("gpt-5" in api_model_name) or ("gpt-5-nano" in api_model_name):
            return default_max, "high"

        return default_max, None

    @staticmethod
    def _extract_message_content(response: Any) -> str | None:
        """Best-effort text extraction from the first response choice."""
        if not getattr(response, "choices", None):
            return None
        message = getattr(response.choices[0], "message", None)
        if message is None:
            return None
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
        return None

    @staticmethod
    def _usage_payload(response: Any) -> dict[str, int | None] | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        cached_input_tokens = getattr(usage, "cached_tokens", None)
        if cached_input_tokens is None:
            details = getattr(usage, "prompt_tokens_details", None)
            if details is not None:
                cached_input_tokens = getattr(details, "cached_tokens", None)
        reasoning_tokens = getattr(usage, "reasoning_tokens", None)
        if reasoning_tokens is None:
            completion_details = getattr(usage, "completion_tokens_details", None)
            if completion_details is not None:
                reasoning_tokens = getattr(completion_details, "reasoning_tokens", None)
        return {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "reasoning_tokens": reasoning_tokens,
            "total_tokens": getattr(usage, "total_tokens", None),
            "cached_input_tokens": cached_input_tokens,
        }

    def _text_failure_result(
        self,
        *,
        model: str,
        api_model_name: str,
        response: Any,
        error: str,
        finish_reason: str | None,
    ) -> Dict[str, Any]:
        partial_text = self._extract_message_content(response)
        char_count = len(partial_text) if isinstance(partial_text, str) else 0
        provider_model = getattr(response, "model", None) or api_model_name
        return {
            "success": False,
            "error": error,
            "text": partial_text,
            "model": model,
            "finish_reason": finish_reason,
            "usage": self._usage_payload(response),
            "char_count": char_count,
            "provider_model": provider_model,
            "api_model": api_model_name,
        }

    def _call_text_streaming(
        self,
        *,
        completion_params: Dict[str, Any],
        model: str,
        api_model_name: str,
        call_opts: Any,
        kwargs: Dict[str, Any],
        ctx: str,
    ) -> Dict[str, Any]:
        """Aggregate streamed chat completion chunks into the standard text envelope."""
        stream_params = dict(completion_params)
        stream_params["stream"] = True
        stream_params["stream_options"] = {"include_usage": True}
        request_started = time.time()
        first_event_at: float | None = None
        text_parts: list[str] = []
        finish_reason: str | None = None
        response_id: str | None = None
        provider_model: str | None = None
        usage_payload: dict[str, int | None] | None = None

        stream = self.client.chat.completions.create(**stream_params)
        for chunk in stream:
            if first_event_at is None:
                first_event_at = time.time()
            response_id = getattr(chunk, "id", None) or response_id
            provider_model = getattr(chunk, "model", None) or provider_model
            choices = getattr(chunk, "choices", None) or []
            if choices:
                choice = choices[0]
                finish_reason = getattr(choice, "finish_reason", None) or finish_reason
                delta = getattr(choice, "delta", None)
                if delta is not None:
                    content = getattr(delta, "content", None)
                    if isinstance(content, str) and content:
                        text_parts.append(content)
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                usage_payload = self._usage_payload(SimpleNamespace(usage=chunk_usage))

        finished_at = time.time()
        response_text = "".join(text_parts)
        token_usage = usage_payload["total_tokens"] if usage_payload else 0
        service_tier_requested = _requested_service_tier_from_kwargs(kwargs, call_opts=call_opts)
        timing_meta = {
            "streaming_requested": True,
            "request_started_at_epoch_seconds": round(request_started, 3),
            "response_finished_at_epoch_seconds": round(finished_at, 3),
        }
        if first_event_at is not None:
            timing_meta["first_response_event_at_epoch_seconds"] = round(first_event_at, 3)
        if usage_payload is None:
            timing_meta["usage_unavailable_reason"] = "streaming_usage_not_returned"

        logger.info(
            f"📨 TEXT stream response received: finish_reason='{finish_reason}', "
            f"tokens={token_usage}{ctx}"
        )

        pseudo_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=response_text), finish_reason=finish_reason)],
            usage=SimpleNamespace(**usage_payload) if usage_payload else None,
            model=provider_model or api_model_name,
            id=response_id,
        )

        if finish_reason == "length":
            result = self._text_failure_result(
                model=model,
                api_model_name=api_model_name,
                response=pseudo_response,
                error=f"OpenAI returned truncated response (finish_reason: {finish_reason})",
                finish_reason=finish_reason,
            )
            result.update(timing_meta)
            return result
        if finish_reason == "content_filter":
            result = self._text_failure_result(
                model=model,
                api_model_name=api_model_name,
                response=pseudo_response,
                error=f"OpenAI blocked response (finish_reason: {finish_reason})",
                finish_reason=finish_reason,
            )
            result.update(timing_meta)
            return result
        if not response_text:
            result = self._text_failure_result(
                model=model,
                api_model_name=api_model_name,
                response=pseudo_response,
                error="OpenAI returned empty text response",
                finish_reason=finish_reason,
            )
            result.update(timing_meta)
            return result

        return {
            "success": True,
            "text": response_text,
            "tokens_used": token_usage,
            "model": model,
            "provider_model": provider_model or api_model_name,
            "api_model": api_model_name,
            "finish_reason": finish_reason,
            "char_count": len(response_text),
            "response_id": response_id,
            "service_tier_requested": service_tier_requested,
            "service_tier_returned": None,
            "usage": usage_payload,
            **timing_meta,
        }
    
    def call_text(self, prompt: str, model: str, **kwargs) -> Dict[str, Any]:
        """Make text-only API call to OpenAI"""
        try:
            # Resolve typed call options first so phase is available for log context.
            call_opts = kwargs.get("call_options")
            if call_opts is not None:
                image_attachments = list(call_opts.image_attachments) if call_opts.image_attachments else []
                output_mode = call_opts.output_mode
                effective_phase = call_opts.phase or kwargs.get("phase")
            else:
                image_attachments = list(kwargs.get("image_attachments") or [])
                output_mode = "text"
                effective_phase = kwargs.get("phase")

            run_context = kwargs.get("run_context")
            draft_index = kwargs.get("draft_index")
            draft_count = kwargs.get("draft_count")
            transcription_id = kwargs.get("transcription_id")
            dossier_id = kwargs.get("dossier_id")
            draft_label = None
            if isinstance(draft_index, int) and isinstance(draft_count, int) and draft_count > 0:
                draft_label = f"{draft_index + 1}/{draft_count}"
            ctx_parts = []
            if run_context:
                ctx_parts.append(f"run={run_context}")
            if effective_phase:
                ctx_parts.append(f"phase={effective_phase}")
            if draft_label:
                ctx_parts.append(f"draft={draft_label}")
            if dossier_id:
                ctx_parts.append(f"dossier={dossier_id}")
            if transcription_id:
                ctx_parts.append(f"transcription={transcription_id}")
            ctx = f" ({' '.join(ctx_parts)})" if ctx_parts else ""

            api_model_name = self._get_api_model_name(model)

            # Build user content (multimodal when image attachments are present).
            if image_attachments:
                content: list[dict] = [{"type": "text", "text": prompt}]
                for att in image_attachments:
                    b64 = att.get("b64", "") if isinstance(att, dict) else ""
                    media_type = att.get("media_type", "image/jpeg") if isinstance(att, dict) else "image/jpeg"
                    if b64:
                        content.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{b64}"},
                        })
                user_content: Any = content
            else:
                user_content = prompt
            completion_params = {
                "model": api_model_name,
                "messages": [{"role": "user", "content": user_content}],
            }
            # Honor structured-output policy.
            if output_mode == "json_object":
                completion_params["response_format"] = {"type": "json_object"}
            
            budget_max_tokens, tuned_reasoning_effort = self._resolve_text_call_budget(
                model=model,
                api_model_name=api_model_name,
                effective_phase=effective_phase,
                output_mode=output_mode,
                kwargs=kwargs,
            )

            # Some small models require max_completion_tokens (no temperature)
            if ("o4-mini" in api_model_name) or ("gpt-5-mini" in api_model_name) or ("gpt-5" in api_model_name) or ("gpt-5-nano" in api_model_name):
                # o4-mini only supports default temperature (1), so don't include it
                completion_params["max_completion_tokens"] = budget_max_tokens
                if tuned_reasoning_effort is not None:
                    completion_params["reasoning_effort"] = tuned_reasoning_effort
            else:
                # Other models use standard parameters
                completion_params["temperature"] = kwargs.get("temperature", 0.1)
                completion_params["max_tokens"] = budget_max_tokens
            max_tokens = completion_params.get("max_completion_tokens") or completion_params.get("max_tokens")
            streaming_requested = _streaming_requested_from_kwargs(kwargs, call_opts=call_opts)
            if streaming_requested:
                logger.info(f"🧠 TEXT CALL (stream) ► model={model} max_tokens={max_tokens}{ctx}")
                return self._call_text_streaming(
                    completion_params=completion_params,
                    model=model,
                    api_model_name=api_model_name,
                    call_opts=call_opts,
                    kwargs=kwargs,
                    ctx=ctx,
                )

            logger.info(f"🧠 TEXT CALL ► model={model} max_tokens={max_tokens}{ctx}")
            
            response = self.client.chat.completions.create(**completion_params)
            finish_reason = response.choices[0].finish_reason if response.choices else None
            usage_payload = self._usage_payload(response)
            token_usage = usage_payload["total_tokens"] if usage_payload else 0
            prompt_tokens = usage_payload["prompt_tokens"] if usage_payload else None
            completion_tokens = usage_payload["completion_tokens"] if usage_payload else None
            reasoning_tokens = usage_payload["reasoning_tokens"] if usage_payload else None
            logger.info(f"📨 TEXT response received: finish_reason='{finish_reason}', tokens={token_usage}{ctx}")
            logger.info(
                f"📊 TEXT TOKEN USAGE ► prompt={prompt_tokens} completion={completion_tokens} "
                f"reasoning={reasoning_tokens} total={token_usage}{ctx}"
            )

            if finish_reason == "length":
                logger.warning(f"⚠️ Text response truncated due to token limit (model={model}){ctx}")
                return self._text_failure_result(
                    model=model,
                    api_model_name=api_model_name,
                    response=response,
                    error=f"OpenAI returned truncated response (finish_reason: {finish_reason})",
                    finish_reason=finish_reason,
                )
            if finish_reason == "content_filter":
                logger.warning(f"⚠️ Text response blocked by content filter (model={model}){ctx}")
                return self._text_failure_result(
                    model=model,
                    api_model_name=api_model_name,
                    response=response,
                    error=f"OpenAI blocked response (finish_reason: {finish_reason})",
                    finish_reason=finish_reason,
                )
            response_text = self._extract_message_content(response)
            if not response.choices or not response_text:
                logger.warning(f"❌ Empty text response content (model={model}){ctx}")
                return self._text_failure_result(
                    model=model,
                    api_model_name=api_model_name,
                    response=response,
                    error="OpenAI returned empty text response",
                    finish_reason=finish_reason,
                )
            
            provider_model = getattr(response, "model", None) or api_model_name
            service_tier_requested = _requested_service_tier_from_kwargs(kwargs, call_opts=call_opts)
            return {
                "success": True,
                "text": response_text,
                "tokens_used": token_usage,
                "model": model,
                "provider_model": provider_model,
                "api_model": api_model_name,
                "finish_reason": finish_reason,
                "char_count": len(response_text),
                "response_id": getattr(response, "id", None),
                "service_tier_requested": service_tier_requested,
                "service_tier_returned": getattr(response, "service_tier", None),
                "usage": usage_payload,
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "text": None,
                "model": model,
                "char_count": 0,
            }
    
    def call_vision(self, prompt: str, image_data: str, model: str, **kwargs) -> Dict[str, Any]:
        """Enhanced with improved retry logic, jitter, and detailed finish_reason logging"""
        # Validate inputs
        if not image_data or not image_data.strip():
            return {
                "success": False,
                "error": "Empty image data provided",
                "text": None,
                "model": model
            }
        
        if not prompt or not prompt.strip():
            return {
                "success": False,
                "error": "Empty prompt provided",
                "text": None,
                "model": model
            }
        
        run_context = kwargs.get("run_context")
        draft_index = kwargs.get("draft_index")
        draft_count = kwargs.get("draft_count")
        transcription_id = kwargs.get("transcription_id")
        dossier_id = kwargs.get("dossier_id")
        draft_label = None
        if isinstance(draft_index, int) and isinstance(draft_count, int) and draft_count > 0:
            draft_label = f"{draft_index + 1}/{draft_count}"
        ctx_parts = []
        if run_context:
            ctx_parts.append(f"run={run_context}")
        if draft_label:
            ctx_parts.append(f"draft={draft_label}")
        if dossier_id:
            ctx_parts.append(f"dossier={dossier_id}")
        if transcription_id:
            ctx_parts.append(f"transcription={transcription_id}")
        ctx = f" ({' '.join(ctx_parts)})" if ctx_parts else ""

        # 🔧 IMPROVEMENT: Enhanced retry logic with exponential backoff + jitter
        max_retries = 4  # Increased from 3 to 4 for o4-mini reliability
        base_delay = 1.0
        
        logger.info(f"🤖 Starting OpenAI API call for {model} (max {max_retries} attempts){ctx}")
        
        for attempt in range(max_retries):
            try:
                # 🔧 IMPROVEMENT: Add pre-send jitter to prevent simultaneous backend hits
                if attempt > 0:
                    jitter = random.uniform(0.2, 0.5)
                    delay = base_delay * (2 ** (attempt - 1)) + jitter  # Exponential backoff + jitter
                    logger.debug(f"🔄 Retry attempt {attempt + 1} after {delay:.2f}s delay{ctx}")
                    time.sleep(delay)
                
                api_model_name = self._get_api_model_name(model)
                
                # CRITICAL: Build OpenAI vision API message format
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_data}",
                                    "detail": kwargs.get("detail", "high")
                                }
                            }
                        ]
                    }
                ]
                
                # Build parameters based on model type
                completion_params = {
                    "model": api_model_name,
                    "messages": messages
                }
                
                # 🔧 IMPROVEMENT: Explicit high max_tokens for all models to prevent cutoffs
                is_reasoning_model = ("o4-mini" in api_model_name) or api_model_name.startswith("gpt-5")
                if is_reasoning_model:
                    default_max = self.models.get(model, {}).get("default_max_tokens", 12000)
                    completion_params["max_completion_tokens"] = kwargs.get("max_tokens", default_max)
                    # GPT-5/o4-mini models expect reasoning controls and max_completion_tokens.
                    completion_params["reasoning_effort"] = "high"
                    if attempt == 0:
                        logger.debug(
                            f"🧠 Using reasoning model {api_model_name} with max_completion_tokens="
                            f"{completion_params['max_completion_tokens']}{ctx}"
                        )
                else:
                    completion_params["temperature"] = kwargs.get("temperature", 0.1)
                    completion_params["max_tokens"] = kwargs.get("max_tokens", 8000)  # Increased from 4000
                    if attempt == 0:
                        logger.debug(f"🤖 Using {api_model_name}, max_tokens: {completion_params['max_tokens']}{ctx}")
                
                # CRITICAL: Add structured JSON response format for JSON extraction mode
                json_mode = kwargs.get("json_mode", False)
                json_mode_kind = "strict" if json_mode is True else str(json_mode or "").strip().lower()
                if json_mode_kind in {"strict", "relaxed"}:
                    if json_mode_kind == "strict":
                        completion_params["response_format"] = {
                            "type": "json_schema",
                            "json_schema": {
                                "name": "document_transcription",
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "documentId": {"type": "string"},
                                        "sections": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "id": {"type": "integer"},
                                                    "body": {"type": "string"}
                                                },
                                                "required": ["id", "body"],
                                                "additionalProperties": False
                                            }
                                        }
                                    },
                                    "required": ["documentId", "sections"],
                                    "additionalProperties": False
                                },
                                "strict": True
                            }
                        }
                    else:
                        completion_params["response_format"] = {"type": "json_object"}
                    if attempt == 0:
                        logger.debug(f"📋 Using JSON output mode={json_mode_kind}{ctx}")
                
                # CRITICAL: Make OpenAI API call
                logger.info(f"📡 Sending API request (attempt {attempt + 1}/{max_retries})...{ctx}")
                response = self.client.chat.completions.create(**completion_params)
                
                # 🔧 IMPROVEMENT: Detailed logging of finish_reason for debugging
                finish_reason = response.choices[0].finish_reason if response.choices else None
                token_usage = response.usage.total_tokens if response.usage else 0
                prompt_tokens = response.usage.prompt_tokens if response.usage else None
                completion_tokens = response.usage.completion_tokens if response.usage else None
                reasoning_tokens = getattr(response.usage, "reasoning_tokens", None) if response.usage else None
                logger.info(f"📨 API response received: finish_reason='{finish_reason}', tokens={token_usage}{ctx}")
                logger.info(
                    f"📊 TOKEN USAGE ► prompt={prompt_tokens} completion={completion_tokens} "
                    f"reasoning={reasoning_tokens} total={token_usage}{ctx}"
                )
                
                # Check for problematic finish reasons
                if finish_reason == "length":
                    max_tokens_hint = (
                        completion_params.get("max_completion_tokens")
                        or completion_params.get("max_tokens")
                    )
                    logger.warning(f"⚠️ Response truncated due to token limit (max_tokens={max_tokens_hint}, prompt_chars={len(prompt)}){ctx}")
                elif finish_reason == "content_filter":
                    logger.warning(f"⚠️ Response blocked by content filter{ctx}")
                elif finish_reason != "stop":
                    logger.warning(f"⚠️ Unexpected finish_reason: {finish_reason}{ctx}")
                
                # Validate response
                if not response.choices or not response.choices[0].message.content:
                    logger.warning(f"❌ Empty response content (finish_reason: {finish_reason}){ctx}")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        return {
                            "success": False,
                            "error": f"OpenAI returned empty response after {max_retries} retries (finish_reason: {finish_reason})",
                            "text": None,
                            "model": model
                        }
                
                # CRITICAL: Extract text content from response
                extracted_text = response.choices[0].message.content.strip()
                
                if not extracted_text:
                    logger.warning(f"❌ Empty text content after strip (finish_reason: {finish_reason}){ctx}")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        return {
                            "success": False,
                            "error": f"OpenAI returned empty text content after {max_retries} retries (finish_reason: {finish_reason})",
                            "text": None,
                            "model": model
                        }
                
                # 🔧 IMPROVEMENT: Success logging with detailed metrics
                char_count = len(extracted_text)
                word_count = len(extracted_text.split())
                logger.info(f"✅ API call successful: {char_count} chars, {word_count} words, {token_usage} tokens, finish_reason: {finish_reason}{ctx}")
                
                return {
                    "success": True,
                    "text": extracted_text,
                    "tokens_used": token_usage,
                    "model": model,
                    "finish_reason": finish_reason,  # 🔧 IMPROVEMENT: Include for debugging
                    "char_count": char_count,
                    "word_count": word_count,
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "reasoning_tokens": reasoning_tokens,
                        "total_tokens": token_usage
                    }
                }
                
            except Exception as e:
                logger.error(f"💥 API call attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    continue
                else:
                    logger.error(f"💥 All {max_retries} attempts failed for {model}")
                    return {
                        "success": False,
                        "error": f"OpenAI API failed after {max_retries} attempts: {str(e)}",
                        "text": None,
                        "model": model
                    }
    
    def process_image_with_text(self, image_data: str, prompt: str, model: str, **kwargs) -> Dict[str, Any]:
        """
        Process image with text prompt (wrapper around call_vision for pipeline compatibility)
        
        🔴 CRITICAL PIPELINE INTERFACE - DO NOT MODIFY SIGNATURE 🔴
        
        Args:
            image_data: Base64 encoded image data (clean, no prefix)
            prompt: Text prompt for processing
            model: Model to use
            **kwargs: Additional parameters
        
        Returns:
            Standardized response format for pipelines
            
        CRITICAL RESPONSIBILITIES:
        1. Call call_vision() with correct parameters
        2. Convert response to pipeline-expected format
        3. Map "text" field to "extracted_text" field
        4. Preserve token usage and metadata
        """
        # CRITICAL: Call vision API with provided parameters
        result = self.call_vision(prompt, image_data, model, **kwargs)
        
        # CRITICAL: Convert to pipeline-expected format
        # Pipeline expects "extracted_text" field, call_vision returns "text"
        if result.get("success"):
            return {
                "success": True,
                "extracted_text": result.get("text", ""),  # CRITICAL: Field mapping
                "tokens_used": result.get("tokens_used"),
                "model_used": result.get("model"),
                "service_type": "llm",
                "confidence_score": 1.0,  # OpenAI doesn't provide confidence scores
                "metadata": {
                    "provider": "openai",
                    "finish_reason": result.get("finish_reason"),
                    "usage": result.get("usage"),
                    "char_count": result.get("char_count"),
                    "word_count": result.get("word_count"),
                    **kwargs
                }
            }
        else:
            # CRITICAL: Preserve error response format
            return result
    
    def call_structured_pydantic(self, prompt: str, input_text: str, model: str, parcel_id: Optional[str] = None, schema: dict = None, **kwargs) -> Dict[str, Any]:
        """Make structured output API call using dynamic schema (recommended approach)"""
        try:
            api_model_name = self._get_api_model_name(model)
            
            # Validate model name for GPT-5 series
            if api_model_name.startswith('gpt-5'):
                assert api_model_name in {
                    "gpt-5",
                    "gpt-5.2",
                    "gpt-5-mini",
                    "gpt-5.4",
                    "gpt-5.4-mini",
                    "gpt-5.6-terra",
                    "gpt-5.6-luna",
                    "gpt-5-nano",
                }, f"Invalid GPT-5 model: {api_model_name}"
            
            # Use provided schema or load default fallback (GENERIC)
            if schema:
                schema_dict = schema
            else:
                schema_dict = self._load_parcel_schema()  # Fallback
            
            # Create the proper OpenAI JSON schema structure
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "plattera_parcel",
                    "schema": schema_dict,
                    "strict": True
                }
            }
            
            # Create the full prompt
            full_prompt = f"{prompt}\n\nLegal Description Text:\n{input_text}"
            
            # Generate parcel ID if not provided
            if not parcel_id:
                parcel_id = f"parcel-{int(time.time() * 1000)}"
            
            # GPT-5 SPECIFIC: Check if this is a GPT-5 model for special handling
            is_gpt5_model = api_model_name.startswith('gpt-5')
            
            # Initialize completion_params based on model type
            if is_gpt5_model:
                # 🔥 MODEL-SPECIFIC OPTIMIZATION
                if api_model_name == "gpt-5-nano":
                    # 🚀 NANO: Optimize for speed and efficiency
                    completion_params = {
                        "model": api_model_name,
                        "messages": [
                            {"role": "system", "content": "Output ONLY a single JSON object matching the schema. Be direct and efficient."},
                            {"role": "user", "content": full_prompt}
                        ],
                        "response_format": response_format,
                        "max_completion_tokens": 8000,   # 🚀 Lower cap - nano should be efficient
                        # 🚀 NO reasoning_effort - let nano be fast like GPT-4o
                    }
                    logger.debug(f"🚀 Using GPT-5 Nano speed-optimized parameters: model={api_model_name}, max_completion_tokens=8000, no_reasoning")
                    
                elif api_model_name in ("gpt-5-mini", "gpt-5.4-mini"):
                    # ⚡ MINI: Balanced approach
                    completion_params = {
                        "model": api_model_name,
                        "messages": [
                            {"role": "system", "content": "Output ONLY a single JSON object matching the schema. No explanations or additional text."},
                            {"role": "user", "content": full_prompt}
                        ],
                        "response_format": response_format,
                        "max_completion_tokens": 12000,  # ⚡ Medium cap
                        "reasoning_effort": "medium"     # ⚡ Balanced reasoning
                    }
                    logger.debug(
                        f"⚡ Using GPT-5 mini-class balanced parameters: model={api_model_name}, "
                        "max_completion_tokens=12000, reasoning_effort=medium"
                    )
                    
                else:  # gpt-5 full model
                    # 🧠 FULL GPT-5: Maximum quality
                    completion_params = {
                        "model": api_model_name,
                        "messages": [
                            {"role": "system", "content": "Output ONLY a single JSON object matching the schema. No explanations or additional text."},
                            {"role": "user", "content": full_prompt}
                        ],
                        "response_format": response_format,
                        "max_completion_tokens": 16000,  # 🧠 High cap for quality
                        "reasoning_effort": "high"       # 🧠 Maximum accuracy
                    }
                    logger.debug(f"🧠 Using GPT-5 full model parameters: model={api_model_name}, max_completion_tokens=16000, reasoning_effort=high")
                    
            else:
                # 🔄 EXISTING LOGIC - Keep exactly as before for non-GPT-5 models
                completion_params = {
                    "model": api_model_name,
                    "messages": [{"role": "user", "content": full_prompt}],
                    "response_format": response_format,
                }
                if ("o4-mini" in api_model_name):
                    completion_params["max_completion_tokens"] = 4000
                else:
                    completion_params["temperature"] = 0
                    completion_params["max_tokens"] = 4000

            completion = self.client.chat.completions.create(**completion_params)
            
            # 🔍 CRITICAL: Log the full response envelope for debugging
            try:
                logger.debug(f"🔍 RAW_OPENAI_ENVELOPE for {api_model_name}:")
                envelope_data = {
                    "choices": [
                        {
                            "message": {
                                "content": completion.choices[0].message.content,
                                "role": completion.choices[0].message.role
                            },
                            "finish_reason": completion.choices[0].finish_reason,
                            "index": completion.choices[0].index
                        }
                    ],
                    "usage": {
                        "completion_tokens": completion.usage.completion_tokens if completion.usage else None,
                        "prompt_tokens": completion.usage.prompt_tokens if completion.usage else None,
                        "total_tokens": completion.usage.total_tokens if completion.usage else None
                    } if completion.usage else None,
                    "model": completion.model if hasattr(completion, 'model') else api_model_name
                }
                logger.debug(f"🔍 Envelope: {json.dumps(envelope_data, indent=2)}")
            except Exception as e:
                logger.warning(f"⚠️ Could not log envelope: {e}")
            
            # Extract the response and check finish_reason
            message = completion.choices[0].message
            response_content = message.content
            finish_reason = completion.choices[0].finish_reason
            
            # 🚨 Check for problematic finish reasons
            if finish_reason in ("length", "content_filter"):
                logger.error(f"🚨 {api_model_name} stopped due to {finish_reason}!")
                return {
                    "success": False,
                    "error": f"{api_model_name} stopped due to {finish_reason}. Usage: {completion.usage}",
                    "text": str(response_content),
                    "model": model,
                    "finish_reason": finish_reason
                }
            
            # 🚨 Check for refusal (rare but possible)
            if hasattr(message, 'refusal') and message.refusal:
                logger.error(f"🚨 {api_model_name} refused request: {message.refusal}")
                return {
                    "success": False,
                    "error": f"{api_model_name} refused request: {message.refusal}",
                    "text": str(response_content),
                    "model": model
                }
            
            # 🔍 Enhanced response content logging
            logger.debug(f"🔍 Raw response received from {api_model_name}:")
            logger.debug(f"🔍 Response type: {type(response_content)}")
            logger.debug(f"🔍 Response length: {len(response_content) if response_content else 'None'}")
            logger.debug(f"🔍 Response content (first 500 chars): {repr(response_content[:500]) if response_content else 'None'}")
            logger.debug(f"🔍 Finish reason: {finish_reason}")
            
            # Check for empty/None response 
            if not response_content:
                logger.error(f"🚨 {api_model_name} returned empty/None response!")
                logger.error(f"🚨 Finish reason: {finish_reason}")
                logger.error(f"🚨 Usage: {completion.usage}")
                return {
                    "success": False,
                    "error": f"{api_model_name} returned empty response. Finish reason: {finish_reason}",
                    "text": str(response_content),
                    "model": model,
                    "finish_reason": finish_reason
                }
            
            # Check for non-string response
            if not isinstance(response_content, str):
                logger.error(f"🚨 {api_model_name} returned non-string response: {type(response_content)}")
                return {
                    "success": False,
                    "error": f"{api_model_name} returned non-string response: {type(response_content)}",
                    "text": str(response_content),
                    "model": model
                }
            
            # Strip whitespace
            response_content = response_content.strip()
            if not response_content:
                logger.error(f"🚨 {api_model_name} returned only whitespace!")
                return {
                    "success": False,
                    "error": f"{api_model_name} returned only whitespace",
                    "text": response_content,
                    "model": model
                }
            
            # 🔍 Log token usage for debugging (especially important for GPT-5)
            if hasattr(completion, 'usage') and completion.usage:
                tokens_used = completion.usage.total_tokens
                output_tokens = getattr(completion.usage, 'completion_tokens', 0)
                prompt_tokens = getattr(completion.usage, 'prompt_tokens', 0)
                logger.debug(f"📊 Token usage: {tokens_used} total ({prompt_tokens} prompt + {output_tokens} output) for {api_model_name}")
                
                # 🚨 Check for potential truncation
                if is_gpt5_model and output_tokens >= 15500:  # Close to 16k cap
                    logger.warning(f"⚠️ GPT-5 output tokens ({output_tokens}) approaching cap - potential truncation!")
                elif not is_gpt5_model and output_tokens >= 3900:  # Close to 4k cap
                    logger.warning(f"⚠️ Output tokens ({output_tokens}) approaching cap - potential truncation!")
            
            # Parse the JSON response
            try:
                logger.debug(f"🔍 Attempting to parse JSON from {api_model_name}...")
                structured_data = json.loads(response_content)
                structured_data['parcel_id'] = parcel_id  # Ensure parcel_id is set
                
                logger.debug(f"✅ Successfully parsed JSON response from {api_model_name}")
                
                # Return standardized response format
                return {
                    "success": True,
                    "structured_data": structured_data,
                    "text": response_content,
                    "tokens_used": completion.usage.total_tokens if completion.usage else 0,
                    "model": model
                }
            except json.JSONDecodeError as e:
                # 🔥 Enhanced JSON parsing error handling
                logger.error(f"🚨 JSON parse failed for {api_model_name}: {e}")
                logger.error(f"🚨 Parse error at position {e.pos if hasattr(e, 'pos') else 'unknown'}")
                logger.error(f"🚨 Full response content: {repr(response_content)}")
                
                # Check if response looks like it might be truncated JSON
                if response_content.count('{') != response_content.count('}'):
                    logger.error(f"🚨 Unbalanced braces - likely truncated JSON!")
                
                if is_gpt5_model:
                    # Check for truncation
                    if hasattr(completion, 'usage') and completion.usage:
                        output_tokens = getattr(completion.usage, 'completion_tokens', 0)
                        if output_tokens >= 15500:
                            return {
                                "success": False,
                                "error": f"GPT-5 response truncated at {output_tokens} tokens - increase max_completion_tokens",
                                "text": response_content,
                                "model": model,
                                "truncated": True
                            }
                
                return {
                    "success": False,
                    "error": f"Failed to parse LLM response as JSON: {e}",
                    "text": response_content,
                    "model": model,
                    "parse_error_position": getattr(e, 'pos', None)
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"OpenAI structured extraction failed: {str(e)}",
                "structured_data": None,
                "model": model
            }
    
    def _load_parcel_schema(self) -> dict:
        """Load the parcel schema as fallback (matches pipeline schema)."""
        try:
            # Use centralized backend_root so this works in both dev and frozen bundles.
            schema_path = backend_root() / "schema" / "plss_m_and_b.json"
            with open(schema_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Parcel schema file not found at {schema_path}")
            return {}
    
    def call_structured(self, prompt: str, input_text: str, schema: dict, model: str, **kwargs) -> Dict[str, Any]:
        """Make structured output API call using JSON schema (fallback method)"""
        try:
            api_model_name = self._get_api_model_name(model)
            
            # Create the full prompt
            full_prompt = f"{prompt}\n\nLegal Description Text:\n{input_text}"
            
            messages = [{"role": "user", "content": full_prompt}]
            
            # Use the passed-in schema parameter (dynamic) instead of hardcoded.
            # Wrap according to OpenAI's json_schema strict format.
            completion_params = {
                "model": api_model_name,
                "messages": messages,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "plattera_parcel",
                        "schema": schema,
                        "strict": True,
                    },
                },
            }
            if ("o4-mini" in api_model_name) or ("gpt-5-mini" in api_model_name) or ("gpt-5" in api_model_name) or ("gpt-5-nano" in api_model_name):
                completion_params["max_completion_tokens"] = kwargs.get("max_tokens", 4000)
            else:
                completion_params["temperature"] = kwargs.get("temperature", 0.1)
                completion_params["max_tokens"] = kwargs.get("max_tokens", 4000)
            
            response = self.client.chat.completions.create(**completion_params)
            
            # Parse the structured JSON response
            response_text = response.choices[0].message.content
            try:
                structured_data = json.loads(response_text)
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "error": f"Failed to parse structured response: {str(e)}",
                    "text": response_text,
                    "model": model
                }
            
            return {
                "success": True,
                "structured_data": structured_data,
                "text": response_text,
                "tokens_used": response.usage.total_tokens,
                "model": model
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "structured_data": None,
                "model": model
            } 
