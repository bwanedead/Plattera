"""Sanitized provider-request failure projection for OpenAI-compatible SDKs."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any

try:
    from openai import APIConnectionError, APIStatusError, APITimeoutError
except ImportError:  # pragma: no cover - providers are unavailable too
    APIConnectionError = None  # type: ignore[assignment,misc]
    APIStatusError = None  # type: ignore[assignment,misc]
    APITimeoutError = None  # type: ignore[assignment,misc]

RETRYABLE_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
PROVIDER_REQUEST_FAILURE_KEY = "provider_request_failure"
DISABLE_SDK_RETRIES_OPTION = "_disable_sdk_retries"


def project_openai_sdk_request_failure(
    exc: BaseException,
    *,
    wall_clock: Callable[[], float] = time.time,
) -> dict[str, Any] | None:
    """Return bounded structured metadata without exception/body/header text."""

    if APITimeoutError is not None and isinstance(exc, APITimeoutError):
        return {"category": "request_timeout", "retryable": True}
    if APIConnectionError is not None and isinstance(exc, APIConnectionError):
        return {"category": "connection_failure", "retryable": True}
    if APIStatusError is not None and isinstance(exc, APIStatusError):
        status_raw = getattr(exc, "status_code", None)
        status = (
            status_raw
            if type(status_raw) is int and 100 <= status_raw <= 599
            else None
        )
        retryable = status in RETRYABLE_HTTP_STATUSES
        out: dict[str, Any] = {
            "category": "http_status",
            "retryable": retryable,
            "http_status": status,
        }
        if retryable:
            retry_after = _retry_after_seconds(exc, wall_clock=wall_clock)
            if retry_after is not None:
                out["retry_after_seconds"] = retry_after
        return out
    return None


def bound_openai_request_timeout(existing_timeout: Any, requested_cap: Any) -> Any:
    """Cap every SDK timeout dimension while preserving stricter dimensions."""

    cap = _positive_finite_float(requested_cap)
    if cap is None:
        return existing_timeout
    existing_scalar = _positive_finite_float(existing_timeout)
    if existing_scalar is not None:
        return min(cap, existing_scalar)
    dimensions = ("connect", "read", "write", "pool")
    if existing_timeout is not None and all(
        hasattr(existing_timeout, name) for name in dimensions
    ):
        values = {
            name: min(cap, _positive_finite_float(getattr(existing_timeout, name)) or cap)
            for name in dimensions
        }
        try:
            return type(existing_timeout)(**values)
        except (TypeError, ValueError):
            return cap
    return cap


def _retry_after_seconds(
    exc: BaseException,
    *,
    wall_clock: Callable[[], float],
) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not isinstance(headers, Mapping) and not hasattr(headers, "get"):
        return None
    raw = headers.get("retry-after")
    if raw is None:
        raw = headers.get("Retry-After")
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None
    if value.isdigit():
        try:
            delay = float(int(value))
        except (ValueError, OverflowError):
            return None
        return delay if math.isfinite(delay) else None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delay = parsed.timestamp() - wall_clock()
    if not math.isfinite(delay):
        return None
    return max(0.0, delay)


def _positive_finite_float(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


__all__ = [
    "DISABLE_SDK_RETRIES_OPTION",
    "PROVIDER_REQUEST_FAILURE_KEY",
    "RETRYABLE_HTTP_STATUSES",
    "bound_openai_request_timeout",
    "project_openai_sdk_request_failure",
]
