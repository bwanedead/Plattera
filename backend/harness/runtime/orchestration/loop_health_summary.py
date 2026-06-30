"""Host-authored loop-health facts for prompt observability.

These summaries are mechanical only. They expose prompt/turn cadence facts to the
model and to operators without deciding semantic meaning or choosing the next
move on the agent's behalf.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from ..hitl.exchange_ledger import build_prompt_ledger_view
from ..user_messages.ledger import (
    build_prompt_user_message_view,
    count_consumed as _count_user_messages_consumed,
    count_deferred as _count_user_messages_deferred,
    count_pending as _count_user_messages_pending,
)
from ..memory import LoopMemoryState
from ..memory.tool_result_slices import check_outputs_excerpt_truncated
from ..memory.atom_evidence_worklist_projection import (
    build_atom_evidence_worklist_for_prompt,
    resolution_state_as_mapping,
)
from ..memory.delegate_observation_worklist_projection import (
    build_delegate_observation_worklist_for_prompt,
    repair_bundle_from_feedback,
    state_as_mapping,
)
from ..memory.performance_evaluation import build_performance_evaluation
from .evidence_locality import (
    BROAD_IMAGE_AREA_THRESHOLD,
    count_earned_exact_units_with_broad_image_locator,
)
from .state_patch_repair_bundle import project_state_patch_repair_bundle_for_prompt


def _closure_bool(closure_state: Any, field: str) -> bool:
    if isinstance(closure_state, Mapping):
        return bool(closure_state.get(field))
    return bool(getattr(closure_state, field, False))


def build_prompt_observability_summary(
    loop_memory: LoopMemoryState,
    *,
    closure_policy: Mapping[str, Any] | None = None,
    turn_records: list[dict[str, Any]] | None = None,
    delegate_observation_worklist_reminder: str | None = None,
    claim_inventory_pressure_enabled: bool = False,
) -> dict[str, Any]:
    """Return host-owned loop-health facts safe to expose in prompts and audits."""
    telemetry = loop_memory.telemetry
    cont = loop_memory.continuity
    step_records = list(cont.kernel_step_records)
    step_result_records = list(getattr(cont, "kernel_step_result_records", ()) or ())
    resolution_items = list(getattr(cont.resolution_state, "items", ()) or ())
    resolution_relations = list(getattr(cont.resolution_state, "relations", ()) or ())
    success_conditions = list(getattr(cont.mission_state, "success_conditions", ()) or ())
    closure_state = cont.mission_state.closure_state
    closure_dimensions = list(getattr(closure_state, "dimensions", ()) or ())
    work_universe_posture = _as_optional_text(getattr(cont.mission_state, "work_universe_posture", None)) or "initial"
    motion_posture = _as_optional_text(getattr(cont.mission_state, "motion_posture", None)) or "inventory"
    motion_posture_basis = _as_optional_text(getattr(cont.mission_state, "motion_posture_basis", None))
    feedback = dict(cont.state_patch_feedback) if isinstance(cont.state_patch_feedback, Mapping) else {}
    relation_index = _relation_index(resolution_relations)
    sequence_metrics = _sequence_metrics(resolution_items)

    closed_items_count = sum(1 for row in resolution_items if _is_closed_status(getattr(row, "status", None)))
    atomic_item_count = sum(
        1 for row in resolution_items if _as_optional_text(getattr(row, "structure_kind", None)) == "atomic"
    )
    group_item_count = sum(
        1 for row in resolution_items if _as_optional_text(getattr(row, "structure_kind", None)) == "group"
    )
    group_items_without_subclaims_count = sum(
        1
        for row in resolution_items
        if _as_optional_text(getattr(row, "structure_kind", None)) == "group"
        and not _group_item_has_subclaims(
            str(getattr(row, "item_id", "") or ""),
            relation_index=relation_index,
        )
        and not bool(getattr(row, "covered_units", ()) or ())
    )
    items_blocking_count = sum(
        1 for row in resolution_items if bool(getattr(row, "blocking", False))
    )
    items_requires_hitl_count = sum(
        1 for row in resolution_items if bool(getattr(row, "requires_hitl", False))
    )
    items_no_further_progress_count = sum(
        1 for row in resolution_items if bool(getattr(row, "no_further_progress", False))
    )
    closed_items_without_earned_determination_count = sum(
        1
        for row in resolution_items
        if _is_closed_status(getattr(row, "status", None))
        and not _has_earned_determination(getattr(row, "determination", None))
    )
    closed_items_without_basis_count = sum(
        1
        for row in resolution_items
        if _is_closed_status(getattr(row, "status", None))
        and not _has_text(getattr(row, "verification_basis", None))
    )
    closed_items_without_completion_criteria_count = sum(
        1
        for row in resolution_items
        if _is_closed_status(getattr(row, "status", None))
        and not _has_text(getattr(row, "completion_criteria", None))
    )
    critical_closed_items_without_evidence_count = sum(
        1
        for row in resolution_items
        if _is_closed_status(getattr(row, "status", None))
        and _materiality(getattr(row, "materiality", None)) == "critical"
        and not bool(getattr(row, "evidence_refs", ()) or ())
    )
    critical_closed_items_without_verification_basis_count = sum(
        1
        for row in resolution_items
        if _is_closed_status(getattr(row, "status", None))
        and _materiality(getattr(row, "materiality", None)) == "critical"
        and not _has_text(getattr(row, "verification_basis", None))
    )
    blocking_items_without_relations_count = sum(
        1
        for row in resolution_items
        if bool(getattr(row, "blocking", False))
        and not _item_has_any_relation(
            str(getattr(row, "item_id", "") or ""),
            relation_index=relation_index,
        )
    )
    closed_dimensions_without_earned_determination_count = sum(
        1
        for row in closure_dimensions
        if _is_closed_status(getattr(row, "status", None))
        and not _has_earned_determination(getattr(row, "determination", None))
    )
    closed_dimensions_without_basis_count = sum(
        1
        for row in closure_dimensions
        if _is_closed_status(getattr(row, "status", None))
        and not _has_text(getattr(row, "verification_basis", None))
    )
    repeated_state_patch_reason_code_streak = _as_int(feedback.get("same_reason_code_streak")) or 0
    turns_since_last_state_patch_applied = _turns_since_last_state_patch_applied(
        feedback, current_iteration=int(loop_memory.iterations)
    )
    consecutive_same_active_item_turns = _consecutive_same_active_item_turns(
        step_records,
        current_active_item_id=cont.active_item_id or cont.resolution_state.active_item_id,
    )
    turns_since_resolution_item_count_change = _turns_since_resolution_item_count_change(
        step_records,
        current_count=len(resolution_items),
    )
    new_resolution_items_since_last_complete_run_attempt = _new_resolution_items_since_last_complete_run_attempt(
        step_records,
        current_count=len(resolution_items),
    )
    repeated_complete_run_without_state_change_count = _repeated_complete_run_without_state_change_count(
        step_records
    )
    same_ref_bundle_reread_no_gain_streak = _same_ref_bundle_reread_no_gain_streak(step_records)
    same_item_same_ref_bundle_stall_streak = _same_item_same_ref_bundle_stall_streak(step_records)
    same_item_hydrate_churn_no_gain_streak = _same_item_hydrate_churn_no_gain_streak(step_records)
    artifact_refresh_trap_risk_count = _artifact_refresh_trap_risk(step_records)
    recent_result_truncated_count = _recent_result_truncated_count(step_result_records, last_n=3)
    semantic_repair_debt_kinds_early = _semantic_repair_debt_kinds(feedback)
    pending_hitl_integration_ids_early = _pending_hitl_integration_ids(feedback)
    repair_ready_without_artifact_write_count = _repair_ready_without_artifact_write(
        step_records,
        semantic_repair_debt_kinds=semantic_repair_debt_kinds_early,
        pending_hitl_integration_ids=pending_hitl_integration_ids_early,
        artifact_refresh_trap_risk_count=artifact_refresh_trap_risk_count,
        feedback=feedback,
    )
    pending_hitl_requests = list(getattr(loop_memory.hitl, "pending_hitl_requests", ()) or ())
    hitl_evidence_readiness_debt_count = _hitl_evidence_readiness_debt(
        step_records,
        step_result_records,
        pending_hitl_requests=pending_hitl_requests,
    )
    post_hitl_spin_count = _post_hitl_spin_count(step_records)
    post_write_artifact_consistency_check_count = _post_write_artifact_consistency_check_count(
        step_records
    )
    artifact_state_dirty_since_write_count = _artifact_state_dirty_since_write_count(step_records)
    substantial_artifact_output_count = _substantial_artifact_output_count(
        step_result_records,
        last_n=3,
    )

    # Build status maps for the dependency open-check (structural only).
    items_status_by_id: dict[str, str] = {
        str(getattr(row, "item_id", "") or ""): str(getattr(row, "status", "") or "")
        for row in resolution_items
    }
    _closed_ids = {iid for iid, st in items_status_by_id.items() if _is_closed_status(st)}
    _open_ids = {iid for iid in items_status_by_id if iid not in _closed_ids}
    # Closed items reachable as a target from an open item via blocking relation types.
    _blocking_relation_types = {"blocks", "prerequisite_of"}
    _closed_targets_of_open_blockers: set[str] = {
        str(getattr(rel, "target_item_id", "") or "")
        for rel in resolution_relations
        if (
            _as_optional_text(getattr(rel, "relation_type", None)) or ""
        ).lower() in _blocking_relation_types
        and str(getattr(rel, "source_item_id", "") or "") in _open_ids
        and str(getattr(rel, "target_item_id", "") or "") in _closed_ids
    }
    closed_items_with_open_dependencies_count = sum(
        1
        for row in resolution_items
        if _is_closed_status(getattr(row, "status", None))
        and (
            # Via explicit dependencies list
            any(
                not _is_closed_status(items_status_by_id.get(str(dep or ""), ""))
                for dep in (getattr(row, "dependencies", None) or ())
                if str(dep or "").strip()
            )
            # Via resolution.relations: an open item blocks/prerequisite_of this closed item
            or str(getattr(row, "item_id", "") or "") in _closed_targets_of_open_blockers
        )
    )
    # Explicitly non-blocking items with no notes or verification basis — structural shape flag.
    explicit_non_blocking_without_notes_count = sum(
        1
        for row in resolution_items
        if getattr(row, "blocking", None) is False
        and not _has_text(getattr(row, "notes", None))
        and not _has_text(getattr(row, "verification_basis", None))
    )
    notebook_shaped_graph_rows_count = _notebook_shaped_graph_rows_count(resolution_items)

    covered_units_metrics = _covered_units_metrics(resolution_items)
    earned_exact_with_broad_image_locator_count = count_earned_exact_units_with_broad_image_locator(
        resolution_items, area_threshold=BROAD_IMAGE_AREA_THRESHOLD
    )
    hitl_answerability_metrics = _hitl_answerability_metrics(resolution_items)
    earned_before_local_evidence_count = len(
        getattr(cont, "earned_before_local_evidence_debt", None) or {}
    )
    posthoc_recheck_needed_count = len(
        getattr(cont, "posthoc_recheck_needed_debt", None) or {}
    )
    # HITL ledger metrics (Track 4 of HITL Exchange Ledger brief).
    hitl_ledger_raw = getattr(cont, "hitl_exchange_ledger", None) or []
    hitl_ledger_metrics = _hitl_ledger_metrics(
        ledger=hitl_ledger_raw,
        step_records=step_records,
        consumed_unknown_count=int(getattr(cont, "hitl_consumed_unknown_prompt_count", 0) or 0),
    )
    # Track 3: bounded prompt projection — pending + answered exchanges with full
    # request and response payloads so the agent can integrate them faithfully.
    recent_hitl_exchanges = build_prompt_ledger_view(hitl_ledger_raw)

    # User-to-agent message ledger projection + counters.  Generic mechanics
    # only — domain decides how to interpret messages.
    user_message_ledger_raw = getattr(cont, "user_message_ledger", None) or []
    recent_user_messages = build_prompt_user_message_view(user_message_ledger_raw)
    user_message_pending_count = _count_user_messages_pending(user_message_ledger_raw)
    user_message_consumed_count = _count_user_messages_consumed(user_message_ledger_raw)
    user_message_deferred_count = _count_user_messages_deferred(user_message_ledger_raw)
    user_message_consumed_unknown_count = int(
        getattr(cont, "user_message_consumed_unknown_count", 0) or 0
    )
    closure_ready_to_close = _closure_bool(closure_state, "ready_to_close")
    artifact_claim_inventory_suspect_count = _artifact_claim_inventory_suspect_count(
        closure_ready_to_close=closure_ready_to_close,
        work_universe_posture=work_universe_posture,
        substantial_artifact_output_count=substantial_artifact_output_count,
        atomic_item_count=atomic_item_count,
        covered_unit_count=covered_units_metrics["covered_unit_count"],
    )

    closure_readiness_projection = _closure_readiness_projection(
        closure_policy=closure_policy,
        closure_state=closure_state,
        resolution_item_count=len(resolution_items),
        work_universe_posture=work_universe_posture,
        feedback=feedback,
        closed_items_without_earned_determination_count=closed_items_without_earned_determination_count,
        closed_items_without_basis_count=closed_items_without_basis_count,
        closed_dimensions_without_earned_determination_count=closed_dimensions_without_earned_determination_count,
        closed_dimensions_without_basis_count=closed_dimensions_without_basis_count,
        items_requires_hitl_count=items_requires_hitl_count,
    )
    from harness.runtime.orchestration.completion_anchor import (
        apply_completion_anchor_to_closure_readiness,
        evaluate_completion_anchor,
    )

    completion_anchor = evaluate_completion_anchor(
        closure_policy=closure_policy,
        latest_refs=cont.latest_refs,
        step_result_records=step_result_records,
    )
    if completion_anchor is not None:
        closure_readiness_projection = apply_completion_anchor_to_closure_readiness(
            closure_readiness_projection,
            anchor=completion_anchor,
            closure_policy=closure_policy,
        )

    summary = {
        "prompt_event_count": int(telemetry.prompt_event_count),
        "last_prompt_event_id": telemetry.last_prompt_event_id,
        "last_prompt_event_surface": telemetry.last_prompt_event_surface,
        "consecutive_no_dispatch_turns": _consecutive_no_dispatch_turns(step_records),
        "turns_since_last_tool_execution": _turns_since_last_tool_execution(step_records),
        "turns_since_latest_refs_change": _turns_since_latest_refs_change(step_records),
        "last_state_patch_outcome": _as_optional_text(feedback.get("outcome")),
        "last_state_patch_reason_code": _as_optional_text(feedback.get("reason_code")),
        "work_universe_posture": work_universe_posture,
        "motion_posture": motion_posture,
        "motion_posture_basis": motion_posture_basis,
        "repeated_state_patch_reason_code_streak": repeated_state_patch_reason_code_streak,
        "turns_since_last_state_patch_applied": turns_since_last_state_patch_applied,
        "consecutive_same_active_item_turns": consecutive_same_active_item_turns,
        "turns_since_resolution_item_count_change": turns_since_resolution_item_count_change,
        "new_resolution_items_since_last_complete_run_attempt": new_resolution_items_since_last_complete_run_attempt,
        "repeated_complete_run_without_state_change_count": repeated_complete_run_without_state_change_count,
        "same_ref_bundle_reread_no_gain_streak": same_ref_bundle_reread_no_gain_streak,
        "same_item_same_ref_bundle_stall_streak": same_item_same_ref_bundle_stall_streak,
        "same_item_hydrate_churn_no_gain_streak": same_item_hydrate_churn_no_gain_streak,
        "artifact_refresh_trap_risk_count": artifact_refresh_trap_risk_count,
        "repair_ready_without_artifact_write_count": repair_ready_without_artifact_write_count,
        "hitl_evidence_readiness_debt_count": hitl_evidence_readiness_debt_count,
        "post_hitl_spin_count": post_hitl_spin_count,
        "post_write_artifact_consistency_check_count": post_write_artifact_consistency_check_count,
        "recent_result_truncated_count": recent_result_truncated_count,
        "substantial_artifact_output_count": substantial_artifact_output_count,
        "covered_unit_count": covered_units_metrics["covered_unit_count"],
        "covered_units_with_candidates_count": covered_units_metrics["covered_units_with_candidates_count"],
        "closed_candidate_units_missing_determined_value_count": covered_units_metrics[
            "closed_candidate_units_missing_determined_value_count"
        ],
        "closed_value_units_missing_evidence_count": covered_units_metrics[
            "closed_value_units_missing_evidence_count"
        ],
        "earned_units_missing_verification_basis_count": covered_units_metrics[
            "earned_units_missing_verification_basis_count"
        ],
        "earned_units_missing_locator_count": covered_units_metrics[
            "earned_units_missing_locator_count"
        ],
        "shared_unlocated_evidence_for_earned_units_count": covered_units_metrics[
            "shared_unlocated_evidence_for_earned_units_count"
        ],
        "long_determined_value_units_count": covered_units_metrics[
            "long_determined_value_units_count"
        ],
        "earned_before_local_evidence_count": earned_before_local_evidence_count,
        "posthoc_recheck_needed_count": posthoc_recheck_needed_count,
        "earned_exact_with_broad_image_locator_count": earned_exact_with_broad_image_locator_count,
        "blocked_without_hitl_answerability_count": hitl_answerability_metrics[
            "blocked_without_hitl_answerability_count"
        ],
        "human_answerable_blocker_without_hitl_count": hitl_answerability_metrics[
            "human_answerable_blocker_without_hitl_count"
        ],
        "not_answerable_missing_reason_count": hitl_answerability_metrics[
            "not_answerable_missing_reason_count"
        ],
        "answered_hitl_unconsumed_count": hitl_ledger_metrics["answered_hitl_unconsumed_count"],
        "complete_with_unconsumed_hitl_count": hitl_ledger_metrics["complete_with_unconsumed_hitl_count"],
        "hitl_consumed_unknown_prompt_count": hitl_ledger_metrics["hitl_consumed_unknown_prompt_count"],
        "artifact_state_dirty_since_write_count": artifact_state_dirty_since_write_count,
        "recent_hitl_exchanges": recent_hitl_exchanges,
        "recent_user_messages": recent_user_messages,
        "user_message_pending_count": user_message_pending_count,
        "user_message_consumed_count": user_message_consumed_count,
        "user_message_deferred_count": user_message_deferred_count,
        "user_message_consumed_unknown_count": user_message_consumed_unknown_count,
        "success_condition_count": len(success_conditions),
        "success_conditions_with_earned_determination_count": sum(
            1 for row in success_conditions if _has_earned_determination(getattr(row, "determination", None))
        ),
        "success_conditions_with_verification_basis_count": sum(
            1 for row in success_conditions if _has_text(getattr(row, "verification_basis", None))
        ),
        "resolution_item_count": len(resolution_items),
        "sequenced_item_count": sequence_metrics["sequenced_item_count"],
        "sequenced_items_missing_scope_count": sequence_metrics["sequenced_items_missing_scope_count"],
        "sequenced_items_missing_index_count": sequence_metrics["sequenced_items_missing_index_count"],
        "duplicate_sequence_positions_count": sequence_metrics["duplicate_sequence_positions_count"],
        "sequence_scope_order_gaps_count": sequence_metrics["sequence_scope_order_gaps_count"],
        "atomic_item_count": atomic_item_count,
        "group_item_count": group_item_count,
        "group_items_without_subclaims_count": group_items_without_subclaims_count,
        "items_with_evidence_count": sum(
            1 for row in resolution_items if bool(getattr(row, "evidence_refs", ()) or ())
        ),
        "items_with_verification_basis_count": sum(
            1 for row in resolution_items if _has_text(getattr(row, "verification_basis", None))
        ),
        "items_blocking_count": items_blocking_count,
        "items_requires_hitl_count": items_requires_hitl_count,
        "items_no_further_progress_count": items_no_further_progress_count,
        "closed_items_count": closed_items_count,
        "closed_items_without_earned_determination_count": closed_items_without_earned_determination_count,
        "closed_items_without_basis_count": closed_items_without_basis_count,
        "closed_items_without_completion_criteria_count": closed_items_without_completion_criteria_count,
        "critical_closed_items_without_evidence_count": critical_closed_items_without_evidence_count,
        "critical_closed_items_without_verification_basis_count": (
            critical_closed_items_without_verification_basis_count
        ),
        "blocking_items_without_relations_count": blocking_items_without_relations_count,
        "closure_dimension_count": len(closure_dimensions),
        "closure_dimensions_with_earned_determination_count": sum(
            1 for row in closure_dimensions if _has_earned_determination(getattr(row, "determination", None))
        ),
        "closed_dimensions_without_earned_determination_count": closed_dimensions_without_earned_determination_count,
        "closed_dimensions_without_basis_count": closed_dimensions_without_basis_count,
        "closed_items_with_open_dependencies_count": closed_items_with_open_dependencies_count,
        "explicit_non_blocking_without_notes_count": explicit_non_blocking_without_notes_count,
        "notebook_shaped_graph_rows_count": notebook_shaped_graph_rows_count,
        "artifact_claim_inventory_suspect_count": artifact_claim_inventory_suspect_count,
        "closure_readiness_projection": closure_readiness_projection,
        "completion_anchor": closure_readiness_projection.get("completion_anchor"),
        "multi_action_turn_count": int(getattr(cont, "multi_action_turn_count", 0) or 0),
        "single_action_turn_count": int(getattr(cont, "single_action_turn_count", 0) or 0),
        "max_actions_in_turn": int(getattr(cont, "max_actions_in_turn", 0) or 0),
    }
    reread_after_failed_persist = _reread_after_failed_persist(
        feedback=feedback, step_records=step_records
    )
    summary["semantic_repair_debt"] = list(semantic_repair_debt_kinds_early)
    summary["pending_hitl_integration_prompt_ids"] = list(pending_hitl_integration_ids_early)

    summary["mechanical_flags"] = _mechanical_flags(
        feedback=feedback,
        success_condition_count=len(success_conditions),
        resolution_item_count=len(resolution_items),
        closure_ready_to_close=closure_ready_to_close,
        work_universe_posture=work_universe_posture,
        atomic_item_count=atomic_item_count,
        covered_unit_count=covered_units_metrics["covered_unit_count"],
        repeated_state_patch_reason_code_streak=repeated_state_patch_reason_code_streak,
        consecutive_same_active_item_turns=consecutive_same_active_item_turns,
        turns_since_resolution_item_count_change=turns_since_resolution_item_count_change,
        new_resolution_items_since_last_complete_run_attempt=new_resolution_items_since_last_complete_run_attempt,
        repeated_complete_run_without_state_change_count=repeated_complete_run_without_state_change_count,
        same_ref_bundle_reread_no_gain_streak=same_ref_bundle_reread_no_gain_streak,
        same_item_same_ref_bundle_stall_streak=same_item_same_ref_bundle_stall_streak,
        same_item_hydrate_churn_no_gain_streak=same_item_hydrate_churn_no_gain_streak,
        artifact_refresh_trap_risk_count=artifact_refresh_trap_risk_count,
        repair_ready_without_artifact_write_count=repair_ready_without_artifact_write_count,
        hitl_evidence_readiness_debt_count=hitl_evidence_readiness_debt_count,
        post_hitl_spin_count=post_hitl_spin_count,
        post_write_artifact_consistency_check_count=post_write_artifact_consistency_check_count,
        recent_result_truncated_count=recent_result_truncated_count,
        artifact_claim_inventory_suspect_count=artifact_claim_inventory_suspect_count,
        closed_candidate_units_missing_determined_value_count=covered_units_metrics[
            "closed_candidate_units_missing_determined_value_count"
        ],
        closed_value_units_missing_evidence_count=covered_units_metrics[
            "closed_value_units_missing_evidence_count"
        ],
        earned_units_missing_verification_basis_count=covered_units_metrics[
            "earned_units_missing_verification_basis_count"
        ],
        earned_units_missing_locator_count=covered_units_metrics[
            "earned_units_missing_locator_count"
        ],
        shared_unlocated_evidence_for_earned_units_count=covered_units_metrics[
            "shared_unlocated_evidence_for_earned_units_count"
        ],
        long_determined_value_units_count=covered_units_metrics[
            "long_determined_value_units_count"
        ],
        sequenced_items_missing_scope_count=sequence_metrics["sequenced_items_missing_scope_count"],
        sequenced_items_missing_index_count=sequence_metrics["sequenced_items_missing_index_count"],
        duplicate_sequence_positions_count=sequence_metrics["duplicate_sequence_positions_count"],
        sequence_scope_order_gaps_count=sequence_metrics["sequence_scope_order_gaps_count"],
        group_items_without_subclaims_count=group_items_without_subclaims_count,
        critical_closed_items_without_evidence_count=critical_closed_items_without_evidence_count,
        critical_closed_items_without_verification_basis_count=(
            critical_closed_items_without_verification_basis_count
        ),
        blocking_items_without_relations_count=blocking_items_without_relations_count,
        closed_items_with_open_dependencies_count=closed_items_with_open_dependencies_count,
        explicit_non_blocking_without_notes_count=explicit_non_blocking_without_notes_count,
        notebook_shaped_graph_rows_count=notebook_shaped_graph_rows_count,
        complete_run_blockers=list(closure_readiness_projection.get("complete_run_blockers", ())),
        semantic_repair_debt_kinds=semantic_repair_debt_kinds_early,
        pending_hitl_integration_ids=pending_hitl_integration_ids_early,
        reread_after_failed_persist=reread_after_failed_persist,
        earned_before_local_evidence_count=earned_before_local_evidence_count,
        posthoc_recheck_needed_count=posthoc_recheck_needed_count,
        earned_exact_with_broad_image_locator_count=earned_exact_with_broad_image_locator_count,
        blocked_without_hitl_answerability_count=hitl_answerability_metrics[
            "blocked_without_hitl_answerability_count"
        ],
        human_answerable_blocker_without_hitl_count=hitl_answerability_metrics[
            "human_answerable_blocker_without_hitl_count"
        ],
        not_answerable_missing_reason_count=hitl_answerability_metrics[
            "not_answerable_missing_reason_count"
        ],
        answered_hitl_unconsumed_count=hitl_ledger_metrics["answered_hitl_unconsumed_count"],
        complete_with_unconsumed_hitl_count=hitl_ledger_metrics["complete_with_unconsumed_hitl_count"],
        hitl_consumed_unknown_prompt_count=hitl_ledger_metrics["hitl_consumed_unknown_prompt_count"],
        artifact_state_dirty_since_write_count=artifact_state_dirty_since_write_count,
        claim_inventory_pressure_enabled=claim_inventory_pressure_enabled,
        completion_anchor=closure_readiness_projection.get("completion_anchor"),
    )
    summary["performance_evaluation"] = build_performance_evaluation(
        loop_memory,
        turn_records=turn_records,
    )
    atom_worklist = build_atom_evidence_worklist_for_prompt(
        resolution_state=resolution_state_as_mapping(cont.resolution_state),
        recent_result_records=step_result_records,
        delegate_result_records=list(getattr(cont, "delegate_subtask_results", ()) or ()),
    )
    if atom_worklist is not None:
        summary["atom_evidence_worklist"] = atom_worklist
    delegate_obs_worklist = build_delegate_observation_worklist_for_prompt(
        delegate_result_records=list(getattr(cont, "delegate_subtask_results", ()) or ()),
        mission_state=state_as_mapping(cont.mission_state),
        resolution_state=resolution_state_as_mapping(cont.resolution_state),
        repair_bundle=repair_bundle_from_feedback(feedback),
        current_turn=int(loop_memory.iterations or 0),
        reminder=delegate_observation_worklist_reminder,
    )
    if delegate_obs_worklist is not None:
        summary["delegate_observation_worklist"] = delegate_obs_worklist
    repair_bundle_projection = project_state_patch_repair_bundle_for_prompt(feedback)
    if repair_bundle_projection:
        summary["state_patch_repair_bundle"] = repair_bundle_projection
    return summary


def _semantic_repair_debt_kinds(feedback: Mapping[str, Any]) -> list[str]:
    raw = feedback.get("semantic_repair_debt")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for value in raw:
        text = str(value).strip()
        if text and text not in out:
            out.append(text)
    return out


def _pending_hitl_integration_ids(feedback: Mapping[str, Any]) -> list[str]:
    raw = feedback.get("pending_hitl_integration_prompt_ids")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for value in raw:
        text = str(value).strip()
        if text and text not in out:
            out.append(text)
    return out


_READ_LIKE_ACTION_TYPES = frozenset(
    {"hydrate_artifact_refs", "hydrate_artifact_ref", "read_artifact", "fetch_artifact_refs"}
)


def _reread_after_failed_persist(
    *,
    feedback: Mapping[str, Any],
    step_records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Conservative mechanical signal.

    Fires when:
      - the last state_patch attempt either was rejected, was not_applied, or had
        skipped resolution rows, AND
      - the most recent step is a read/hydrate action.

    Does not inspect ref-bundle equality across multiple turns; that strictness is
    already covered by ``same_ref_bundle_reread_no_gain_streak``. The point of
    this flag is to make the *one-step* repair-before-reread expectation visible
    to the agent.
    """
    if not step_records:
        return None
    tail = step_records[-1]
    action_type = _as_optional_text(tail.get("action_type"))
    if action_type not in _READ_LIKE_ACTION_TYPES:
        return None
    outcome = _as_optional_text(feedback.get("outcome"))
    has_failed_persist = (
        outcome in ("rejected", "not_applied")
        or bool(feedback.get("skipped_resolution_rows"))
    )
    has_sticky_debt = bool(_semantic_repair_debt_kinds(feedback)) or bool(
        _pending_hitl_integration_ids(feedback)
    )
    if not (has_failed_persist or has_sticky_debt):
        return None
    return {
        "action_type": action_type,
        "feedback_outcome": outcome,
        "feedback_iteration": _as_int(feedback.get("iteration")),
        "context": "failed_persist" if has_failed_persist else "sticky_debt",
    }


