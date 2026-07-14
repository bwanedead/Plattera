"""Section assembly helpers for the harness-owned prompt builder."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ..composition import ComposedTurnInput
from ..hitl.transport import hitl_prompt_visible_slice
from ..upstream_run_lineage import UPSTREAM_RUN_LINEAGE_LAUNCH_KEY
from ..memory.continuity_journal import (
    recent_journal_entries_for_prompt,
    recent_step_records_for_prompt,
    recent_step_result_records_for_prompt,
    verbatim_turn_indices,
)
from ..memory.atom_evidence_worklist_projection import compact_atom_evidence_worklist_for_prompt
from ..memory.delegate_observation_worklist_projection import (
    compact_delegate_observation_worklist_for_prompt,
    delegate_observation_reminder_from_context,
)
from ..memory.tool_result_slices import build_recent_tool_result_slices
from .contracts import OrchestratorContext, SharedStateProjection
from .loop_health_summary import build_prompt_observability_summary
from .prompt_modes import PromptBuildDocument, PromptMode, PromptModeSpec, require_prompt_mode_spec
from .prompt_budget import build_prompt_budget_report
from .prompt_sanitization import doctrine_blocks_document, projection_document, surface_packet_document
from .prompt_utils import jsonable
from .ref_window_projection import (
    build_hot_latest_ref_keys,
    collect_hot_refs_for_prompt,
    project_refs_map_for_prompt,
)
from .recent_result_projection import (
    project_recent_action_sequence_for_prompt,
    project_recent_tool_result_slices_for_prompt,
)

_HIDDEN_LAUNCH_CONTEXT_KEYS = frozenset(
    {
        "max_iterations",
        "kernel_resume_snapshot",
        "kernel_resume_snapshot_path",
        UPSTREAM_RUN_LINEAGE_LAUNCH_KEY,
        "domain_work_graph_policy",
        # Host mechanic: module path for optional per-turn domain projection.
        "domain_prompt_runtime_projection_module",
    }
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
        "required_output_ref_for_complete",
    }
)


def domain_closure_policy_for_ref_projection(
    opaque_launch_context: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Unfiltered closure policy for mechanical hot-ref derivation only."""
    raw = opaque_launch_context.get("domain_closure_policy")
    if not isinstance(raw, Mapping):
        return None
    return dict(raw)


def _union_hot_artifact_refs(
    hot_refs: frozenset[str],
    domain_runtime_projection: Mapping[str, Any],
) -> frozenset[str]:
    """Mechanically union optional domain-declared hot artifact refs (opaque list)."""
    raw = domain_runtime_projection.get("hot_artifact_refs")
    if not isinstance(raw, list):
        return hot_refs
    extra = {str(ref).strip() for ref in raw if str(ref or "").strip()}
    if not extra:
        return hot_refs
    return frozenset(set(hot_refs) | extra)


