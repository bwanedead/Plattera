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
from .continuity_journal_entry import normalize_continuity_journal_entry
from .contracts import ActionPlan
from .hydrate_next import (
    HydrateNextValidationError,
    normalize_hydrate_next,
    normalize_hydrate_next_reason,
)
from .user_message_action_plan_shape import (
    validate_user_message_consumed_ids,
    validate_user_message_defers,
)

_ALLOWED_ACTION_PLAN_KEYS = {
    "action_type", "action_inputs", "idempotency_key",
    "skip_execution", "wait_for_human", "complete_run",
    "rationale", "state_patch", "continuity_journal_entry",
    "operator_progress_message", "hitl_request", "hitl_consumed_prompt_ids",
    "user_message_consumed_ids", "user_message_defers",
    "hydrate_next", "hydrate_next_reason",
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


def _parse_error(message: str) -> ModelActionParseError:
    return ModelActionParseError("invalid_model_action_json", message)


def _json_object_or_null(value: Any, field_name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    raise _parse_error(f"{field_name} must be a JSON object or null")


def _json_bool_with_default(payload: Mapping[str, Any], key: str, *, default: bool) -> bool:
    if key not in payload:
        return default
    value = payload.get(key)
    if type(value) is not bool:
        raise _parse_error(f"{key} must be a JSON boolean")
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_text(raw_response: Mapping[str, Any] | str) -> str:
    if isinstance(raw_response, str):
        text = raw_response.strip()
        if not text:
            raise _parse_error("model output was empty")
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
    raise _parse_error("model caller did not return text")


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
        raise _parse_error("model output was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise _parse_error("model output must be a JSON object")

    unknown_keys = sorted(set(payload.keys()) - _ALLOWED_ACTION_PLAN_KEYS)
    if unknown_keys:
        raise _parse_error(f"unexpected action plan keys: {', '.join(unknown_keys)}")

    action_type = _optional_text(payload.get("action_type"))
    action_inputs = payload.get("action_inputs")
    if action_inputs is None:
        action_inputs = {}
    if not isinstance(action_inputs, Mapping):
        raise _parse_error("action_inputs must be an object")

    # Omitted low-information control flags default to false on the external seam.
    # Internal normalization may still promote no-dispatch shapes to skip_execution=True
    # when the authored turn is clearly state/HITL-only.
    complete_run = _json_bool_with_default(payload, "complete_run", default=False)
    wait_for_human = _json_bool_with_default(payload, "wait_for_human", default=False)
    skip_execution = _json_bool_with_default(payload, "skip_execution", default=False)

    if complete_run and wait_for_human:
        raise _parse_error("complete_run and wait_for_human are mutually exclusive")
    if complete_run and payload.get("hitl_request") is not None:
        raise _parse_error("complete_run and hitl_request are mutually exclusive")

    hitl_out = _json_object_or_null(payload.get("hitl_request"), "hitl_request")

    if wait_for_human and hitl_out is None:
        raise _parse_error("wait_for_human requires a non-null hitl_request object")

    if hitl_out is not None:
        try:
            normalize_hitl_request(hitl_out, iteration=0)
        except ValueError as exc:
            raise _parse_error(f"hitl_request failed canonical validation: {exc}") from exc

    try:
        consumed_out = validate_hitl_consumed_prompt_ids(payload.get("hitl_consumed_prompt_ids"))
    except ValueError as exc:
        raise _parse_error(f"hitl_consumed_prompt_ids failed canonical validation: {exc}") from exc

    try:
        user_msg_consumed_out = validate_user_message_consumed_ids(
            payload.get("user_message_consumed_ids")
        )
    except ValueError as exc:
        raise _parse_error(f"user_message_consumed_ids failed canonical validation: {exc}") from exc

    try:
        user_msg_defers_out = validate_user_message_defers(payload.get("user_message_defers"))
    except ValueError as exc:
        raise _parse_error(f"user_message_defers failed canonical validation: {exc}") from exc

    try:
        hydrate_next_refs, hydrate_next_parse_errors = normalize_hydrate_next(
            payload.get("hydrate_next")
        )
    except HydrateNextValidationError as exc:
        raise _parse_error(f"hydrate_next failed canonical validation: {exc}") from exc
    if hydrate_next_parse_errors:
        bad_indices = [str(e.get("index")) for e in hydrate_next_parse_errors]
        raise _parse_error(
            "hydrate_next entries must be non-empty strings "
            f"(invalid at index {', '.join(bad_indices)})"
        )

    try:
        hydrate_next_reason_out = normalize_hydrate_next_reason(
            payload.get("hydrate_next_reason")
        )
    except HydrateNextValidationError as exc:
        raise _parse_error(f"hydrate_next_reason failed canonical validation: {exc}") from exc

    state_patch_out = _json_object_or_null(payload.get("state_patch"), "state_patch")

    # A turn that only consumes/defers user messages (no state patch, no HITL,
    # no tool dispatch) is a valid no-dispatch acknowledgment turn — the agent
    # is telling the harness "I've read these messages and acted in another
    # turn / am deliberately deferring" without doing other work this turn.
    user_message_ack_only = (
        bool(user_msg_consumed_out) or bool(user_msg_defers_out)
    )
    implicit_no_dispatch_turn = (
        not complete_run
        and not action_type
        and (
            state_patch_out is not None
            or hitl_out is not None
            or user_message_ack_only
        )
    )
    if implicit_no_dispatch_turn:
        skip_execution = True

    if not complete_run and not wait_for_human:
        if not action_type:
            if not skip_execution:
                raise _parse_error(
                    "action_type is required unless completing, waiting, or authoring an explicit state/HITL-only turn",
                )
            if action_inputs:
                raise _parse_error("action_inputs must be empty when action_type is null on a no-dispatch turn")
            if state_patch_out is None and hitl_out is None and not user_message_ack_only:
                raise _parse_error(
                    "state_patch or hitl_request is required when action_type is null on a no-dispatch turn "
                    "(a user_message_consumed_ids or user_message_defers acknowledgment also satisfies this)",
                )
        elif available_tool_ids and action_type not in available_tool_ids:
            raise _parse_error(f"unknown action_type: {action_type}")

    rationale_raw = payload.get("rationale")
    if rationale_raw is None:
        raise _parse_error(
            "rationale is required on every turn: short decision note with why-this-move and expected-gain",
        )
    if not isinstance(rationale_raw, str):
        raise _parse_error("rationale must be a string")
    rationale_text = rationale_raw.strip()
    if not rationale_text:
        raise _parse_error(
            "rationale must be a non-empty string explaining why this move and what gain is expected",
        )

    cje_raw = payload.get("continuity_journal_entry")
    if cje_raw is None:
        cje_out: dict[str, Any] | None = None
    elif not isinstance(cje_raw, dict):
        raise _parse_error("continuity_journal_entry must be a JSON object or null")
    elif len(cje_raw) < 1:
        raise _parse_error("continuity_journal_entry must be a non-empty JSON object when present")
    else:
        cje_out = normalize_continuity_journal_entry(dict(cje_raw))

    opm_raw = payload.get("operator_progress_message")
    if opm_raw is None:
        opm_out: str | None = None
    elif isinstance(opm_raw, str):
        opm_out = _optional_text(opm_raw)
    else:
        raise _parse_error("operator_progress_message must be a string or null")

    return ActionPlan(
        action_type=action_type or None,
        action_inputs=dict(action_inputs),
        idempotency_key=_optional_text(payload.get("idempotency_key")) or "",
        skip_execution=skip_execution,
        wait_for_human=wait_for_human,
        complete_run=complete_run,
        hitl_request=hitl_out,
        hitl_consumed_prompt_ids=consumed_out,
        user_message_consumed_ids=user_msg_consumed_out,
        user_message_defers=user_msg_defers_out,
        rationale=rationale_text,
        state_patch=state_patch_out,
        continuity_journal_entry=cje_out,
        operator_progress_message=opm_out,
        hydrate_next=tuple(hydrate_next_refs),
        hydrate_next_reason=hydrate_next_reason_out,
    )