def _consecutive_no_dispatch_turns(step_records: list[dict[str, Any]]) -> int:
    count = 0
    for row in reversed(step_records):
        if bool(row.get("skip_execution")):
            count += 1
            continue
        break
    return count


def _turns_since_last_tool_execution(step_records: list[dict[str, Any]]) -> int | None:
    turns = 0
    for row in reversed(step_records):
        if str(row.get("execution_state") or "") == "executed":
            return turns
        turns += 1
    return None


def _turns_since_latest_refs_change(step_records: list[dict[str, Any]]) -> int | None:
    if not step_records:
        return None
    latest_sig = _stable_signature(step_records[-1].get("latest_refs_snapshot"))
    trailing_same = 0
    for row in reversed(step_records):
        if _stable_signature(row.get("latest_refs_snapshot")) != latest_sig:
            break
        trailing_same += 1
    return max(0, trailing_same - 1)


def _turns_since_last_state_patch_applied(
    feedback: Mapping[str, Any],
    *,
    current_iteration: int,
) -> int | None:
    applied_iteration = _as_int(feedback.get("last_applied_iteration"))
    if applied_iteration is None:
        return None
    return max(0, current_iteration - applied_iteration)


def _consecutive_same_active_item_turns(
    step_records: list[dict[str, Any]],
    *,
    current_active_item_id: str | None,
) -> int:
    active_item_id = _as_optional_text(current_active_item_id)
    if active_item_id is None:
        return 0
    count = 0
    for row in reversed(step_records):
        if _as_optional_text(row.get("active_item_id_snapshot")) != active_item_id:
            break
        count += 1
    return count


