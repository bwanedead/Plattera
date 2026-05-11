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
    verbatim_turn_indices,
)
from ..memory.tool_result_slices import build_recent_tool_result_slices
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
    run_context: dict[str, Any] = {
        "iteration": context.loop_memory.iterations,
        "session_id": context.session_id,
        "request_id_prefix": context.request_id_prefix,
        "launch_context": dict(visible_launch_context),
        "latest_refs": dict(cont.latest_refs),
        "active_item_id": cont.active_item_id,
        "state_patch_feedback": dict(cont.state_patch_feedback),
        "hitl_state": hitl_st,
        "projection": projection_document(
            projection,
            state_patch_feedback=cont.state_patch_feedback,
        ),
    }
    contract_feedback = jsonable(context.loop_memory.contract_feedback)
    if contract_feedback:
        run_context["contract_feedback"] = contract_feedback
    if context.loop_memory.turn_recovery.has_pending_recovery():
        run_context["turn_recovery"] = context.loop_memory.turn_recovery.to_wire()
    if cont.operator_progress_message is not None:
        run_context["operator_progress_message"] = cont.operator_progress_message
    if hitl_pend:
        run_context["pending_hitl_requests"] = hitl_pend
    if hitl_ans:
        run_context["answered_hitl_responses"] = hitl_ans
    return run_context


