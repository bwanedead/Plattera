from __future__ import annotations

from typing import Any

import pytest

from harness.runtime.runner.runner import _stable_reason_code_from_exception


class _ReasonedError(RuntimeError):
    def __init__(
        self,
        message: str = "failed",
        *,
        reason_code: Any = None,
        failure_record: dict[str, Any] | None = None,
        include_reason_code: bool = True,
    ) -> None:
        super().__init__(message)
        if include_reason_code:
            self.reason_code = reason_code
        if failure_record is not None:
            self.failure_record = failure_record


def test_stable_reason_code_strips_direct_string() -> None:
    exc = _ReasonedError(reason_code="  model_call_failed  ")
    assert _stable_reason_code_from_exception(exc) == "model_call_failed"


def test_stable_reason_code_rejects_whitespace_only_direct() -> None:
    exc = _ReasonedError(reason_code="   \n")
    assert _stable_reason_code_from_exception(exc) == "runner_exception"


@pytest.mark.parametrize("invalid", [True, False, 12, {"code": "model_call_failed"}, ["model_call_failed"]])
def test_stable_reason_code_rejects_invalid_direct_types(invalid: Any) -> None:
    exc = _ReasonedError(reason_code=invalid)
    assert _stable_reason_code_from_exception(exc) == "runner_exception"


def test_stable_reason_code_uses_nested_failure_record_when_direct_invalid() -> None:
    exc = _ReasonedError(
        reason_code=True,
        failure_record={"reason_code": "  model_call_failed  "},
    )
    assert _stable_reason_code_from_exception(exc) == "model_call_failed"


def test_stable_reason_code_nested_fallback_when_direct_absent() -> None:
    exc = _ReasonedError(
        include_reason_code=False,
        failure_record={"reason_code": "recoverable_turn_failure"},
    )
    assert _stable_reason_code_from_exception(exc) == "recoverable_turn_failure"


def test_stable_reason_code_generic_fallback_when_neither_valid() -> None:
    exc = _ReasonedError(
        reason_code="",
        failure_record={"reason_code": {"nested": True}},
    )
    assert _stable_reason_code_from_exception(exc) == "runner_exception"
    assert _stable_reason_code_from_exception(None) == "runner_exception"
    assert _stable_reason_code_from_exception(RuntimeError("boom")) == "runner_exception"