def _turns_since_resolution_item_count_change(
    step_records: list[dict[str, Any]],
    *,
    current_count: int,
) -> int | None:
    if not step_records:
        return None
    count = 0
    for row in reversed(step_records):
        snap = _as_int(row.get("resolution_item_count_snapshot"))
        if snap is None:
            return None
        if snap != current_count:
            break
        count += 1
    return max(0, count - 1)


def _new_resolution_items_since_last_complete_run_attempt(
    step_records: list[dict[str, Any]],
    *,
    current_count: int,
) -> int:
    for row in reversed(step_records):
        if bool(row.get("complete_run")):
            snap = _as_int(row.get("resolution_item_count_snapshot"))
            if snap is None:
                return 0
            return max(0, current_count - snap)
    return 0


def _ref_bundle_signature_for_step(row: Mapping[str, Any]) -> str | None:
    action_type = _as_optional_text(row.get("action_type"))
    if action_type is None:
        return None
    inputs = row.get("action_inputs") if isinstance(row.get("action_inputs"), Mapping) else {}
    try:
        payload = json.dumps(
            {"action_type": action_type, "action_inputs": dict(inputs)},
            sort_keys=True,
            default=str,
            ensure_ascii=False,
        )
    except (TypeError, ValueError):
        return None
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]


def _same_ref_bundle_reread_no_gain_streak(step_records: list[dict[str, Any]]) -> int:
    """Trailing turns: same action+inputs fingerprint **and** unchanged refs **and** unchanged authored state.

    "No gain" requires that nothing moved: not the ref bundle, not the resolution/mission
    state signature. A run that keeps reading the same crop but is still closing subclaims
    each turn is progress, not spin — the `work_state_signature` changes and the streak resets.
    """
    if not step_records:
        return 0
    tail = step_records[-1]
    latest_sig = _ref_bundle_signature_for_step(tail)
    if latest_sig is None:
        return 0
    latest_refs_sig = _stable_signature(tail.get("latest_refs_snapshot"))
    latest_state_sig = _as_optional_text(tail.get("work_state_signature"))
    if latest_state_sig is None:
        return 0
    streak = 0
    for row in reversed(step_records):
        if _ref_bundle_signature_for_step(row) != latest_sig:
            break
        if _stable_signature(row.get("latest_refs_snapshot")) != latest_refs_sig:
            break
        if _as_optional_text(row.get("work_state_signature")) != latest_state_sig:
            break
        streak += 1
    return streak


