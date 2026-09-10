"""Deterministic tests for the harness-wide provider retry rail."""

from __future__ import annotations

from typing import Any

import pytest

from harness.runtime.llm.provider_retry import (
    MAX_PROVIDER_RETRIES,
    PROVIDER_CALL_DEADLINE_SECONDS,
    UNCLASSIFIED_PROVIDER_EXCEPTION_PUBLIC_MESSAGE,
    UnclassifiedProviderCallerError,
    call_with_provider_retries,
    public_exception_detail,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _failure(
    *,
    retryable: bool = True,
    status: int | None = 500,
    retry_after: Any = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "category": "http_status",
        "retryable": retryable,
        "http_status": status,
    }
    if retry_after is not None:
        metadata["retry_after_seconds"] = retry_after
    return {
        "success": False,
        "error": "adapter-safe-error",
        "text": None,
        "model": "model-a",
        "provider_request_failure": metadata,
    }


def test_transient_failure_then_success_retries_once() -> None:
    clock = _Clock()
    outcomes = [_failure(), {"success": True, "text": "ok", "model": "model-a"}]
    timeouts: list[float] = []

    def caller(prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
        timeouts.append(kwargs["timeout"])
        return outcomes.pop(0)

    result = call_with_provider_retries(
        caller,
        "same prompt",
        "model-a",
        kwargs={},
        clock=clock,
        sleep=clock.sleep,
    )
    assert result["success"] is True
    assert result["max_retries_configured"] == MAX_PROVIDER_RETRIES
    assert result["retry_count_observed"] == 1
    assert result["timeout_configured_seconds"] == PROVIDER_CALL_DEADLINE_SECONDS
    assert clock.sleeps == [1.0]
    assert timeouts == [300.0, 299.0]


def test_repeated_transient_failures_stop_at_three_total_attempts() -> None:
    clock = _Clock()
    calls = 0

    def caller(prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return _failure(status=503)

    result = call_with_provider_retries(
        caller,
        "p",
        "model-a",
        kwargs={},
        clock=clock,
        sleep=clock.sleep,
    )
    assert calls == 3
    assert clock.sleeps == [1.0, 2.0]
    assert result["success"] is False
    assert result["failure_classification"] == "transient_exhausted"
    assert result["http_status"] == 503
    assert result["retry_count_observed"] == 2


def test_deadline_prevents_another_attempt_and_caps_request_timeout() -> None:
    clock = _Clock()
    timeouts: list[float] = []
    calls = 0

    def caller(prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        timeouts.append(kwargs["timeout"])
        clock.now += 299.5
        return _failure(status=500)

    result = call_with_provider_retries(
        caller,
        "p",
        "model-a",
        kwargs={"timeout": 120.0},
        clock=clock,
        sleep=clock.sleep,
    )
    assert calls == 1
    assert timeouts == [120.0]
    assert clock.sleeps == []
    assert result["failure_classification"] == "transient_exhausted"
    assert result["retry_count_observed"] == 0
    assert result["timeout_configured_seconds"] == 120.0


def test_response_arriving_after_logical_deadline_is_exhausted() -> None:
    clock = _Clock()

    def caller(prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
        clock.now = 301.0
        return {"success": True, "text": "late", "model": model}

    result = call_with_provider_retries(
        caller,
        "p",
        "model-a",
        kwargs={},
        clock=clock,
        sleep=clock.sleep,
    )
    assert result["success"] is False
    assert result["failure_classification"] == "transient_exhausted"
    assert result["retry_count_observed"] == 0
    assert "late" not in str(result)


@pytest.mark.parametrize(
    ("retry_after", "expected_sleep"),
    [
        (7.0, 7.0),
        ("malformed", 1.0),
        (-1.0, 1.0),
        (10**400, 1.0),
    ],
)
def test_retry_after_valid_and_malformed_values(
    retry_after: Any,
    expected_sleep: float,
) -> None:
    clock = _Clock()
    outcomes = [
        _failure(retry_after=retry_after),
        {"success": True, "text": "ok", "model": "model-a"},
    ]

    result = call_with_provider_retries(
        lambda prompt, model, **kwargs: outcomes.pop(0),
        "p",
        "model-a",
        kwargs={},
        clock=clock,
        sleep=clock.sleep,
    )
    assert result["success"] is True
    assert clock.sleeps == [expected_sleep]


def test_retry_after_exceeding_remaining_budget_exhausts_without_retry() -> None:
    clock = _Clock()
    calls = 0

    def caller(prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return _failure(retry_after=301.0)

    result = call_with_provider_retries(
        caller,
        "p",
        "model-a",
        kwargs={},
        clock=clock,
        sleep=clock.sleep,
    )
    assert calls == 1
    assert result["failure_classification"] == "transient_exhausted"
    assert result["retry_count_observed"] == 0


def test_terminal_response_and_unknown_exception_receive_no_retry() -> None:
    clock = _Clock()
    terminal_calls = 0

    def terminal(prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal terminal_calls
        terminal_calls += 1
        return _failure(retryable=False, status=401)

    terminal_result = call_with_provider_retries(
        terminal,
        "p",
        "model-a",
        kwargs={},
        clock=clock,
        sleep=clock.sleep,
    )
    assert terminal_calls == 1
    assert terminal_result["failure_classification"] == "terminal_provider_failure"
    assert terminal_result["http_status"] == 401

    unknown_calls = 0

    def unknown(prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal unknown_calls
        unknown_calls += 1
        raise RuntimeError("secret exception body")

    with pytest.raises(UnclassifiedProviderCallerError) as raised:
        call_with_provider_retries(
            unknown,
            "p",
            "model-a",
            kwargs={},
            clock=clock,
            sleep=clock.sleep,
        )
    assert unknown_calls == 1
    assert str(raised.value) == UNCLASSIFIED_PROVIDER_EXCEPTION_PUBLIC_MESSAGE
    assert public_exception_detail(raised.value) == UNCLASSIFIED_PROVIDER_EXCEPTION_PUBLIC_MESSAGE
    assert "secret exception body" not in str(raised.value)
    assert isinstance(raised.value.original_exception, RuntimeError)
    assert str(raised.value.original_exception) == "secret exception body"
    assert raised.value.__cause__ is raised.value.original_exception
    assert raised.value.provider_retry_metadata == {
        "max_retries_configured": 2,
        "retry_count_observed": 0,
        "timeout_configured_seconds": 300.0,
        "failure_classification": "terminal_unclassified_exception",
    }


def test_model_response_failures_are_not_retried() -> None:
    clock = _Clock()
    for finish_reason in ("content_filter", "length", "invalid_json"):
        calls = 0

        def caller(prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {
                "success": False,
                "error": "existing outcome owner",
                "finish_reason": finish_reason,
                "text": "partial",
                "model": model,
            }

        result = call_with_provider_retries(
            caller,
            "p",
            "model-a",
            kwargs={},
            clock=clock,
            sleep=clock.sleep,
        )
        assert calls == 1
        assert result["retry_count_observed"] == 0
        assert result["finish_reason"] == finish_reason
