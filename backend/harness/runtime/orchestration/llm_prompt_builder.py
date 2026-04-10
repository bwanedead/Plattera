"""Choose-action prompt construction for kernel LLM turns.

Assembles the JSON envelope and instruction text passed to the model on each kernel turn.
Shared JSON serialization helper ``jsonable`` is also exported for adapter-side use.
"""

from __future__ import annotations

import dataclasses
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

_HIDDEN_LAUNCH_CONTEXT_KEYS = frozenset({"max_iterations"})
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
_PROJECTION_OPAQUE_KEYS_STRIPPED_FROM_PROMPT = frozenset({"launch_context", "turn_snapshot"})


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
        "launch_context": prompt_visible_launch_context(opaque_launch_context),
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
        "prompt_observability_summary": build_prompt_observability_summary(context.loop_memory),
        "hitl_state": hitl_st,
        "pending_hitl_requests": hitl_pend,
        "answered_hitl_responses": hitl_ans,
        "projection": _projection_document(projection),
    }
    instruction = (
        "You are operating inside the Plattera harness. "
        "The JSON envelope below contains doctrine blocks in turn_input.blocks, the current run context and memory, "
        "and the executable tool surface for this turn. Read those blocks and choose one next move that makes truthful, cumulative, evidence-justified progress.\n"
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
        "Investigation-first turns are valid. Use them mainly to orient, itemize the real work, repair malformed durable state, "
        "or preserve new understanding that would otherwise be lost before another dispatch. If the most justified progress is to "
        "clarify focus, itemize unresolved work, or record closure posture before dispatching another tool, you may return an explicit no-dispatch turn with "
        "action_type null, action_inputs {}, skip_execution true, wait_for_human false, complete_run false, and a non-null "
        "state_patch.\n"
        "Once an actionable item exists and a bounded discriminating check is available through current tools or evidence, the "
        "normal next move is to take that check rather than restating the same posture.\n"
        "Envelope fields compacted_continuity_summary, recent_continuity_journal_entries, recent_kernel_step_records, "
        "and recent_kernel_step_result_records are host-labeled memory: the three recent_* lists cover the same last N "
        "distinct kernel turns (journal author payloads, mechanical step rows, and bounded mechanical tool-result rows); "
        "author replacements only via continuity_journal_entry / compaction, not by editing those envelope keys.\n"
        "prompt_observability_summary is host-authored loop-health context (for example repeated no-dispatch turns or turns "
        "since the last tool execution). Treat it as mechanical context that may reveal drift or stall risk; it does not decide "
        "what matters for you.\n"
        "Optional state_patch: generic { resolution?: { active_item_id, items, relations, opaque_payload }, "
        "mission?: { objective, active_mode, blocker_summary, verification_summary, waiting_summary, "
        "continuity_summary, mission_mode_summary, high_signal_artifact_refs, closure_state, opaque_payload } — only those keys; "
        "do not put latest_refs_summary, terminal_summary, or prompt_observability_summary in mission (host-owned). "
        "you author all work semantics inside allowed shapes; the runtime merges mechanically "
        "(resolution items merge by item_id; closure_state dimensions merge by dimension_id: only fields you include are overwritten). "
        "closure_state is a generic run-level closure ledger when the domain uses explicit closure dimensions; "
        "its generic shape is { overall_status?, summary?, ready_to_publish?, ready_to_close?, requires_hitl?, "
        "no_further_progress?, dimensions?: [{dimension_id, title, status, summary?, blocking?, requires_hitl?, "
        "no_further_progress?, evidence_refs?, verification_basis?, next_needed_step?, opaque_payload?}], opaque_payload? }. "
        "the harness persists its structure but domains define the actual semantics of those dimensions. "
        "state_patch_feedback in the envelope reports the kernel outcome of the prior patch (applied / rejected / not_applied / no_patch); "
        "when outcome is applied but some resolution item/relation rows were dropped, look for skipped_resolution_rows and row_skips counts. "
        "Summary-field shorthand: mission summary fields (blocker_summary, verification_summary, waiting_summary, "
        'continuity_summary, mission_mode_summary) accept a plain string — it normalizes to {"summary": "..."} automatically. '
        'Example: "blocker_summary": "Need clearer image evidence" is valid shorthand for {"summary": "Need clearer image evidence"}. '
        "Do not emit mission or resolution as top-level keys; they belong only inside state_patch.\n"
        "contract_feedback in the envelope reports the mechanical outcome of the prior choose-action parse attempt; "
        "if repair_attempted is true, your previous response failed parsing and a repair was needed — "
        "review the reason_code and adjust your output format accordingly.\n"
        "hitl_request: optional generic human prompt transport {message (required non-empty string), choices (array), context (object), "
        "opaque_payload (object), prompt_id (optional string)}. wait_for_human is the canonical blocking flag: true requires hitl_request "
        "and pauses the loop until feedback arrives; false with hitl_request emits the request but the loop continues. "
        "hitl_consumed_prompt_ids: optional array of prompt_id strings you have mechanically incorporated — host removes matching "
        "answered_hitl_responses only. Envelope hitl_state, pending_hitl_requests, answered_hitl_responses are host-owned.\n"
        "Choose action_type only from the provided tool_ids when dispatching a tool. For an explicit no-dispatch investigation/state turn, "
        "action_type may be null only for the skip_execution shape described above.\n"
        "Canonical valid active-item tool-dispatch example: "
        '{"action_type": "some_tool", "action_inputs": {"key": "value"}, "idempotency_key": "ik-active-item-check-1", '
        '"skip_execution": false, "wait_for_human": false, "complete_run": false, '
        '"rationale": "The active item already exists, and this bounded check can materially change what I know about it.", '
        '"state_patch": {"mission": {"active_mode": "<domain_mode>", "verification_summary": "Running the strongest available check for the active item."}, '
        '"resolution": {"active_item_id": "<item-id>", "items": [{"item_id": "<item-id>", "title": "<item-title>", "kind": "claim_verification", "status": "open", "summary": "Needs one more bounded check before resolution."}]}} , '
        '"continuity_journal_entry": {"step": "dispatching bounded active-item check", "open_threads": ["interpret the returned evidence for <item-id>"]}, '
        '"operator_progress_message": "Running the next verification check.", "hitl_request": null, "hitl_consumed_prompt_ids": null}\n'
        "Canonical valid no-dispatch opening-itemization example: "
        '{"action_type": null, "action_inputs": {}, "idempotency_key": "ik-investigate-1", '
        '"skip_execution": true, "wait_for_human": false, "complete_run": false, '
        '"rationale": "I should first record the real unresolved items before choosing another tool action.", '
        '"state_patch": {"mission": {"active_mode": "<domain_mode>"}, "resolution": {"active_item_id": "<item-id>", "items": [{"item_id": "<item-id>", "title": "<item-title>", "kind": "open_question", "status": "open"}]}}, '
        '"continuity_journal_entry": {"step": "itemized unresolved work", "open_threads": ["verify the active item"]}, '
        '"operator_progress_message": "Clarifying investigation state.", "hitl_request": null, "hitl_consumed_prompt_ids": null}\n'
        "Canonical valid HITL-after-exhaustion example: "
        '{"action_type": null, "action_inputs": {}, "idempotency_key": "ik-hitl-1", '
        '"skip_execution": true, "wait_for_human": true, "complete_run": false, '
        '"rationale": "The remaining issue is material, the current run has exhausted its strongest in-run checks, and human input is now the most justified next move.", '
        '"state_patch": {"mission": {"waiting_summary": "Awaiting human clarification on the remaining blocker."}, '
        '"resolution": {"active_item_id": "<item-id>", "items": [{"item_id": "<item-id>", "title": "<item-title>", "kind": "blocking_dependency", "status": "blocked", "summary": "In-run evidence is exhausted; awaiting HITL."}]}} , '
        '"continuity_journal_entry": {"step": "escalating to human", "open_threads": ["integrate the answered prompt when it arrives"]}, '
        '"operator_progress_message": "Waiting for human clarification.", "hitl_request": {"message": "<question for operator>", "choices": [], "context": {}}, "hitl_consumed_prompt_ids": null}\n'
        "Do not force a tool action or artifact mutation merely to appear active. Prefer the most justified move."
        " Do not wrap the JSON in markdown and do not add commentary."
    )
    return instruction + "\n\n" + json.dumps(envelope, ensure_ascii=False, sort_keys=True)