def _same_item_same_ref_bundle_stall_streak(step_records: list[dict[str, Any]]) -> int:
    """Trailing turns: same active item + same action+inputs fingerprint + unchanged authored state + unchanged refs.

    A genuine stall is when nothing is moving. Repeated turns on the same item with the same
    ref bundle are fine if each turn closes a subclaim, updates a determination, or otherwise
    changes `work_state_signature`. Only flag when state and refs both stay frozen.
    """
    if not step_records:
        return 0
    tail = step_records[-1]
    latest_sig = _ref_bundle_signature_for_step(tail)
    if latest_sig is None:
        return 0
    active_item_id = _as_optional_text(tail.get("active_item_id_snapshot"))
    if active_item_id is None:
        return 0
    latest_state_sig = _as_optional_text(tail.get("work_state_signature"))
    if latest_state_sig is None:
        return 0
    latest_refs_sig = _stable_signature(tail.get("latest_refs_snapshot"))
    streak = 0
    for row in reversed(step_records):
        if _as_optional_text(row.get("active_item_id_snapshot")) != active_item_id:
            break
        if _ref_bundle_signature_for_step(row) != latest_sig:
            break
        if _as_optional_text(row.get("work_state_signature")) != latest_state_sig:
            break
        if _stable_signature(row.get("latest_refs_snapshot")) != latest_refs_sig:
            break
        streak += 1
    return streak


def _same_item_hydrate_churn_no_gain_streak(step_records: list[dict[str, Any]]) -> int:
    """Trailing turns: same active item + action_type=hydrate_artifact_refs + unchanged refs + unchanged state.

    Advisory signal for "rotating hydrate" churn — repeatedly hydrating refs on the
    same item without the ref bundle or work state advancing, and without any save
    happening in between. Purely structural: only inspects action_type, active item,
    refs snapshot, and work_state_signature.
    """
    if not step_records:
        return 0
    tail = step_records[-1]
    if _as_optional_text(tail.get("action_type")) != "hydrate_artifact_refs":
        return 0
    active_item_id = _as_optional_text(tail.get("active_item_id_snapshot"))
    if active_item_id is None:
        return 0
    latest_state_sig = _as_optional_text(tail.get("work_state_signature"))
    if latest_state_sig is None:
        return 0
    latest_refs_sig = _stable_signature(tail.get("latest_refs_snapshot"))
    streak = 0
    for row in reversed(step_records):
        if _as_optional_text(row.get("action_type")) != "hydrate_artifact_refs":
            break
        if _as_optional_text(row.get("active_item_id_snapshot")) != active_item_id:
            break
        if _as_optional_text(row.get("work_state_signature")) != latest_state_sig:
            break
        if _stable_signature(row.get("latest_refs_snapshot")) != latest_refs_sig:
            break
        streak += 1
    return streak


_ARTIFACT_REFRESH_TRAP_SAVE_LOOKBACK: int = 8
_ARTIFACT_REFRESH_TRAP_HYDRATE_THRESHOLD: int = 3
_ARTIFACT_REFRESH_TRAP_SAVE_ACTION_TYPES: frozenset[str] = frozenset(
    {"save_workspace_artifact", "copy_forward_save_workspace_artifact"}
)
_ARTIFACT_MATERIALIZE_ACTION_TYPES: frozenset[str] = frozenset(
    {"save_workspace_artifact", "copy_forward_save_workspace_artifact", "publish_workspace_artifact"}
)
_ARTIFACT_REFRESH_TRAP_WINDOW: int = 16
_ARTIFACT_REFRESH_TRAP_SAVE_LOOKBACK_WIDE: int = 20
_ARTIFACT_REFRESH_TRAP_SMALL_TARGET_SET_MAX: int = 4

_REPAIR_READY_WRITE_ACTION_TYPES: frozenset[str] = _ARTIFACT_REFRESH_TRAP_SAVE_ACTION_TYPES
_REPAIR_READY_MIN_NO_WRITE_TURNS: int = 3
_POST_HITL_SPIN_MIN_TURNS: int = 3
_HITL_EVIDENCE_READINESS_WINDOW: int = 5
_HITL_EVIDENCE_CONTEXT_KEYS: frozenset[str] = frozenset({
    "evidence_refs",
    "primary_evidence_ref",
    "annotated_evidence_ref",
    "rendered_evidence_refs",
    "question_regions",
})
_HITL_EVIDENCE_CAVEAT_KEYS: frozenset[str] = frozenset({
    "evidence_not_needed",
    "evidence_unavailable",
    "evidence_not_applicable",
})


def _artifact_refresh_trap_streak(step_records: list[dict[str, Any]]) -> int:
    """Simple consecutive hydrate streak after a recent save.

    Fires when the trailing turns are all hydrate_artifact_refs with unchanged refs
    and unchanged state, and a save exists in the immediately preceding lookback.
    Does not fire if any non-hydrate turn breaks the physical streak.
    """
    if not step_records:
        return 0
    tail = step_records[-1]
    if _as_optional_text(tail.get("action_type")) != "hydrate_artifact_refs":
        return 0
    tail_input_sig = _ref_bundle_signature_for_step(tail)
    if tail_input_sig is None:
        return 0
    latest_refs_sig = _stable_signature(tail.get("latest_refs_snapshot"))
    latest_state_sig = _as_optional_text(tail.get("work_state_signature"))
    if latest_state_sig is None:
        return 0

    streak = 0
    for row in reversed(step_records):
        if _as_optional_text(row.get("action_type")) != "hydrate_artifact_refs":
            break
        if _ref_bundle_signature_for_step(row) != tail_input_sig:
            break
        if _stable_signature(row.get("latest_refs_snapshot")) != latest_refs_sig:
            break
        if _as_optional_text(row.get("work_state_signature")) != latest_state_sig:
            break
        streak += 1

    if streak < _ARTIFACT_REFRESH_TRAP_HYDRATE_THRESHOLD:
        return 0

    pre_streak = step_records[: len(step_records) - streak]
    lookback = pre_streak[-_ARTIFACT_REFRESH_TRAP_SAVE_LOOKBACK:]
    if not any(
        _as_optional_text(row.get("action_type")) in _ARTIFACT_REFRESH_TRAP_SAVE_ACTION_TYPES
        for row in lookback
    ):
        return 0

    return streak


def _artifact_refresh_trap_windowed(step_records: list[dict[str, Any]]) -> int:
    """Windowed hydrate-churn detector — fires on same-target repeats and small-set cycling.

    Catches the run-10 interleaved trap: save → hydrate(A) → state_patch → hydrate(B) →
    state_patch → hydrate(A) → ... where the agent cycles over a small bounded set of
    recovery refs without producing new refs and without using copy_forward_save.
    State-only turns (state patches, no-dispatch) are invisible to the count.

    Two firing conditions (both require prior save and no escape tool in window):
    1. Trailing fruitless hydrate sub-streak: all trailing hydrate rows have the same
       latest_refs_snapshot as the most recent hydrate AND the same read-target signature.
    2. Cyclic small-set recovery: trailing fruitless hydrate rows (same latest_refs_snapshot)
       cycle over ≤ SMALL_TARGET_SET_MAX distinct read-target signatures and at least one
       target is repeated (len rows > len distinct sigs). Suppressed when every target appears
       exactly once — that is one-off post-save verification, not a recovery cycle.
    """
    if not step_records:
        return 0

    window = step_records[-_ARTIFACT_REFRESH_TRAP_WINDOW:]

    if any(
        _as_optional_text(row.get("action_type")) == "copy_forward_save_workspace_artifact"
        for row in window
    ):
        return 0

    hydrate_rows = [
        row for row in window
        if _as_optional_text(row.get("action_type")) == "hydrate_artifact_refs"
    ]

    if not hydrate_rows:
        return 0

    # Collect trailing fruitless hydrate rows: same latest_refs_snapshot as the most recent
    # hydrate means those reads produced no new refs.
    tail_ref_sig = _stable_signature(hydrate_rows[-1].get("latest_refs_snapshot"))
    fruitless_rows: list[dict[str, Any]] = []
    for row in reversed(hydrate_rows):
        if _stable_signature(row.get("latest_refs_snapshot")) != tail_ref_sig:
            break
        fruitless_rows.append(row)

    if len(fruitless_rows) < _ARTIFACT_REFRESH_TRAP_HYDRATE_THRESHOLD:
        return 0

    input_sigs = [_ref_bundle_signature_for_step(r) for r in fruitless_rows]
    distinct_sigs = {s for s in input_sigs if s is not None}

    if not distinct_sigs:
        return 0

    if len(distinct_sigs) > _ARTIFACT_REFRESH_TRAP_SMALL_TARGET_SET_MAX:
        # Too many distinct targets — broad exploration, not a focused recovery cycle.
        return 0

    if len(fruitless_rows) <= len(distinct_sigs):
        # Each target appeared exactly once — one-off post-save verification, not cycling.
        return 0

    wide_lookback = step_records[-_ARTIFACT_REFRESH_TRAP_SAVE_LOOKBACK_WIDE:]
    if not any(
        _as_optional_text(row.get("action_type")) in _ARTIFACT_REFRESH_TRAP_SAVE_ACTION_TYPES
        for row in wide_lookback
    ):
        return 0

    return len(fruitless_rows)


def _artifact_refresh_trap_risk(step_records: list[dict[str, Any]]) -> int:
    """Artifact-refresh trap risk: max of the simple streak and windowed hydrate-churn detectors.

    The streak detector catches the simplest form (consecutive hydrates after a save).
    The windowed detector catches the run-10 interleaved form (hydrates broken up by
    state patches, but still fruitless over the wider window).
    Purely structural — no ref content inspection, no domain knowledge.
    """
    return max(
        _artifact_refresh_trap_streak(step_records),
        _artifact_refresh_trap_windowed(step_records),
    )


def _repair_ready_without_artifact_write(
    step_records: list[dict[str, Any]],
    *,
    semantic_repair_debt_kinds: list[str],
    pending_hitl_integration_ids: list[str],
    artifact_refresh_trap_risk_count: int,
    feedback: Mapping[str, Any],
) -> int:
    """Advisory counter: repair/save pressure is present but recent turns avoid artifact writes.

    Fires when any of the following signal repair pressure:
    - semantic_repair_debt_kinds is non-empty
    - pending_hitl_integration_ids is non-empty
    - artifact_refresh_trap_risk_count > 0
    - feedback carries salvaged_rows (prose fields omitted on apply)

    AND the trailing step_records carry no save_workspace_artifact or
    copy_forward_save_workspace_artifact turn.

    Returns the count of consecutive trailing turns without an artifact write when
    the count meets _REPAIR_READY_MIN_NO_WRITE_TURNS. Returns 0 when no repair
    pressure exists, when a write appears in the trailing turns, or when the
    trailing count is below the minimum threshold.
    """
    if not step_records:
        return 0

    has_repair_pressure = (
        bool(semantic_repair_debt_kinds)
        or bool(pending_hitl_integration_ids)
        or artifact_refresh_trap_risk_count > 0
        or bool(feedback.get("salvaged_rows"))
    )
    if not has_repair_pressure:
        return 0

    trailing_no_write: int = 0
    for row in reversed(step_records):
        if _as_optional_text(row.get("action_type")) in _REPAIR_READY_WRITE_ACTION_TYPES:
            break
        trailing_no_write += 1

    if trailing_no_write < _REPAIR_READY_MIN_NO_WRITE_TURNS:
        return 0

    return trailing_no_write


