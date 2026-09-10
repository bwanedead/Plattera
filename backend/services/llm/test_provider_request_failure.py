"""Structured OpenAI-compatible SDK failure projection tests."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime

import httpx
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
)

from services.llm.provider_request_failure import (
    RETRYABLE_HTTP_STATUSES,
    bound_openai_request_timeout,
    project_openai_sdk_request_failure,
)


def _response(status: int, *, retry_after: str | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://provider.invalid/v1/responses")
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return httpx.Response(status, request=request, headers=headers)


def _status_error(status: int, *, retry_after: str | None = None) -> APIStatusError:
    return APIStatusError(
        "sensitive response body",
        response=_response(status, retry_after=retry_after),
        body={"secret": "must-not-cross"},
    )


@pytest.mark.parametrize("status", sorted(RETRYABLE_HTTP_STATUSES))
def test_eligible_http_statuses_are_retryable(status: int) -> None:
    projected = project_openai_sdk_request_failure(_status_error(status))
    assert projected == {
        "category": "http_status",
        "retryable": True,
        "http_status": status,
    }


def test_connection_and_timeout_are_retryable() -> None:
    request = httpx.Request("POST", "https://provider.invalid/v1/responses")
    connection = project_openai_sdk_request_failure(APIConnectionError(request=request))
    timeout = project_openai_sdk_request_failure(APITimeoutError(request))
    assert connection == {"category": "connection_failure", "retryable": True}
    assert timeout == {"category": "request_timeout", "retryable": True}


@pytest.mark.parametrize(
    "exc",
    [
        AuthenticationError(
            "secret auth body",
            response=_response(401),
            body={"secret": "auth"},
        ),
        PermissionDeniedError(
            "secret permission body",
            response=_response(403),
            body={"secret": "permission"},
        ),
        BadRequestError(
            "secret invalid body",
            response=_response(400),
            body={"secret": "invalid"},
        ),
        _status_error(409),
    ],
)
def test_terminal_sdk_exceptions_are_not_retryable(exc: BaseException) -> None:
    projected = project_openai_sdk_request_failure(exc)
    assert projected is not None
    assert projected["retryable"] is False
    assert "secret" not in str(projected)


def test_unknown_exception_is_not_projected_as_provider_failure() -> None:
    assert project_openai_sdk_request_failure(RuntimeError("secret unknown body")) is None


def test_retry_after_delta_date_and_malformed() -> None:
    delta = project_openai_sdk_request_failure(_status_error(429, retry_after="7"))
    assert delta["retry_after_seconds"] == 7.0

    now = 1_800_000_000.0
    future = datetime.fromtimestamp(now + 11, tz=timezone.utc)
    dated = project_openai_sdk_request_failure(
        _status_error(503, retry_after=format_datetime(future, usegmt=True)),
        wall_clock=lambda: now,
    )
    assert dated["retry_after_seconds"] == 11.0

    malformed = project_openai_sdk_request_failure(
        _status_error(500, retry_after="not-a-delay")
    )
    assert "retry_after_seconds" not in malformed
    oversized = project_openai_sdk_request_failure(
        _status_error(500, retry_after="9" * 10_000)
    )
    assert "retry_after_seconds" not in oversized


def test_request_timeout_caps_dimensions_and_preserves_stricter_values() -> None:
    existing = httpx.Timeout(connect=5.0, read=600.0, write=20.0, pool=2.0)
    bounded = bound_openai_request_timeout(existing, 100.0)
    assert bounded.connect == 5.0
    assert bounded.read == 100.0
    assert bounded.write == 20.0
    assert bounded.pool == 2.0
