"""Repair-lane helpers for action-plan parse recovery."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

from services.llm.call_options import LlmCallOptions

from .action_plan_parser import ModelActionParseError, parse_action_plan_response
from .contracts import ActionPlan
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


def attempt_repair(
    *,
    model_caller: TextModelCaller,
    model_name: str,
    prior_prompt_mode: str,
    previous_response_text: str,
    original_exc: ModelActionParseError,
    available_tool_ids: tuple[str, ...],
    original_image_attachments: tuple[dict[str, Any], ...] = (),
) -> RepairAttempt:
    repair_prompt = build_repair_prompt_document(
        available_tool_ids=available_tool_ids,
        prior_prompt_mode=prior_prompt_mode,
        parse_reason_code=original_exc.reason_code,
        parse_error_detail=str(original_exc),
        previous_response_text=previous_response_text,
    )
    repair_prompt_text = repair_prompt.prompt_text
    repair_opts = LlmCallOptions(
        output_mode="json_object",
        image_attachments=original_image_attachments,
        phase=repair_prompt.call_phase,
    )
    raw_repair: Any = None
    try:
        raw_repair = model_caller(repair_prompt_text, model_name, call_options=repair_opts)
        plan = parse_action_plan_response(raw_repair, available_tool_ids=available_tool_ids)
        return RepairAttempt(
            repair_prompt_text=repair_prompt_text,
            repair_raw_response_text=extract_audit_text(raw_repair),
            repair_parse_ok=True,
            repair_parse_reason_code=None,
            repair_parsed_action_plan=plan,
            repair_error=None,
        )
    except ModelActionParseError as exc:
        return RepairAttempt(
            repair_prompt_text=repair_prompt_text,
            repair_raw_response_text=extract_audit_text(raw_repair),
            repair_parse_ok=False,
            repair_parse_reason_code=exc.reason_code,
            repair_parsed_action_plan=None,
            repair_error=exc,
        )
    except Exception:
        err = ModelActionParseError("model_caller_exception", "repair attempt raised unexpected exception")
        return RepairAttempt(
            repair_prompt_text=repair_prompt_text,
            repair_raw_response_text=extract_audit_text(raw_repair),
            repair_parse_ok=False,
            repair_parse_reason_code="model_caller_exception",
            repair_parsed_action_plan=None,
            repair_error=err,
        )


def extract_audit_text(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, Mapping):
        for key in ("text", "content", "output_text", "error"):
            value = raw.get(key)
            if isinstance(value, str):
                return value
    return "" if raw is None else str(raw)
