"""Repair-lane helpers for action-plan parse recovery."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

from services.llm.call_options import LlmCallOptions

from harness.runtime.llm.streaming_config import apply_streaming_to_call_options

from .action_plan_parser import ModelActionParseError, parse_action_plan_response
from .contracts import ActionPlan
from .subtasks.registry import DEFAULT_SUBTASK_REGISTRY, SubtaskProfileRegistry
from .tool_batch_policy import DomainActionBatchPolicy, ToolBatchPolicy
from .llm_prompt_builder import build_repair_prompt_document

TextModelCaller = Callable[..., Mapping[str, Any] | str]


@dataclass(frozen=True)
class RepairAttempt:
    repair_prompt_text: str
    repair_raw_response_text: str
    repair_parse_ok: bool
    repair_parse_reason_code: str | None
    repair_parsed_action_plan: ActionPlan | None
    repair_error: ModelActionParseError | None
    llm_call_trace: Mapping[str, Any] | None = None


def count_attempted_actions_in_object(payload: Mapping[str, Any]) -> int | None:
    """Mechanical count of authored dispatch rows for audit/timeline (no semantic inference)."""
    actions = payload.get("actions")
    if isinstance(actions, list):
        return len(actions)
    batch = payload.get("action_batch")
    if isinstance(batch, list):
        return len(batch)
    if payload.get("action_type"):
        return 1
    return None


def count_attempted_actions_in_text(previous_response_text: str) -> int | None:
    try:
        parsed = json.loads(previous_response_text)
    except Exception:
        return None
    if isinstance(parsed, dict):
        return count_attempted_actions_in_object(parsed)
    return None


def _derive_repair_context(
    previous_response_text: str,
    parse_error_detail: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Return (previous_response_object, repair_targets) derived from the prior response.

    Opportunistically parses the prior response text as JSON.  When the text is a
    valid JSON object, derives structural repair targets from the known shape mistakes.
    Returns (None, []) when the text is not parseable as a JSON object.
    """
    previous_response_object: dict[str, Any] | None = None
    repair_targets: list[str] = []

    try:
        parsed = json.loads(previous_response_text)
    except Exception:
        return None, []

    if not isinstance(parsed, dict):
        return None, []

    previous_response_object = parsed

    # Derive structural repair targets from known shape mistakes.
    error_lower = parse_error_detail.lower()

    # Missing continuity journal: only surface as a target when the parse error itself
    # explicitly referenced the field. The field is now optional, so absence alone is not
    # a structural fault; only report it when the error confirms it was the trigger.
    if "continuity_journal_entry" not in parsed and "continuity_journal_entry" in error_lower:
        repair_targets.append("add_missing_continuity_journal_entry")

    # Missing or blank rationale: rationale is required on every turn. Surface the target
    # whenever the parse error mentions rationale, so repair knows to author the shortest
    # honest rationale consistent with the already-chosen move rather than reshape the plan.
    if "rationale" in error_lower:
        rationale_raw = parsed.get("rationale")
        if rationale_raw is None or (isinstance(rationale_raw, str) and not rationale_raw.strip()):
            repair_targets.append("add_missing_rationale")

    # Misplaced closure_state: authored at state_patch top-level instead of under mission.
    state_patch = parsed.get("state_patch")
    if isinstance(state_patch, dict) and "closure_state" in state_patch:
        mission = state_patch.get("mission")
        if not isinstance(mission, dict) or "closure_state" not in mission:
            repair_targets.append("move_state_patch_closure_state_under_mission")

    # Unknown top-level keys — surface only when the error is specifically about
    # unexpected action plan keys, not other "unknown" errors (e.g. unknown action_type).
    if "unexpected action plan keys" in error_lower:
        repair_targets.append("remove_unknown_top_level_keys")

    if isinstance(parsed.get("actions"), list):
        repair_targets.append("preserve_native_actions_array")
        action_count = len(parsed["actions"])
        if action_count > 1:
            repair_targets.append("preserve_multi_action_intent")
        if "exceeds per-tool cap" in error_lower or "exceeds max batch size" in error_lower:
            repair_targets.append("reduce_actions_to_tool_cap_not_single_action")
        if "cannot be mixed" in error_lower and (
            parsed.get("hydrate_next") is not None or parsed.get("hydrate_next_reason") is not None
        ):
            repair_targets.append("remove_top_level_hydrate_when_using_per_action_hydrate")
        if "actions[" in error_lower and action_count > 1:
            repair_targets.append("repair_or_drop_malformed_action_rows_preserve_valid_rows")

    return previous_response_object, repair_targets


