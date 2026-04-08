"""Action-plan parsing for kernel LLM responses.

Single source of truth for all parsing, coercion, and canonical validation of
model-emitted action-plan payloads. HITL field validation delegates to
``runtime/hitl/request_shape.py`` — no local duplication of those rules.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ..hitl.request_shape import normalize_hitl_request, validate_hitl_consumed_prompt_ids
from .contracts import ActionPlan

_ALLOWED_ACTION_PLAN_KEYS = {
    "action_type",
    "action_inputs",
    "idempotency_key",
    "skip_execution",
    "wait_for_human",
    "complete_run",
    "rationale",
    "state_patch",
    "continuity_journal_entry",
    "operator_progress_message",
    "hitl_request",
    "hitl_consumed_prompt_ids",
}


class ModelActionParseError(ValueError):
    """Raised when the model output cannot be mechanically parsed into an action plan."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


# Allowlist: only these reason codes indicate failures the LLM can fix by reformatting.
# Provider/transport codes (model_call_failed, model_caller_exception) are excluded.
_REPAIRABLE_REASON_CODES: frozenset[str] = frozenset({"invalid_model_action_json"})


def is_repairable_action_plan_error(reason_code: str) -> bool:
    """True only for LLM output-contract failures the model can fix by reformatting."""
    return reason_code in _REPAIRABLE_REASON_CODES


def parse_action_plan_response(
    raw_response: Mapping[str, Any] | str,
    *,
    available_tool_ids: tuple[str, ...],
) -> ActionPlan:
    """Parse and validate a raw model response into an ``ActionPlan``.

    Raises ``ModelActionParseError`` on any structural or canonical validation failure.
    """
    text = _extract_text(raw_response)
    try:
        payload = json.loads(text)
    except Exception as exc:
        raise ModelActionParseError("invalid_model_action_json", "model output was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ModelActionParseError("invalid_model_action_json", "model output must be a JSON object")

    unknown_keys = sorted(set(payload.keys()) - _ALLOWED_ACTION_PLAN_KEYS)
    if unknown_keys:
        raise ModelActionParseError(
            "invalid_model_action_json",
            f"unexpected action plan keys: {', '.join(unknown_keys)}",
        )

    action_type = _optional_text(payload.get("action_type"))
    action_inputs = payload.get("action_inputs")
    if action_inputs is None:
        action_inputs = {}
    if not isinstance(action_inputs, Mapping):
        raise ModelActionParseError("invalid_model_action_json", "action_inputs must be an object")

    complete_run = _require_json_bool(payload, "complete_run")
    wait_for_human = _require_json_bool(payload, "wait_for_human")
    skip_execution = _require_json_bool(payload, "skip_execution")

    if complete_run and wait_for_human:
        raise ModelActionParseError("invalid_model_action_json", "complete_run and wait_for_human are mutually exclusive")

    if complete_run and payload.get("hitl_request") is not None:
        raise ModelActionParseError("invalid_model_action_json", "complete_run and hitl_request are mutually exclusive")

    hitl_raw = payload.get("hitl_request")
    if hitl_raw is None:
        hitl_out: dict[str, Any] | None = None
    elif isinstance(hitl_raw, dict):
        hitl_out = dict(hitl_raw)
    else:
        raise ModelActionParseError("invalid_model_action_json", "hitl_request must be a JSON object or null")

    if wait_for_human and hitl_out is None:
        raise ModelActionParseError(
            "invalid_model_action_json",
            "wait_for_human requires a non-null hitl_request object",
        )

    if hitl_out is not None:
        try:
            normalize_hitl_request(hitl_out, iteration=0)
        except ValueError as exc:
            raise ModelActionParseError(
                "invalid_model_action_json",
                f"hitl_request failed canonical validation: {exc}",
            ) from exc

    cons_raw = payload.get("hitl_consumed_prompt_ids")
    try:
        consumed_out = validate_hitl_consumed_prompt_ids(cons_raw)
    except ValueError as exc:
        raise ModelActionParseError(
            "invalid_model_action_json",
            f"hitl_consumed_prompt_ids failed canonical validation: {exc}",
        ) from exc

    if not complete_run and not wait_for_human:
        if not action_type:
            raise ModelActionParseError("invalid_model_action_json", "action_type is required unless completing or waiting")
        if available_tool_ids and action_type not in available_tool_ids:
            raise ModelActionParseError("invalid_model_action_json", f"unknown action_type: {action_type}")

    state_patch_raw = payload.get("state_patch")
    if state_patch_raw is None:
        state_patch_out: dict[str, Any] | None = None
    elif isinstance(state_patch_raw, dict):
        state_patch_out = dict(state_patch_raw)
    else:
        raise ModelActionParseError(
            "invalid_model_action_json",
            "state_patch must be a JSON object or null",
        )

    cje_raw = payload.get("continuity_journal_entry")
    if cje_raw is None:
        raise ModelActionParseError(
            "invalid_model_action_json",
            "continuity_journal_entry is required and must be a non-empty JSON object",
        )
    if not isinstance(cje_raw, dict):
        raise ModelActionParseError(
            "invalid_model_action_json",
            "continuity_journal_entry must be a JSON object",
        )
    cje_out = dict(cje_raw)
    if len(cje_out) < 1:
        raise ModelActionParseError(
            "invalid_model_action_json",
            "continuity_journal_entry must be a non-empty JSON object",
        )

    opm_raw = payload.get("operator_progress_message")
    if opm_raw is None:
        opm_out: str | None = None
    elif isinstance(opm_raw, str):
        opm_out = _optional_text(opm_raw)
    else:
        raise ModelActionParseError(
            "invalid_model_action_json",
            "operator_progress_message must be a string or null",
        )

    return ActionPlan(
        action_type=action_type or None,
        action_inputs=dict(action_inputs),
        idempotency_key=_optional_text(payload.get("idempotency_key")) or "",
        skip_execution=skip_execution,
        wait_for_human=wait_for_human,
        complete_run=complete_run,
        hitl_request=hitl_out,
        hitl_consumed_prompt_ids=consumed_out,
        rationale=_optional_text(payload.get("rationale")),
        state_patch=state_patch_out,
        continuity_journal_entry=cje_out,
        operator_progress_message=opm_out,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_text(raw_response: Mapping[str, Any] | str) -> str:
    if isinstance(raw_response, str):
        text = raw_response.strip()
        if not text:
            raise ModelActionParseError("invalid_model_action_json", "model output was empty")
        return text
    if raw_response.get("success") is False:
        raise ModelActionParseError(
            "model_call_failed",
            str(raw_response.get("error") or "model caller reported failure"),
        )
    for key in ("text", "content", "output_text"):
        value = raw_response.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ModelActionParseError("invalid_model_action_json", "model caller did not return text")


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_json_bool(payload: Mapping[str, Any], key: str) -> bool:
    if key not in payload:
        raise ModelActionParseError("invalid_model_action_json", f"{key} is required and must be a boolean")
    value = payload.get(key)
    if type(value) is not bool:
        raise ModelActionParseError("invalid_model_action_json", f"{key} must be a JSON boolean")
    return value
