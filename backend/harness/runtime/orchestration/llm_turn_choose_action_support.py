"""Mechanical helpers for ``LlmTurnOrchestrationAdapter.choose_action`` (audit, policies, repair I/O)."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from ..composition import ComposedTurnInput
from .audit_turn_mechanics import build_host_hydration_before_turn
from .contracts import OrchestratorContext
from .lifecycle import lifecycle_jsonable
from .llm_prompt_builder import jsonable
from .repair_lane import RepairAttempt, extract_audit_text
from .tool_batch_policy import ToolBatchPolicy, resolve_policies_for_action_plan_parse


def restore_drained_image_evidence(
    context: OrchestratorContext,
    drained: list[dict[str, Any]],
) -> None:
    """Re-queue image pixels drained before a resumable model-call interruption."""
    if not drained:
        return
    pending = context.loop_memory.pending_image_evidence
    context.loop_memory.pending_image_evidence = list(drained) + list(pending)


def tool_batch_policies_for_turn(
    composed_input: ComposedTurnInput,
    *,
    opaque_run_context: Mapping[str, Any] | None = None,
) -> dict[str, ToolBatchPolicy]:
    return resolve_policies_for_action_plan_parse(
        surface_payloads=composed_input.surface_payloads,
        opaque_run_context=opaque_run_context,
    )


def serialize_state(state: Any) -> Any:
    """Best-effort serialization of a Pydantic model or plain value for audit records."""
    if state is None:
        return None
    if hasattr(state, "model_dump"):
        try:
            return state.model_dump(mode="json")
        except Exception:
            return str(state)
    return state


def turn_snapshot(composed_input: ComposedTurnInput) -> dict[str, Any]:
    return {
        "surface_payloads": {
            surface_id: jsonable(payload)
            for surface_id, payload in composed_input.surface_payloads.items()
        },
        "tool_ids": list(composed_input.tool_handlers.keys()),
    }


def provider_audit_fields(
    raw_response: Any,
    *,
    raw_response_text: str,
) -> dict[str, Any]:
    if not isinstance(raw_response, Mapping):
        return {
            "provider_finish_reason": None,
            "provider_prompt_tokens": None,
            "provider_completion_tokens": None,
            "provider_reasoning_tokens": None,
            "provider_total_tokens": None,
            "provider_error": None,
            "provider_model": None,
            "api_model": None,
            "raw_llm_response_char_count": len(raw_response_text) if raw_response_text else 0,
            "raw_llm_response_tail": raw_response_text[-1000:] if raw_response_text else None,
        }

    usage = raw_response.get("usage")
    prompt_tokens = None
    completion_tokens = None
    reasoning_tokens = None
    total_tokens = None
    if isinstance(usage, Mapping):
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        reasoning_tokens = usage.get("reasoning_tokens")
        total_tokens = usage.get("total_tokens")

    char_count = len(raw_response_text) if raw_response_text else raw_response.get("char_count")
    if not isinstance(char_count, int):
        char_count = 0

    return {
        "provider_finish_reason": raw_response.get("finish_reason"),
        "provider_prompt_tokens": prompt_tokens,
        "provider_completion_tokens": completion_tokens,
        "provider_reasoning_tokens": reasoning_tokens,
        "provider_total_tokens": total_tokens,
        "provider_error": raw_response.get("error"),
        "provider_model": raw_response.get("provider_model") or raw_response.get("model"),
        "api_model": raw_response.get("api_model"),
        "raw_llm_response_char_count": char_count,
        "raw_llm_response_tail": raw_response_text[-1000:] if raw_response_text else None,
    }


def build_llm_io_audit_record(
    *,
    context: OrchestratorContext,
    started_at_epoch_seconds: float,
    prompt_mode: str,
    prompt: str,
    raw_response: Any,
    parse_ok: bool,
    parse_reason_code: str | None,
    plan: Any,
    repair_records: list[dict[str, Any]] | None,
    parse_error_detail: str | None,
    original_action_count_attempted: int | None,
    mission_state_before: Any,
    resolution_state_before: Any,
    latest_refs_before: Mapping[str, Any],
    prompt_observability_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    raw_response_text = extract_audit_text(raw_response)
    provider_audit = provider_audit_fields(raw_response, raw_response_text=raw_response_text)
    record = lifecycle_jsonable(
        {
            "turn_index": int(context.loop_memory.iterations),
            "started_at_epoch_seconds": started_at_epoch_seconds,
            "finished_at_epoch_seconds": time.time(),
            "prompt_mode": prompt_mode,
            "raw_prompt_text": prompt,
            "raw_llm_response_text": raw_response_text,
            **provider_audit,
            "parse_ok": parse_ok,
            "parse_reason_code": parse_reason_code,
            "parse_error_detail": parse_error_detail,
            "original_action_count_attempted": original_action_count_attempted,
            "native_actions_attempted": (
                original_action_count_attempted is not None
                and original_action_count_attempted > 0
            ),
            "parsed_action_plan": lifecycle_jsonable(plan) if plan is not None else None,
            "repair_attempted": bool(repair_records),
            "repair_records": repair_records or [],
            "repair_parse_ok": repair_records[0]["repair_parse_ok"] if repair_records else None,
            "repair_parse_reason_code": (
                repair_records[0]["repair_parse_reason_code"] if repair_records else None
            ),
            "mission_state_before": mission_state_before,
            "resolution_state_before": resolution_state_before,
            "latest_refs_before": dict(latest_refs_before),
            "contract_feedback": dict(context.loop_memory.contract_feedback),
            "host_hydration_before_turn": build_host_hydration_before_turn(
                pending_agent_hydration=context.loop_memory.continuity.pending_agent_hydration,
                pinned_refs_hydration=context.loop_memory.continuity.pinned_refs_hydration,
            ),
        }
    )
    if isinstance(prompt_observability_summary, Mapping) and prompt_observability_summary:
        record["prompt_observability_summary"] = dict(prompt_observability_summary)
    return record


def build_repair_audit_record(repair_attempt: RepairAttempt) -> dict[str, Any]:
    repaired_plan = repair_attempt.repair_parsed_action_plan
    repaired_count: int | None = None
    if repaired_plan is not None and repaired_plan.actions:
        repaired_count = len(repaired_plan.actions)
    return {
        "repair_prompt_mode": "repair",
        "repair_prompt_text": repair_attempt.repair_prompt_text,
        "repair_raw_response_text": repair_attempt.repair_raw_response_text,
        "repair_parse_ok": repair_attempt.repair_parse_ok,
        "repair_parse_reason_code": repair_attempt.repair_parse_reason_code,
        "repaired_action_count": repaired_count,
        "repair_parsed_action_plan": (
            jsonable(repaired_plan) if repaired_plan is not None else None
        ),
    }
