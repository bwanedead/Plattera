from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class RecoverableTurnFailure(RuntimeError):
    """A model turn failed before emitting a usable action, but the run can continue."""

    def __init__(self, failure_record: Mapping[str, Any]) -> None:
        self.failure_record = dict(failure_record)
        reason = str(self.failure_record.get("reason_code") or "recoverable_turn_failure")
        detail = str(self.failure_record.get("provider_error") or self.failure_record.get("message") or reason)
        super().__init__(detail)


def is_recoverable_output_failure(
    *,
    reason_code: str,
    raw_response: Any,
    raw_response_text: str,
) -> bool:
    """Return true for provider output failures that should become a retryable turn.

    This deliberately excludes safety/content-filter refusals. It targets cases where
    the model call reached the provider but produced no usable action-plan text due
    to output truncation or empty output.
    """

    finish_reason = ""
    provider_error = ""
    success = None
    if isinstance(raw_response, Mapping):
        finish_reason = str(raw_response.get("finish_reason") or "").strip().lower()
        provider_error = str(raw_response.get("error") or "").strip().lower()
        success = raw_response.get("success")

    text = str(raw_response_text or "").strip().lower()
    combined = " ".join(part for part in (finish_reason, provider_error, text) if part)

    if finish_reason == "content_filter" or "content_filter" in combined:
        return False
    if finish_reason == "length" or "finish_reason: length" in combined:
        return True
    if "truncated response" in combined or "token limit" in combined:
        return True
    if "empty text response" in combined:
        return True
    if reason_code == "invalid_model_action_json":
        return False
    if reason_code == "model_call_failed" and success is False and not text and not provider_error:
        return True
    return False
