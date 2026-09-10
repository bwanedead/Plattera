"""Provider-neutral bounded retries for harness model calls."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from typing import Any

from services.llm.provider_request_failure import (
    DISABLE_SDK_RETRIES_OPTION,
    PROVIDER_REQUEST_FAILURE_KEY,
)

MAX_PROVIDER_ATTEMPTS = 3
MAX_PROVIDER_RETRIES = MAX_PROVIDER_ATTEMPTS - 1
PROVIDER_CALL_DEADLINE_SECONDS = 300.0
DEFAULT_RETRY_DELAYS_SECONDS = (1.0, 2.0)
UNCLASSIFIED_PROVIDER_EXCEPTION_PUBLIC_MESSAGE = "Unclassified provider caller exception"


class UnclassifiedProviderCallerError(Exception):
    """Sanitized public carrier for unknown provider-call exceptions.

    ``__str__`` and ``public_error_detail`` are the only public projection.
    The original exception is retained as ``original_exception`` / ``__cause__``.
    """

    def __init__(
        self,
        original: BaseException,
        *,
        retry_metadata: Mapping[str, Any],
    ) -> None:
        super().__init__(UNCLASSIFIED_PROVIDER_EXCEPTION_PUBLIC_MESSAGE)
        self.original_exception = original
        self.provider_retry_metadata = dict(retry_metadata)
        self.public_error_detail = UNCLASSIFIED_PROVIDER_EXCEPTION_PUBLIC_MESSAGE
        self.reason_code = "model_caller_exception"

    def __str__(self) -> str:
        return UNCLASSIFIED_PROVIDER_EXCEPTION_PUBLIC_MESSAGE


def public_exception_detail(exc: BaseException) -> str:
    """Return the sanitized public message when one was attached."""

    public = getattr(exc, "public_error_detail", None)
    if isinstance(public, str) and public.strip():
        return public.strip()
    return str(exc)


def call_with_provider_retries(
    caller: Callable[..., Mapping[str, Any] | str],
    prompt: str,
    model: str,
    *,
    kwargs: Mapping[str, Any],
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Mapping[str, Any] | str:
    """Call one provider under the harness-wide attempt/deadline policy.

    ``timeout_configured_seconds`` records the first attempt's maximum transport
    timeout. Providers may preserve stricter client timeout dimensions. Later
    attempts receive the smaller remaining logical-call budget.
    """

    started = clock()
    deadline = started + PROVIDER_CALL_DEADLINE_SECONDS
    attempts_started = 0
    configured_timeout = _configured_timeout_seconds(kwargs.get("timeout"))
    last_failure: Mapping[str, Any] | None = None
    last_result: Mapping[str, Any] | None = None

    while attempts_started < MAX_PROVIDER_ATTEMPTS:
        remaining = deadline - clock()
        if remaining <= 0:
            break
        attempt_timeout = min(configured_timeout, remaining)
        attempt_kwargs = dict(kwargs)
        attempt_kwargs["timeout"] = attempt_timeout
        attempt_kwargs[DISABLE_SDK_RETRIES_OPTION] = True
        attempts_started += 1
        try:
            raw = caller(prompt, model, **attempt_kwargs)
        except UnclassifiedProviderCallerError:
            raise
        except Exception as exc:
            # Unknown exceptions stay non-retryable. Keep the original for
            # chaining/debug, but raise a sanitized public projection.
            raise UnclassifiedProviderCallerError(
                exc,
                retry_metadata={
                    "max_retries_configured": MAX_PROVIDER_RETRIES,
                    "retry_count_observed": max(0, attempts_started - 1),
                    "timeout_configured_seconds": configured_timeout,
                    "failure_classification": "terminal_unclassified_exception",
                },
            ) from exc

        if clock() >= deadline:
            return _finalize_request_failure(
                dict(raw) if isinstance(raw, Mapping) else {"model": model},
                failure={"category": "logical_deadline"},
                exhausted=True,
                retry_count=max(0, attempts_started - 1),
                configured_timeout=configured_timeout,
            )
        if not isinstance(raw, Mapping):
            return raw
        result = dict(raw)
        failure_raw = result.pop(PROVIDER_REQUEST_FAILURE_KEY, None)
        if not isinstance(failure_raw, Mapping):
            return _with_retry_metadata(
                result,
                retry_count=max(0, attempts_started - 1),
                configured_timeout=configured_timeout,
            )

        failure = dict(failure_raw)
        last_failure = failure
        last_result = result
        retryable = failure.get("retryable") is True
        if not retryable:
            return _finalize_request_failure(
                result,
                failure=failure,
                exhausted=False,
                retry_count=max(0, attempts_started - 1),
                configured_timeout=configured_timeout,
            )
        if attempts_started >= MAX_PROVIDER_ATTEMPTS:
            break

        delay = _retry_delay(failure, retry_index=attempts_started - 1)
        remaining = deadline - clock()
        # Never retry earlier than a valid Retry-After instruction. If honoring
        # it consumes the deadline, the logical call is exhausted.
        if delay >= remaining:
            break
        sleep(delay)

    base = dict(last_result or {})
    return _finalize_request_failure(
        base,
        failure=last_failure or {"category": "logical_deadline"},
        exhausted=True,
        retry_count=max(0, attempts_started - 1),
        configured_timeout=configured_timeout,
    )


def _configured_timeout_seconds(raw: Any) -> float:
    if type(raw) in (int, float):
        try:
            value = float(raw)
        except (TypeError, ValueError, OverflowError):
            value = 0.0
        if math.isfinite(value) and value > 0:
            return min(value, PROVIDER_CALL_DEADLINE_SECONDS)
    read_timeout = getattr(raw, "read", None)
    if type(read_timeout) in (int, float):
        try:
            value = float(read_timeout)
        except (TypeError, ValueError, OverflowError):
            value = 0.0
        if math.isfinite(value) and value > 0:
            return min(value, PROVIDER_CALL_DEADLINE_SECONDS)
    return PROVIDER_CALL_DEADLINE_SECONDS


def _retry_delay(failure: Mapping[str, Any], *, retry_index: int) -> float:
    retry_after = failure.get("retry_after_seconds")
    if type(retry_after) in (int, float):
        try:
            value = float(retry_after)
        except (TypeError, ValueError, OverflowError):
            value = -1.0
        if math.isfinite(value) and value >= 0:
            return value
    return DEFAULT_RETRY_DELAYS_SECONDS[retry_index]


def _with_retry_metadata(
    result: dict[str, Any],
    *,
    retry_count: int,
    configured_timeout: float,
) -> dict[str, Any]:
    out = dict(result)
    out["max_retries_configured"] = MAX_PROVIDER_RETRIES
    out["retry_count_observed"] = retry_count
    out["timeout_configured_seconds"] = configured_timeout
    return out


def _finalize_request_failure(
    result: dict[str, Any],
    *,
    failure: Mapping[str, Any],
    exhausted: bool,
    retry_count: int,
    configured_timeout: float,
) -> dict[str, Any]:
    # Rebuild from an allowlist so exception/body/header content accidentally
    # added by an adapter cannot cross the harness failure boundary.
    out = _with_retry_metadata(
        {
            "success": False,
            "error": (
                "Provider transient request failure exhausted"
                if exhausted
                else "Provider terminal request failure"
            ),
            "text": None,
            "tokens_used": None,
            "model": result.get("model"),
            "provider_model": result.get("provider_model"),
            "api_model": result.get("api_model"),
            "finish_reason": "provider_request_failure",
            "char_count": 0,
            "response_id": None,
            "usage": None,
        },
        retry_count=retry_count,
        configured_timeout=configured_timeout,
    )
    out.update(
        {
            "failure_classification": (
                "transient_exhausted" if exhausted else "terminal_provider_failure"
            ),
        }
    )
    status = failure.get("http_status")
    out["http_status"] = status if type(status) is int else None
    # Internal retryability and Retry-After data never leave the retry owner.
    return out


__all__ = [
    "DEFAULT_RETRY_DELAYS_SECONDS",
    "MAX_PROVIDER_ATTEMPTS",
    "MAX_PROVIDER_RETRIES",
    "PROVIDER_CALL_DEADLINE_SECONDS",
    "UNCLASSIFIED_PROVIDER_EXCEPTION_PUBLIC_MESSAGE",
    "UnclassifiedProviderCallerError",
    "call_with_provider_retries",
    "public_exception_detail",
]