def _build_structured_state(
    context: OrchestratorContext,
    journal_verbatim_keep_n: int,
    *,
    closure_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    cont = context.loop_memory.continuity
    structured: dict[str, Any] = {
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
        "prompt_observability_summary": _compact_prompt_observability_summary(
            build_prompt_observability_summary(
                context.loop_memory,
                closure_policy=closure_policy,
            )
        ),
    }
    timeline = _build_recent_turn_timeline(
        cont.continuity_journal_entries,
        cont.kernel_step_records,
        cont.kernel_step_result_records,
        keep_n=journal_verbatim_keep_n,
    )
    if timeline:
        structured["recent_turn_timeline"] = timeline
    tool_result_slices = build_recent_tool_result_slices(
        cont.kernel_step_result_records,
    )
    if tool_result_slices:
        structured["recent_tool_result_slices"] = tool_result_slices
    return structured


def _build_recent_turn_timeline(
    journal_entries: list[dict[str, Any]],
    step_records: list[dict[str, Any]],
    step_result_records: list[dict[str, Any]],
    *,
    keep_n: int,
) -> list[dict[str, Any]]:
    """Deterministic drop-only projection of recent turn mechanics.

    Emits one small row per recent kernel turn (aligned by ``kernel_turn_index``)
    with only mechanical facts already present in stored step and step-result
    rows. No semantic interpretation or mission-relevance decisions happen here.
    """
    kept = verbatim_turn_indices(
        journal_entries, step_records, step_result_records, keep_n=keep_n
    )
    if not kept:
        return []

    step_by_turn: dict[int, dict[str, Any]] = {}
    for row in step_records:
        try:
            ki = int(row.get("kernel_turn_index"))
        except (TypeError, ValueError):
            continue
        if ki in kept:
            step_by_turn[ki] = row

    result_by_turn: dict[int, dict[str, Any]] = {}
    for row in step_result_records:
        try:
            ki = int(row.get("kernel_turn_index"))
        except (TypeError, ValueError):
            continue
        if ki in kept:
            result_by_turn[ki] = row

    ordered_turns = sorted(kept)
    prior_refs: Mapping[str, Any] | None = None
    # Seed prior_refs from the row immediately before the first kept turn, if any,
    # so the first emitted row's latest_refs_changed is meaningful.
    first_turn = ordered_turns[0]
    prior_candidates = [
        row for row in step_records
        if _safe_turn_index(row) is not None and _safe_turn_index(row) < first_turn
    ]
    if prior_candidates:
        prior_candidates.sort(key=lambda r: int(r["kernel_turn_index"]))
        prior_refs = prior_candidates[-1].get("latest_refs_snapshot") or {}

    timeline: list[dict[str, Any]] = []
    for turn in ordered_turns:
        step = step_by_turn.get(turn, {})
        result = result_by_turn.get(turn, {})
        current_refs = step.get("latest_refs_snapshot")
        if current_refs is None:
            current_refs = result.get("latest_refs_snapshot") or {}
        refs_changed = False
        if prior_refs is not None:
            refs_changed = dict(current_refs or {}) != dict(prior_refs or {})
        artifact_refs = result.get("artifact_refs") or []
        row: dict[str, Any] = {
            "kernel_turn_index": int(turn),
            "action_type": step.get("action_type"),
            "execution_state": step.get("execution_state") or result.get("execution_state"),
            "execution_reason_code": step.get("execution_reason_code")
            or result.get("execution_reason_code"),
            "skip_execution": bool(step.get("skip_execution", False)),
            "wait_for_human": bool(step.get("wait_for_human", False)),
            "complete_run": bool(step.get("complete_run", False)),
            "active_item_id_snapshot": step.get("active_item_id_snapshot"),
            "latest_refs_changed": bool(refs_changed),
            "result_truncated": bool(result.get("result_truncated", False)),
            "artifact_ref_count": len(artifact_refs) if isinstance(artifact_refs, list) else 0,
        }
        timeline.append(row)
        prior_refs = current_refs or prior_refs
    return timeline


def _safe_turn_index(row: Mapping[str, Any]) -> int | None:
    try:
        return int(row.get("kernel_turn_index"))
    except (TypeError, ValueError):
        return None


_ALWAYS_KEEP_OBSERVABILITY_KEYS: tuple[str, ...] = (
    "work_universe_posture",
    "resolution_item_count",
    "success_condition_count",
    "closure_dimension_count",
    # Graph-shape counters: zero is diagnostically meaningful, so keep them
    # even when 0. Surfaces "4 items, 0 atomic, 0 groups, 0 covered units"
    # rather than just "4 items".
    "atomic_item_count",
    "group_item_count",
    "covered_unit_count",
    "covered_units_with_candidates_count",
    "closed_value_units_missing_evidence_count",
    "earned_units_missing_verification_basis_count",
    # Locator debt: zero is diagnostically meaningful — confirms all earned
    # units have claim-local proof. Non-zero signals broad-only evidence.
    "earned_units_missing_locator_count",
    "shared_unlocated_evidence_for_earned_units_count",
    "notebook_shaped_graph_rows_count",
    "artifact_claim_inventory_suspect_count",
)
_OPTIONAL_OBSERVABILITY_COUNTERS: tuple[str, ...] = (
    "repeated_state_patch_reason_code_streak",
    "turns_since_last_state_patch_applied",
    "consecutive_same_active_item_turns",
    "turns_since_resolution_item_count_change",
    "new_resolution_items_since_last_complete_run_attempt",
    "repeated_complete_run_without_state_change_count",
    "artifact_refresh_trap_risk_count",
    "repair_ready_without_artifact_write_count",
    "hitl_evidence_readiness_debt_count",
    "post_hitl_spin_count",
    # Sequencing / locality debt (active pressure when non-zero)
    "earned_before_local_evidence_count",
    "posthoc_recheck_needed_count",
    "earned_exact_with_broad_image_locator_count",
    # HITL answerability pressure (advisory; show when non-zero)
    "blocked_without_hitl_answerability_count",
    "human_answerable_blocker_without_hitl_count",
    "not_answerable_missing_reason_count",
    # HITL exchange ledger pressure (active when non-zero)
    "answered_hitl_unconsumed_count",
    "complete_with_unconsumed_hitl_count",
    "hitl_consumed_unknown_prompt_count",
)


def _compact_prompt_observability_summary(full_summary: Mapping[str, Any]) -> dict[str, Any]:
    """Drop-only projection of the full observability summary for prompt transport.

    Keeps structural anchors always, optional mechanical counters only when
    non-zero/non-null, ``closure_readiness_projection`` only when it carries
    non-empty blocker arrays, ``mechanical_flags`` only when non-empty, and
    ``last_state_patch_reason_code`` only when present. No semantic
    relevance decisions — this is transport compression.
    """
    compact: dict[str, Any] = {}
    for key in _ALWAYS_KEEP_OBSERVABILITY_KEYS:
        if key in full_summary:
            compact[key] = full_summary[key]

    if "last_state_patch_outcome" in full_summary:
        compact["last_state_patch_outcome"] = full_summary["last_state_patch_outcome"]
    reason_code = full_summary.get("last_state_patch_reason_code")
    if reason_code:
        compact["last_state_patch_reason_code"] = reason_code

    for key in _OPTIONAL_OBSERVABILITY_COUNTERS:
        value = full_summary.get(key)
        if value:  # drop None and 0
            compact[key] = value

    projection = full_summary.get("closure_readiness_projection")
    if isinstance(projection, Mapping):
        kept_projection: dict[str, list[str]] = {}
        for proj_key in ("complete_run_blockers", "publish_blockers"):
            rows = projection.get(proj_key) or []
            if rows:
                kept_projection[proj_key] = list(rows)
        if kept_projection:
            compact["closure_readiness_projection"] = kept_projection

    flags = full_summary.get("mechanical_flags") or []
    if flags:
        compact["mechanical_flags"] = list(flags)

    # HITL exchange ledger projection — include only when non-empty so the
    # agent sees exact request/response payloads it must integrate.
    exchanges = full_summary.get("recent_hitl_exchanges") or []
    if exchanges:
        compact["recent_hitl_exchanges"] = list(exchanges)

    return compact


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
