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
from .action_sequence import action_plan_with_canonical_actions
from .action_sequence_plan_shape import canonicalize_actions_from_payload
from .tool_batch_policy import DomainActionBatchPolicy, ToolBatchPolicy
from .pinned_refs import PinnedRefsValidationError, normalize_pin_ref_list
from .subtasks.registry import DEFAULT_SUBTASK_REGISTRY, SubtaskProfileRegistry
from .user_message_action_plan_shape import (
    validate_user_message_consumed_ids,
    validate_user_message_defers,
)

MAX_OPERATOR_PROGRESS_MESSAGE_CHARS = 240


_ALLOWED_ACTION_PLAN_KEYS = {
    "actions", "action_type", "action_inputs", "action_batch", "idempotency_key",
    "skip_execution", "wait_for_human", "complete_run",
    "rationale", "state_patch", "continuity_journal_entry",
    "operator_progress_message", "hitl_request", "hitl_consumed_prompt_ids",
    "user_message_consumed_ids", "user_message_defers",
    "hydrate_next", "hydrate_next_reason",
    "pin_refs", "unpin_refs",
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
    tool_batch_policies: Mapping[str, ToolBatchPolicy] | None = None,
    domain_batch_policy: DomainActionBatchPolicy | None = None,
    subtask_profile_registry: SubtaskProfileRegistry = DEFAULT_SUBTASK_REGISTRY,
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

    try:
        canonical = canonicalize_actions_from_payload(
            payload,
            available_tool_ids=available_tool_ids,
            tool_batch_policies=dict(tool_batch_policies or {}),
            domain_batch_policy=domain_batch_policy,
            subtask_profile_registry=subtask_profile_registry,
        )
    except ValueError as exc:
        raise _parse_error(f"actions failed canonical validation: {exc}") from exc
    actions_out = canonical.actions
    legacy_top_hydrate = canonical.legacy_top_hydrate_next
    legacy_top_hydrate_reason = canonical.legacy_top_hydrate_next_reason
    has_native_or_legacy_dispatch = bool(actions_out)

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

    hydrate_next_refs = list(legacy_top_hydrate)
    hydrate_next_reason_out = legacy_top_hydrate_reason

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
        and not has_native_or_legacy_dispatch
        and (
            state_patch_out is not None
            or hitl_out is not None
            or user_message_ack_only
        )
    )
    if implicit_no_dispatch_turn:
        skip_execution = True

    if not complete_run and not wait_for_human:
        if not has_native_or_legacy_dispatch:
            if not skip_execution:
                raise _parse_error(
                    "actions (or legacy action_type / action_batch) is required unless completing, "
                    "waiting, or authoring an explicit state/HITL-only turn",
                )
            if payload.get("action_inputs"):
                raise _parse_error("action_inputs must be empty on a no-dispatch turn")
            if state_patch_out is None and hitl_out is None and not user_message_ack_only:
                raise _parse_error(
                    "state_patch or hitl_request is required on a no-dispatch turn "
                    "(a user_message_consumed_ids or user_message_defers acknowledgment also satisfies this)",
                )

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
        if opm_out is not None and len(opm_out) > MAX_OPERATOR_PROGRESS_MESSAGE_CHARS:
            raise _parse_error(
                "operator_progress_message exceeds max length "
                f"({MAX_OPERATOR_PROGRESS_MESSAGE_CHARS} chars)"
            )
    else:
        raise _parse_error("operator_progress_message must be a string or null")

    try:
        pin_refs_out = normalize_pin_ref_list(payload.get("pin_refs"), field_name="pin_refs")
        unpin_refs_out = normalize_pin_ref_list(payload.get("unpin_refs"), field_name="unpin_refs")
    except PinnedRefsValidationError as exc:
        raise _parse_error(str(exc)) from exc

    return action_plan_with_canonical_actions(
        actions=actions_out,
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
        pin_refs=pin_refs_out,
        unpin_refs=unpin_refs_out,
    )
