"""Tests for generic model failure classification."""

from __future__ import annotations

from harness.runtime.model_failure_classifier import (
    bound_error_excerpt,
    classify_model_failure,
)


def test_classify_insufficient_quota() -> None:
    result = classify_model_failure(
        raw_response={"success": False, "error": "insufficient_quota", "status_code": 429},
    )
    assert result.reason_code == "api_quota_exhausted"
    assert result.resumable is True


def test_classify_connection_error() -> None:
    result = classify_model_failure(raw_response={"success": False, "error": "Connection error."})
    assert result.reason_code == "model_connection_interrupted"
    assert result.resumable is True


def test_classify_rate_limit_retryable() -> None:
    result = classify_model_failure(
        raw_response={"success": False, "error": "Rate limit exceeded; retry after 20s"},
    )
    assert result.reason_code == "model_rate_limited_retryable"
    assert result.resumable is True


def test_classify_bare_http_429_as_rate_limit_not_quota() -> None:
    result = classify_model_failure(
        raw_response={"success": False, "error": "HTTP 429", "status_code": 429},
    )
    assert result.reason_code == "model_rate_limited_retryable"
    assert result.resumable is True


def test_classify_429_with_rate_limit_text_as_rate_limit() -> None:
    result = classify_model_failure(
        raw_response={
            "success": False,
            "error": "rate limit exceeded; retry after 20s",
            "status_code": 429,
        },
    )
    assert result.reason_code == "model_rate_limited_retryable"


def test_classify_fallback_model_call_failed() -> None:
    result = classify_model_failure(raw_response={"success": False, "error": "unknown provider fault"})
    assert result.reason_code == "model_call_failed"
    assert result.resumable is False


def test_bound_error_excerpt_redacts_secrets() -> None:
    text = bound_error_excerpt("failure sk-abcdefghijklmnopqrstuvwxyz1234567890")
    assert "sk-" not in text
    assert "[redacted]" in text