def jsonable(value: Any) -> Any:
    """Recursively convert a value to a JSON-serializable form."""
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump(mode="python"))  # type: ignore[call-arg]
    if dataclasses.is_dataclass(value):
        return jsonable(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): jsonable(raw_value) for key, raw_value in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, set):
        return [jsonable(item) for item in sorted(value, key=str)]
    return value


def prompt_visible_launch_context(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return the launch-context slice that should be visible to the model.

    Host budget mechanics such as ``max_iterations`` are intentionally withheld so
    the model optimizes for truthful progress, not turn-count compression.
    """
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


def _projection_document(projection: SharedStateProjection | None) -> dict[str, Any]:
    if projection is None:
        return {}
    return {
        "mission_state": _prompt_visible_projection_state(projection.mission_state),
        "resolution_state": _prompt_visible_projection_state(projection.resolution_state),
        "latest_refs": dict(projection.latest_refs),
        "active_item_id": projection.active_item_id,
    }


def _turn_input_document(composed_input: ComposedTurnInput) -> dict[str, Any]:
    return {
        "blocks": [
            {"content": block.content, "metadata": _prompt_visible_block_metadata(block.metadata)}
            for block in composed_input.blocks
        ],
        "surface_payloads": _prompt_visible_surface_payloads(composed_input.surface_payloads),
        "tool_ids": list(composed_input.tool_handlers.keys()),
    }


def _prompt_visible_projection_state(state: Any) -> Any:
    return _strip_projection_opaque_duplicates(jsonable(state))


def _prompt_visible_block_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    payload = jsonable(metadata)
    if not isinstance(payload, dict):
        return {}
    return payload


def _prompt_visible_surface_payloads(surface_payloads: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    visible: dict[str, Any] = {}
    for surface_id, payload in surface_payloads.items():
        visible[str(surface_id)] = _prompt_visible_payload_node(jsonable(payload))
    return visible


def _prompt_visible_payload_node(value: Any) -> Any:
    if isinstance(value, list):
        return [_prompt_visible_payload_node(item) for item in value]
    if not isinstance(value, dict):
        return value

    if {"tool_id", "category", "purpose", "expected_request_shape"}.issubset(value.keys()):
        return {
            "tool_id": value.get("tool_id"),
            "category": value.get("category"),
            "purpose": value.get("purpose"),
            "expected_request_shape": value.get("expected_request_shape"),
        }

    filtered: dict[str, Any] = {}
    for key, raw in value.items():
        skey = str(key)
        if skey in {"tool_ids", "closure_policy"}:
            continue
        filtered[skey] = _prompt_visible_payload_node(raw)
    return filtered


def _strip_projection_opaque_duplicates(value: Any) -> Any:
    if isinstance(value, list):
        return [_strip_projection_opaque_duplicates(item) for item in value]
    if not isinstance(value, dict):
        return value

    filtered: dict[str, Any] = {}
    for key, raw in value.items():
        skey = str(key)
        if skey == "opaque_payload" and isinstance(raw, dict):
            filtered[skey] = {
                str(inner_key): _strip_projection_opaque_duplicates(inner_value)
                for inner_key, inner_value in raw.items()
                if str(inner_key) not in _PROJECTION_OPAQUE_KEYS_STRIPPED_FROM_PROMPT
            }
            continue
        filtered[skey] = _strip_projection_opaque_duplicates(raw)
    return filtered
