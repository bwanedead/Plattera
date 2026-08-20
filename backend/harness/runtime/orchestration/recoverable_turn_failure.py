from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .action_plan_parser import ModelActionParseError
from .repair_lane import (
    REPAIR_METHOD_MODEL,
    RepairAttempt,
    count_attempted_actions_in_text,
    extract_audit_text,
)

POST_REPAIR_PARSE_FAILURE_STAGE = "post_repair_parse"
QUEUED_TURN_RECOVERY_DISPOSITION = "queued_turn_recovery"

PARSE_ERROR_PREVIEW_CHARS = 240
PROVIDER_IDENTITY_MAX_CHARS = 80
TRANSFORMATION_MAX_CHARS = 64
MAX_REPAIR_TRANSFORMATIONS = 8
MAX_USAGE_TOKENS = 100_000_000
FAILURE_RECORD_COMPACT_JSON_CAP = 1024

CORE_FAILURE_RECORD_KEYS = (
    "reason_code",
    "failure_stage",
    "iteration",
    "prompt_mode",
    "repair_method",
    "repair_parse_reason_code",
    "original_action_count_attempted",
)

# First listed is dropped first when the compact-JSON cap is exceeded.
_OPTIONAL_FIELD_OMIT_ORDER = (
    "repair_transformations",
    "api_model",
    "provider_model",
    "provider_reasoning_tokens",
    "provider_prompt_tokens",
    "provider_completion_tokens",
    "provider_total_tokens",
    "provider_finish_reason",
    "parse_error_preview",
    "parse_error_char_count",
)


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


def is_recoverable_post_repair_contract_failure(
    *,
    original_reason_code: str,
    repair_method: str,
    repair_parse_ok: bool,
    repair_parse_reason_code: str | None,
) -> bool:
    """True when a normal provider call stayed contract-invalid after one model repair."""

    if original_reason_code != "invalid_model_action_json":
        return False
    if repair_method != REPAIR_METHOD_MODEL:
        return False
    if repair_parse_ok:
        return False
    return repair_parse_reason_code == "invalid_model_action_json"


def recovery_disposition_for_audit(
    *,
    parse_ok: bool,
    parse_reason_code: str | None,
    repair_records: list[dict[str, Any]] | None,
) -> str | None:
    if parse_ok or not repair_records:
        return None
    row = repair_records[0]
    if not isinstance(row, Mapping):
        return None
    if not is_recoverable_post_repair_contract_failure(
        original_reason_code=str(parse_reason_code or ""),
        repair_method=str(row.get("repair_method") or ""),
        repair_parse_ok=bool(row.get("repair_parse_ok")),
        repair_parse_reason_code=(
            str(row.get("repair_parse_reason_code"))
            if row.get("repair_parse_reason_code") is not None
            else None
        ),
    ):
        return None
    return QUEUED_TURN_RECOVERY_DISPOSITION