def _hitl_context_has_evidence(context: Any) -> bool:
    """True when the HITL context dict carries focused evidence keys."""
    if not isinstance(context, Mapping):
        return False
    return any(bool(context.get(key)) for key in _HITL_EVIDENCE_CONTEXT_KEYS)


def _hitl_context_has_caveat(context: Any) -> bool:
    """True when the HITL context explicitly declares evidence is not needed or unavailable."""
    if not isinstance(context, Mapping):
        return False
    return any(bool(context.get(key)) for key in _HITL_EVIDENCE_CAVEAT_KEYS)


def _hitl_evidence_readiness_debt(
    step_records: list[dict[str, Any]],
    step_result_records: list[dict[str, Any]],
    *,
    pending_hitl_requests: list[dict[str, Any]],
    window: int = _HITL_EVIDENCE_READINESS_WINDOW,
) -> int:
    """Advisory: recent HITL turns carry no focused evidence and no explicit evidence caveat.

    Fires when: a HITL step exists in the recent window AND the HITL step carried
    non-empty refs (evidence was available to curate) AND neither the HITL's own
    context (from pending_hitl_requests) nor recent result records expose evidence
    or an explicit evidence-not-applicable declaration.

    Suppressed when:
    - The HITL request context contains evidence keys (evidence_refs, primary_evidence_ref,
      annotated_evidence_ref, rendered_evidence_refs, question_regions), OR
    - The HITL request context contains a caveat key (evidence_not_needed,
      evidence_unavailable, evidence_not_applicable), OR
    - A recent result record exposes evidence artifact metadata, OR
    - latest_refs_snapshot was empty at HITL time (evidence genuinely unavailable).

    Returns the count of underprepared HITL turns (those without evidence or caveat).
    """
    if not step_records:
        return 0
    recent = step_records[-window:]
    hitl_turns = [r for r in recent if bool(r.get("wait_for_human"))]
    if not hitl_turns:
        return 0

    # Index pending requests by issued_at_iteration for O(1) context lookup.
    pending_by_iteration: dict[int, dict[str, Any]] = {}
    for req in pending_hitl_requests:
        if not isinstance(req, Mapping):
            continue
        iteration = _as_int(req.get("issued_at_iteration"))
        if iteration is not None:
            pending_by_iteration[iteration] = req

    # Identify HITL turns that are actually underprepared.
    debt_turns: list[dict[str, Any]] = []
    for turn in hitl_turns:
        refs = turn.get("latest_refs_snapshot") or {}
        if not refs:
            # Evidence genuinely unavailable at this turn — not a debt.
            continue
        turn_index = _as_int(turn.get("kernel_turn_index"))
        if turn_index is not None and turn_index in pending_by_iteration:
            req = pending_by_iteration[turn_index]
            context = req.get("context")
            if _hitl_context_has_evidence(context) or _hitl_context_has_caveat(context):
                continue
        debt_turns.append(turn)

    if not debt_turns:
        return 0

    # Suppress entirely when a recent result exposes focused evidence metadata.
    if step_result_records:
        recent_results = step_result_records[-window:]
        for row in recent_results:
            if not isinstance(row, Mapping):
                continue
            outputs = row.get("outputs_for_continuity")
            if not isinstance(outputs, Mapping):
                continue
            if (
                outputs.get("rendered_evidence_refs")
                or outputs.get("evidence_artifact_summary")
                or outputs.get("derived_ref_id")
                or outputs.get("derived_ref")
            ):
                return 0

    return len(debt_turns)


def _post_hitl_spin_count(step_records: list[dict[str, Any]]) -> int:
    """Advisory: trailing post-HITL turns with no new refs, no artifact write, no state change.

    Fires when a wait_for_human turn exists in the step history AND the
    trailing consecutive turns since that HITL turn show no refs change (vs
    HITL-turn baseline), no artifact write, and no work_state_signature change.
    Returns the count when >= _POST_HITL_SPIN_MIN_TURNS, else 0.
    """
    last_hitl_pos: int | None = None
    for i, row in enumerate(step_records):
        if bool(row.get("wait_for_human")):
            last_hitl_pos = i
    if last_hitl_pos is None:
        return 0
    post_hitl = step_records[last_hitl_pos + 1:]
    if len(post_hitl) < _POST_HITL_SPIN_MIN_TURNS:
        return 0
    # Build a progress flag for each post-HITL turn by comparing to the previous turn.
    # "Progress" = refs changed vs previous, state changed vs previous, or artifact write.
    # This catches "integrated-then-stuck" loops where a save happens mid-window but
    # no-gain rereads follow. A save counts as progress only for that turn itself.
    hitl_row = step_records[last_hitl_pos]
    prev_refs_sig = _stable_signature(hitl_row.get("latest_refs_snapshot"))
    prev_state_sig = _as_optional_text(hitl_row.get("work_state_signature"))
    progress_flags: list[bool] = []
    for row in post_hitl:
        curr_refs_sig = _stable_signature(row.get("latest_refs_snapshot"))
        curr_state_sig = _as_optional_text(row.get("work_state_signature"))
        action_type = _as_optional_text(row.get("action_type"))
        had_progress = (
            action_type in _REPAIR_READY_WRITE_ACTION_TYPES
            or curr_refs_sig != prev_refs_sig
            or (
                curr_state_sig is not None
                and prev_state_sig is not None
                and curr_state_sig != prev_state_sig
            )
        )
        progress_flags.append(had_progress)
        prev_refs_sig = curr_refs_sig
        prev_state_sig = curr_state_sig
    # Count trailing consecutive no-progress turns.
    spin_count = 0
    for had_progress in reversed(progress_flags):
        if had_progress:
            break
        spin_count += 1
    if spin_count < _POST_HITL_SPIN_MIN_TURNS:
        return 0
    return spin_count


def _post_write_artifact_consistency_check_count(step_records: list[dict[str, Any]]) -> int:
    """One-turn advisory after a successful save-like artifact write.

    This is a reminder, not a gate: the agent should compare the saved revision
    against compact earned/determined atoms using the write result when possible.
    """
    if not step_records:
        return 0
    latest = step_records[-1]
    action_type = _as_optional_text(latest.get("action_type"))
    if action_type not in _ARTIFACT_REFRESH_TRAP_SAVE_ACTION_TYPES:
        return 0
    if _as_optional_text(latest.get("execution_state")) != "executed":
        return 0
    return 1


def _artifact_state_dirty_since_write_count(step_records: list[dict[str, Any]]) -> int:
    """Count turns since last materializing write when work state has changed after it."""
    if len(step_records) < 2:
        return 0
    latest_sig = _as_optional_text(step_records[-1].get("work_state_signature"))
    if latest_sig is None:
        return 0
    for offset, row in enumerate(reversed(step_records), start=0):
        action_type = _as_optional_text(row.get("action_type"))
        if action_type not in _ARTIFACT_MATERIALIZE_ACTION_TYPES:
            continue
        if _as_optional_text(row.get("execution_state")) != "executed":
            continue
        materialized_sig = _as_optional_text(row.get("work_state_signature"))
        if materialized_sig is None or materialized_sig == latest_sig:
            return 0
        return offset
    return 0


def _covered_units_metrics(items: list[Any]) -> dict[str, int]:
    """Advisory-only structural metrics over covered_units across all resolution items.

    Does not decide whether a value is correct; only flags shape-level gaps.
    """
    covered_unit_count = 0
    covered_units_with_candidates = 0
    closed_candidate_missing_determined = 0
    closed_value_missing_evidence = 0
    earned_missing_basis = 0
    earned_units_missing_locator = 0
    long_determined_value_units = 0
    # Track evidence_refs cited by unlocated earned units to detect shared broad refs.
    unlocated_earned_ref_counts: dict[str, int] = {}
    for item in items:
        units = getattr(item, "covered_units", None) or ()
        for unit in units:
            covered_unit_count += 1
            status = _as_optional_text(getattr(unit, "status", None))
            determination = _as_optional_text(getattr(unit, "determination", None))
            determination_lower = determination.lower() if determination else ""
            closed_or_earned = _is_closed_status(status) or determination_lower == "earned"
            candidate_values = getattr(unit, "candidate_values", None) or ()
            has_candidates = bool(candidate_values)
            determined_value = _as_optional_text(getattr(unit, "determined_value", None))
            determined_value_raw = getattr(unit, "determined_value", None)
            evidence_refs = getattr(unit, "evidence_refs", None) or ()
            evidence_locators = getattr(unit, "evidence_locators", None) or ()
            verification_basis = _as_optional_text(getattr(unit, "verification_basis", None))
            if has_candidates:
                covered_units_with_candidates += 1
                if closed_or_earned and determined_value is None:
                    closed_candidate_missing_determined += 1
            if (
                closed_or_earned
                and (has_candidates or determined_value is not None)
                and not bool(evidence_refs)
            ):
                closed_value_missing_evidence += 1
            if determination_lower == "earned" and verification_basis is None:
                earned_missing_basis += 1
            # Earned/closed unit with evidence artifact but no locator pointing
            # inside it. Advisory only — some media kinds may not yet support
            # locators.
            is_unlocated_earned = (
                closed_or_earned
                and determined_value is not None
                and bool(evidence_refs)
                and not bool(evidence_locators)
            )
            if is_unlocated_earned:
                earned_units_missing_locator += 1
                for ref in evidence_refs:
                    ref_text = str(ref).strip()
                    if ref_text:
                        unlocated_earned_ref_counts[ref_text] = (
                            unlocated_earned_ref_counts.get(ref_text, 0) + 1
                        )
            # Compact-atom pressure: closed/earned unit whose determined_value is
            # long enough to look like prose/transcript storage. Threshold is a
            # conservative structural cue, not a hard schema cap.
            if (
                closed_or_earned
                and isinstance(determined_value_raw, str)
                and len(determined_value_raw) > 200
            ):
                long_determined_value_units += 1
    # Advisory structural flag: how many unique evidence_refs are shared by 2+
    # earned unlocated units. A single broad ref backing many claims is a
    # locator-debt amplifier. Purely structural — no content inspection.
    shared_unlocated_evidence_count = sum(
        1 for count in unlocated_earned_ref_counts.values() if count >= 2
    )
    return {
        "covered_unit_count": covered_unit_count,
        "covered_units_with_candidates_count": covered_units_with_candidates,
        "closed_candidate_units_missing_determined_value_count": closed_candidate_missing_determined,
        "closed_value_units_missing_evidence_count": closed_value_missing_evidence,
        "earned_units_missing_verification_basis_count": earned_missing_basis,
        "earned_units_missing_locator_count": earned_units_missing_locator,
        "shared_unlocated_evidence_for_earned_units_count": shared_unlocated_evidence_count,
        "long_determined_value_units_count": long_determined_value_units,
    }