def should_use_state_repair_lane(feedback: Mapping[str, Any] | None) -> bool:
    """Return whether the next choose-action turn should enter the proof/state repair lane."""
    if not isinstance(feedback, Mapping):
        return False
    outcome = str(feedback.get("outcome") or "").strip().lower()
    if outcome == "rejected":
        return True
    if outcome == "applied" and bool(feedback.get("skipped_resolution_rows")):
        return True
    return False


def attempt_repair(
    *,
    model_caller: TextModelCaller,
    model_name: str,
    prior_prompt_mode: str,
    previous_response_text: str,
    original_exc: ModelActionParseError,
    available_tool_ids: tuple[str, ...],
    original_image_attachments: tuple[dict[str, Any], ...] = (),
    tool_batch_policies: Mapping[str, ToolBatchPolicy] | None = None,
    domain_batch_policy: DomainActionBatchPolicy | None = None,
    subtask_profile_registry: SubtaskProfileRegistry = DEFAULT_SUBTASK_REGISTRY,
    run_context: Mapping[str, Any] | None = None,
) -> RepairAttempt:
    previous_response_object, repair_targets = _derive_repair_context(
        previous_response_text, str(original_exc)
    )
    repair_prompt = build_repair_prompt_document(
        available_tool_ids=available_tool_ids,
        prior_prompt_mode=prior_prompt_mode,
        parse_reason_code=original_exc.reason_code,
        parse_error_detail=str(original_exc),
        previous_response_text=previous_response_text,
        previous_response_object=previous_response_object,
        repair_targets=repair_targets if repair_targets else None,
    )
    repair_prompt_text = repair_prompt.prompt_text
    repair_opts = apply_streaming_to_call_options(
        LlmCallOptions(
            output_mode="json_object",
            image_attachments=original_image_attachments,
            phase=repair_prompt.call_phase,
        ),
        run_context=run_context,
    )
    raw_repair: Any = None
    repair_trace: Mapping[str, Any] | None = None
    try:
        raw_repair = model_caller(repair_prompt_text, model_name, call_options=repair_opts)
        repair_trace = _trace_from_response(raw_repair)
        plan = parse_action_plan_response(
            raw_repair,
            available_tool_ids=available_tool_ids,
            tool_batch_policies=tool_batch_policies,
            domain_batch_policy=domain_batch_policy,
            subtask_profile_registry=subtask_profile_registry,
        )
        return RepairAttempt(
            repair_prompt_text=repair_prompt_text,
            repair_raw_response_text=extract_audit_text(raw_repair),
            repair_parse_ok=True,
            repair_parse_reason_code=None,
            repair_parsed_action_plan=plan,
            repair_error=None,
            llm_call_trace=repair_trace,
        )
    except ModelActionParseError as exc:
        return RepairAttempt(
            repair_prompt_text=repair_prompt_text,
            repair_raw_response_text=extract_audit_text(raw_repair),
            repair_parse_ok=False,
            repair_parse_reason_code=exc.reason_code,
            repair_parsed_action_plan=None,
            repair_error=exc,
            llm_call_trace=repair_trace,
        )
    except Exception as exc:
        err = ModelActionParseError("model_caller_exception", "repair attempt raised unexpected exception")
        return RepairAttempt(
            repair_prompt_text=repair_prompt_text,
            repair_raw_response_text=extract_audit_text(raw_repair),
            repair_parse_ok=False,
            repair_parse_reason_code="model_caller_exception",
            repair_parsed_action_plan=None,
            repair_error=err,
            llm_call_trace=_trace_from_exception(exc) or repair_trace,
        )


def _trace_from_response(raw: Any) -> Mapping[str, Any] | None:
    if isinstance(raw, Mapping):
        trace = raw.get("llm_call_trace")
        if isinstance(trace, Mapping):
            return dict(trace)
    return None


def _trace_from_exception(exc: BaseException) -> Mapping[str, Any] | None:
    trace = getattr(exc, "llm_call_trace", None)
    if isinstance(trace, Mapping):
        return dict(trace)
    return None


def extract_audit_text(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, Mapping):
        for key in ("text", "content", "output_text", "error"):
            value = raw.get(key)
            if isinstance(value, str):
                return value
    return "" if raw is None else str(raw)