def compact_failure_record_size(record: Mapping[str, Any]) -> int:
    """Compact JSON size of a durable failure record. Raises if the record is not JSON-native."""
    return len(
        json.dumps(dict(record), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    )


def build_post_repair_contract_failure_record(
    *,
    original_exc: ModelActionParseError,
    repair_attempt: RepairAttempt,
    iteration: int,
    prompt_mode: str,
    raw_response: Any,
) -> dict[str, Any]:
    repair_error = repair_attempt.repair_error
    repair_reason = (
        repair_error.reason_code if repair_error is not None else repair_attempt.repair_parse_reason_code
    )
    iteration_n = _nonneg_int(iteration)
    record: dict[str, Any] = {
        "reason_code": "invalid_model_action_json",
        "failure_stage": POST_REPAIR_PARSE_FAILURE_STAGE,
        "iteration": 0 if iteration_n is None else iteration_n,
        "prompt_mode": _core_token(prompt_mode, fallback="full_choose_action"),
        "repair_method": _core_token(repair_attempt.repair_method, fallback=REPAIR_METHOD_MODEL),
        "repair_parse_reason_code": _core_token(repair_reason, fallback="invalid_model_action_json"),
        "original_action_count_attempted": _attempted_action_count(raw_response),
    }
    preview, char_count = _parse_error_preview(str(original_exc))
    if preview:
        record["parse_error_preview"] = preview
        record["parse_error_char_count"] = char_count
    transformations = _bounded_transformations(repair_attempt.repair_transformations)
    if transformations:
        record["repair_transformations"] = transformations
    record.update(_provider_metadata_fields(raw_response))
    return _enforce_compact_json_cap(record)


def post_repair_failure(
    *,
    original_exc: ModelActionParseError,
    repair_attempt: RepairAttempt,
    iteration: int,
    prompt_mode: str,
    raw_response: Any,
) -> BaseException:
    repair_error = repair_attempt.repair_error
    assert repair_error is not None
    if is_recoverable_post_repair_contract_failure(
        original_reason_code=original_exc.reason_code,
        repair_method=repair_attempt.repair_method,
        repair_parse_ok=repair_attempt.repair_parse_ok,
        repair_parse_reason_code=repair_error.reason_code,
    ):
        return RecoverableTurnFailure(
            build_post_repair_contract_failure_record(
                original_exc=original_exc,
                repair_attempt=repair_attempt,
                iteration=iteration,
                prompt_mode=prompt_mode,
                raw_response=raw_response,
            )
        )
    return repair_error


def _parse_error_preview(detail: str) -> tuple[str, int]:
    return detail[:PARSE_ERROR_PREVIEW_CHARS], len(detail)


def _core_token(value: Any, *, fallback: str) -> str:
    bounded = _bounded_identity(value, max_chars=PROVIDER_IDENTITY_MAX_CHARS)
    return bounded if bounded is not None else fallback


def _attempted_action_count(raw_response: Any) -> int | None:
    return _nonneg_int(count_attempted_actions_in_text(extract_audit_text(raw_response)))


def _bounded_identity(value: Any, *, max_chars: int) -> str | None:
    if type(value) is not str:
        return None
    text = value.strip()
    if not text or len(text) > max_chars:
        return None
    return text


def _nonneg_int(value: Any) -> int | None:
    if type(value) is not int:
        return None
    if value < 0 or value > MAX_USAGE_TOKENS:
        return None
    return value


def _bounded_transformations(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    out: list[str] = []
    for item in values[:MAX_REPAIR_TRANSFORMATIONS]:
        bounded = _bounded_identity(item, max_chars=TRANSFORMATION_MAX_CHARS)
        if bounded is None:
            continue
        out.append(bounded)
    return out


def _provider_metadata_fields(raw_response: Any) -> dict[str, Any]:
    if not isinstance(raw_response, Mapping):
        return {}
    fields: dict[str, Any] = {}
    finish = _bounded_identity(raw_response.get("finish_reason"), max_chars=PROVIDER_IDENTITY_MAX_CHARS)
    if finish is not None:
        fields["provider_finish_reason"] = finish
    model = _bounded_identity(
        raw_response.get("provider_model") if type(raw_response.get("provider_model")) is str else raw_response.get("model"),
        max_chars=PROVIDER_IDENTITY_MAX_CHARS,
    )
    if model is not None:
        fields["provider_model"] = model
    api_model = _bounded_identity(raw_response.get("api_model"), max_chars=PROVIDER_IDENTITY_MAX_CHARS)
    if api_model is not None:
        fields["api_model"] = api_model
    usage = raw_response.get("usage")
    usage_map = usage if isinstance(usage, Mapping) else {}
    tokens = {
        "provider_prompt_tokens": _nonneg_int(usage_map.get("prompt_tokens")),
        "provider_completion_tokens": _nonneg_int(usage_map.get("completion_tokens")),
        "provider_reasoning_tokens": _nonneg_int(usage_map.get("reasoning_tokens")),
        "provider_total_tokens": _nonneg_int(usage_map.get("total_tokens")),
    }
    for key, value in tokens.items():
        if value is not None:
            fields[key] = value
    return fields


def _enforce_compact_json_cap(record: dict[str, Any]) -> dict[str, Any]:
    out = dict(record)
    for key in _OPTIONAL_FIELD_OMIT_ORDER:
        if compact_failure_record_size(out) <= FAILURE_RECORD_COMPACT_JSON_CAP:
            return out
        out.pop(key, None)
    return {key: out[key] for key in CORE_FAILURE_RECORD_KEYS if key in out}