def _hitl_answerability_metrics(items: list[Any]) -> dict[str, int]:
    """Advisory counts for HITL answerability pressure on blocking/stalled items and units.

    Three mechanical checks, all advisory:
    - ``blocked_without_hitl_answerability_count``: blocking or no_further_progress
      item/unit with no requires_hitl and no human_answerability classification set.
    - ``human_answerable_blocker_without_hitl_count``: item/unit with
      ``human_answerability == "likely_answerable"`` but no requires_hitl pending.
    - ``not_answerable_missing_reason_count``: item/unit with
      ``human_answerability == "not_answerable"`` but no hitl_not_applicable_reason.

    Covered units of a blocking/stalled parent item are also checked so that
    answerability pressure is visible at the atom level, not only the item level.
    A covered unit is considered stalled when its parent item is blocked/stalled
    and the unit itself is not yet earned or closed.
    """
    blocked_without = 0
    answerable_without_hitl = 0
    not_answerable_missing_reason = 0
    for item in items:
        is_blocking = bool(getattr(item, "blocking", False))
        is_no_further = bool(getattr(item, "no_further_progress", False))
        is_requires_hitl = bool(getattr(item, "requires_hitl", False))
        answerability = _as_optional_text(getattr(item, "human_answerability", None))
        reason = _as_optional_text(getattr(item, "hitl_not_applicable_reason", None))

        is_blocked_or_stalled = is_blocking or is_no_further
        if not is_blocked_or_stalled:
            continue

        # Blocked/stalled material item with no HITL and no answerability assessment.
        if not is_requires_hitl and (answerability is None or answerability == "unknown"):
            blocked_without += 1

        # Agent assessed as likely answerable but hasn't emitted requires_hitl.
        if answerability == "likely_answerable" and not is_requires_hitl:
            answerable_without_hitl += 1

        # Agent asserted not-answerable but didn't explain why.
        if answerability == "not_answerable" and not reason:
            not_answerable_missing_reason += 1

        # Also check covered units — atoms where the actual stuck state may live.
        # A covered unit is considered stalled when its parent is blocked/stalled
        # and the unit itself is not yet earned or closed.
        for unit in list(getattr(item, "covered_units", None) or []):
            unit_status = str(getattr(unit, "status", "") or "").strip().lower()
            unit_determination = str(getattr(unit, "determination", "") or "").strip().lower()
            unit_is_done = unit_status == "closed" or unit_determination == "earned"
            if unit_is_done:
                continue  # unit is resolved; skip answerability check

            unit_answerability = _as_optional_text(getattr(unit, "human_answerability", None))
            unit_reason = _as_optional_text(getattr(unit, "hitl_not_applicable_reason", None))

            # Stalled unit in a blocked item with no HITL path and no answerability assessment.
            if not is_requires_hitl and (unit_answerability is None or unit_answerability == "unknown"):
                blocked_without += 1

            if unit_answerability == "likely_answerable" and not is_requires_hitl:
                answerable_without_hitl += 1

            if unit_answerability == "not_answerable" and not unit_reason:
                not_answerable_missing_reason += 1

    return {
        "blocked_without_hitl_answerability_count": blocked_without,
        "human_answerable_blocker_without_hitl_count": answerable_without_hitl,
        "not_answerable_missing_reason_count": not_answerable_missing_reason,
    }


def _hitl_ledger_metrics(
    *,
    ledger: list[Any],
    step_records: list[Any],
    consumed_unknown_count: int,
) -> dict[str, int]:
    """Mechanical counts derived from the durable HITL exchange ledger.

    - ``answered_hitl_unconsumed_count``: ledger exchanges in ``answered`` status
      (operator answered, agent has not declared consumption).
    - ``complete_with_unconsumed_hitl_count``: 1 when the most recent kernel step
      attempted ``complete_run`` AND there is at least one answered-unconsumed
      exchange in the ledger; 0 otherwise.  Mechanical only — not a moral judgment.
    - ``hitl_consumed_unknown_prompt_count``: cumulative count of agent-declared
      consumed prompt ids that did not match any ledger exchange (drift signal).
    """
    answered_unconsumed = sum(
        1 for entry in ledger
        if isinstance(entry, Mapping) and entry.get("status") == "answered"
    )
    complete_with_unconsumed = 0
    if answered_unconsumed > 0 and step_records:
        last = step_records[-1] if isinstance(step_records[-1], Mapping) else None
        if last is not None:
            action_type = str(last.get("action_type") or "").strip().lower()
            complete_run_flag = bool(last.get("complete_run"))
            if action_type == "complete_run" or complete_run_flag:
                complete_with_unconsumed = 1
    return {
        "answered_hitl_unconsumed_count": int(answered_unconsumed),
        "complete_with_unconsumed_hitl_count": int(complete_with_unconsumed),
        "hitl_consumed_unknown_prompt_count": int(max(0, consumed_unknown_count)),
    }


def _notebook_shaped_graph_rows_count(items: list[Any]) -> int:
    """Conservative structural pressure for closed rows shaped like prose notebooks.

    A row is counted only when it is closed/earned, has long prose fields, and
    lacks compact skeleton anchors such as values, candidates, evidence,
    closure memory, reopen triggers, dependencies, or covered units.
    """
    count = 0
    for item in items:
        if (
            _is_closed_status(getattr(item, "status", None))
            or _has_earned_determination(getattr(item, "determination", None))
        ) and _is_prose_heavy_without_skeleton(
            prose_values=(
                getattr(item, "summary", None),
                getattr(item, "notes", None),
                getattr(item, "verification_basis", None),
                getattr(item, "completion_criteria", None),
            ),
            compact_values=(
                getattr(item, "evidence_refs", None),
                getattr(item, "evidence_locators", None),
                getattr(item, "dependencies", None),
                getattr(item, "closure_summary", None),
                getattr(item, "reopen_triggers", None),
                getattr(item, "covered_units", None),
            ),
        ):
            count += 1

        for unit in getattr(item, "covered_units", None) or ():
            if (
                _is_closed_status(getattr(unit, "status", None))
                or _has_earned_determination(getattr(unit, "determination", None))
            ) and _is_prose_heavy_without_skeleton(
                prose_values=(
                    getattr(unit, "summary", None),
                    getattr(unit, "verification_basis", None),
                    getattr(unit, "next_needed_step", None),
                ),
                compact_values=(
                    getattr(unit, "candidate_values", None),
                    getattr(unit, "determined_value", None),
                    getattr(unit, "evidence_refs", None),
                    getattr(unit, "evidence_locators", None),
                    getattr(unit, "closure_summary", None),
                    getattr(unit, "reopen_triggers", None),
                ),
            ):
                count += 1
    return count


def _artifact_claim_inventory_suspect_count(
    *,
    closure_ready_to_close: bool,
    work_universe_posture: str | None,
    substantial_artifact_output_count: int,
    atomic_item_count: int,
    covered_unit_count: int,
) -> int:
    near_closure = closure_ready_to_close or _as_optional_text(work_universe_posture) in (
        "believed_adequate",
        "audited",
    )
    weak_claim_inventory = atomic_item_count == 0 and covered_unit_count == 0
    if near_closure and weak_claim_inventory:
        return substantial_artifact_output_count
    return 0


def _substantial_artifact_output_count(
    step_result_records: list[Any],
    *,
    last_n: int = 3,
) -> int:
    count = 0
    for row in step_result_records[-last_n:]:
        if not isinstance(row, Mapping):
            continue
        refs = row.get("artifact_refs")
        if not isinstance(refs, list) or not refs:
            continue
        if _substantial_text_signal(row.get("outputs_for_continuity")):
            count += 1
    return count


def _substantial_text_signal(value: Any, *, max_depth: int = 4) -> bool:
    return _text_signal_chars(value, max_depth=max_depth) >= 800


def _text_signal_chars(value: Any, *, max_depth: int) -> int:
    if max_depth < 0:
        return 0
    if isinstance(value, str):
        return len(value.strip())
    if isinstance(value, Mapping):
        return sum(_text_signal_chars(inner, max_depth=max_depth - 1) for inner in value.values())
    if isinstance(value, list):
        return sum(_text_signal_chars(inner, max_depth=max_depth - 1) for inner in value[:16])
    return 0


def _is_prose_heavy_without_skeleton(
    *,
    prose_values: tuple[Any, ...],
    compact_values: tuple[Any, ...],
) -> bool:
    has_long_prose = any(
        isinstance(value, str) and len(value.strip()) > 240
        for value in prose_values
    )
    has_compact_skeleton = any(bool(value) for value in compact_values)
    return has_long_prose and not has_compact_skeleton


def _repeated_complete_run_without_state_change_count(step_records: list[dict[str, Any]]) -> int:
    attempts = [row for row in step_records if bool(row.get("complete_run"))]
    if len(attempts) < 2:
        return 0
    latest = attempts[-1]
    latest_state_sig = _as_optional_text(latest.get("work_state_signature"))
    latest_refs_sig = _stable_signature(latest.get("latest_refs_snapshot"))
    if latest_state_sig is None:
        return 0
    repeated = 0
    for row in reversed(attempts[:-1]):
        if _as_optional_text(row.get("work_state_signature")) != latest_state_sig:
            break
        if _stable_signature(row.get("latest_refs_snapshot")) != latest_refs_sig:
            break
        repeated += 1
    return repeated


