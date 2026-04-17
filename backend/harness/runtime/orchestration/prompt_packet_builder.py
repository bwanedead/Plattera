"""Section assembly helpers for the harness-owned prompt builder."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ..composition import ComposedTurnInput
from ..hitl.transport import hitl_prompt_visible_slice
from ..memory.continuity_journal import (
    recent_journal_entries_for_prompt,
    recent_step_records_for_prompt,
    recent_step_result_records_for_prompt,
)
from .contracts import OrchestratorContext, SharedStateProjection
from .loop_health_summary import build_prompt_observability_summary
from .prompt_modes import PromptBuildDocument, PromptMode, PromptModeSpec, require_prompt_mode_spec
from .prompt_sanitization import doctrine_blocks_document, projection_document, surface_packet_document
from .prompt_utils import jsonable

_HIDDEN_LAUNCH_CONTEXT_KEYS = frozenset(
    {"max_iterations", "kernel_resume_snapshot", "kernel_resume_snapshot_path"}
)
_PROMPT_VISIBLE_DOMAIN_CLOSURE_POLICY_KEYS = frozenset(
    {
        "hard_enforced",
        "enforce_on_publish",
        "enforce_on_complete",
        "minimum_resolution_items_for_save",
        "minimum_resolution_items_for_wait",
        "minimum_resolution_items_for_publish",
        "minimum_resolution_items_for_complete",
        "required_dimension_ids",
    }
)


def build_turn_prompt_document(
    *,
    mode: PromptMode,
    composed_input: ComposedTurnInput,
    opaque_launch_context: Mapping[str, Any],
    context: OrchestratorContext,
    projection: SharedStateProjection | None,
    journal_verbatim_keep_n: int,
) -> PromptBuildDocument:
    visible_launch_context = prompt_visible_launch_context(opaque_launch_context)
    return _assemble_prompt_document(
        mode=mode,
        doctrine_blocks=doctrine_blocks_document(composed_input),
        surface_packet=surface_packet_document(composed_input),
        run_context=_build_run_context(visible_launch_context, context, projection),
        structured_state=_build_structured_state(
            context,
            journal_verbatim_keep_n,
            closure_policy=visible_launch_context.get("domain_closure_policy"),
        ),
    )


def build_repair_prompt_document(
    *,
    available_tool_ids: tuple[str, ...],
    prior_prompt_mode: str,
    parse_reason_code: str,
    parse_error_detail: str,
    previous_response_text: str,
    previous_response_object: dict[str, Any] | None = None,
    repair_targets: list[str] | None = None,
    repair_hints: list[str] | None = None,
) -> PromptBuildDocument:
    repair_context: dict[str, Any] = {
        "prior_prompt_mode": prior_prompt_mode,
        "reason_code": parse_reason_code,
        "detail": parse_error_detail,
        "previous_response_text": previous_response_text,
    }
    if previous_response_object is not None:
        repair_context["previous_response_object"] = previous_response_object
    if repair_targets:
        repair_context["repair_targets"] = repair_targets
    if repair_hints:
        repair_context["repair_hints"] = repair_hints
    return _assemble_prompt_document(
        mode="repair",
        doctrine_blocks=[],
        surface_packet={"tool_ids": list(available_tool_ids)},
        run_context={},
        structured_state={},
        mode_packet=repair_context,
    )


def build_compaction_prompt_document(
    *,
    prior_compacted_continuity_summary: str | None,
    journal_entries_to_fold: list[dict[str, Any]],
    kernel_step_records_to_fold: list[dict[str, Any]],
    kernel_step_result_records_to_fold: list[dict[str, Any]],
    target_compacted_summary_chars: int,
) -> PromptBuildDocument:
    return _assemble_prompt_document(
        mode="compaction",
        doctrine_blocks=[],
        surface_packet={},
        run_context={},
        structured_state={},
        mode_packet={
            "prior_compacted_continuity_summary": prior_compacted_continuity_summary,
            "journal_entries_to_fold": journal_entries_to_fold,
            "kernel_step_records_to_fold": kernel_step_records_to_fold,
            "kernel_step_result_records_to_fold": kernel_step_result_records_to_fold,
            "target_compacted_summary_chars": int(target_compacted_summary_chars),
        },
    )


def prompt_visible_launch_context(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return the launch-context slice that should be visible to the model."""
    visible: dict[str, Any] = {}
    for key, raw_value in value.items():
        skey = str(key)
        if skey in _HIDDEN_LAUNCH_CONTEXT_KEYS:
            continue
        if skey == "domain_closure_policy" and isinstance(raw_value, Mapping):
            visible[skey] = {
                str(inner_key): jsonable(inner_value)
                for inner_key, inner_value in raw_value.items()
                if str(inner_key) in _PROMPT_VISIBLE_DOMAIN_CLOSURE_POLICY_KEYS
            }
            continue
        visible[skey] = jsonable(raw_value)
    return visible


