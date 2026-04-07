"""Choose-action prompt construction for kernel LLM turns.

Assembles the JSON envelope and instruction text passed to the model on each kernel turn.
Shared JSON serialization helper ``jsonable`` is also exported for adapter-side use.
"""

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


def build_choose_action_prompt(
    *,
    composed_input: ComposedTurnInput,
    opaque_launch_context: Mapping[str, Any],
    context: OrchestratorContext,
    projection: SharedStateProjection | None,
    journal_verbatim_keep_n: int,
) -> str:
    """Assemble the full choose-action prompt string for one kernel turn."""
    cont = context.loop_memory.continuity
    hitl_pend, hitl_ans, hitl_st = hitl_prompt_visible_slice(context.loop_memory.hitl)
    envelope = {
        "iteration": context.loop_memory.iterations,
        "session_id": context.session_id,
        "request_id_prefix": context.request_id_prefix,
        "launch_context": jsonable(opaque_launch_context),
        "turn_input": _turn_input_document(composed_input),
        "latest_refs": dict(cont.latest_refs),
        "active_item_id": cont.active_item_id,
        "state_patch_feedback": dict(cont.state_patch_feedback),
        "contract_feedback": jsonable(context.loop_memory.contract_feedback),
        "operator_progress_message": cont.operator_progress_message,
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
        "hitl_state": hitl_st,
        "pending_hitl_requests": hitl_pend,
        "answered_hitl_responses": hitl_ans,
        "projection": _projection_document(projection),
    }
    instruction = (
        "Return exactly one JSON object matching this schema:\n"
        "{"
        '"action_type": string|null, '
        '"action_inputs": object, '
        '"idempotency_key": string, '
        '"skip_execution": boolean, '
        '"wait_for_human": boolean, '
        '"complete_run": boolean, '
        '"rationale": string|null, '
        '"state_patch": object|null, '
        '"continuity_journal_entry": object, '
        '"operator_progress_message": string|null, '
        '"hitl_request": object|null, '
        '"hitl_consumed_prompt_ids": array|null'
        "}\n"
        "continuity_journal_entry: required non-empty JSON object each turn (append-only continuity: observations, decisions, "
        "open threads, expected next). operator_progress_message: optional short user-facing status line; null keeps the prior "
        "message.\n"
        "Envelope fields compacted_continuity_summary, recent_continuity_journal_entries, recent_kernel_step_records, "
        "and recent_kernel_step_result_records are host-labeled memory: the three recent_* lists cover the same last N "
        "distinct kernel turns (journal author payloads, mechanical step rows, and bounded mechanical tool-result rows); "
        "author replacements only via continuity_journal_entry / compaction, not by editing those envelope keys.\n"
        "Optional state_patch: generic { resolution?: { active_item_id, items, relations, opaque_payload }, "
        "mission?: { objective, active_mode, blocker_summary, verification_summary, waiting_summary, "
        "continuity_summary, mission_mode_summary, high_signal_artifact_refs, opaque_payload } — only those keys; "
        "do not put latest_refs_summary, terminal_summary, or prompt_observability_summary in mission (host-owned). "
        "you author all work semantics inside allowed shapes; the runtime merges mechanically "
        "(resolution items merge by item_id: only fields you include are overwritten). "
        "state_patch_feedback in the envelope reports the kernel outcome of the prior patch (applied / rejected / not_applied / no_patch); "
        "when outcome is applied but some resolution item/relation rows were dropped, look for skipped_resolution_rows and row_skips counts. "
        "Summary-field shorthand: mission summary fields (blocker_summary, verification_summary, waiting_summary, "
        'continuity_summary, mission_mode_summary) accept a plain string — it normalizes to {"summary": "..."} automatically. '
        'Example: "blocker_summary": "Need clearer image evidence" is valid shorthand for {"summary": "Need clearer image evidence"}.\n'
        "contract_feedback in the envelope reports the mechanical outcome of the prior choose-action parse attempt; "
        "if repair_attempted is true, your previous response failed parsing and a repair was needed — "
        "review the reason_code and adjust your output format accordingly.\n"
        "hitl_request: optional generic human prompt transport {message (required non-empty string), choices (array), context (object), "
        "opaque_payload (object), prompt_id (optional string)}. wait_for_human is the canonical blocking flag: true requires hitl_request "
        "and pauses the loop until feedback arrives; false with hitl_request emits the request but the loop continues. "
        "hitl_consumed_prompt_ids: optional array of prompt_id strings you have mechanically incorporated — host removes matching "
        "answered_hitl_responses only. Envelope hitl_state, pending_hitl_requests, answered_hitl_responses are host-owned.\n"
        "Choose action_type only from the provided tool_ids unless complete_run or wait_for_human is true.\n"
        "Canonical valid example: "
        '{"action_type": "some_tool", "action_inputs": {"key": "value"}, "idempotency_key": "ik-1", '
        '"skip_execution": false, "wait_for_human": false, "complete_run": false, '
        '"rationale": "doing X because Y", '
        '"state_patch": {"mission": {"blocker_summary": "Awaiting image evidence"}}, '
        '"continuity_journal_entry": {"step": "hydrating ref", "open_threads": ["verify section 3"]}, '
        '"operator_progress_message": null, "hitl_request": null, "hitl_consumed_prompt_ids": null}\n'
        "Do not wrap the JSON in markdown and do not add commentary."
    )
    return instruction + "\n\n" + json.dumps(envelope, ensure_ascii=False, sort_keys=True)


def jsonable(value: Any) -> Any:
    """Recursively convert a value to a JSON-serializable form."""
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump(mode="python"))  # type: ignore[call-arg]
    if isinstance(value, Mapping):
        return {str(key): jsonable(raw_value) for key, raw_value in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, set):
        return [jsonable(item) for item in sorted(value, key=str)]
    return value


def _projection_document(projection: SharedStateProjection | None) -> dict[str, Any]:
    if projection is None:
        return {}
    return {
        "mission_state": jsonable(projection.mission_state),
        "resolution_state": jsonable(projection.resolution_state),
        "latest_refs": dict(projection.latest_refs),
        "active_item_id": projection.active_item_id,
    }


def _turn_input_document(composed_input: ComposedTurnInput) -> dict[str, Any]:
    return {
        "blocks": [
            {"content": block.content, "metadata": jsonable(block.metadata)}
            for block in composed_input.blocks
        ],
        "surface_payloads": {
            surface_id: jsonable(payload)
            for surface_id, payload in composed_input.surface_payloads.items()
        },
        "tool_ids": list(composed_input.tool_handlers.keys()),
    }