def _closure_readiness_projection(
    *,
    closure_policy: Mapping[str, Any] | None,
    closure_state: Any,
    resolution_item_count: int,
    work_universe_posture: str | None = None,
    feedback: Mapping[str, Any],
    closed_items_without_earned_determination_count: int,
    closed_items_without_basis_count: int,
    closed_dimensions_without_earned_determination_count: int,
    closed_dimensions_without_basis_count: int,
    items_requires_hitl_count: int = 0,
) -> dict[str, list[str]]:
    complete_run_blockers: list[str] = []
    publish_blockers: list[str] = []
    hard_enforced = bool(closure_policy and closure_policy.get("hard_enforced"))
    posture = _as_optional_text(work_universe_posture)
    dimensions_by_id = {
        str(getattr(row, "dimension_id", "") or ""): row
        for row in getattr(closure_state, "dimensions", ()) or ()
        if str(getattr(row, "dimension_id", "") or "")
    }

    if posture is not None and posture != "audited":
        blocker = f"work_universe_not_audited:{posture}"
        complete_run_blockers.append(blocker)
        publish_blockers.append(blocker)

    required_dimension_ids = tuple(
        str(value).strip()
        for value in (closure_policy or {}).get("required_dimension_ids", ())
        if str(value).strip()
    )
    missing_dimensions = [
        dim_id
        for dim_id in required_dimension_ids
        if dim_id not in dimensions_by_id or not _has_text(getattr(dimensions_by_id[dim_id], "status", None))
    ]
    if hard_enforced and missing_dimensions:
        blocker = f"required_dimensions_missing:{','.join(missing_dimensions)}"
        if bool((closure_policy or {}).get("enforce_on_complete")):
            complete_run_blockers.append(blocker)
        if bool((closure_policy or {}).get("enforce_on_publish")):
            publish_blockers.append(blocker)

    if hard_enforced and bool(getattr(closure_state, "requires_hitl", False)):
        if bool((closure_policy or {}).get("enforce_on_complete")):
            complete_run_blockers.append("closure_requires_hitl")
        if bool((closure_policy or {}).get("enforce_on_publish")):
            publish_blockers.append("closure_requires_hitl")

    if hard_enforced and items_requires_hitl_count > 0:
        blocker = f"items_require_hitl:{items_requires_hitl_count}"
        if bool((closure_policy or {}).get("enforce_on_complete")):
            complete_run_blockers.append(blocker)
        if bool((closure_policy or {}).get("enforce_on_publish")):
            publish_blockers.append(blocker)

    minimum_complete_items = int((closure_policy or {}).get("minimum_resolution_items_for_complete") or 0)
    if hard_enforced and minimum_complete_items > resolution_item_count:
        complete_run_blockers.append(
            f"resolution_items_below_minimum:{resolution_item_count}/{minimum_complete_items}"
        )
    minimum_publish_items = int((closure_policy or {}).get("minimum_resolution_items_for_publish") or 0)
    if hard_enforced and minimum_publish_items > resolution_item_count:
        publish_blockers.append(
            f"resolution_items_below_minimum:{resolution_item_count}/{minimum_publish_items}"
        )

    if not _closure_bool(closure_state, "ready_to_close"):
        complete_run_blockers.append("ready_to_close_false")
    if not _closure_bool(closure_state, "ready_to_publish"):
        publish_blockers.append("ready_to_publish_false")

    if _as_optional_text(feedback.get("outcome")) == "rejected":
        reason_code = _as_optional_text(feedback.get("reason_code")) or "unknown"
        complete_run_blockers.append(f"recent_state_patch_rejected:{reason_code}")
        publish_blockers.append(f"recent_state_patch_rejected:{reason_code}")
    if bool(feedback.get("skipped_resolution_rows")):
        complete_run_blockers.append("skipped_resolution_rows_pending")
        publish_blockers.append("skipped_resolution_rows_pending")
    if closed_items_without_earned_determination_count > 0:
        blocker = f"closed_items_without_earned_determination:{closed_items_without_earned_determination_count}"
        complete_run_blockers.append(blocker)
        publish_blockers.append(blocker)
    if closed_items_without_basis_count > 0:
        blocker = f"closed_items_without_basis:{closed_items_without_basis_count}"
        complete_run_blockers.append(blocker)
        publish_blockers.append(blocker)
    if closed_dimensions_without_earned_determination_count > 0:
        blocker = (
            f"closed_dimensions_without_earned_determination:"
            f"{closed_dimensions_without_earned_determination_count}"
        )
        complete_run_blockers.append(blocker)
        publish_blockers.append(blocker)
    if closed_dimensions_without_basis_count > 0:
        blocker = f"closed_dimensions_without_basis:{closed_dimensions_without_basis_count}"
        complete_run_blockers.append(blocker)
        publish_blockers.append(blocker)

    return {
        "complete_run_blockers": _sanitize_complete_run_blockers(
            complete_run_blockers,
            closure_ready_to_close=_closure_bool(closure_state, "ready_to_close"),
        ),
        "publish_blockers": _unique_texts(publish_blockers),
    }


def _sanitize_complete_run_blockers(
    blockers: list[str],
    *,
    closure_ready_to_close: bool,
) -> list[str]:
    unique = _unique_texts(blockers)
    if not closure_ready_to_close:
        return unique
    return [blocker for blocker in unique if blocker != "ready_to_close_false"]


def _mechanical_flags(
    *,
    feedback: Mapping[str, Any],
    success_condition_count: int,
    resolution_item_count: int,
    closure_ready_to_close: bool,
    work_universe_posture: str | None = None,
    atomic_item_count: int = 0,
    covered_unit_count: int = 0,
    repeated_state_patch_reason_code_streak: int,
    consecutive_same_active_item_turns: int,
    turns_since_resolution_item_count_change: int | None,
    new_resolution_items_since_last_complete_run_attempt: int,
    repeated_complete_run_without_state_change_count: int,
    same_ref_bundle_reread_no_gain_streak: int,
    same_item_same_ref_bundle_stall_streak: int,
    same_item_hydrate_churn_no_gain_streak: int,
    artifact_refresh_trap_risk_count: int = 0,
    repair_ready_without_artifact_write_count: int = 0,
    hitl_evidence_readiness_debt_count: int = 0,
    post_hitl_spin_count: int = 0,
    post_write_artifact_consistency_check_count: int = 0,
    recent_result_truncated_count: int = 0,
    artifact_claim_inventory_suspect_count: int = 0,
    closed_candidate_units_missing_determined_value_count: int = 0,
    closed_value_units_missing_evidence_count: int,
    earned_units_missing_verification_basis_count: int,
    earned_units_missing_locator_count: int = 0,
    shared_unlocated_evidence_for_earned_units_count: int = 0,
    long_determined_value_units_count: int = 0,
    sequenced_items_missing_scope_count: int,
    sequenced_items_missing_index_count: int,
    duplicate_sequence_positions_count: int,
    sequence_scope_order_gaps_count: int,
    group_items_without_subclaims_count: int,
    critical_closed_items_without_evidence_count: int,
    critical_closed_items_without_verification_basis_count: int,
    blocking_items_without_relations_count: int,
    closed_items_with_open_dependencies_count: int,
    explicit_non_blocking_without_notes_count: int,
    complete_run_blockers: list[str],
    semantic_repair_debt_kinds: list[str] | None = None,
    pending_hitl_integration_ids: list[str] | None = None,
    reread_after_failed_persist: Mapping[str, Any] | None = None,
    notebook_shaped_graph_rows_count: int = 0,
    earned_before_local_evidence_count: int = 0,
    posthoc_recheck_needed_count: int = 0,
    earned_exact_with_broad_image_locator_count: int = 0,
    blocked_without_hitl_answerability_count: int = 0,
    human_answerable_blocker_without_hitl_count: int = 0,
    not_answerable_missing_reason_count: int = 0,
    answered_hitl_unconsumed_count: int = 0,
    complete_with_unconsumed_hitl_count: int = 0,
    hitl_consumed_unknown_prompt_count: int = 0,
    artifact_state_dirty_since_write_count: int = 0,
    claim_inventory_pressure_enabled: bool = False,
    completion_anchor: Mapping[str, Any] | None = None,
) -> list[str]:
    flags: list[str] = []
    repair_bundle = feedback.get("state_patch_repair_bundle")
    if isinstance(repair_bundle, Mapping):
        fragments = repair_bundle.get("fragments")
        if isinstance(fragments, list) and fragments:
            flags.append(f"state_patch_repair_pending:{len(fragments)}")
    if semantic_repair_debt_kinds:
        flags.append("semantic_repair_debt:" + ",".join(semantic_repair_debt_kinds))
    if pending_hitl_integration_ids:
        flags.append(
            f"pending_hitl_integration:{len(pending_hitl_integration_ids)}"
        )
    if isinstance(reread_after_failed_persist, Mapping):
        outcome = reread_after_failed_persist.get("feedback_outcome") or "failed"
        flags.append(f"reread_after_failed_persist_risk:{outcome}")
    last_reason_code = _as_optional_text(feedback.get("reason_code"))
    if repeated_state_patch_reason_code_streak >= 2 and last_reason_code is not None:
        flags.append(
            f"state_patch_reason_code_repeated:{last_reason_code}:{repeated_state_patch_reason_code_streak}"
        )
    if consecutive_same_active_item_turns >= 3:
        flags.append(f"active_item_unchanged_turns:{consecutive_same_active_item_turns}")
    if turns_since_resolution_item_count_change is not None and turns_since_resolution_item_count_change >= 4:
        flags.append(
            f"resolution_item_count_unchanged_turns:{turns_since_resolution_item_count_change}"
        )
    if new_resolution_items_since_last_complete_run_attempt > 0:
        flags.append(
            f"new_resolution_items_since_complete_run_attempt:{new_resolution_items_since_last_complete_run_attempt}"
        )
    if repeated_complete_run_without_state_change_count > 0:
        flags.append(
            f"repeated_complete_run_without_state_change:{repeated_complete_run_without_state_change_count}"
        )
    if same_ref_bundle_reread_no_gain_streak >= 3:
        flags.append(f"same_ref_bundle_reread_no_gain:{same_ref_bundle_reread_no_gain_streak}")
    if same_item_same_ref_bundle_stall_streak >= 3:
        flags.append(f"same_item_same_ref_bundle_stall:{same_item_same_ref_bundle_stall_streak}")
    if same_item_hydrate_churn_no_gain_streak >= 3:
        flags.append(f"same_item_hydrate_churn_no_gain:{same_item_hydrate_churn_no_gain_streak}")
    if artifact_refresh_trap_risk_count >= _ARTIFACT_REFRESH_TRAP_HYDRATE_THRESHOLD:
        flags.append(f"artifact_refresh_trap_risk:{artifact_refresh_trap_risk_count}")
    if repair_ready_without_artifact_write_count >= _REPAIR_READY_MIN_NO_WRITE_TURNS:
        flags.append(f"repair_ready_without_artifact_write:{repair_ready_without_artifact_write_count}")
    if hitl_evidence_readiness_debt_count > 0:
        flags.append(f"hitl_evidence_readiness_debt:{hitl_evidence_readiness_debt_count}")
    if post_hitl_spin_count >= _POST_HITL_SPIN_MIN_TURNS:
        flags.append(f"post_hitl_spin:{post_hitl_spin_count}")
    if post_write_artifact_consistency_check_count > 0:
        flags.append(
            f"post_write_artifact_consistency_check:{post_write_artifact_consistency_check_count}"
        )
    if closed_candidate_units_missing_determined_value_count > 0:
        flags.append(
            f"closed_candidate_unit_missing_determined_value:{closed_candidate_units_missing_determined_value_count}"
        )
    if closed_value_units_missing_evidence_count > 0:
        flags.append(
            f"closed_value_unit_missing_evidence:{closed_value_units_missing_evidence_count}"
        )
    if earned_units_missing_verification_basis_count > 0:
        flags.append(
            f"earned_unit_missing_verification_basis:{earned_units_missing_verification_basis_count}"
        )
    if earned_units_missing_locator_count > 0:
        flags.append(f"earned_unit_missing_locator:{earned_units_missing_locator_count}")
    if shared_unlocated_evidence_for_earned_units_count > 0:
        flags.append(
            f"shared_unlocated_evidence_for_earned_units:{shared_unlocated_evidence_for_earned_units_count}"
        )
    if long_determined_value_units_count > 0:
        flags.append(f"long_determined_value_units:{long_determined_value_units_count}")
    if claim_inventory_pressure_enabled and artifact_claim_inventory_suspect_count > 0:
        flags.append(f"artifact_claim_inventory_suspect:{artifact_claim_inventory_suspect_count}")
    if resolution_item_count >= 3 and success_condition_count == 0:
        flags.append(
            f"success_conditions_empty_with_resolution_items:{resolution_item_count}"
        )
    elif (
        resolution_item_count >= 4
        and success_condition_count > 0
        and resolution_item_count >= success_condition_count * 2
    ):
        flags.append(
            f"resolution_items_outnumber_success_conditions:{resolution_item_count}_vs_{success_condition_count}"
        )
    if sequenced_items_missing_scope_count > 0:
        flags.append(f"sequenced_items_missing_scope:{sequenced_items_missing_scope_count}")
    if sequenced_items_missing_index_count > 0:
        flags.append(f"sequenced_items_missing_index:{sequenced_items_missing_index_count}")
    if duplicate_sequence_positions_count > 0:
        flags.append(f"duplicate_sequence_positions:{duplicate_sequence_positions_count}")
    if sequence_scope_order_gaps_count > 0:
        flags.append(f"sequence_scope_order_gaps:{sequence_scope_order_gaps_count}")
    if group_items_without_subclaims_count > 0:
        flags.append(f"group_items_without_subclaims:{group_items_without_subclaims_count}")
    if critical_closed_items_without_evidence_count > 0:
        flags.append(
            f"critical_closed_items_without_evidence:{critical_closed_items_without_evidence_count}"
        )
    if critical_closed_items_without_verification_basis_count > 0:
        flags.append(
            "critical_closed_items_without_verification_basis:"
            f"{critical_closed_items_without_verification_basis_count}"
        )
    if blocking_items_without_relations_count > 0:
        flags.append(f"blocking_items_without_relations:{blocking_items_without_relations_count}")
    # Coarse work-graph flag: structural pressure when a partial posture has
    # enough broad items to be "working", but no atomic items and no covered
    # units, and the graph has been stable while the agent keeps reading or
    # dwelling on the same active item. Strictly structural — no mission-specific
    # content inspection.
    if (
        claim_inventory_pressure_enabled
        and _as_optional_text(work_universe_posture) == "partial"
        and resolution_item_count >= 3
        and atomic_item_count == 0
        and covered_unit_count == 0
        and turns_since_resolution_item_count_change is not None
        and turns_since_resolution_item_count_change >= 3
        and (
            consecutive_same_active_item_turns >= 2
            or same_ref_bundle_reread_no_gain_streak >= 2
            or same_item_hydrate_churn_no_gain_streak >= 2
        )
    ):
        flags.append(
            f"coarse_work_graph_under_active_investigation:{resolution_item_count}"
        )
    if closed_items_with_open_dependencies_count > 0:
        flags.append(
            f"closed_item_with_open_dependency:{closed_items_with_open_dependencies_count}"
        )
    if explicit_non_blocking_without_notes_count > 0:
        flags.append(
            f"explicit_non_blocking_without_notes:{explicit_non_blocking_without_notes_count}"
        )
    if notebook_shaped_graph_rows_count > 0:
        flags.append(f"notebook_shaped_graph_rows:{notebook_shaped_graph_rows_count}")
    # Track 1: earned-before-claim-local-evidence sequencing debt.
    # Both flags reflect *unresolved* units — entries are removed when the agent
    # re-evaluates (changes verification_basis / determined_value or reopens).
    # earned_before_claim_local_evidence: unit earned without locators, not yet repaired.
    # posthoc_evidence_recheck_needed: locators added post-hoc, re-evaluation still pending.
    if earned_before_local_evidence_count > 0:
        flags.append(f"earned_before_claim_local_evidence:{earned_before_local_evidence_count}")
    if posthoc_recheck_needed_count > 0:
        flags.append(f"posthoc_evidence_recheck_needed:{posthoc_recheck_needed_count}")
    # Track 2: earned exact units with only broad image-region locators.
    if earned_exact_with_broad_image_locator_count > 0:
        flags.append(
            f"broad_image_locator_for_earned_exact_units:{earned_exact_with_broad_image_locator_count}"
        )
    # Track 3: HITL answerability pressure.
    if blocked_without_hitl_answerability_count > 0:
        flags.append(
            f"blocked_without_hitl_answerability:{blocked_without_hitl_answerability_count}"
        )
    if human_answerable_blocker_without_hitl_count > 0:
        flags.append(
            f"human_answerable_blocker_without_hitl:{human_answerable_blocker_without_hitl_count}"
        )
    if not_answerable_missing_reason_count > 0:
        flags.append(f"not_answerable_missing_reason:{not_answerable_missing_reason_count}")
    # HITL exchange ledger pressure: answered HITL responses the agent has not yet
    # declared consumed.  When complete_run is attempted while these are non-zero,
    # also fire a stronger flag so closing without integration is loud.
    if answered_hitl_unconsumed_count > 0:
        flags.append(f"answered_hitl_unconsumed:{answered_hitl_unconsumed_count}")
    if complete_with_unconsumed_hitl_count > 0:
        flags.append(f"complete_with_unconsumed_hitl:{complete_with_unconsumed_hitl_count}")
    if hitl_consumed_unknown_prompt_count > 0:
        flags.append(f"hitl_consumed_unknown_prompt:{hitl_consumed_unknown_prompt_count}")
    if artifact_state_dirty_since_write_count > 0:
        flags.append(f"artifact_state_dirty_since_write:{artifact_state_dirty_since_write_count}")
    # Output claim coverage debt: work graph has resolution items but no or very sparse
    # fine-grained claim inventory while the run is in or approaching the closure zone.
    # Structural pressure only — does not inspect content.
    fine_grained_claim_inventory_count = atomic_item_count + covered_unit_count
    sparse_claim_inventory = (
        fine_grained_claim_inventory_count == 0
        or (
            resolution_item_count >= 4
            and fine_grained_claim_inventory_count * 2 < resolution_item_count
        )
    )
    if (
        claim_inventory_pressure_enabled
        and sparse_claim_inventory
        and resolution_item_count >= 2
        and (
            closure_ready_to_close
            or _as_optional_text(work_universe_posture) in ("believed_adequate", "audited")
        )
    ):
        flags.append(f"output_claim_coverage_debt:{resolution_item_count}")
    # Artifact excerpt boundary risk: recent tool results carried truncated outputs
    # while the run is in or approaching a closure zone. Structural pressure only —
    # does not inspect whether the truncation is actually material to the current claim.
    if (
        recent_result_truncated_count >= 1
        and (
            closure_ready_to_close
            or _as_optional_text(work_universe_posture) in ("believed_adequate", "audited")
        )
    ):
        flags.append(f"artifact_excerpt_boundary_risk:{recent_result_truncated_count}")
    blockers_for_flag = list(complete_run_blockers)
    anchor = completion_anchor if isinstance(completion_anchor, Mapping) else {}
    anchor_satisfied = bool(anchor.get("satisfied"))
    if anchor_satisfied:
        flags.append("completion_anchor_satisfied")
        expected_next = str(anchor.get("expected_next") or "").strip()
        if expected_next:
            flags.append(f"expected_next:{expected_next}")
    if closure_ready_to_close:
        blockers_for_flag = [
            blocker for blocker in blockers_for_flag if blocker != "ready_to_close_false"
        ]
    if anchor_satisfied:
        if blockers_for_flag:
            for blocker in blockers_for_flag[:3]:
                flags.append(f"complete_run_blocked:{blocker}")
    elif not closure_ready_to_close and blockers_for_flag:
        flags.append("complete_run_blockers_present")
    elif closure_ready_to_close and blockers_for_flag:
        for blocker in blockers_for_flag[:3]:
            flags.append(f"complete_run_blocked:{blocker}")
    return flags[:24]