def _resolution_items_for_domain_projection(
    context: OrchestratorContext,
    projection: SharedStateProjection | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    source_items = ()
    if projection is not None:
        source_items = projection.resolution_state.items
    else:
        source_items = context.loop_memory.continuity.resolution_state.items
    for item in source_items:
        payload = jsonable(item)
        if isinstance(payload, dict):
            items.append(payload)
    return items


def _build_domain_runtime_projection(
    *,
    opaque_launch_context: Mapping[str, Any],
    context: OrchestratorContext,
    projection: SharedStateProjection | None,
) -> dict[str, Any] | None:
    """Load optional domain projection module and invoke its opaque builder.

    Harness never interprets domain contents — only transports the mapping and
    optionally unions declared ``hot_artifact_refs`` into exact-ref windowing.
    """
    module_ref = str(
        opaque_launch_context.get("domain_prompt_runtime_projection_module") or ""
    ).strip()
    if not module_ref:
        return None
    try:
        import importlib

        module = importlib.import_module(module_ref)
        builder = getattr(module, "build_prompt_runtime_projection", None)
        if not callable(builder):
            return None
        result = builder(
            launch_context=dict(opaque_launch_context),
            resolution_items=_resolution_items_for_domain_projection(context, projection),
        )
    except Exception:
        return None
    if not isinstance(result, Mapping) or not result:
        return None
    return dict(result)


def _claim_inventory_pressure_from_launch_context(
    opaque_launch_context: Mapping[str, Any] | None,
) -> bool:
    from domains.work_graph_policy import claim_inventory_pressure_enabled

    return claim_inventory_pressure_enabled(opaque_launch_context)


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
    hot_refs, hot_latest_ref_keys = _prompt_ref_projection_context(
        context,
        projection,
        domain_closure_policy=domain_closure_policy_for_ref_projection(opaque_launch_context),
    )
    domain_runtime_projection = _build_domain_runtime_projection(
        opaque_launch_context=opaque_launch_context,
        context=context,
        projection=projection,
    )
    if isinstance(domain_runtime_projection, Mapping):
        hot_refs = _union_hot_artifact_refs(hot_refs, domain_runtime_projection)
    return _assemble_prompt_document(
        mode=mode,
        doctrine_blocks=doctrine_blocks_document(composed_input),
        surface_packet=surface_packet_document(composed_input),
        run_context=_build_run_context(
            visible_launch_context,
            context,
            projection,
            hot_refs=hot_refs,
            hot_latest_ref_keys=hot_latest_ref_keys,
            domain_runtime_projection=domain_runtime_projection,
        ),
        structured_state=_build_structured_state(
            context,
            journal_verbatim_keep_n,
            closure_policy=visible_launch_context.get("domain_closure_policy"),
            hot_refs=hot_refs,
            opaque_launch_context=opaque_launch_context,
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
    *,
    hot_refs: frozenset[str],
    hot_latest_ref_keys: frozenset[str],
    domain_runtime_projection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cont = context.loop_memory.continuity
    hitl_pend, hitl_ans, hitl_st = hitl_prompt_visible_slice(context.loop_memory.hitl)
    run_context: dict[str, Any] = {
        "iteration": context.loop_memory.iterations,
        "session_id": context.session_id,
        "request_id_prefix": context.request_id_prefix,
        "launch_context": dict(visible_launch_context),
        "latest_refs": project_refs_map_for_prompt(
            cont.latest_refs,
            hot_refs=hot_refs,
            hot_latest_ref_keys=hot_latest_ref_keys,
        ),
        "active_item_id": cont.active_item_id,
        "state_patch_feedback": dict(cont.state_patch_feedback),
        "hitl_state": hitl_st,
        "projection": projection_document(
            projection,
            state_patch_feedback=cont.state_patch_feedback,
            hot_refs=hot_refs,
            hot_latest_ref_keys=hot_latest_ref_keys,
        ),
    }
    if isinstance(domain_runtime_projection, Mapping) and domain_runtime_projection:
        # Opaque domain lane — harness does not interpret contents.
        run_context["domain_runtime_projection"] = dict(domain_runtime_projection)
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


def _prompt_ref_projection_context(
    context: OrchestratorContext,
    projection: SharedStateProjection | None,
    *,
    domain_closure_policy: Mapping[str, Any] | None,
) -> tuple[frozenset[str], frozenset[str]]:
    cont = context.loop_memory.continuity
    from .pinned_refs import build_pinned_refs_projection

    pinned_projection = build_pinned_refs_projection(
        cont.pinned_refs,
        current_turn=int(context.loop_memory.iterations),
    )
    resolution_items: list[dict[str, Any]] = []
    active_item_id = cont.active_item_id
    latest_refs = dict(cont.latest_refs)
    if projection is not None:
        active_item_id = projection.active_item_id or active_item_id
        latest_refs = dict(projection.latest_refs)
        for item in projection.resolution_state.items:
            payload = jsonable(item)
            if isinstance(payload, dict):
                resolution_items.append(payload)
    hot_latest_ref_keys = build_hot_latest_ref_keys(
        domain_closure_policy=domain_closure_policy,
        latest_refs=latest_refs,
    )
    hot_refs = collect_hot_refs_for_prompt(
        latest_refs=latest_refs,
        pinned_refs_projection=pinned_projection,
        agent_requested_hydration=_build_agent_requested_hydration(cont.pending_agent_hydration),
        recent_action_sequence_result=cont.recent_action_sequence_result,
        delegate_subtask_results=cont.delegate_subtask_results,
        resolution_items=resolution_items,
        active_item_id=active_item_id,
        hot_latest_ref_keys=hot_latest_ref_keys,
    )
    return hot_refs, hot_latest_ref_keys


def _build_structured_state(
    context: OrchestratorContext,
    journal_verbatim_keep_n: int,
    *,
    closure_policy: Mapping[str, Any] | None,
    hot_refs: frozenset[str],
    opaque_launch_context: Mapping[str, Any] | None = None,
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
                delegate_observation_worklist_reminder=delegate_observation_reminder_from_context(
                    opaque_launch_context,
                ),
                claim_inventory_pressure_enabled=_claim_inventory_pressure_from_launch_context(
                    opaque_launch_context,
                ),
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
        structured["recent_tool_result_slices"] = project_recent_tool_result_slices_for_prompt(
            tool_result_slices,
            current_turn=int(context.loop_memory.iterations),
            hot_refs=hot_refs,
        )
    pending_hydration = _build_agent_requested_hydration(cont.pending_agent_hydration)
    if pending_hydration is not None:
        structured["agent_requested_hydration"] = pending_hydration
    sequence_lane = project_recent_action_sequence_for_prompt(
        cont.recent_action_sequence_result,
        current_turn=int(context.loop_memory.iterations),
        hot_refs=hot_refs,
    )
    if sequence_lane is not None:
        structured["recent_action_sequence_result"] = sequence_lane
    from .subtasks.delegate_result_refs import project_recent_delegate_results_for_prompt

    feedback = cont.state_patch_feedback if isinstance(cont.state_patch_feedback, Mapping) else {}
    repair_bundle = (
        feedback.get("state_patch_repair_bundle")
        if isinstance(feedback.get("state_patch_repair_bundle"), Mapping)
        else None
    )
    delegate_lane = project_recent_delegate_results_for_prompt(
        cont.delegate_subtask_results,
        current_turn=int(context.loop_memory.iterations),
        hot_refs=hot_refs,
        mission_state=cont.mission_state.model_dump(mode="json"),
        resolution_state=cont.resolution_state.model_dump(mode="json"),
        repair_bundle=repair_bundle,
    )
    if delegate_lane is not None:
        structured["recent_delegate_results"] = delegate_lane
    from .pinned_refs import build_pinned_refs_projection

    pinned_projection = build_pinned_refs_projection(
        cont.pinned_refs,
        current_turn=int(context.loop_memory.iterations),
    )
    if pinned_projection.get("active") or pinned_projection.get("expired"):
        structured["pinned_refs"] = pinned_projection
    pinned_hydration = _build_pinned_refs_hydration(cont.pinned_refs_hydration)
    if pinned_hydration is not None:
        structured["pinned_refs_hydration"] = pinned_hydration
    from ..memory.stable_context import build_stable_context_projection

    stable_projection = build_stable_context_projection(
        cont.stable_context,
        current_turn=int(context.loop_memory.iterations),
    )
    if stable_projection is not None:
        structured["stable_context"] = stable_projection
    return structured


def _build_pinned_refs_hydration(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    out: dict[str, Any] = {
        "refs": list(record.get("refs") or []),
        "status": str(record.get("status") or ""),
    }
    hydrated = record.get("hydrated_results")
    if isinstance(hydrated, list) and hydrated:
        out["hydrated_results"] = hydrated[:5]
    errors = record.get("hydration_errors")
    if isinstance(errors, list) and errors:
        out["hydration_errors"] = errors[:5]
    return out


def _build_agent_requested_hydration(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """One-shot prompt-visible projection of a pending hydrate_next record.

    Returns ``None`` when there is no record.  Otherwise emits a compact view
    with the requested refs, resolved refs, optional reason, any compact
    resolution/dispatch errors, and the bounded hydrated payload (results +
    errors as returned by ``hydrate_artifact_refs``).  This is host-owned
    transport; the orchestrator drops the record after surface.
    """
    if not record:
        return None
    out: dict[str, Any] = {
        "source_turn_index": int(record.get("source_turn_index") or 0),
        "requested_refs": list(record.get("requested_refs") or []),
        "resolved_refs": list(record.get("resolved_refs") or []),
    }
    reason = record.get("reason")
    if isinstance(reason, str) and reason:
        out["reason"] = reason
    errors = record.get("errors") or []
    if errors:
        out["errors"] = list(errors)
    hydrated_results = record.get("hydrated_results")
    if hydrated_results is not None:
        out["hydrated_results"] = list(hydrated_results)
    hydration_errors = record.get("hydration_errors")
    if hydration_errors:
        out["hydration_errors"] = list(hydration_errors)
    return out


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
    "motion_posture",
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
    "performance_evaluation",
    "state_patch_repair_bundle",
    "atom_evidence_worklist",
    "delegate_observation_worklist",
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
    "post_write_artifact_consistency_check_count",
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
    "artifact_state_dirty_since_write_count",
    "multi_action_turn_count",
    "single_action_turn_count",
    "max_actions_in_turn",
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
    motion_basis = full_summary.get("motion_posture_basis")
    if isinstance(motion_basis, str) and motion_basis.strip():
        compact["motion_posture_basis"] = motion_basis.strip()

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

    # User-to-agent message ledger projection — include only when non-empty.
    # Counters surface as compact metrics for the prompt observability layer.
    user_messages = full_summary.get("recent_user_messages") or []
    if user_messages:
        compact["recent_user_messages"] = list(user_messages)
    for key in (
        "user_message_pending_count",
        "user_message_consumed_count",
        "user_message_deferred_count",
        "user_message_consumed_unknown_count",
    ):
        val = full_summary.get(key)
        if val:  # drop None and 0
            compact[key] = val

    worklist = full_summary.get("atom_evidence_worklist")
    if isinstance(worklist, Mapping):
        compact_worklist = compact_atom_evidence_worklist_for_prompt(worklist)
        if compact_worklist is not None:
            compact["atom_evidence_worklist"] = compact_worklist
        elif "atom_evidence_worklist" in compact:
            del compact["atom_evidence_worklist"]

    delegate_worklist = full_summary.get("delegate_observation_worklist")
    if isinstance(delegate_worklist, Mapping):
        compact_delegate_worklist = compact_delegate_observation_worklist_for_prompt(
            delegate_worklist
        )
        if compact_delegate_worklist is not None:
            compact["delegate_observation_worklist"] = compact_delegate_worklist
        elif "delegate_observation_worklist" in compact:
            del compact["delegate_observation_worklist"]

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
    prompt_budget = build_prompt_budget_report(
        instruction_text=spec.instruction_text,
        prompt_body=prompt_body,
    )
    return PromptBuildDocument(
        mode=mode,
        call_phase=spec.call_phase,
        instruction_text=spec.instruction_text,
        prompt_body=prompt_body,
        prompt_text=prompt_text,
        prompt_budget=prompt_budget,
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