def _build_run_context(
    visible_launch_context: Mapping[str, Any],
    context: OrchestratorContext,
    projection: SharedStateProjection | None,
) -> dict[str, Any]:
    cont = context.loop_memory.continuity
    hitl_pend, hitl_ans, hitl_st = hitl_prompt_visible_slice(context.loop_memory.hitl)
    return {
        "iteration": context.loop_memory.iterations,
        "session_id": context.session_id,
        "request_id_prefix": context.request_id_prefix,
        "launch_context": dict(visible_launch_context),
        "latest_refs": dict(cont.latest_refs),
        "active_item_id": cont.active_item_id,
        "state_patch_feedback": dict(cont.state_patch_feedback),
        "contract_feedback": jsonable(context.loop_memory.contract_feedback),
        "operator_progress_message": cont.operator_progress_message,
        "hitl_state": hitl_st,
        "pending_hitl_requests": hitl_pend,
        "answered_hitl_responses": hitl_ans,
        "projection": projection_document(projection),
    }


def _build_structured_state(
    context: OrchestratorContext,
    journal_verbatim_keep_n: int,
    *,
    closure_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    cont = context.loop_memory.continuity
    return {
        "compacted_continuity_summary": cont.compacted_continuity_summary,
        "recent_continuity_journal_entries": recent_journal_entries_for_prompt(
            cont.continuity_journal_entries,
            cont.kernel_step_records,
            cont.kernel_step_result_records,
            keep_n=journal_verbatim_keep_n,
        ),
        "recent_kernel_step_records": recent_step_records_for_prompt(
            cont.continuity_journal_entries,
            cont.kernel_step_records,
            cont.kernel_step_result_records,
            keep_n=journal_verbatim_keep_n,
        ),
        "recent_kernel_step_result_records": recent_step_result_records_for_prompt(
            cont.continuity_journal_entries,
            cont.kernel_step_records,
            cont.kernel_step_result_records,
            keep_n=journal_verbatim_keep_n,
        ),
        "prompt_observability_summary": build_prompt_observability_summary(
            context.loop_memory,
            closure_policy=closure_policy,
        ),
    }


def _assemble_prompt_document(
    *,
    mode: PromptMode,
    doctrine_blocks: list[dict[str, Any]],
    surface_packet: dict[str, Any],
    run_context: dict[str, Any],
    structured_state: dict[str, Any],
    mode_packet: Mapping[str, Any] | None = None,
) -> PromptBuildDocument:
    spec = require_prompt_mode_spec(mode)
    prompt_body: dict[str, Any] = {"prompt_mode": mode}
    if spec.include_doctrine_blocks and doctrine_blocks:
        prompt_body["doctrine_blocks"] = doctrine_blocks
    filtered_surface_packet = _filter_surface_packet(surface_packet, spec)
    if filtered_surface_packet:
        prompt_body["surface_packet"] = filtered_surface_packet
    filtered_run_context = _filter_fields(run_context, spec.run_context_fields)
    if filtered_run_context:
        prompt_body["run_context"] = filtered_run_context
    filtered_structured_state = _filter_fields(structured_state, spec.structured_state_fields)
    if filtered_structured_state:
        prompt_body["structured_state"] = filtered_structured_state
    if spec.mode_packet_key is not None:
        prompt_body[spec.mode_packet_key] = jsonable(dict(mode_packet or {}))
    prompt_text = spec.instruction_text + "\n\n" + json.dumps(prompt_body, ensure_ascii=False)
    return PromptBuildDocument(
        mode=mode,
        call_phase=spec.call_phase,
        instruction_text=spec.instruction_text,
        prompt_body=prompt_body,
        prompt_text=prompt_text,
    )


def _filter_surface_packet(surface_packet: Mapping[str, Any], spec: PromptModeSpec) -> dict[str, Any]:
    filtered: dict[str, Any] = {}
    if spec.include_surface_packet_blocks and surface_packet.get("blocks"):
        filtered["blocks"] = list(surface_packet["blocks"])
    if spec.include_surface_payloads and surface_packet.get("surface_payloads"):
        filtered["surface_payloads"] = dict(surface_packet["surface_payloads"])
    if spec.include_tool_ids and surface_packet.get("tool_ids") is not None:
        filtered["tool_ids"] = list(surface_packet.get("tool_ids", []))
    return filtered


def _filter_fields(payload: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: payload[field] for field in fields if field in payload}