def _recent_result_truncated_count(
    step_result_records: list[Any],
    *,
    last_n: int = 3,
) -> int:
    """Count rows in the last N result records where the prompt excerpt would be truncated.

    Checks both ``result_truncated`` (raw tool-output truncation stored on the
    record) and prompt-visible excerpt truncation (computed via the same
    bounded-excerpt projection the slice builder uses).  This ensures the flag
    fires for the run-6 failure shape where ``result_truncated`` was False but
    the prompt-visible excerpt was cut before the contract keys.

    Structural only — does not inspect outputs content.
    """
    if not step_result_records:
        return 0
    tail = step_result_records[-last_n:]
    count = 0
    for row in tail:
        if not isinstance(row, Mapping):
            continue
        if bool(row.get("result_truncated", False)):
            count += 1
        elif check_outputs_excerpt_truncated(row):
            count += 1
    return count


def _stable_signature(value: Any) -> str:
    try:
        return json.dumps(value if isinstance(value, Mapping) else {}, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return "{}"


def _unique_texts(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in out:
            out.append(text)
    return out


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_closed_status(value: Any) -> bool:
    return str(value or "").strip().lower() == "closed"


def _has_earned_determination(value: Any) -> bool:
    return str(value or "").strip().lower() == "earned"


def _has_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def _materiality(value: Any) -> str | None:
    text = _as_optional_text(value)
    return text.lower() if text is not None else None


def _relation_index(relations: list[Any]) -> dict[str, set[str]]:
    sources: set[str] = set()
    targets: set[str] = set()
    group_parent_ids: set[str] = set()
    for row in relations:
        source_item_id = _as_optional_text(getattr(row, "source_item_id", None))
        target_item_id = _as_optional_text(getattr(row, "target_item_id", None))
        relation_type = _as_optional_text(getattr(row, "relation_type", None))
        relation_type = relation_type.lower() if relation_type is not None else None
        if source_item_id is not None:
            sources.add(source_item_id)
        if target_item_id is not None:
            targets.add(target_item_id)
        if relation_type == "subclaim_of" and target_item_id is not None:
            group_parent_ids.add(target_item_id)
        if relation_type == "aggregates" and source_item_id is not None:
            group_parent_ids.add(source_item_id)
    return {
        "sources": sources,
        "targets": targets,
        "group_parent_ids": group_parent_ids,
    }


def _group_item_has_subclaims(
    item_id: str,
    *,
    relation_index: Mapping[str, set[str]],
) -> bool:
    return bool(item_id and item_id in relation_index.get("group_parent_ids", set()))


def _item_has_any_relation(
    item_id: str,
    *,
    relation_index: Mapping[str, set[str]],
) -> bool:
    return bool(
        item_id
        and (
            item_id in relation_index.get("sources", set())
            or item_id in relation_index.get("targets", set())
        )
    )


def _sequence_metrics(items: list[Any]) -> dict[str, int]:
    scoped_positions: dict[str, list[int]] = {}
    sequenced_item_count = 0
    sequenced_items_missing_scope_count = 0
    sequenced_items_missing_index_count = 0

    for row in items:
        sequence_scope = _as_optional_text(getattr(row, "sequence_scope", None))
        sequence_index = _as_int(getattr(row, "sequence_index", None))
        if sequence_scope is None and sequence_index is None:
            continue
        if sequence_scope is None:
            sequenced_items_missing_scope_count += 1
            continue
        if sequence_index is None:
            sequenced_items_missing_index_count += 1
            continue
        sequenced_item_count += 1
        scoped_positions.setdefault(sequence_scope, []).append(sequence_index)

    duplicate_sequence_positions_count = 0
    sequence_scope_order_gaps_count = 0
    for positions in scoped_positions.values():
        unique_positions = sorted(set(positions))
        duplicate_sequence_positions_count += max(0, len(positions) - len(unique_positions))
        if unique_positions and unique_positions != list(
            range(unique_positions[0], unique_positions[0] + len(unique_positions))
        ):
            sequence_scope_order_gaps_count += 1

    return {
        "sequenced_item_count": sequenced_item_count,
        "sequenced_items_missing_scope_count": sequenced_items_missing_scope_count,
        "sequenced_items_missing_index_count": sequenced_items_missing_index_count,
        "duplicate_sequence_positions_count": duplicate_sequence_positions_count,
        "sequence_scope_order_gaps_count": sequence_scope_order_gaps_count,
    }
