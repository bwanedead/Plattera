"""Provider-neutral harness model caller built on the service registry.

Resolves the effective model per invocation, routes to the owning configured
provider, and instruments the call with that provider's identity.

Streaming is a transport optimization. This layer negotiates capability:
requested streaming is passed through when the resolved provider supports it,
and transparently downgraded to a one-shot call when it does not.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from services.llm.call_options import LlmCallOptions
from services.registry import ModelProviderError, ServiceRegistry, get_registry

from .instrumented_caller import TextModelCaller, instrument_model_caller
from .llm_call_trace import extract_streaming_requested


def build_provider_model_caller(
    *,
    default_model_name: str,
    registry: ServiceRegistry | None = None,
) -> TextModelCaller:
    """Build the default harness text-model caller.

    For every invocation:
    - resolve the effective model from the call argument, falling back to
      ``default_model_name`` only when blank
    - resolve that model's owning provider via the service registry
    - refuse clearly when the model is unknown, ambiguous, or its provider is
      unavailable
    - call that provider's ``call_text``
    - instrument the result with the resolved provider identity
    """

    reg = registry if registry is not None else get_registry()
    fallback = str(default_model_name or "").strip()
    wrapped_by_provider: dict[str, TextModelCaller] = {}

    def _call(prompt: str, model: str, **kwargs: Any) -> Mapping[str, Any] | str:
        effective = str(model or "").strip() or fallback
        if not effective:
            raise ModelProviderError("model_provider_not_found", "Model id is blank.")
        service = reg.get_available_llm_service_for_model(effective)
        provider_name = str(getattr(service, "name", "") or "").strip() or "unknown"
        wrapped = wrapped_by_provider.get(provider_name)
        if wrapped is None:
            streaming_supported = bool(service.supports_streaming())

            # Bind the resolved service by default-arg so later cross-provider
            # resolutions cannot rewrite this provider's cached caller.
            def _raw(
                inner_prompt: str,
                inner_model: str,
                *,
                _service: Any = service,
                _streaming_supported: bool = streaming_supported,
                **inner_kwargs: Any,
            ) -> Mapping[str, Any] | str:
                call_kwargs = _negotiate_streaming_kwargs(
                    inner_kwargs,
                    streaming_supported=_streaming_supported,
                )
                return _service.call_text(inner_prompt, inner_model, **call_kwargs)

            wrapped = instrument_model_caller(
                _raw,
                provider=provider_name,
                streaming_supported=streaming_supported,
            )
            wrapped_by_provider[provider_name] = wrapped
        return wrapped(prompt, effective, **kwargs)

    return _call


def ensure_model_provider_ready(
    model_name: str,
    *,
    registry: ServiceRegistry | None = None,
) -> None:
    """Fail before the model loop when the selected model cannot be called."""

    reg = registry if registry is not None else get_registry()
    mid = str(model_name or "").strip()
    if not mid:
        raise ModelProviderError("model_provider_not_found", "Model id is blank.")
    reg.get_available_llm_service_for_model(mid)


def _negotiate_streaming_kwargs(
    kwargs: Mapping[str, Any],
    *,
    streaming_supported: bool,
) -> dict[str, Any]:
    """Downgrade requested streaming when the resolved provider cannot stream.

    Caller-owned ``LlmCallOptions`` objects are not mutated. Legacy ``streaming``
    / ``stream`` kwargs are removed so they cannot re-enable streaming downstream.
    """
    call_kwargs = dict(kwargs)
    if streaming_supported:
        return call_kwargs
    requested = extract_streaming_requested(
        kwargs=call_kwargs,
        call_options=call_kwargs.get("call_options"),
    )
    if not requested:
        return call_kwargs
    call_kwargs.pop("streaming", None)
    call_kwargs.pop("stream", None)
    call_opts = call_kwargs.get("call_options")
    if isinstance(call_opts, LlmCallOptions) and call_opts.streaming:
        call_kwargs["call_options"] = replace(call_opts, streaming=False)
    return call_kwargs
