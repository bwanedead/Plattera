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

from ..memory import LoopMemoryState


def build_prompt_observability_summary(
    loop_memory: LoopMemoryState,
    *,
    closure_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return host-owned loop-health facts safe to expose in prompts and audits."""
    telemetry = loop_memory.telemetry
    cont = loop_memory.continuity
    step_records = list(cont.kernel_step_records)
    resolution_items = list(getattr(cont.resolution_state, "items", ()) or ())
    resolution_relations = list(getattr(cont.resolution_state, "relations", ()) or ())
    success_conditions = list(getattr(cont.mission_state, "success_conditions", ()) or ())
    closure_state = cont.mission_state.closure_state
    closure_dimensions = list(getattr(closure_state, "dimensions", ()) or ())
    work_universe_posture = _as_optional_text(getattr(cont.mission_state, "work_universe_posture", None)) or "initial"
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

    covered_units_metrics = _covered_units_metrics(resolution_items)

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
        "repeated_state_patch_reason_code_streak": repeated_state_patch_reason_code_streak,
        "turns_since_last_state_patch_applied": turns_since_last_state_patch_applied,
        "consecutive_same_active_item_turns": consecutive_same_active_item_turns,
        "turns_since_resolution_item_count_change": turns_since_resolution_item_count_change,
        "new_resolution_items_since_last_complete_run_attempt": new_resolution_items_since_last_complete_run_attempt,
        "repeated_complete_run_without_state_change_count": repeated_complete_run_without_state_change_count,
        "same_ref_bundle_reread_no_gain_streak": same_ref_bundle_reread_no_gain_streak,
        "same_item_same_ref_bundle_stall_streak": same_item_same_ref_bundle_stall_streak,
        "same_item_hydrate_churn_no_gain_streak": same_item_hydrate_churn_no_gain_streak,
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
        "closure_readiness_projection": closure_readiness_projection,
    }
    summary["mechanical_flags"] = _mechanical_flags(
        feedback=feedback,
        success_condition_count=len(success_conditions),
        resolution_item_count=len(resolution_items),
        closure_ready_to_close=bool(getattr(closure_state, "ready_to_close", False)),
        repeated_state_patch_reason_code_streak=repeated_state_patch_reason_code_streak,
        consecutive_same_active_item_turns=consecutive_same_active_item_turns,
        turns_since_resolution_item_count_change=turns_since_resolution_item_count_change,
        new_resolution_items_since_last_complete_run_attempt=new_resolution_items_since_last_complete_run_attempt,
        repeated_complete_run_without_state_change_count=repeated_complete_run_without_state_change_count,
        same_ref_bundle_reread_no_gain_streak=same_ref_bundle_reread_no_gain_streak,
        same_item_same_ref_bundle_stall_streak=same_item_same_ref_bundle_stall_streak,
        same_item_hydrate_churn_no_gain_streak=same_item_hydrate_churn_no_gain_streak,
        closed_candidate_units_missing_determined_value_count=covered_units_metrics[
            "closed_candidate_units_missing_determined_value_count"
        ],
        closed_value_units_missing_evidence_count=covered_units_metrics[
            "closed_value_units_missing_evidence_count"
        ],
        earned_units_missing_verification_basis_count=covered_units_metrics[
            "earned_units_missing_verification_basis_count"
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
        complete_run_blockers=list(closure_readiness_projection.get("complete_run_blockers", ())),
    )
    return summary


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


def _covered_units_metrics(items: list[Any]) -> dict[str, int]:
    """Advisory-only structural metrics over covered_units across all resolution items.

    Does not decide whether a value is correct; only flags shape-level gaps:
    - ``covered_units_with_candidates_count``: units whose ``candidate_values`` is non-empty.
    - ``closed_candidate_units_missing_determined_value_count``: closed/earned units with
      candidates but no ``determined_value``.
    - ``closed_value_units_missing_evidence_count``: closed/earned units with
      ``candidate_values`` or ``determined_value`` but no ``evidence_refs``.
    - ``earned_units_missing_verification_basis_count``: earned units missing
      ``verification_basis`` text.
    """
    covered_units_with_candidates = 0
    closed_candidate_missing_determined = 0
    closed_value_missing_evidence = 0
    earned_missing_basis = 0
    for item in items:
        units = getattr(item, "covered_units", None) or ()
        for unit in units:
            status = _as_optional_text(getattr(unit, "status", None))
            determination = _as_optional_text(getattr(unit, "determination", None))
            determination_lower = determination.lower() if determination else ""
            closed_or_earned = _is_closed_status(status) or determination_lower == "earned"
            candidate_values = getattr(unit, "candidate_values", None) or ()
            has_candidates = bool(candidate_values)
            determined_value = _as_optional_text(getattr(unit, "determined_value", None))
            evidence_refs = getattr(unit, "evidence_refs", None) or ()
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
    return {
        "covered_units_with_candidates_count": covered_units_with_candidates,
        "closed_candidate_units_missing_determined_value_count": closed_candidate_missing_determined,
        "closed_value_units_missing_evidence_count": closed_value_missing_evidence,
        "earned_units_missing_verification_basis_count": earned_missing_basis,
    }


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

    if not bool(getattr(closure_state, "ready_to_close", False)):
        complete_run_blockers.append("ready_to_close_false")
    if not bool(getattr(closure_state, "ready_to_publish", False)):
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
        "complete_run_blockers": _unique_texts(complete_run_blockers),
        "publish_blockers": _unique_texts(publish_blockers),
    }


def _mechanical_flags(
    *,
    feedback: Mapping[str, Any],
    success_condition_count: int,
    resolution_item_count: int,
    closure_ready_to_close: bool,
    repeated_state_patch_reason_code_streak: int,
    consecutive_same_active_item_turns: int,
    turns_since_resolution_item_count_change: int | None,
    new_resolution_items_since_last_complete_run_attempt: int,
    repeated_complete_run_without_state_change_count: int,
    same_ref_bundle_reread_no_gain_streak: int,
    same_item_same_ref_bundle_stall_streak: int,
    same_item_hydrate_churn_no_gain_streak: int,
    closed_candidate_units_missing_determined_value_count: int,
    closed_value_units_missing_evidence_count: int,
    earned_units_missing_verification_basis_count: int,
    sequenced_items_missing_scope_count: int,
    sequenced_items_missing_index_count: int,
    duplicate_sequence_positions_count: int,
    sequence_scope_order_gaps_count: int,
    group_items_without_subclaims_count: int,
    critical_closed_items_without_evidence_count: int,
    critical_closed_items_without_verification_basis_count: int,
    blocking_items_without_relations_count: int,
    complete_run_blockers: list[str],
) -> list[str]:
    flags: list[str] = []
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
    if not closure_ready_to_close and complete_run_blockers:
        flags.append("complete_run_blockers_present")
    return flags[:16]


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
