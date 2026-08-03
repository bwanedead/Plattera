"""Unit tests for loop_health_summary.py — the coverage-posture contract.

Pins the key invariants for build_prompt_observability_summary,
_closure_readiness_projection, and _mechanical_flags without requiring
a real orchestration run.
"""
from __future__ import annotations

from harness.mission_state import (
    ClosureDimension,
    ClosureState,
    MissionSuccessCondition,
    ResolutionCoveredUnit,
    ResolutionItem,
    ResolutionRelation,
    new_mission_state,
    new_resolution_state,
)
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.loop_health_summary import (
    _closure_readiness_projection,
    _mechanical_flags,
    build_prompt_observability_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mem(
    *,
    resolution_items: list[ResolutionItem] | None = None,
    resolution_relations: list[ResolutionRelation] | None = None,
    success_conditions: list[MissionSuccessCondition] | None = None,
    dimensions: list[ClosureDimension] | None = None,
    ready_to_close: bool = False,
    ready_to_publish: bool = False,
    requires_hitl: bool = False,
    work_universe_posture: str = "initial",
    state_patch_feedback: dict | None = None,
    step_records: list[dict] | None = None,
    step_result_records: list[dict] | None = None,
) -> LoopMemoryState:
    ms = new_mission_state(mission_id="m-health", loop_family="orchestration_kernel")
    ms = ms.model_copy(
        update={
            "work_universe_posture": work_universe_posture,
            "closure_state": ClosureState(
                dimensions=list(dimensions or []),
                ready_to_close=ready_to_close,
                ready_to_publish=ready_to_publish,
                requires_hitl=requires_hitl,
            ),
            "success_conditions": list(success_conditions or []),
        }
    )
    rs = new_resolution_state()
    if resolution_items or resolution_relations:
        rs = rs.model_copy(
            update={
                "items": list(resolution_items or []),
                "relations": list(resolution_relations or []),
            }
        )
    ms = ms.model_copy(update={"resolution_state": rs})
    mem = LoopMemoryState()
    mem.continuity.mission_state = ms
    mem.continuity.resolution_state = rs
    if state_patch_feedback is not None:
        mem.continuity.state_patch_feedback = dict(state_patch_feedback)
    if step_records is not None:
        mem.continuity.kernel_step_records = list(step_records)
    if step_result_records is not None:
        mem.continuity.kernel_step_result_records = list(step_result_records)
    return mem


def _dim(dimension_id: str, *, status: str = "closed", determination: str | None = None, verification_basis: str | None = None, requires_hitl: bool = False) -> ClosureDimension:
    return ClosureDimension(
        dimension_id=dimension_id,
        title=dimension_id,
        status=status,
        determination=determination,
        verification_basis=verification_basis,
        requires_hitl=requires_hitl,
    )


def _item(
    item_id: str,
    *,
    status: str = "closed",
    determination: str | None = None,
    verification_basis: str | None = None,
    completion_criteria: str | None = None,
    blocking: bool | None = None,
    requires_hitl: bool = False,
    no_further_progress: bool = False,
    structure_kind: str | None = None,
    materiality: str | None = None,
    evidence_refs: list[str] | None = None,
    sequence_scope: str | None = None,
    sequence_index: int | None = None,
    covered_units: list[ResolutionCoveredUnit] | None = None,
    notes: str | None = None,
    dependencies: list[str] | None = None,
) -> ResolutionItem:
    return ResolutionItem(
        item_id=item_id,
        title=item_id,
        kind="work_unit",
        status=status,
        determination=determination,
        verification_basis=verification_basis,
        completion_criteria=completion_criteria,
        blocking=blocking,
        requires_hitl=requires_hitl,
        no_further_progress=no_further_progress,
        structure_kind=structure_kind,
        materiality=materiality,
        evidence_refs=list(evidence_refs or []),
        sequence_scope=sequence_scope,
        sequence_index=sequence_index,
        covered_units=list(covered_units or []),
        notes=notes,
        dependencies=list(dependencies or []),
    )


def _rel(source_item_id: str, target_item_id: str, relation_type: str) -> ResolutionRelation:
    return ResolutionRelation(
        source_item_id=source_item_id,
        target_item_id=target_item_id,
        relation_type=relation_type,
    )


def _condition(condition_id: str, *, status: str = "open", determination: str | None = None, verification_basis: str | None = None) -> MissionSuccessCondition:
    return MissionSuccessCondition(
        condition_id=condition_id,
        title=condition_id,
        status=status,
        determination=determination,
        verification_basis=verification_basis,
    )


def _step_record(
    turn_index: int,
    *,
    action_type: str = "hydrate_artifact_refs",
    action_inputs: dict | None = None,
    active_item_id: str | None = None,
    latest_refs_snapshot: dict | None = None,
    work_state_signature: str | None = None,
    skip_execution: bool = False,
    execution_state: str = "executed",
) -> dict:
    return {
        "kernel_turn_index": turn_index,
        "action_type": action_type,
        "action_inputs": dict(action_inputs or {}),
        "active_item_id_snapshot": active_item_id,
        "latest_refs_snapshot": dict(latest_refs_snapshot or {}),
        "work_state_signature": work_state_signature,
        "skip_execution": skip_execution,
        "wait_for_human": False,
        "complete_run": False,
        "execution_state": execution_state,
        "execution_reason_code": None,
    }


def _result_record(
    turn_index: int,
    *,
    artifact_refs: list[str] | None = None,
    outputs_for_continuity: dict | str | None = None,
) -> dict:
    return {
        "kernel_turn_index": turn_index,
        "action_type": "save_workspace_artifact",
        "execution_state": "executed",
        "artifact_refs": list(artifact_refs or []),
        "outputs_for_continuity": outputs_for_continuity if outputs_for_continuity is not None else {},
        "result_truncated": False,
    }


def _projection(
    *,
    closure_policy: dict | None = None,
    closure_state: object = None,
    resolution_item_count: int = 0,
    work_universe_posture: str | None = None,
    feedback: dict | None = None,
    closed_items_without_earned_determination_count: int = 0,
    closed_items_without_basis_count: int = 0,
    closed_dimensions_without_earned_determination_count: int = 0,
    closed_dimensions_without_basis_count: int = 0,
    items_requires_hitl_count: int = 0,
    covered_units_requires_hitl_count: int = 0,
) -> dict:
    return dict(
        closure_policy=closure_policy,
        closure_state=closure_state,
        resolution_item_count=resolution_item_count,
        work_universe_posture=work_universe_posture,
        feedback=feedback or {},
        closed_items_without_earned_determination_count=closed_items_without_earned_determination_count,
        closed_items_without_basis_count=closed_items_without_basis_count,
        closed_dimensions_without_earned_determination_count=closed_dimensions_without_earned_determination_count,
        closed_dimensions_without_basis_count=closed_dimensions_without_basis_count,
        items_requires_hitl_count=items_requires_hitl_count,
        covered_units_requires_hitl_count=covered_units_requires_hitl_count,
    )


def _call_projection(**kwargs) -> dict:
    return _closure_readiness_projection(**_projection(**kwargs))


# ---------------------------------------------------------------------------
# _closure_readiness_projection — blocker accumulation
# ---------------------------------------------------------------------------


def test_projection_no_policy_only_readiness_flags() -> None:
    """Without a closure policy, only ready_to_close and ready_to_publish flags appear."""
    result = _call_projection()
    assert "ready_to_close_false" in result["complete_run_blockers"]
    assert "ready_to_publish_false" in result["publish_blockers"]
    # No dimension-policy blockers
    assert not any("required_dimensions_missing" in b for b in result["complete_run_blockers"])


def test_projection_all_ready_no_blockers() -> None:
    """ready_to_close + ready_to_publish with no other issues → empty blocker lists."""
    cs = ClosureState(ready_to_close=True, ready_to_publish=True)
    result = _call_projection(closure_state=cs, work_universe_posture="audited")
    assert result["complete_run_blockers"] == []
    assert result["publish_blockers"] == []


def test_projection_work_universe_not_audited_blocks_complete_and_publish() -> None:
    cs = ClosureState(ready_to_close=True, ready_to_publish=True)
    result = _call_projection(closure_state=cs, work_universe_posture="partial")
    assert "work_universe_not_audited:partial" in result["complete_run_blockers"]
    assert "work_universe_not_audited:partial" in result["publish_blockers"]


def test_projection_hard_enforced_missing_dimension_blocks_complete() -> None:
    """Hard enforced policy with a required dimension absent → complete_run blocker."""
    cs = ClosureState(ready_to_close=True, ready_to_publish=True)
    policy = {
        "hard_enforced": True,
        "enforce_on_complete": True,
        "enforce_on_publish": False,
        "required_dimension_ids": ["layer_a"],
    }
    result = _call_projection(closure_policy=policy, closure_state=cs)
    assert any("required_dimensions_missing" in b for b in result["complete_run_blockers"])
    assert "layer_a" in " ".join(result["complete_run_blockers"])
    # Not in publish_blockers (enforce_on_publish=False)
    assert not any("required_dimensions_missing" in b for b in result["publish_blockers"])


def test_projection_hard_enforced_dimension_present_no_blocker() -> None:
    """Required dimension present in closure_state → no missing-dimension blocker."""
    cs = ClosureState(
        dimensions=[_dim("layer_a")],
        ready_to_close=True,
        ready_to_publish=True,
    )
    policy = {
        "hard_enforced": True,
        "enforce_on_complete": True,
        "required_dimension_ids": ["layer_a"],
    }
    result = _call_projection(closure_policy=policy, closure_state=cs)
    assert not any("required_dimensions_missing" in b for b in result["complete_run_blockers"])


def test_projection_closure_requires_hitl_blocks_complete_and_publish() -> None:
    """closure_state.requires_hitl=True + hard_enforced → both blocker lists."""
    cs = ClosureState(requires_hitl=True, ready_to_close=True, ready_to_publish=True)
    policy = {
        "hard_enforced": True,
        "enforce_on_complete": True,
        "enforce_on_publish": True,
    }
    result = _call_projection(closure_policy=policy, closure_state=cs)
    assert "closure_requires_hitl" in result["complete_run_blockers"]
    assert "closure_requires_hitl" in result["publish_blockers"]


def test_projection_resolution_items_require_hitl_blocks_complete_and_publish() -> None:
    """Outstanding item-level HITL requirements are mechanical closure blockers."""
    cs = ClosureState(ready_to_close=True, ready_to_publish=True)
    policy = {
        "hard_enforced": True,
        "enforce_on_complete": True,
        "enforce_on_publish": True,
    }
    result = _call_projection(
        closure_policy=policy,
        closure_state=cs,
        items_requires_hitl_count=2,
    )
    assert "items_require_hitl:2" in result["complete_run_blockers"]
    assert "items_require_hitl:2" in result["publish_blockers"]


def test_projection_covered_units_require_hitl_blocks_complete_and_publish() -> None:
    cs = ClosureState(ready_to_close=True, ready_to_publish=True)
    policy = {
        "hard_enforced": True,
        "enforce_on_complete": True,
        "enforce_on_publish": True,
    }
    result = _call_projection(
        closure_policy=policy,
        closure_state=cs,
        covered_units_requires_hitl_count=3,
    )
    assert "covered_units_require_hitl:3" in result["complete_run_blockers"]
    assert "covered_units_require_hitl:3" in result["publish_blockers"]


def test_projection_resolution_items_below_minimum_for_complete() -> None:
    """Items below minimum_resolution_items_for_complete → complete blocker."""
    cs = ClosureState(ready_to_close=True, ready_to_publish=True)
    policy = {"hard_enforced": True, "minimum_resolution_items_for_complete": 3}
    result = _call_projection(closure_policy=policy, closure_state=cs, resolution_item_count=1)
    assert any("resolution_items_below_minimum" in b for b in result["complete_run_blockers"])
    assert "1/3" in " ".join(result["complete_run_blockers"])


def test_projection_resolution_items_at_minimum_no_blocker() -> None:
    """Items at or above minimum → no minimum blocker."""
    cs = ClosureState(ready_to_close=True, ready_to_publish=True)
    policy = {"hard_enforced": True, "minimum_resolution_items_for_complete": 3}
    result = _call_projection(closure_policy=policy, closure_state=cs, resolution_item_count=3)
    assert not any("resolution_items_below_minimum" in b for b in result["complete_run_blockers"])


def test_projection_resolution_items_below_minimum_without_hard_enforcement_is_advisory_only() -> None:
    """Minimum item counts are not mechanical blockers unless hard_enforced is enabled."""
    cs = ClosureState(ready_to_close=True, ready_to_publish=True)
    policy = {
        "hard_enforced": False,
        "minimum_resolution_items_for_complete": 3,
        "minimum_resolution_items_for_publish": 2,
    }
    result = _call_projection(closure_policy=policy, closure_state=cs, resolution_item_count=1)
    assert not any("resolution_items_below_minimum" in b for b in result["complete_run_blockers"])
    assert not any("resolution_items_below_minimum" in b for b in result["publish_blockers"])


def test_projection_recent_patch_rejected_blocks_both() -> None:
    """Feedback outcome=rejected → both lists get recent_state_patch_rejected."""
    cs = ClosureState(ready_to_close=True, ready_to_publish=True)
    feedback = {"outcome": "rejected", "reason_code": "bad_path"}
    result = _call_projection(closure_state=cs, feedback=feedback)
    assert any("recent_state_patch_rejected:bad_path" == b for b in result["complete_run_blockers"])
    assert any("recent_state_patch_rejected:bad_path" == b for b in result["publish_blockers"])


def test_projection_skipped_rows_blocks_both() -> None:
    """skipped_resolution_rows in feedback → both lists get skipped_resolution_rows_pending."""
    cs = ClosureState(ready_to_close=True, ready_to_publish=True)
    feedback = {"skipped_resolution_rows": True}
    result = _call_projection(closure_state=cs, feedback=feedback)
    assert "skipped_resolution_rows_pending" in result["complete_run_blockers"]
    assert "skipped_resolution_rows_pending" in result["publish_blockers"]


def test_projection_closed_items_without_earned_determination_blocks() -> None:
    """closed_items_without_earned_determination_count > 0 → both lists blocked."""
    cs = ClosureState(ready_to_close=True, ready_to_publish=True)
    result = _call_projection(closure_state=cs, closed_items_without_earned_determination_count=2)
    assert any("closed_items_without_earned_determination:2" == b for b in result["complete_run_blockers"])
    assert any("closed_items_without_earned_determination:2" == b for b in result["publish_blockers"])


def test_projection_closed_items_without_basis_blocks() -> None:
    """closed_items_without_basis_count > 0 → both lists blocked."""
    cs = ClosureState(ready_to_close=True, ready_to_publish=True)
    result = _call_projection(closure_state=cs, closed_items_without_basis_count=1)
    assert any("closed_items_without_basis:1" == b for b in result["complete_run_blockers"])


def test_projection_closed_dimensions_without_earned_determination_blocks() -> None:
    """closed_dimensions_without_earned_determination_count > 0 → both lists blocked."""
    cs = ClosureState(ready_to_close=True, ready_to_publish=True)
    result = _call_projection(closure_state=cs, closed_dimensions_without_earned_determination_count=1)
    assert any("closed_dimensions_without_earned_determination:1" == b for b in result["complete_run_blockers"])


def test_projection_not_hard_enforced_skips_dimension_check() -> None:
    """Policy with hard_enforced=False → missing dimensions not a blocker."""
    cs = ClosureState(ready_to_close=True, ready_to_publish=True)
    policy = {
        "hard_enforced": False,
        "enforce_on_complete": True,
        "required_dimension_ids": ["layer_a"],
    }
    result = _call_projection(closure_policy=policy, closure_state=cs)
    assert not any("required_dimensions_missing" in b for b in result["complete_run_blockers"])


# ---------------------------------------------------------------------------
# _mechanical_flags
# ---------------------------------------------------------------------------


def _flags(**kwargs) -> list[str]:
    base = dict(
        feedback={},
        success_condition_count=0,
        resolution_item_count=0,
        closure_ready_to_close=False,
        repeated_state_patch_reason_code_streak=0,
        consecutive_same_active_item_turns=0,
        turns_since_resolution_item_count_change=None,
        new_resolution_items_since_last_complete_run_attempt=0,
        repeated_complete_run_without_state_change_count=0,
        same_ref_bundle_reread_no_gain_streak=0,
        same_item_same_ref_bundle_stall_streak=0,
        same_item_hydrate_churn_no_gain_streak=0,
        closed_candidate_units_missing_determined_value_count=0,
        closed_value_units_missing_evidence_count=0,
        earned_units_missing_verification_basis_count=0,
        sequenced_items_missing_scope_count=0,
        sequenced_items_missing_index_count=0,
        duplicate_sequence_positions_count=0,
        sequence_scope_order_gaps_count=0,
        group_items_without_subclaims_count=0,
        critical_closed_items_without_evidence_count=0,
        critical_closed_items_without_verification_basis_count=0,
        blocking_items_without_relations_count=0,
        closed_items_with_open_dependencies_count=0,
        explicit_non_blocking_without_notes_count=0,
        notebook_shaped_graph_rows_count=0,
        complete_run_blockers=[],
        claim_inventory_pressure_enabled=True,
    )
    base.update(kwargs)
    return _mechanical_flags(**base)


def test_flags_empty_by_default() -> None:
    assert _flags() == []


def test_flags_notebook_shaped_graph_rows() -> None:
    result = _flags(notebook_shaped_graph_rows_count=2)
    assert "notebook_shaped_graph_rows:2" in result


def test_flags_artifact_claim_inventory_suspect() -> None:
    result = _flags(artifact_claim_inventory_suspect_count=2)
    assert "artifact_claim_inventory_suspect:2" in result


def test_flags_repeated_rejection_streak() -> None:
    result = _flags(
        feedback={"reason_code": "bad_schema"},
        repeated_state_patch_reason_code_streak=2,
    )
    assert "state_patch_reason_code_repeated:bad_schema:2" in result


def test_flags_streak_below_threshold_no_flag() -> None:
    result = _flags(
        feedback={"reason_code": "bad_schema"},
        repeated_state_patch_reason_code_streak=1,
    )
    assert not any("bad_schema" in f for f in result)


def test_flags_same_active_item_threshold() -> None:
    result = _flags(consecutive_same_active_item_turns=3)
    assert "active_item_unchanged_turns:3" in result


def test_flags_same_active_item_below_threshold() -> None:
    result = _flags(consecutive_same_active_item_turns=2)
    assert not any("active_item_unchanged_turns:" in f for f in result)


def test_flags_stale_resolution_item_count() -> None:
    result = _flags(turns_since_resolution_item_count_change=4)
    assert "resolution_item_count_unchanged_turns:4" in result


def test_flags_stale_count_below_threshold() -> None:
    result = _flags(turns_since_resolution_item_count_change=3)
    assert not any("resolution_item_count_unchanged_turns:" in f for f in result)


def test_flags_new_items_since_complete_run() -> None:
    result = _flags(new_resolution_items_since_last_complete_run_attempt=2)
    assert "new_resolution_items_since_complete_run_attempt:2" in result


def test_flags_repeated_complete_run_without_state_change() -> None:
    result = _flags(repeated_complete_run_without_state_change_count=1)
    assert "repeated_complete_run_without_state_change:1" in result


def test_flags_resolution_items_without_success_conditions() -> None:
    """≥3 resolution items but 0 success_conditions → flag."""
    result = _flags(resolution_item_count=3, success_condition_count=0)
    assert "success_conditions_empty_with_resolution_items:3" in result


def test_flags_resolution_items_without_success_conditions_below_threshold() -> None:
    """2 resolution items → no success_condition coverage flag."""
    result = _flags(resolution_item_count=2, success_condition_count=0)
    assert not any("success_conditions_empty_with_resolution_items:" in f for f in result)


def test_flags_items_substantially_outnumber_conditions() -> None:
    """≥4 items and ≥2x conditions → probe-coverage flag."""
    result = _flags(resolution_item_count=8, success_condition_count=2)
    assert "resolution_items_outnumber_success_conditions:8_vs_2" in result


def test_flags_items_not_outnumbering_conditions() -> None:
    """Items < 2x conditions → no outnumber flag."""
    result = _flags(resolution_item_count=4, success_condition_count=3)
    assert not any("resolution_items_outnumber_success_conditions:" in f for f in result)


def test_flags_complete_run_blockers_with_not_ready_to_close() -> None:
    """Blockers present and not ready_to_close → mechanical reminder flag."""
    result = _flags(
        closure_ready_to_close=False,
        complete_run_blockers=["ready_to_close_false"],
    )
    assert "complete_run_blockers_present" in result


def test_flags_ready_to_close_with_blockers_suppresses_flag() -> None:
    """ready_to_close=True means no mechanical-blockers reminder."""
    result = _flags(
        closure_ready_to_close=True,
        complete_run_blockers=["some_blocker"],
    )
    assert "complete_run_blockers_present" not in result
    assert "complete_run_blocked:some_blocker" in result


def test_terminal_ready_snapshot_suppresses_stale_ready_to_close_false_blocker() -> None:
    cs = ClosureState(ready_to_close=True, ready_to_publish=True)
    result = _call_projection(closure_state=cs, work_universe_posture="audited")
    assert result["complete_run_blockers"] == []


def test_sanitize_complete_run_blockers_drops_stale_ready_to_close_false() -> None:
    cs = ClosureState(ready_to_close=True, ready_to_publish=False)
    result = _call_projection(closure_state=cs, work_universe_posture="audited")
    assert "ready_to_close_false" not in result["complete_run_blockers"]
    assert "ready_to_publish_false" in result["publish_blockers"]


def test_terminal_ready_summary_has_no_complete_run_blockers_present_flag() -> None:
    mem = _mem(ready_to_close=True, ready_to_publish=True, work_universe_posture="audited")
    summary = build_prompt_observability_summary(mem)
    assert summary["closure_readiness_projection"]["complete_run_blockers"] == []
    assert "complete_run_blockers_present" not in summary["mechanical_flags"]


def test_flags_surface_group_and_critical_rigor_gaps() -> None:
    result = _flags(
        group_items_without_subclaims_count=1,
        critical_closed_items_without_evidence_count=2,
        critical_closed_items_without_verification_basis_count=3,
        blocking_items_without_relations_count=1,
    )
    assert "group_items_without_subclaims:1" in result
    assert "critical_closed_items_without_evidence:2" in result
    assert "critical_closed_items_without_verification_basis:3" in result
    assert "blocking_items_without_relations:1" in result


def test_flags_surface_sequence_structure_gaps() -> None:
    result = _flags(
        sequenced_items_missing_scope_count=1,
        sequenced_items_missing_index_count=2,
        duplicate_sequence_positions_count=3,
        sequence_scope_order_gaps_count=1,
    )
    assert "sequenced_items_missing_scope:1" in result
    assert "sequenced_items_missing_index:2" in result
    assert "duplicate_sequence_positions:3" in result
    assert "sequence_scope_order_gaps:1" in result


def test_flags_capped_at_ten() -> None:
    """Output never exceeds 10 flags even when all conditions fire."""
    result = _flags(
        feedback={"reason_code": "r"},
        repeated_state_patch_reason_code_streak=3,
        consecutive_same_active_item_turns=5,
        turns_since_resolution_item_count_change=6,
        new_resolution_items_since_last_complete_run_attempt=3,
        repeated_complete_run_without_state_change_count=1,
        same_ref_bundle_reread_no_gain_streak=5,
        same_item_same_ref_bundle_stall_streak=5,
        resolution_item_count=10,
        success_condition_count=1,
        closure_ready_to_close=False,
        complete_run_blockers=["ready_to_close_false"],
    )
    assert len(result) <= 10


def test_flags_same_ref_bundle_reread_no_gain() -> None:
    result = _flags(same_ref_bundle_reread_no_gain_streak=3)
    assert "same_ref_bundle_reread_no_gain:3" in result


def test_flags_same_ref_bundle_reread_below_threshold() -> None:
    result = _flags(same_ref_bundle_reread_no_gain_streak=2)
    assert not any(f.startswith("same_ref_bundle_reread_no_gain") for f in result)


def test_flags_same_item_same_ref_bundle_stall() -> None:
    result = _flags(same_item_same_ref_bundle_stall_streak=4)
    assert "same_item_same_ref_bundle_stall:4" in result


def test_flags_same_item_same_ref_bundle_stall_below_threshold() -> None:
    result = _flags(same_item_same_ref_bundle_stall_streak=2)
    assert not any(f.startswith("same_item_same_ref_bundle_stall") for f in result)


def test_flags_same_item_hydrate_churn_no_gain_at_threshold() -> None:
    result = _flags(same_item_hydrate_churn_no_gain_streak=3)
    assert "same_item_hydrate_churn_no_gain:3" in result


def test_flags_same_item_hydrate_churn_below_threshold() -> None:
    result = _flags(same_item_hydrate_churn_no_gain_streak=2)
    assert not any(f.startswith("same_item_hydrate_churn_no_gain") for f in result)


def test_flags_closed_candidate_unit_missing_determined_value() -> None:
    result = _flags(closed_candidate_units_missing_determined_value_count=2)
    assert "closed_candidate_unit_missing_determined_value:2" in result


def test_flags_closed_value_unit_missing_evidence() -> None:
    result = _flags(closed_value_units_missing_evidence_count=1)
    assert "closed_value_unit_missing_evidence:1" in result



def test_flags_earned_unit_missing_verification_basis() -> None:
    result = _flags(earned_units_missing_verification_basis_count=3)
    assert "earned_unit_missing_verification_basis:3" in result


# ---------------------------------------------------------------------------
# Anti-spin streak semantics
# ---------------------------------------------------------------------------


def test_summary_same_ref_bundle_progress_is_not_counted_as_no_gain() -> None:
    records = [
        _step_record(
            1,
            action_inputs={"ref_slot": "working"},
            latest_refs_snapshot={"working": "ref-1"},
            work_state_signature="state-a",
        ),
        _step_record(
            2,
            action_inputs={"ref_slot": "working"},
            latest_refs_snapshot={"working": "ref-1"},
            work_state_signature="state-b",
        ),
        _step_record(
            3,
            action_inputs={"ref_slot": "working"},
            latest_refs_snapshot={"working": "ref-1"},
            work_state_signature="state-c",
        ),
    ]
    result = build_prompt_observability_summary(_mem(step_records=records))
    assert result["same_ref_bundle_reread_no_gain_streak"] == 1
    assert not any(flag.startswith("same_ref_bundle_reread_no_gain:") for flag in result["mechanical_flags"])


def test_summary_same_item_same_ref_bundle_progress_is_not_counted_as_stall() -> None:
    records = [
        _step_record(
            1,
            action_inputs={"ref_slot": "working"},
            active_item_id="item-1",
            latest_refs_snapshot={"working": "ref-1"},
            work_state_signature="state-a",
        ),
        _step_record(
            2,
            action_inputs={"ref_slot": "working"},
            active_item_id="item-1",
            latest_refs_snapshot={"working": "ref-1"},
            work_state_signature="state-b",
        ),
        _step_record(
            3,
            action_inputs={"ref_slot": "working"},
            active_item_id="item-1",
            latest_refs_snapshot={"working": "ref-1"},
            work_state_signature="state-c",
        ),
    ]
    mem = _mem(step_records=records)
    mem.continuity.active_item_id = "item-1"
    result = build_prompt_observability_summary(mem)
    assert result["same_ref_bundle_reread_no_gain_streak"] == 1
    assert result["same_item_same_ref_bundle_stall_streak"] == 1
    assert not any(flag.startswith("same_item_same_ref_bundle_stall:") for flag in result["mechanical_flags"])


def test_summary_same_item_same_ref_bundle_same_state_counts_true_no_gain_and_stall() -> None:
    records = [
        _step_record(
            1,
            action_inputs={"ref_slot": "working"},
            active_item_id="item-1",
            latest_refs_snapshot={"working": "ref-1"},
            work_state_signature="state-a",
        ),
        _step_record(
            2,
            action_inputs={"ref_slot": "working"},
            active_item_id="item-1",
            latest_refs_snapshot={"working": "ref-1"},
            work_state_signature="state-a",
        ),
        _step_record(
            3,
            action_inputs={"ref_slot": "working"},
            active_item_id="item-1",
            latest_refs_snapshot={"working": "ref-1"},
            work_state_signature="state-a",
        ),
    ]
    mem = _mem(step_records=records)
    mem.continuity.active_item_id = "item-1"
    result = build_prompt_observability_summary(mem)
    assert result["same_ref_bundle_reread_no_gain_streak"] == 3
    assert result["same_item_same_ref_bundle_stall_streak"] == 3
    assert "same_ref_bundle_reread_no_gain:3" in result["mechanical_flags"]
    assert "same_item_same_ref_bundle_stall:3" in result["mechanical_flags"]


# ---------------------------------------------------------------------------
# build_prompt_observability_summary — integration contract
# ---------------------------------------------------------------------------


def test_summary_returns_all_required_top_level_keys() -> None:
    mem = _mem()
    result = build_prompt_observability_summary(mem)
    for key in (
        "prompt_event_count",
        "resolution_item_count",
        "sequenced_item_count",
        "sequenced_items_missing_scope_count",
        "sequenced_items_missing_index_count",
        "duplicate_sequence_positions_count",
        "sequence_scope_order_gaps_count",
        "atomic_item_count",
        "group_item_count",
        "group_items_without_subclaims_count",
        "closed_items_count",
        "items_blocking_count",
        "items_requires_hitl_count",
        "items_no_further_progress_count",
        "closed_items_without_earned_determination_count",
        "closed_items_without_basis_count",
        "closed_items_without_completion_criteria_count",
        "critical_closed_items_without_evidence_count",
        "critical_closed_items_without_verification_basis_count",
        "blocking_items_without_relations_count",
        "closure_dimension_count",
        "success_condition_count",
        "work_universe_posture",
        "closure_readiness_projection",
        "mechanical_flags",
        "performance_evaluation",
    ):
        assert key in result, f"missing key: {key}"


def test_summary_counts_closed_items_without_earned_determination() -> None:
    items = [
        _item("i1", status="closed", determination="earned", verification_basis="checked"),
        _item("i2", status="closed"),  # no determination
        _item("i3", status="open"),
    ]
    mem = _mem(resolution_items=items)
    result = build_prompt_observability_summary(mem)
    assert result["resolution_item_count"] == 3
    assert result["closed_items_count"] == 2
    assert result["closed_items_without_earned_determination_count"] == 1


def test_summary_counts_item_blocking_hitl_and_no_further_progress_flags() -> None:
    items = [
        _item("i1", blocking=True, requires_hitl=True, no_further_progress=True),
        _item("i2", blocking=True),
        _item("i3"),
    ]
    mem = _mem(resolution_items=items)
    result = build_prompt_observability_summary(mem)
    assert result["items_blocking_count"] == 2
    assert result["items_requires_hitl_count"] == 1
    assert result["items_no_further_progress_count"] == 1


def test_summary_counts_unit_hitl_and_no_further_progress_separately_from_items() -> None:
    items = [
        _item(
            "g1",
            requires_hitl=True,
            covered_units=[
                ResolutionCoveredUnit(
                    unit_id="u1",
                    title="u1",
                    requires_hitl=True,
                    no_further_progress=True,
                ),
                ResolutionCoveredUnit(
                    unit_id="u2",
                    title="u2",
                    no_further_progress=True,
                ),
            ],
        ),
        _item("i2"),
    ]
    mem = _mem(resolution_items=items)
    result = build_prompt_observability_summary(mem)
    assert result["items_requires_hitl_count"] == 1
    assert result["items_no_further_progress_count"] == 0
    assert result["covered_units_requires_hitl_count"] == 1
    assert result["covered_units_no_further_progress_count"] == 2


def test_summary_counts_sequence_advisories() -> None:
    items = [
        _item("lane-a-1", status="open", sequence_scope="lane-a", sequence_index=1),
        _item("lane-a-dup", status="open", sequence_scope="lane-a", sequence_index=1),
        _item("lane-a-gap", status="open", sequence_scope="lane-a", sequence_index=3),
        _item("lane-missing-scope", status="open", sequence_index=1),
        _item("lane-missing-index", status="open", sequence_scope="lane-b"),
        _item("unsequenced", status="open"),
    ]
    mem = _mem(resolution_items=items)
    result = build_prompt_observability_summary(mem)
    assert result["sequenced_item_count"] == 3
    assert result["sequenced_items_missing_scope_count"] == 1
    assert result["sequenced_items_missing_index_count"] == 1
    assert result["duplicate_sequence_positions_count"] == 1
    assert result["sequence_scope_order_gaps_count"] == 1
    flags = result["mechanical_flags"]
    assert "sequenced_items_missing_scope:1" in flags
    assert "sequenced_items_missing_index:1" in flags
    assert "duplicate_sequence_positions:1" in flags
    assert "sequence_scope_order_gaps:1" in flags


def test_summary_does_not_flag_lane_that_is_contiguous_but_starts_later() -> None:
    items = [
        _item("lane-c-3", status="open", sequence_scope="lane-c", sequence_index=3),
        _item("lane-c-4", status="open", sequence_scope="lane-c", sequence_index=4),
    ]
    mem = _mem(resolution_items=items)
    result = build_prompt_observability_summary(mem)
    assert result["sequenced_item_count"] == 2
    assert result["duplicate_sequence_positions_count"] == 0
    assert result["sequence_scope_order_gaps_count"] == 0
    assert "sequence_scope_order_gaps:" not in result["mechanical_flags"]


def test_summary_counts_group_structure_and_thin_critical_proof_gaps() -> None:
    items = [
        _item("group-ok", status="open", structure_kind="group"),
        _item("atomic-a", status="open", structure_kind="atomic"),
        _item("group-missing", status="open", structure_kind="group"),
        _item(
            "critical-no-evidence",
            status="closed",
            materiality="critical",
            verification_basis="Compared against the strongest available source.",
        ),
        _item(
            "critical-no-basis",
            status="closed",
            materiality="critical",
            evidence_refs=["artifact://focused"],
        ),
        _item("blocking-no-rel", status="blocked", blocking=True),
    ]
    relations = [_rel("atomic-a", "group-ok", "subclaim_of")]
    mem = _mem(resolution_items=items, resolution_relations=relations)
    result = build_prompt_observability_summary(mem)
    assert result["atomic_item_count"] == 1
    assert result["group_item_count"] == 2
    assert result["group_items_without_subclaims_count"] == 1
    assert result["critical_closed_items_without_evidence_count"] == 1
    assert result["critical_closed_items_without_verification_basis_count"] == 1
    assert result["blocking_items_without_relations_count"] == 1
    flags = result["mechanical_flags"]
    assert "group_items_without_subclaims:1" in flags
    assert "critical_closed_items_without_evidence:1" in flags
    assert "critical_closed_items_without_verification_basis:1" in flags
    assert "blocking_items_without_relations:1" in flags


def test_summary_counts_closed_items_without_basis() -> None:
    items = [
        _item("i1", status="closed", verification_basis="doc reviewed"),
        _item("i2", status="closed"),  # no basis
    ]
    mem = _mem(resolution_items=items)
    result = build_prompt_observability_summary(mem)
    assert result["closed_items_without_basis_count"] == 1


def test_summary_counts_closure_dimensions() -> None:
    dims = [
        _dim("d1", determination="earned", verification_basis="checked"),
        _dim("d2"),  # no determination, no basis
    ]
    mem = _mem(dimensions=dims, ready_to_close=True)
    result = build_prompt_observability_summary(mem)
    assert result["closure_dimension_count"] == 2
    assert result["closed_dimensions_without_earned_determination_count"] == 1
    assert result["closed_dimensions_without_basis_count"] == 1


def test_group_item_with_covered_units_counts_as_decomposed() -> None:
    """A group item that carries covered_units should not be flagged as missing subclaims."""
    covered = [
        ResolutionCoveredUnit(unit_id="u1", title="sub-a"),
        ResolutionCoveredUnit(unit_id="u2", title="sub-b"),
    ]
    items = [
        _item("group-via-covered", status="open", structure_kind="group", covered_units=covered),
        _item("group-bare", status="open", structure_kind="group"),
    ]
    mem = _mem(resolution_items=items)
    result = build_prompt_observability_summary(mem)
    assert result["group_item_count"] == 2
    assert result["group_items_without_subclaims_count"] == 1


def test_determined_value_without_evidence_flags_missing_evidence_even_without_candidates() -> None:
    """Closed/earned units with determined_value must have evidence_refs regardless of candidates."""
    covered_no_candidates = [
        ResolutionCoveredUnit(
            unit_id="u-exact",
            title="exact-value",
            status="closed",
            determination="earned",
            determined_value="1638 feet",
            # no candidate_values, no evidence_refs — the exact loophole
        ),
    ]
    items = [_item("parent", status="open", covered_units=covered_no_candidates)]
    mem = _mem(resolution_items=items)
    result = build_prompt_observability_summary(mem)
    assert result["closed_value_units_missing_evidence_count"] == 1


def test_summary_closure_readiness_projection_populated_from_policy() -> None:
    """With a closure policy that has an unmet requirement, projection carries the blocker."""
    items = [_item("i1")]
    mem = _mem(resolution_items=items, ready_to_close=True, ready_to_publish=True)
    policy = {
        "hard_enforced": True,
        "enforce_on_complete": True,
        "required_dimension_ids": ["layer_z"],
    }
    result = build_prompt_observability_summary(mem, closure_policy=policy)
    blockers = result["closure_readiness_projection"]["complete_run_blockers"]
    assert any("layer_z" in b for b in blockers)


def test_summary_mechanical_flags_populated_for_stale_active_item() -> None:
    """consecutive_same_active_item_turns >= 3 surfaces a mechanical flag."""
    records = [
        {"skip_execution": False, "active_item_id_snapshot": "item-x", "execution_state": "executed"},
        {"skip_execution": False, "active_item_id_snapshot": "item-x", "execution_state": "executed"},
        {"skip_execution": False, "active_item_id_snapshot": "item-x", "execution_state": "executed"},
    ]
    mem = _mem(step_records=records)
    mem.continuity.active_item_id = "item-x"
    result = build_prompt_observability_summary(mem)
    flags: list[str] = result["mechanical_flags"]
    assert "active_item_unchanged_turns:3" in flags


def test_summary_surfaces_work_universe_posture_and_projection_blocker() -> None:
    mem = _mem(work_universe_posture="believed_adequate", ready_to_close=True, ready_to_publish=True)
    result = build_prompt_observability_summary(mem)
    assert result["work_universe_posture"] == "believed_adequate"
    projection = result["closure_readiness_projection"]
    assert "work_universe_not_audited:believed_adequate" in projection["complete_run_blockers"]
    assert "work_universe_not_audited:believed_adequate" in projection["publish_blockers"]


def test_summary_covered_unit_count_exposed_even_when_zero() -> None:
    """covered_unit_count is a graph-shape counter and must appear even at zero."""
    items = [_item("i1", status="open")]
    mem = _mem(resolution_items=items)
    result = build_prompt_observability_summary(mem)
    assert "covered_unit_count" in result
    assert result["covered_unit_count"] == 0


def test_summary_covered_unit_count_counts_all_units_across_items() -> None:
    units_a = [ResolutionCoveredUnit(unit_id="u1", title="a")]
    units_b = [
        ResolutionCoveredUnit(unit_id="u2", title="b"),
        ResolutionCoveredUnit(unit_id="u3", title="c"),
    ]
    items = [
        _item("parent-a", status="open", covered_units=units_a),
        _item("parent-b", status="open", covered_units=units_b),
    ]
    mem = _mem(resolution_items=items)
    result = build_prompt_observability_summary(mem)
    assert result["covered_unit_count"] == 3


def test_flags_coarse_work_graph_fires_under_partial_with_stable_thin_graph() -> None:
    """Partial posture + 3+ items + 0 atomic + 0 covered + stable + same active item → flag."""
    result = _flags(
        work_universe_posture="partial",
        resolution_item_count=4,
        atomic_item_count=0,
        covered_unit_count=0,
        turns_since_resolution_item_count_change=5,
        consecutive_same_active_item_turns=3,
    )
    assert any(f.startswith("coarse_work_graph_under_active_investigation:") for f in result)


def test_flags_coarse_work_graph_requires_partial_posture() -> None:
    """Audited posture should not fire the coarse-graph flag even if the structure matches."""
    result = _flags(
        work_universe_posture="audited",
        resolution_item_count=4,
        atomic_item_count=0,
        covered_unit_count=0,
        turns_since_resolution_item_count_change=5,
        consecutive_same_active_item_turns=3,
    )
    assert not any(f.startswith("coarse_work_graph_under_active_investigation") for f in result)


def test_flags_coarse_work_graph_suppressed_when_atomic_items_exist() -> None:
    """Presence of any atomic item suppresses the coarse-graph flag."""
    result = _flags(
        work_universe_posture="partial",
        resolution_item_count=4,
        atomic_item_count=1,
        covered_unit_count=0,
        turns_since_resolution_item_count_change=5,
        consecutive_same_active_item_turns=3,
    )
    assert not any(f.startswith("coarse_work_graph_under_active_investigation") for f in result)


def test_flags_coarse_work_graph_suppressed_when_covered_units_exist() -> None:
    result = _flags(
        work_universe_posture="partial",
        resolution_item_count=4,
        atomic_item_count=0,
        covered_unit_count=2,
        turns_since_resolution_item_count_change=5,
        consecutive_same_active_item_turns=3,
    )
    assert not any(f.startswith("coarse_work_graph_under_active_investigation") for f in result)


def test_flags_coarse_work_graph_requires_stable_and_dwell_signals() -> None:
    """Structural shape alone is not enough; the graph must be stable and activity repeated."""
    result = _flags(
        work_universe_posture="partial",
        resolution_item_count=4,
        atomic_item_count=0,
        covered_unit_count=0,
        turns_since_resolution_item_count_change=1,
        consecutive_same_active_item_turns=0,
    )
    assert not any(f.startswith("coarse_work_graph_under_active_investigation") for f in result)


def test_flags_coarse_work_graph_fires_via_hydrate_churn_signal() -> None:
    """Repeated hydrate churn on the same item can substitute for same-active-item dwell."""
    result = _flags(
        work_universe_posture="partial",
        resolution_item_count=3,
        atomic_item_count=0,
        covered_unit_count=0,
        turns_since_resolution_item_count_change=3,
        consecutive_same_active_item_turns=0,
        same_item_hydrate_churn_no_gain_streak=2,
    )
    assert any(f.startswith("coarse_work_graph_under_active_investigation:") for f in result)


def test_summary_success_condition_coverage_counted() -> None:
    conds = [
        _condition("c1", determination="earned", verification_basis="reviewed"),
        _condition("c2"),
    ]
    mem = _mem(success_conditions=conds)
    result = build_prompt_observability_summary(mem)
    assert result["success_condition_count"] == 2
    assert result["success_conditions_with_earned_determination_count"] == 1
    assert result["success_conditions_with_verification_basis_count"] == 1


# ---------------------------------------------------------------------------
# closed_items_with_open_dependencies_count — structural dependency flag
# ---------------------------------------------------------------------------


def test_summary_closed_item_with_open_dependency_detected() -> None:
    """Closed item whose dependency list points to an open item triggers the count."""
    dep = _item("dep-open", status="open")
    closed = _item("closed-a", status="closed", dependencies=["dep-open"])
    mem = _mem(resolution_items=[dep, closed])
    result = build_prompt_observability_summary(mem)
    assert result["closed_items_with_open_dependencies_count"] == 1


def test_summary_closed_item_with_closed_dependency_not_flagged() -> None:
    """Closed item whose dependency is also closed does not trigger."""
    dep = _item("dep-closed", status="closed", determination="earned", verification_basis="ok")
    closed = _item("closed-b", status="closed", dependencies=["dep-closed"])
    mem = _mem(resolution_items=[dep, closed])
    result = build_prompt_observability_summary(mem)
    assert result["closed_items_with_open_dependencies_count"] == 0


def test_summary_open_item_with_open_dependency_not_flagged() -> None:
    """Only closed items are examined — open items with open deps don't count."""
    dep = _item("dep-open", status="open")
    parent = _item("open-parent", status="open", dependencies=["dep-open"])
    mem = _mem(resolution_items=[dep, parent])
    result = build_prompt_observability_summary(mem)
    assert result["closed_items_with_open_dependencies_count"] == 0


def test_flags_closed_item_with_open_dependency_fires() -> None:
    """_mechanical_flags surfaces the count when > 0."""
    result = _flags(closed_items_with_open_dependencies_count=2)
    assert "closed_item_with_open_dependency:2" in result


def test_flags_closed_item_with_open_dependency_zero_no_flag() -> None:
    result = _flags(closed_items_with_open_dependencies_count=0)
    assert not any(f.startswith("closed_item_with_open_dependency:") for f in result)


def test_summary_closed_item_blocked_by_open_via_blocks_relation() -> None:
    """An open item with a `blocks` relation targeting a closed item triggers the count."""
    blocker = _item("blocker", status="open")
    closed = _item("closed-c", status="closed", determination="earned", verification_basis="ok")
    rel = _rel("blocker", "closed-c", "blocks")
    mem = _mem(resolution_items=[blocker, closed], resolution_relations=[rel])
    result = build_prompt_observability_summary(mem)
    assert result["closed_items_with_open_dependencies_count"] == 1


def test_summary_closed_item_blocked_by_open_via_prerequisite_of_relation() -> None:
    """An open item with a `prerequisite_of` relation targeting a closed item triggers."""
    prereq = _item("prereq", status="open")
    closed = _item("closed-d", status="closed", determination="earned", verification_basis="ok")
    rel = _rel("prereq", "closed-d", "prerequisite_of")
    mem = _mem(resolution_items=[prereq, closed], resolution_relations=[rel])
    result = build_prompt_observability_summary(mem)
    assert result["closed_items_with_open_dependencies_count"] == 1


def test_summary_open_item_blocked_by_closed_not_flagged() -> None:
    """Reversed direction (closed blocks open) is normal forward-dependency ordering; no flag."""
    closed_blocker = _item("closed-e", status="closed", determination="earned", verification_basis="ok")
    waiting = _item("waiting", status="open")
    rel = _rel("closed-e", "waiting", "blocks")
    mem = _mem(resolution_items=[closed_blocker, waiting], resolution_relations=[rel])
    result = build_prompt_observability_summary(mem)
    assert result["closed_items_with_open_dependencies_count"] == 0


def test_summary_subclaim_of_relation_not_counted_as_blocking() -> None:
    """`subclaim_of` is not a blocking relation type; should not trigger the flag."""
    parent = _item("parent", status="open")
    child = _item("child", status="closed", determination="earned", verification_basis="ok")
    rel = _rel("child", "parent", "subclaim_of")
    mem = _mem(resolution_items=[parent, child], resolution_relations=[rel])
    result = build_prompt_observability_summary(mem)
    assert result["closed_items_with_open_dependencies_count"] == 0


# ---------------------------------------------------------------------------
# explicit_non_blocking_without_notes_count — structural non-blocking flag
# ---------------------------------------------------------------------------


def test_summary_explicit_non_blocking_without_notes_detected() -> None:
    """Item with blocking=False and no notes triggers the count."""
    it = _item("no-notes", status="open", blocking=False)
    mem = _mem(resolution_items=[it])
    result = build_prompt_observability_summary(mem)
    assert result["explicit_non_blocking_without_notes_count"] == 1


def test_summary_explicit_non_blocking_with_notes_not_flagged() -> None:
    """Item with blocking=False but notes present does not trigger."""
    it = _item("has-notes", status="open", blocking=False, notes="range conflict is cosmetic")
    mem = _mem(resolution_items=[it])
    result = build_prompt_observability_summary(mem)
    assert result["explicit_non_blocking_without_notes_count"] == 0


def test_summary_explicit_non_blocking_with_verification_basis_not_flagged() -> None:
    """Item with blocking=False but verification_basis present does not trigger."""
    it = _item("has-basis", status="open", blocking=False, verification_basis="confirmed non-binding")
    mem = _mem(resolution_items=[it])
    result = build_prompt_observability_summary(mem)
    assert result["explicit_non_blocking_without_notes_count"] == 0


def test_summary_none_blocking_not_flagged() -> None:
    """Item with blocking=None (default) is not counted — only explicit False."""
    it = _item("default-blocking", status="open")
    assert it.blocking is None
    mem = _mem(resolution_items=[it])
    result = build_prompt_observability_summary(mem)
    assert result["explicit_non_blocking_without_notes_count"] == 0


def test_flags_explicit_non_blocking_without_notes_fires() -> None:
    result = _flags(explicit_non_blocking_without_notes_count=1)
    assert "explicit_non_blocking_without_notes:1" in result


def test_flags_explicit_non_blocking_without_notes_zero_no_flag() -> None:
    result = _flags(explicit_non_blocking_without_notes_count=0)
    assert not any(f.startswith("explicit_non_blocking_without_notes:") for f in result)


# ---------------------------------------------------------------------------
# output_claim_coverage_debt flag
# ---------------------------------------------------------------------------


def test_flags_output_claim_coverage_debt_fires_when_closure_ready_no_inventory() -> None:
    """closure_ready_to_close + ≥2 items + no atomic/covered inventory → flag fires."""
    result = _flags(resolution_item_count=3, closure_ready_to_close=True)
    assert any(f.startswith("output_claim_coverage_debt:") for f in result)


def test_flags_output_claim_coverage_debt_fires_when_posture_believed_adequate() -> None:
    """believed_adequate posture triggers the flag even without ready_to_close."""
    result = _flags(resolution_item_count=4, work_universe_posture="believed_adequate")
    assert any(f.startswith("output_claim_coverage_debt:") for f in result)


def test_flags_output_claim_coverage_debt_fires_when_posture_audited() -> None:
    """audited posture triggers the flag even without ready_to_close."""
    result = _flags(resolution_item_count=2, work_universe_posture="audited")
    assert any(f.startswith("output_claim_coverage_debt:") for f in result)


def test_flags_output_claim_coverage_debt_not_fired_with_atomic_items() -> None:
    """A small graph with at least one atomic item has some claim inventory."""
    result = _flags(resolution_item_count=3, closure_ready_to_close=True, atomic_item_count=1)
    assert not any(f.startswith("output_claim_coverage_debt:") for f in result)


def test_flags_output_claim_coverage_debt_fires_with_sparse_atomic_inventory() -> None:
    """One or two atomic rows should not hide a broad closure graph."""
    result = _flags(resolution_item_count=6, closure_ready_to_close=True, atomic_item_count=2)
    assert "output_claim_coverage_debt:6" in result


def test_flags_output_claim_coverage_debt_not_fired_with_balanced_atomic_inventory() -> None:
    """Enough atomic rows for the graph shape suppresses the structural warning."""
    result = _flags(resolution_item_count=4, closure_ready_to_close=True, atomic_item_count=2)
    assert not any(f.startswith("output_claim_coverage_debt:") for f in result)


def test_flags_output_claim_coverage_debt_not_fired_with_covered_units() -> None:
    """covered_unit_count > 0 suppresses the flag — claim inventory is present."""
    result = _flags(resolution_item_count=3, closure_ready_to_close=True, covered_unit_count=2)
    assert not any(f.startswith("output_claim_coverage_debt:") for f in result)


def test_flags_output_claim_coverage_debt_not_fired_with_too_few_items() -> None:
    """Fewer than 2 resolution items → flag suppressed (no meaningful work graph to audit)."""
    result = _flags(resolution_item_count=1, closure_ready_to_close=True)
    assert not any(f.startswith("output_claim_coverage_debt:") for f in result)


def test_flags_output_claim_coverage_debt_not_fired_when_not_approaching_closure() -> None:
    """Initial posture and not ready_to_close → flag suppressed (not in closure zone)."""
    result = _flags(
        resolution_item_count=5,
        work_universe_posture="initial",
        closure_ready_to_close=False,
    )
    assert not any(f.startswith("output_claim_coverage_debt:") for f in result)


def test_flags_output_claim_coverage_debt_carries_item_count() -> None:
    """Flag string encodes the resolution_item_count for observability."""
    result = _flags(resolution_item_count=7, closure_ready_to_close=True)
    assert "output_claim_coverage_debt:7" in result


# ---------------------------------------------------------------------------
# notebook_shaped_graph_rows flag
# ---------------------------------------------------------------------------


def test_notebook_shaped_graph_rows_flags_closed_prose_heavy_item() -> None:
    long_prose = "This closed row carries paragraph-like notebook prose without compact anchors. " * 5
    item = _item("i1", status="closed", determination="earned", notes=long_prose)
    summary = build_prompt_observability_summary(_mem(resolution_items=[item]))

    assert summary["notebook_shaped_graph_rows_count"] == 1
    assert "notebook_shaped_graph_rows:1" in summary["mechanical_flags"]


def test_notebook_shaped_graph_rows_does_not_flag_open_working_item() -> None:
    long_prose = "This open row can still need prose while the item is actively being worked. " * 5
    item = _item("i1", status="open", notes=long_prose)
    summary = build_prompt_observability_summary(_mem(resolution_items=[item]))

    assert summary["notebook_shaped_graph_rows_count"] == 0
    assert not any(flag.startswith("notebook_shaped_graph_rows") for flag in summary["mechanical_flags"])


def test_notebook_shaped_graph_rows_does_not_flag_compact_closed_atom() -> None:
    unit = ResolutionCoveredUnit(
        unit_id="u1",
        title="compact atom",
        status="closed",
        determination="earned",
        candidate_values=["A", "B"],
        determined_value="A",
        evidence_refs=["artifact://evidence"],
        closure_summary="A was verified.",
    )
    item = _item(
        "i1",
        status="closed",
        determination="earned",
        verification_basis="Compact evidence check passed.",
        evidence_refs=["artifact://evidence"],
        covered_units=[unit],
    )
    summary = build_prompt_observability_summary(_mem(resolution_items=[item]))

    assert summary["notebook_shaped_graph_rows_count"] == 0
    assert not any(flag.startswith("notebook_shaped_graph_rows") for flag in summary["mechanical_flags"])


# ---------------------------------------------------------------------------
# artifact_claim_inventory_suspect flag
# ---------------------------------------------------------------------------


def test_artifact_claim_inventory_suspect_fires_near_closure_with_substantial_artifact_and_empty_inventory() -> None:
    result_record = _result_record(
        1,
        artifact_refs=["artifact://working"],
        outputs_for_continuity={"payload": {"text": "substantial output text " * 60}},
    )
    summary = build_prompt_observability_summary(
        _mem(ready_to_close=True, step_result_records=[result_record]),
        claim_inventory_pressure_enabled=True,
    )

    assert summary["artifact_claim_inventory_suspect_count"] == 1
    assert "artifact_claim_inventory_suspect:1" in summary["mechanical_flags"]
    assert "complete_run_blockers_present" not in summary["mechanical_flags"]


def test_artifact_claim_inventory_suspect_does_not_fire_when_not_near_closure() -> None:
    result_record = _result_record(
        1,
        artifact_refs=["artifact://working"],
        outputs_for_continuity={"payload": {"text": "substantial output text " * 60}},
    )
    summary = build_prompt_observability_summary(
        _mem(work_universe_posture="partial", step_result_records=[result_record])
    )

    assert summary["artifact_claim_inventory_suspect_count"] == 0
    assert not any(flag.startswith("artifact_claim_inventory_suspect") for flag in summary["mechanical_flags"])


def test_artifact_claim_inventory_suspect_does_not_fire_with_compact_inventory() -> None:
    unit = ResolutionCoveredUnit(
        unit_id="u1",
        title="compact atom",
        status="closed",
        determination="earned",
        candidate_values=["A", "B"],
        determined_value="A",
        evidence_refs=["artifact://evidence"],
    )
    item = _item("i1", status="closed", structure_kind="group", covered_units=[unit])
    result_record = _result_record(
        1,
        artifact_refs=["artifact://working"],
        outputs_for_continuity={"payload": {"text": "substantial output text " * 60}},
    )
    summary = build_prompt_observability_summary(
        _mem(ready_to_close=True, resolution_items=[item], step_result_records=[result_record])
    )

    assert summary["artifact_claim_inventory_suspect_count"] == 0
    assert not any(flag.startswith("artifact_claim_inventory_suspect") for flag in summary["mechanical_flags"])


def test_artifact_claim_inventory_suspect_does_not_fire_for_small_artifact_payload() -> None:
    result_record = _result_record(
        1,
        artifact_refs=["artifact://working"],
        outputs_for_continuity={"payload": {"text": "small output"}},
    )
    summary = build_prompt_observability_summary(
        _mem(ready_to_close=True, step_result_records=[result_record])
    )

    assert summary["artifact_claim_inventory_suspect_count"] == 0
    assert not any(flag.startswith("artifact_claim_inventory_suspect") for flag in summary["mechanical_flags"])


def test_claim_inventory_flags_suppressed_when_pressure_disabled() -> None:
    result_record = _result_record(
        1,
        artifact_refs=["artifact://working"],
        outputs_for_continuity={"payload": {"text": "substantial output text " * 60}},
    )
    summary = build_prompt_observability_summary(
        _mem(ready_to_close=True, step_result_records=[result_record]),
        claim_inventory_pressure_enabled=False,
    )
    assert summary["artifact_claim_inventory_suspect_count"] == 1
    assert not any(flag.startswith("artifact_claim_inventory_suspect") for flag in summary["mechanical_flags"])
    assert not any(flag.startswith("output_claim_coverage_debt") for flag in summary["mechanical_flags"])
    assert not any(
        flag.startswith("coarse_work_graph_under_active_investigation")
        for flag in summary["mechanical_flags"]
    )


def test_claim_inventory_flags_surface_when_pressure_enabled() -> None:
    result_record = _result_record(
        1,
        artifact_refs=["artifact://working"],
        outputs_for_continuity={"payload": {"text": "substantial output text " * 60}},
    )
    summary = build_prompt_observability_summary(
        _mem(ready_to_close=True, step_result_records=[result_record]),
        claim_inventory_pressure_enabled=True,
    )
    assert summary["artifact_claim_inventory_suspect_count"] == 1
    assert "artifact_claim_inventory_suspect:1" in summary["mechanical_flags"]


# ---------------------------------------------------------------------------
# Brief 1, items 2-4: semantic_repair_debt / pending_hitl_integration /
# reread_after_failed_persist_risk surface through loop_health_summary.
# ---------------------------------------------------------------------------


def test_semantic_repair_debt_surfaces_in_mechanical_flags() -> None:
    mem = _mem(
        state_patch_feedback={
            "outcome": "rejected",
            "iteration": 5,
            "reason_code": "state_patch_unknown_keys",
            "semantic_repair_debt": ["determined_value", "evidence_refs"],
        },
    )
    result = build_prompt_observability_summary(mem)
    assert result["semantic_repair_debt"] == ["determined_value", "evidence_refs"]
    assert any(
        f.startswith("semantic_repair_debt:") and "determined_value" in f
        for f in result["mechanical_flags"]
    ), result["mechanical_flags"]


def test_pending_hitl_integration_surfaces_in_mechanical_flags() -> None:
    mem = _mem(
        state_patch_feedback={
            "outcome": "rejected",
            "iteration": 7,
            "pending_hitl_integration_prompt_ids": ["hitl-abc", "hitl-def"],
        },
    )
    result = build_prompt_observability_summary(mem)
    assert result["pending_hitl_integration_prompt_ids"] == ["hitl-abc", "hitl-def"]
    assert any(
        f.startswith("pending_hitl_integration:2") for f in result["mechanical_flags"]
    ), result["mechanical_flags"]


def test_reread_after_failed_persist_risk_fires_when_recent_step_is_hydrate() -> None:
    mem = _mem(
        state_patch_feedback={
            "outcome": "rejected",
            "iteration": 10,
            "reason_code": "state_patch_unknown_keys",
        },
        step_records=[
            {
                "kernel_turn_index": 11,
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_ids": ["artifact://1"]},
                "execution_state": "executed",
            }
        ],
    )
    result = build_prompt_observability_summary(mem)
    assert any(
        f.startswith("reread_after_failed_persist_risk:") for f in result["mechanical_flags"]
    ), result["mechanical_flags"]


def test_reread_after_failed_persist_risk_does_not_fire_after_repair_apply() -> None:
    mem = _mem(
        state_patch_feedback={"outcome": "applied", "iteration": 11},
        step_records=[
            {
                "kernel_turn_index": 11,
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_ids": ["artifact://1"]},
                "execution_state": "executed",
            }
        ],
    )
    result = build_prompt_observability_summary(mem)
    assert not any(
        f.startswith("reread_after_failed_persist_risk:") for f in result["mechanical_flags"]
    )


def test_reread_after_failed_persist_risk_fires_when_no_patch_but_debt_sticky() -> None:
    """Live shape: outcome resets to no_patch on a hydrate turn while
    semantic_repair_debt remains sticky from an earlier failed persist."""
    mem = _mem(
        state_patch_feedback={
            "outcome": "no_patch",
            "iteration": 12,
            "semantic_repair_debt": ["determined_value"],
        },
        step_records=[
            {
                "kernel_turn_index": 12,
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_ids": ["artifact://1"]},
                "execution_state": "executed",
            }
        ],
    )
    result = build_prompt_observability_summary(mem)
    assert any(
        f.startswith("reread_after_failed_persist_risk:") for f in result["mechanical_flags"]
    ), result["mechanical_flags"]


def test_reread_after_failed_persist_risk_fires_when_pending_hitl_integration() -> None:
    mem = _mem(
        state_patch_feedback={
            "outcome": "no_patch",
            "iteration": 13,
            "pending_hitl_integration_prompt_ids": ["hitl-abc"],
        },
        step_records=[
            {
                "kernel_turn_index": 13,
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_ids": ["artifact://1"]},
                "execution_state": "executed",
            }
        ],
    )
    result = build_prompt_observability_summary(mem)
    assert any(
        f.startswith("reread_after_failed_persist_risk:") for f in result["mechanical_flags"]
    ), result["mechanical_flags"]


def test_reread_after_failed_persist_risk_does_not_fire_without_failed_persist() -> None:
    mem = _mem(
        state_patch_feedback={"outcome": "no_patch", "iteration": 11},
        step_records=[
            {
                "kernel_turn_index": 11,
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_ids": ["artifact://1"]},
                "execution_state": "executed",
            }
        ],
    )
    result = build_prompt_observability_summary(mem)
    assert not any(
        f.startswith("reread_after_failed_persist_risk:") for f in result["mechanical_flags"]
    )


# ---------------------------------------------------------------------------
# Brief 2: earned_unit_missing_locator + long_determined_value_units flags
# ---------------------------------------------------------------------------


def _unit(unit_id: str, **kwargs) -> ResolutionCoveredUnit:
    base = {
        "unit_id": unit_id,
        "title": kwargs.pop("title", unit_id),
        "kind": kwargs.pop("kind", None),
        "status": kwargs.pop("status", None),
        "determination": kwargs.pop("determination", None),
        "verification_basis": kwargs.pop("verification_basis", None),
        "evidence_refs": list(kwargs.pop("evidence_refs", []) or []),
        "evidence_locators": list(kwargs.pop("evidence_locators", []) or []),
        "candidate_values": list(kwargs.pop("candidate_values", []) or []),
        "determined_value": kwargs.pop("determined_value", None),
    }
    return ResolutionCoveredUnit.model_validate({k: v for k, v in base.items() if v is not None or k in {"unit_id", "title"}})


def test_earned_unit_missing_locator_flag_fires_when_locator_absent() -> None:
    unit = _unit(
        "u1",
        status="closed",
        determination="earned",
        verification_basis="ok",
        evidence_refs=["artifact://x"],
        determined_value="v",
    )
    item = _item("i1", status="closed", determination="earned", verification_basis="ok", covered_units=[unit])
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["earned_units_missing_locator_count"] == 1
    assert any(f.startswith("earned_unit_missing_locator:1") for f in result["mechanical_flags"])


def test_earned_unit_with_locator_does_not_flag() -> None:
    from harness.mission_state import EvidenceLocator
    locator = EvidenceLocator(ref_id="artifact://x", locator_kind="image_region", box_norm=[0.1, 0.1, 0.2, 0.2])
    unit = _unit(
        "u1",
        status="closed",
        determination="earned",
        verification_basis="ok",
        evidence_refs=["artifact://x"],
        evidence_locators=[locator],
        determined_value="v",
    )
    item = _item("i1", status="closed", determination="earned", verification_basis="ok", covered_units=[unit])
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["earned_units_missing_locator_count"] == 0
    assert not any(f.startswith("earned_unit_missing_locator:") for f in result["mechanical_flags"])


def test_open_unit_does_not_trigger_locator_flag() -> None:
    unit = _unit("u1", status="open", evidence_refs=["artifact://x"], determined_value="v")
    item = _item("i1", status="open", covered_units=[unit])
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["earned_units_missing_locator_count"] == 0


def test_long_determined_value_flag_fires_when_value_is_long() -> None:
    unit = _unit(
        "u1",
        status="closed",
        determination="earned",
        verification_basis="ok",
        evidence_refs=["artifact://x"],
        determined_value="x" * 250,
    )
    item = _item("i1", status="closed", determination="earned", verification_basis="ok", covered_units=[unit])
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["long_determined_value_units_count"] == 1
    assert any(f.startswith("long_determined_value_units:1") for f in result["mechanical_flags"])


def test_short_determined_value_does_not_flag() -> None:
    unit = _unit(
        "u1",
        status="closed",
        determination="earned",
        verification_basis="ok",
        evidence_refs=["artifact://x"],
        determined_value="N. 4°00' W.",
    )
    item = _item("i1", status="closed", determination="earned", verification_basis="ok", covered_units=[unit])
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["long_determined_value_units_count"] == 0
    assert not any(f.startswith("long_determined_value_units:") for f in result["mechanical_flags"])


# ---------------------------------------------------------------------------
# Track 2: Local-proof debt — run-9 regression shape
# ---------------------------------------------------------------------------


def _earned_unit_no_locator(
    unit_id: str,
    *,
    determined_value: str = "N. 4° 00' W.",
    evidence_refs: list[str] | None = None,
) -> ResolutionCoveredUnit:
    """Covered unit shaped like a run-9 atom: earned, compact value, refs but no locators."""
    return ResolutionCoveredUnit(
        unit_id=unit_id,
        title=unit_id,
        status="closed",
        determination="earned",
        determined_value=determined_value,
        evidence_refs=list(evidence_refs or ["image:assoc:draft_legal_text_image:original"]),
        evidence_locators=[],
    )


def test_earned_unit_missing_locator_count_for_run9_shape() -> None:
    """A run-9-shaped covered unit (earned, compact value, refs, no locators) is counted."""
    unit = _earned_unit_no_locator("bearing-unit")
    items = [_item("parent", status="open", covered_units=[unit])]
    mem = _mem(resolution_items=items)
    result = build_prompt_observability_summary(mem)
    assert result["earned_units_missing_locator_count"] == 1


def test_earned_unit_missing_locator_flag_fires() -> None:
    """earned_unit_missing_locator:N flag fires when count > 0."""
    unit = _earned_unit_no_locator("bearing-unit")
    items = [_item("parent", status="open", covered_units=[unit])]
    mem = _mem(resolution_items=items)
    result = build_prompt_observability_summary(mem)
    assert "earned_unit_missing_locator:1" in result["mechanical_flags"]


def test_earned_units_missing_locator_count_in_compact_observability() -> None:
    """earned_units_missing_locator_count appears in compact summary even when zero."""
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )
    mem = _mem(resolution_items=[])
    full = build_prompt_observability_summary(mem)
    compact = _compact_prompt_observability_summary(full)
    assert "earned_units_missing_locator_count" in compact


def test_shared_unlocated_evidence_count_zero_when_all_units_unique_refs() -> None:
    """No shared refs → shared_unlocated_evidence_for_earned_units_count == 0."""
    unit_a = _earned_unit_no_locator("u-a", evidence_refs=["image:assoc:doc:original"])
    unit_b = _earned_unit_no_locator("u-b", evidence_refs=["image:assoc:doc:page2"])
    items = [_item("parent", status="open", covered_units=[unit_a, unit_b])]
    mem = _mem(resolution_items=items)
    result = build_prompt_observability_summary(mem)
    assert result["shared_unlocated_evidence_for_earned_units_count"] == 0


def test_shared_unlocated_evidence_count_fires_when_multiple_units_share_one_ref() -> None:
    """Multiple earned unlocated units citing the same broad ref → flag fires."""
    broad_ref = "image:assoc:draft_legal_text_image:original"
    unit_a = _earned_unit_no_locator("u-a", evidence_refs=[broad_ref])
    unit_b = _earned_unit_no_locator("u-b", evidence_refs=[broad_ref])
    unit_c = _earned_unit_no_locator("u-c", evidence_refs=[broad_ref])
    items = [_item("parent", status="open", covered_units=[unit_a, unit_b, unit_c])]
    mem = _mem(resolution_items=items)
    result = build_prompt_observability_summary(mem)
    # One shared ref (cited by 3 units) → count == 1
    assert result["shared_unlocated_evidence_for_earned_units_count"] == 1
    assert "shared_unlocated_evidence_for_earned_units:1" in result["mechanical_flags"]


def test_shared_unlocated_evidence_count_in_compact_observability() -> None:
    """shared_unlocated_evidence_for_earned_units_count appears in compact summary."""
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )
    mem = _mem(resolution_items=[])
    full = build_prompt_observability_summary(mem)
    compact = _compact_prompt_observability_summary(full)
    assert "shared_unlocated_evidence_for_earned_units_count" in compact


def test_shared_unlocated_evidence_does_not_fire_when_units_have_locators() -> None:
    """Units with locators are not counted even if they share the same ref."""
    broad_ref = "image:assoc:draft_legal_text_image:original"
    from harness.mission_state import EvidenceLocator
    locator = EvidenceLocator(ref_id=broad_ref, locator_kind="image_region")
    unit_a = ResolutionCoveredUnit(
        unit_id="u-a",
        title="u-a",
        status="closed",
        determination="earned",
        determined_value="N. 4° 00' W.",
        evidence_refs=[broad_ref],
        evidence_locators=[locator],
    )
    unit_b = ResolutionCoveredUnit(
        unit_id="u-b",
        title="u-b",
        status="closed",
        determination="earned",
        determined_value="S. 2° 00' E.",
        evidence_refs=[broad_ref],
        evidence_locators=[locator],
    )
    items = [_item("parent", status="open", covered_units=[unit_a, unit_b])]
    mem = _mem(resolution_items=items)
    result = build_prompt_observability_summary(mem)
    assert result["shared_unlocated_evidence_for_earned_units_count"] == 0
    assert result["earned_units_missing_locator_count"] == 0


# ---------------------------------------------------------------------------
# artifact_refresh_trap_risk — Engineering Brief 2
# ---------------------------------------------------------------------------


def _hydrate_record(
    turn_index: int,
    *,
    refs: dict | None = None,
    state_sig: str = "state-constant",
    action_inputs: dict | None = None,
) -> dict:
    return _step_record(
        turn_index,
        action_type="hydrate_artifact_refs",
        action_inputs=action_inputs or {"ref_ids": ["artifact://working:rev:0001"]},
        latest_refs_snapshot=refs or {"working": "artifact://working:rev:0001"},
        work_state_signature=state_sig,
    )


def _save_record(turn_index: int) -> dict:
    return _step_record(
        turn_index,
        action_type="save_workspace_artifact",
        latest_refs_snapshot={"working": "artifact://working:rev:0001"},
        work_state_signature="state-constant",
    )


def test_artifact_refresh_trap_risk_fires_on_save_plus_three_hydrates() -> None:
    """Save followed by 3 hydrates with unchanged refs/state → flag fires at threshold."""
    records = [
        _save_record(1),
        _hydrate_record(2),
        _hydrate_record(3),
        _hydrate_record(4),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    assert result["artifact_refresh_trap_risk_count"] == 3
    assert "artifact_refresh_trap_risk:3" in result["mechanical_flags"]


def test_artifact_refresh_trap_risk_does_not_fire_for_one_off_verification_after_save() -> None:
    """A single hydration after a save is normal verification — streak is below threshold."""
    records = [
        _save_record(1),
        _hydrate_record(2),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    assert result["artifact_refresh_trap_risk_count"] == 0
    assert not any(f.startswith("artifact_refresh_trap_risk:") for f in result["mechanical_flags"])


def test_artifact_refresh_trap_risk_does_not_fire_when_most_recent_hydrate_changed_refs() -> None:
    """A ref change on the most recent turn breaks the frozen-streak pattern — no trap."""
    records = [
        _save_record(1),
        _hydrate_record(2, refs={"working": "artifact://working:rev:0001"}),
        _hydrate_record(3, refs={"working": "artifact://working:rev:0001"}),
        _hydrate_record(4, refs={"working": "artifact://working:rev:0002"}),  # new ref on tail
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    # Tail has rev:0002; looking back, turn 3 has rev:0001 → streak breaks at turn 3.
    # Streak from tail = 1 (only turn 4 matches), below threshold → no flag.
    assert result["artifact_refresh_trap_risk_count"] == 0
    assert not any(f.startswith("artifact_refresh_trap_risk:") for f in result["mechanical_flags"])


def test_artifact_refresh_trap_risk_does_not_fire_without_prior_save_in_lookback() -> None:
    """Repeated hydrations with no prior save in the lookback window → trap signal suppressed."""
    records = [
        _hydrate_record(1),
        _hydrate_record(2),
        _hydrate_record(3),
        _hydrate_record(4),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    assert result["artifact_refresh_trap_risk_count"] == 0
    assert not any(f.startswith("artifact_refresh_trap_risk:") for f in result["mechanical_flags"])


def test_artifact_refresh_trap_risk_count_in_compact_observability() -> None:
    """artifact_refresh_trap_risk_count appears in compact observability when non-zero."""
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )
    records = [
        _save_record(1),
        _hydrate_record(2),
        _hydrate_record(3),
        _hydrate_record(4),
    ]
    mem = _mem(step_records=records)
    full = build_prompt_observability_summary(mem)
    compact = _compact_prompt_observability_summary(full)
    assert "artifact_refresh_trap_risk_count" in compact
    assert compact["artifact_refresh_trap_risk_count"] == 3


# ---------------------------------------------------------------------------
# artifact_refresh_trap_risk — windowed detector (run-10 interleaved shape)
# ---------------------------------------------------------------------------


def _state_patch_record(turn_index: int, *, refs: dict | None = None, state_sig: str = "state-constant") -> dict:
    """A state-only bookkeeping turn — does not hydrate or save."""
    return _step_record(
        turn_index,
        action_type="state_patch_apply",
        latest_refs_snapshot=refs or {"working": "artifact://working:rev:0001"},
        work_state_signature=state_sig,
    )


def test_artifact_refresh_trap_windowed_fires_on_run10_interleaved_shape() -> None:
    """Save → interleaved state patches and hydrates of same refs → windowed detector fires.

    The physical streak (consecutive hydrates) is broken by state patches, so the
    simple streak detector returns 0. The windowed detector skips the state-only turns
    and sees 3 fruitless hydrate rows — flag fires.
    """
    refs = {"working": "artifact://working:rev:0001"}
    records = [
        _save_record(18),
        _state_patch_record(19, refs=refs),
        _hydrate_record(20, refs=refs),
        _state_patch_record(21, refs=refs),
        _hydrate_record(22, refs=refs),
        _state_patch_record(23, refs=refs),
        _hydrate_record(24, refs=refs),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    # Simple streak should be 0 — state_patch at turn 23 breaks the physical streak
    # Windowed count should be 3 (hydrate rows at 20, 22, 24 all have same refs sig)
    assert result["artifact_refresh_trap_risk_count"] == 3
    assert "artifact_refresh_trap_risk:3" in result["mechanical_flags"]


def test_artifact_refresh_trap_windowed_save_much_earlier_still_fires() -> None:
    """Save well outside the streak lookback but within the wide lookback fires via windowed detector."""
    refs = {"working": "artifact://working:rev:0001"}
    records = (
        [_save_record(1)]
        + [_state_patch_record(i, refs=refs) for i in range(2, 12)]
        + [
            _hydrate_record(12, refs=refs),
            _state_patch_record(13, refs=refs),
            _hydrate_record(14, refs=refs),
            _state_patch_record(15, refs=refs),
            _hydrate_record(16, refs=refs),
        ]
    )
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    # Save at turn 1 is within the wide lookback of 20 from the tail (turn 16)
    assert result["artifact_refresh_trap_risk_count"] >= 3
    assert any(f.startswith("artifact_refresh_trap_risk:") for f in result["mechanical_flags"])


def test_artifact_refresh_trap_windowed_suppressed_by_copy_forward_in_window() -> None:
    """copy_forward_save in the recent window suppresses the windowed detector."""
    refs = {"working": "artifact://working:rev:0001"}
    records = [
        _save_record(1),
        _hydrate_record(2, refs=refs),
        _step_record(3, action_type="copy_forward_save_workspace_artifact",
                     latest_refs_snapshot=refs, work_state_signature="state-constant"),
        _hydrate_record(4, refs=refs),
        _state_patch_record(5, refs=refs),
        _hydrate_record(6, refs=refs),
        _state_patch_record(7, refs=refs),
        _hydrate_record(8, refs=refs),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    assert result["artifact_refresh_trap_risk_count"] == 0
    assert not any(f.startswith("artifact_refresh_trap_risk:") for f in result["mechanical_flags"])


def test_artifact_refresh_trap_windowed_suppressed_when_most_recent_hydrate_changed_refs() -> None:
    """The windowed fruitless count breaks when the most recent hydrate produced new refs."""
    old_refs = {"working": "artifact://working:rev:0001"}
    new_refs = {"working": "artifact://working:rev:0001", "draft": "artifact://draft:rev:0001"}
    records = [
        _save_record(1),
        _hydrate_record(2, refs=old_refs),
        _state_patch_record(3, refs=old_refs),
        _hydrate_record(4, refs=old_refs),
        _state_patch_record(5, refs=old_refs),
        _hydrate_record(6, refs=new_refs),  # most recent hydrate: new ref added
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    # Tail hydrate (turn 6) shows new_refs; counting backward through hydrate rows,
    # turns 2 and 4 show old_refs ≠ new_refs → fruitless count = 1 (only turn 6) < 3
    assert result["artifact_refresh_trap_risk_count"] == 0
    assert not any(f.startswith("artifact_refresh_trap_risk:") for f in result["mechanical_flags"])


def test_artifact_refresh_trap_windowed_suppressed_without_prior_save() -> None:
    """Interleaved hydrate churn with no prior save in wide lookback → suppressed."""
    refs = {"working": "artifact://working:rev:0001"}
    records = [
        _hydrate_record(1, refs=refs),
        _state_patch_record(2, refs=refs),
        _hydrate_record(3, refs=refs),
        _state_patch_record(4, refs=refs),
        _hydrate_record(5, refs=refs),
        _state_patch_record(6, refs=refs),
        _hydrate_record(7, refs=refs),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    assert result["artifact_refresh_trap_risk_count"] == 0
    assert not any(f.startswith("artifact_refresh_trap_risk:") for f in result["mechanical_flags"])


def test_artifact_refresh_trap_windowed_fires_on_run10_cyclic_recovery_shape() -> None:
    """Run-10 shape: save, then cycling across working rev + all drafts + single draft
    with state-only turns between reads, no new refs produced — windowed detector fires.

    Three distinct read targets, each repeated across the cycle, unchanged latest refs.
    Distinct targets (3) < hydrate rows (5) → pigeonhole confirms cycling → fires.
    """
    refs = {"working": "artifact://working:rev:0001"}
    working_rev = {"ref_ids": ["transcript_edit:working:rev:0001"]}
    all_drafts = {"ref_ids": ["t0:raw:draft_1", "t0:raw:draft_2", "t0:raw:draft_3"]}
    draft_1 = {"ref_ids": ["t0:raw:draft_1"]}

    records = [
        _save_record(18),
        _state_patch_record(19, refs=refs),
        _hydrate_record(20, refs=refs, action_inputs=working_rev),
        _state_patch_record(21, refs=refs),
        _hydrate_record(22, refs=refs, action_inputs=all_drafts),
        _state_patch_record(23, refs=refs),
        _hydrate_record(24, refs=refs, action_inputs=draft_1),
        _state_patch_record(25, refs=refs),
        _hydrate_record(26, refs=refs, action_inputs=working_rev),   # repeat
        _state_patch_record(27, refs=refs),
        _hydrate_record(28, refs=refs, action_inputs=all_drafts),    # repeat
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    # 5 fruitless hydrate rows (all refs=X), 3 distinct targets, 5 > 3 → cycling
    assert result["artifact_refresh_trap_risk_count"] >= 3
    assert any(f.startswith("artifact_refresh_trap_risk:") for f in result["mechanical_flags"])


def test_artifact_refresh_trap_windowed_does_not_fire_for_different_targets_with_unchanged_refs() -> None:
    """Post-save verification of three different artifacts: latest_refs_snapshot unchanged for all,
    but each hydrate targets a different ref bundle → input sigs differ → no false positive."""
    shared_refs = {"working": "artifact://working:rev:0001"}
    records = [
        _save_record(1),
        _hydrate_record(2, refs=shared_refs, action_inputs={"ref_ids": ["artifact://working:rev:0001"]}),
        _hydrate_record(3, refs=shared_refs, action_inputs={"ref_ids": ["artifact://draft-a:rev:0001"]}),
        _hydrate_record(4, refs=shared_refs, action_inputs={"ref_ids": ["artifact://draft-b:rev:0001"]}),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    # Each hydrate reads a different artifact → input sigs differ → fruitless count = 1 (only tail)
    assert result["artifact_refresh_trap_risk_count"] == 0
    assert not any(f.startswith("artifact_refresh_trap_risk:") for f in result["mechanical_flags"])


# ---------------------------------------------------------------------------
# repair_ready_without_artifact_write — Engineering Brief 4
# ---------------------------------------------------------------------------


def _copy_forward_save_record(turn_index: int) -> dict:
    return _step_record(
        turn_index,
        action_type="copy_forward_save_workspace_artifact",
        latest_refs_snapshot={"working": "artifact://working:rev:0002"},
        work_state_signature="state-v2",
    )


def _read_record(turn_index: int, *, action_type: str = "hydrate_artifact_refs") -> dict:
    return _step_record(
        turn_index,
        action_type=action_type,
        latest_refs_snapshot={"working": "artifact://working:rev:0001"},
        work_state_signature="state-constant",
    )


def test_repair_ready_without_artifact_write_fires_after_repair_debt_and_reads() -> None:
    """Semantic repair debt in feedback + 3 hydrate turns → flag fires."""
    records = [
        _read_record(1),
        _read_record(2),
        _read_record(3),
    ]
    feedback = {"semantic_repair_debt": ["determined_value"]}
    mem = _mem(step_records=records, state_patch_feedback=feedback)
    result = build_prompt_observability_summary(mem)
    count = result["repair_ready_without_artifact_write_count"]
    assert count >= 3
    assert any(f.startswith("repair_ready_without_artifact_write:") for f in result["mechanical_flags"])


def test_repair_ready_without_artifact_write_fires_after_artifact_refresh_trap() -> None:
    """artifact_refresh_trap_risk_count > 0 → repair pressure, 3 hydrates → flag fires."""
    records = [
        _save_record(1),
        _hydrate_record(2),
        _hydrate_record(3),
        _hydrate_record(4),
    ]
    # No need to set feedback — trap risk itself is the pressure signal.
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    # Verify the trap risk actually fired so this test is meaningful.
    assert result["artifact_refresh_trap_risk_count"] >= 3
    count = result["repair_ready_without_artifact_write_count"]
    assert count >= 3
    assert any(f.startswith("repair_ready_without_artifact_write:") for f in result["mechanical_flags"])


def test_repair_ready_without_artifact_write_suppressed_after_save() -> None:
    """Flag is suppressed when a save_workspace_artifact turn appears in the trailing records."""
    records = [
        _read_record(1),
        _read_record(2),
        _save_record(3),
    ]
    feedback = {"semantic_repair_debt": ["determined_value"]}
    mem = _mem(step_records=records, state_patch_feedback=feedback)
    result = build_prompt_observability_summary(mem)
    assert result["repair_ready_without_artifact_write_count"] == 0
    assert not any(f.startswith("repair_ready_without_artifact_write:") for f in result["mechanical_flags"])


def test_repair_ready_without_artifact_write_suppressed_after_copy_forward_save() -> None:
    """Flag is suppressed when copy_forward_save_workspace_artifact appears in trailing records."""
    records = [
        _read_record(1),
        _read_record(2),
        _copy_forward_save_record(3),
    ]
    feedback = {"semantic_repair_debt": ["determined_value"]}
    mem = _mem(step_records=records, state_patch_feedback=feedback)
    result = build_prompt_observability_summary(mem)
    assert result["repair_ready_without_artifact_write_count"] == 0
    assert not any(f.startswith("repair_ready_without_artifact_write:") for f in result["mechanical_flags"])


def test_repair_ready_without_artifact_write_not_for_one_off_post_save_read() -> None:
    """Save followed by a single verification hydrate: trailing_no_write=1 < threshold → no flag."""
    records = [
        _save_record(1),
        _hydrate_record(2),
    ]
    # Introduce repair debt so the pressure condition is met.
    feedback = {"semantic_repair_debt": ["notes"]}
    mem = _mem(step_records=records, state_patch_feedback=feedback)
    result = build_prompt_observability_summary(mem)
    # trailing_no_write is 1 (only the hydrate after the save), below threshold of 3.
    assert result["repair_ready_without_artifact_write_count"] == 0
    assert not any(f.startswith("repair_ready_without_artifact_write:") for f in result["mechanical_flags"])


def test_repair_ready_without_artifact_write_typed_projection() -> None:
    """repair_ready_without_artifact_write_count surfaces in the typed PromptObservabilitySummary."""
    from harness.observability.summary.prompt_observability import (
        _prompt_observability_summary_from_payload,
    )

    summary = _prompt_observability_summary_from_payload(
        {"prompt_observability_summary": {"repair_ready_without_artifact_write_count": 4}}
    )
    assert summary.repair_ready_without_artifact_write_count == 4


def test_repair_ready_without_artifact_write_in_compact_observability() -> None:
    """Counter appears in compact observability when non-zero; absent when zero."""
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )

    records = [
        _read_record(1),
        _read_record(2),
        _read_record(3),
    ]
    feedback = {"semantic_repair_debt": ["determined_value"]}
    mem = _mem(step_records=records, state_patch_feedback=feedback)
    full = build_prompt_observability_summary(mem)
    compact = _compact_prompt_observability_summary(full)
    assert "repair_ready_without_artifact_write_count" in compact
    assert compact["repair_ready_without_artifact_write_count"] >= 3

    # Zero case: no repair pressure → absent from compact.
    mem_clean = _mem(step_records=records)
    full_clean = build_prompt_observability_summary(mem_clean)
    compact_clean = _compact_prompt_observability_summary(full_clean)
    assert "repair_ready_without_artifact_write_count" not in compact_clean


def test_repair_ready_choose_action_guidance_names_flag_no_domain_terms() -> None:
    """choose_action_instruction.py names the flag and expected behavior; no domain jargon."""
    from harness.runtime.orchestration.choose_action_instruction import CHOOSE_ACTION_INSTRUCTION

    assert "repair_ready_without_artifact_write" in CHOOSE_ACTION_INSTRUCTION
    assert "save_workspace_artifact" in CHOOSE_ACTION_INSTRUCTION
    assert "copy_forward_save_workspace_artifact" in CHOOSE_ACTION_INSTRUCTION
    # No domain-specific terms.
    domain_terms = ["deed", "parcel", "plss", "transcription", "dossier", "mapping"]
    for term in domain_terms:
        assert term not in CHOOSE_ACTION_INSTRUCTION.lower(), f"Domain term found: {term}"


# ---------------------------------------------------------------------------
# hitl_evidence_readiness_debt — Engineering Brief 5
# ---------------------------------------------------------------------------


def _hitl_step_record(turn_index: int, *, refs: dict | None = None) -> dict:
    rec = _step_record(
        turn_index,
        action_type="hitl_request",
        latest_refs_snapshot=refs if refs is not None else {"working": "artifact://working:rev:0001"},
        work_state_signature="state-hitl",
    )
    rec["wait_for_human"] = True
    return rec


def _evidence_result_record() -> dict:
    """A step_result_record that exposes focused evidence metadata."""
    return {"outputs_for_continuity": {"rendered_evidence_refs": ["artifact://evidence:rev:0001"]}}


def test_hitl_evidence_readiness_debt_fires_when_no_evidence() -> None:
    """HITL turn with refs but no evidence artifact in results → flag fires."""
    records = [
        _hitl_step_record(1),
        _read_record(2),
        _read_record(3),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    count = result["hitl_evidence_readiness_debt_count"]
    assert count >= 1
    assert any(f.startswith("hitl_evidence_readiness_debt:") for f in result["mechanical_flags"])


def test_hitl_evidence_readiness_debt_suppressed_when_evidence_present() -> None:
    """Recent result carries rendered_evidence_refs → flag is suppressed."""
    records = [
        _hitl_step_record(1),
    ]
    result_records = [_evidence_result_record()]
    mem = _mem(step_records=records, step_result_records=result_records)
    result = build_prompt_observability_summary(mem)
    assert result["hitl_evidence_readiness_debt_count"] == 0
    assert not any(f.startswith("hitl_evidence_readiness_debt:") for f in result["mechanical_flags"])


def test_hitl_evidence_readiness_debt_suppressed_when_no_refs() -> None:
    """HITL turn with empty refs (evidence genuinely unavailable) → flag suppressed."""
    records = [
        _hitl_step_record(1, refs={}),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    assert result["hitl_evidence_readiness_debt_count"] == 0
    assert not any(f.startswith("hitl_evidence_readiness_debt:") for f in result["mechanical_flags"])


def test_hitl_evidence_readiness_debt_suppressed_for_derived_ref() -> None:
    """derived_ref in outputs_for_continuity suppresses the flag."""
    records = [_hitl_step_record(1)]
    result_records = [{"outputs_for_continuity": {"derived_ref": "artifact://derived:rev:0001"}}]
    mem = _mem(step_records=records, step_result_records=result_records)
    result = build_prompt_observability_summary(mem)
    assert result["hitl_evidence_readiness_debt_count"] == 0


def test_hitl_evidence_readiness_debt_typed_projection() -> None:
    """hitl_evidence_readiness_debt_count surfaces in the typed PromptObservabilitySummary."""
    from harness.observability.summary.prompt_observability import (
        _prompt_observability_summary_from_payload,
    )

    summary = _prompt_observability_summary_from_payload(
        {"prompt_observability_summary": {"hitl_evidence_readiness_debt_count": 2}}
    )
    assert summary.hitl_evidence_readiness_debt_count == 2


def test_hitl_evidence_readiness_debt_in_compact_observability() -> None:
    """Counter appears in compact observability when non-zero; absent when zero."""
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )

    records = [_hitl_step_record(1), _read_record(2)]
    mem = _mem(step_records=records)
    full = build_prompt_observability_summary(mem)
    compact = _compact_prompt_observability_summary(full)
    assert "hitl_evidence_readiness_debt_count" in compact
    assert compact["hitl_evidence_readiness_debt_count"] >= 1

    # Zero case: evidence artifact present → absent from compact.
    result_records = [_evidence_result_record()]
    mem_clean = _mem(step_records=records, step_result_records=result_records)
    full_clean = build_prompt_observability_summary(mem_clean)
    compact_clean = _compact_prompt_observability_summary(full_clean)
    assert "hitl_evidence_readiness_debt_count" not in compact_clean


def test_hitl_evidence_readiness_debt_suppressed_when_context_carries_evidence() -> None:
    """HITL pending request whose context has evidence_refs → flag suppressed."""
    from harness.runtime.hitl.transport import HitlTransportPosture

    records = [_hitl_step_record(1)]  # kernel_turn_index=1
    mem = _mem(step_records=records)
    mem.hitl = HitlTransportPosture(
        pending_hitl_requests=[
            {
                "prompt_id": "p-1",
                "message": "Which value is correct?",
                "choices": [],
                "context": {"primary_evidence_ref": "artifact://evidence:rev:0001"},
                "opaque_payload": {},
                "issued_at_iteration": 1,
            }
        ]
    )
    result = build_prompt_observability_summary(mem)
    assert result["hitl_evidence_readiness_debt_count"] == 0
    assert not any(f.startswith("hitl_evidence_readiness_debt:") for f in result["mechanical_flags"])


def test_hitl_evidence_readiness_debt_suppressed_when_context_carries_caveat() -> None:
    """HITL pending request whose context has evidence_not_needed → flag suppressed."""
    from harness.runtime.hitl.transport import HitlTransportPosture

    records = [_hitl_step_record(1)]
    mem = _mem(step_records=records)
    mem.hitl = HitlTransportPosture(
        pending_hitl_requests=[
            {
                "prompt_id": "p-2",
                "message": "Please confirm the approach.",
                "choices": ["Approve", "Reject"],
                "context": {"evidence_not_needed": True, "notes": "Preference question, no artifact required"},
                "opaque_payload": {},
                "issued_at_iteration": 1,
            }
        ]
    )
    result = build_prompt_observability_summary(mem)
    assert result["hitl_evidence_readiness_debt_count"] == 0
    assert not any(f.startswith("hitl_evidence_readiness_debt:") for f in result["mechanical_flags"])


def test_hitl_evidence_readiness_choose_action_guidance_no_domain_terms() -> None:
    """choose_action_instruction.py names the flag and expected behavior; no domain jargon."""
    from harness.runtime.orchestration.choose_action_instruction import CHOOSE_ACTION_INSTRUCTION

    assert "hitl_evidence_readiness_debt" in CHOOSE_ACTION_INSTRUCTION
    assert "primary_evidence_ref" in CHOOSE_ACTION_INSTRUCTION
    domain_terms = ["deed", "parcel", "plss", "transcription", "dossier", "mapping"]
    for term in domain_terms:
        assert term not in CHOOSE_ACTION_INSTRUCTION.lower(), f"Domain term found: {term}"


def test_artifact_state_dirty_since_write_count_fires_after_state_change_post_save() -> None:
    records = [
        _step_record(1, action_type="save_workspace_artifact", work_state_signature="saved"),
        _step_record(2, action_type="no_dispatch", work_state_signature="changed"),
        _step_record(3, action_type="hydrate_artifact_refs", work_state_signature="changed"),
    ]
    result = build_prompt_observability_summary(_mem(step_records=records))
    assert result["artifact_state_dirty_since_write_count"] == 2
    assert "artifact_state_dirty_since_write:2" in result["mechanical_flags"]


def test_artifact_state_dirty_since_write_suppressed_when_latest_save_is_fresh() -> None:
    records = [
        _step_record(1, action_type="save_workspace_artifact", work_state_signature="old"),
        _step_record(2, action_type="no_dispatch", work_state_signature="changed"),
        _step_record(3, action_type="copy_forward_save_workspace_artifact", work_state_signature="changed"),
    ]
    result = build_prompt_observability_summary(_mem(step_records=records))
    assert result["artifact_state_dirty_since_write_count"] == 0
    assert not any(f.startswith("artifact_state_dirty_since_write:") for f in result["mechanical_flags"])


def test_post_write_artifact_consistency_check_fires_after_successful_save() -> None:
    records = [
        _step_record(1, action_type="hydrate_artifact_refs", work_state_signature="old"),
        _step_record(
            2,
            action_type="copy_forward_save_workspace_artifact",
            execution_state="executed",
            work_state_signature="new",
        ),
    ]
    result = build_prompt_observability_summary(_mem(step_records=records))
    assert result["post_write_artifact_consistency_check_count"] == 1
    assert "post_write_artifact_consistency_check:1" in result["mechanical_flags"]


def test_post_write_artifact_consistency_check_is_one_turn_only() -> None:
    records = [
        _step_record(1, action_type="save_workspace_artifact", work_state_signature="saved"),
        _step_record(2, action_type="no_dispatch", work_state_signature="saved"),
    ]
    result = build_prompt_observability_summary(_mem(step_records=records))
    assert result["post_write_artifact_consistency_check_count"] == 0
    assert not any(
        f.startswith("post_write_artifact_consistency_check:")
        for f in result["mechanical_flags"]
    )


def test_artifact_consistency_counters_typed_and_compact_projection() -> None:
    from harness.observability.summary.prompt_observability import (
        _prompt_observability_summary_from_payload,
    )
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )

    summary = _prompt_observability_summary_from_payload(
        {
            "prompt_observability_summary": {
                "artifact_state_dirty_since_write_count": 4,
                "post_write_artifact_consistency_check_count": 1,
            }
        }
    )
    assert summary.artifact_state_dirty_since_write_count == 4
    assert summary.post_write_artifact_consistency_check_count == 1

    compact = _compact_prompt_observability_summary(
        {
            "artifact_state_dirty_since_write_count": 4,
            "post_write_artifact_consistency_check_count": 1,
        }
    )
    assert compact["artifact_state_dirty_since_write_count"] == 4
    assert compact["post_write_artifact_consistency_check_count"] == 1
    zero_compact = _compact_prompt_observability_summary(
        {
            "artifact_state_dirty_since_write_count": 0,
            "post_write_artifact_consistency_check_count": 0,
        }
    )
    assert "artifact_state_dirty_since_write_count" not in zero_compact
    assert "post_write_artifact_consistency_check_count" not in zero_compact


# ---------------------------------------------------------------------------
# Brief: Run-13 — post_hitl_spin_count detector
# ---------------------------------------------------------------------------


def _hitl_turn(turn_index: int, *, refs: dict | None = None, state_sig: str = "sig-a") -> dict:
    rec = _step_record(turn_index, action_type="wait_for_human", latest_refs_snapshot=refs or {"r": "v"}, work_state_signature=state_sig)
    rec["wait_for_human"] = True
    return rec


def test_post_hitl_spin_fires_when_threshold_met() -> None:
    """3 post-HITL turns with no progress triggers post_hitl_spin:3."""
    refs = {"r": "v"}
    records = [
        _hitl_turn(1, refs=refs, state_sig="sig-a"),
        _step_record(2, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-a"),
        _step_record(3, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-a"),
        _step_record(4, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-a"),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    assert result["post_hitl_spin_count"] == 3
    assert any(f.startswith("post_hitl_spin:") for f in result["mechanical_flags"])


def test_post_hitl_spin_does_not_fire_below_threshold() -> None:
    """2 post-HITL turns — below threshold, no flag."""
    refs = {"r": "v"}
    records = [
        _hitl_turn(1, refs=refs, state_sig="sig-a"),
        _step_record(2, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-a"),
        _step_record(3, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-a"),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    assert result["post_hitl_spin_count"] == 0
    assert not any(f.startswith("post_hitl_spin:") for f in result["mechanical_flags"])


def test_post_hitl_spin_resets_on_refs_change() -> None:
    """A post-HITL turn that produces new refs breaks the spin count."""
    refs_before = {"r": "v1"}
    refs_after = {"r": "v1", "new": "v2"}
    records = [
        _hitl_turn(1, refs=refs_before, state_sig="sig-a"),
        _step_record(2, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs_after, work_state_signature="sig-a"),
        _step_record(3, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs_after, work_state_signature="sig-a"),
        _step_record(4, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs_after, work_state_signature="sig-a"),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    # refs changed from HITL baseline, so no spin
    assert result["post_hitl_spin_count"] == 0


def test_post_hitl_spin_fires_for_integrated_then_stuck() -> None:
    """Integrated-then-stuck: save shows progress at turn 2, but trailing hydrates at 3-5 spin."""
    refs = {"r": "v"}
    records = [
        _hitl_turn(1, refs=refs, state_sig="sig-a"),
        _step_record(2, action_type="save_workspace_artifact", latest_refs_snapshot=refs, work_state_signature="sig-a"),
        _step_record(3, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-a"),
        _step_record(4, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-a"),
        _step_record(5, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-a"),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    # save counts as progress for turn 2 only; turns 3-5 are trailing no-progress → spin fires
    assert result["post_hitl_spin_count"] == 3
    assert any(f.startswith("post_hitl_spin:") for f in result["mechanical_flags"])


def test_post_hitl_spin_no_fire_when_save_is_last_turn() -> None:
    """A save as the final post-HITL turn means the agent is still making progress."""
    refs = {"r": "v"}
    records = [
        _hitl_turn(1, refs=refs, state_sig="sig-a"),
        _step_record(2, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-a"),
        _step_record(3, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-a"),
        _step_record(4, action_type="save_workspace_artifact", latest_refs_snapshot=refs, work_state_signature="sig-a"),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    # save at turn 4 is progress → trailing no-progress count = 0 → no spin
    assert result["post_hitl_spin_count"] == 0


def test_post_hitl_spin_no_hitl_turn_returns_zero() -> None:
    """No wait_for_human turn → counter is 0."""
    refs = {"r": "v"}
    records = [
        _step_record(1, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-a"),
        _step_record(2, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-a"),
        _step_record(3, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-a"),
        _step_record(4, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-a"),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    assert result["post_hitl_spin_count"] == 0


def test_post_hitl_spin_resets_on_state_change() -> None:
    """A state signature change after HITL breaks spin detection."""
    refs = {"r": "v"}
    records = [
        _hitl_turn(1, refs=refs, state_sig="sig-a"),
        _step_record(2, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-b"),
        _step_record(3, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-b"),
        _step_record(4, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs, work_state_signature="sig-b"),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    assert result["post_hitl_spin_count"] == 0


def test_post_hitl_spin_uses_last_hitl_turn_as_baseline() -> None:
    """When multiple HITL turns exist, baseline is the LAST one."""
    refs_v1 = {"r": "v1"}
    refs_v2 = {"r": "v1", "x": "v2"}
    records = [
        _hitl_turn(1, refs=refs_v1, state_sig="sig-a"),
        # some progress happens
        _step_record(2, action_type="save_workspace_artifact", latest_refs_snapshot=refs_v2, work_state_signature="sig-b"),
        # second HITL turn — this is the new baseline
        _hitl_turn(3, refs=refs_v2, state_sig="sig-b"),
        # post-HITL spin with refs matching second HITL baseline
        _step_record(4, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs_v2, work_state_signature="sig-b"),
        _step_record(5, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs_v2, work_state_signature="sig-b"),
        _step_record(6, action_type="hydrate_artifact_refs", latest_refs_snapshot=refs_v2, work_state_signature="sig-b"),
    ]
    mem = _mem(step_records=records)
    result = build_prompt_observability_summary(mem)
    assert result["post_hitl_spin_count"] == 3
    assert any(f.startswith("post_hitl_spin:") for f in result["mechanical_flags"])


def test_post_hitl_spin_choose_action_guidance_has_no_domain_terms() -> None:
    """post_hitl_spin guidance must be in choose_action_instruction.py without domain jargon."""
    from harness.runtime.orchestration.choose_action_instruction import CHOOSE_ACTION_INSTRUCTION

    assert "post_hitl_spin" in CHOOSE_ACTION_INSTRUCTION
    domain_terms = ["deed", "parcel", "plss", "transcription", "dossier", "mapping"]
    for term in domain_terms:
        assert term not in CHOOSE_ACTION_INSTRUCTION.lower(), f"Domain term found: {term}"


# ---------------------------------------------------------------------------
# Track 1 — earned_before_local_evidence_count / posthoc_recheck_needed_count
# (debt is stored on continuity; summary reads from there)
# ---------------------------------------------------------------------------

def test_earned_before_local_evidence_count_reflects_continuity_debt() -> None:
    """Summary surfaces non-zero earned_before_local_evidence_count from continuity."""
    mem = _mem()
    mem.continuity.earned_before_local_evidence_debt = {"item1//u1": 23, "item1//u2": 24}
    result = build_prompt_observability_summary(mem)
    assert result["earned_before_local_evidence_count"] == 2


def test_earned_before_local_evidence_count_zero_when_no_debt() -> None:
    mem = _mem()
    mem.continuity.earned_before_local_evidence_debt = {}
    result = build_prompt_observability_summary(mem)
    assert result["earned_before_local_evidence_count"] == 0


def test_earned_before_claim_local_evidence_flag_fires_when_count_nonzero() -> None:
    mem = _mem()
    mem.continuity.earned_before_local_evidence_debt = {"item1//u1": 5}
    result = build_prompt_observability_summary(mem)
    assert any(f.startswith("earned_before_claim_local_evidence:") for f in result["mechanical_flags"])


def test_posthoc_recheck_needed_count_reflects_continuity_debt() -> None:
    mem = _mem()
    mem.continuity.earned_before_local_evidence_debt = {"item1//u1": 23}
    mem.continuity.posthoc_recheck_needed_debt = {"item1//u1": 25}
    result = build_prompt_observability_summary(mem)
    assert result["posthoc_recheck_needed_count"] == 1


def test_posthoc_evidence_recheck_needed_flag_fires_when_count_nonzero() -> None:
    mem = _mem()
    mem.continuity.posthoc_recheck_needed_debt = {"item1//u1": 25}
    result = build_prompt_observability_summary(mem)
    assert any(f.startswith("posthoc_evidence_recheck_needed:") for f in result["mechanical_flags"])


def test_posthoc_recheck_count_zero_when_no_debt() -> None:
    mem = _mem()
    mem.continuity.posthoc_recheck_needed_debt = {}
    result = build_prompt_observability_summary(mem)
    assert result["posthoc_recheck_needed_count"] == 0


# ---------------------------------------------------------------------------
# Track 2 — broad_image_locator_for_earned_exact_units flag
# ---------------------------------------------------------------------------

def test_broad_image_locator_flag_fires_for_earned_unit_with_only_broad_locator() -> None:
    """Earned exact unit with all broad image locators produces a flag."""
    from harness.mission_state import EvidenceLocator
    # box area = 0.4 × 0.4 = 0.16 > 5%
    broad = EvidenceLocator(ref_id="artifact://x", locator_kind="image_region", box_norm=[0.1, 0.1, 0.5, 0.5])
    unit = _unit(
        "u1",
        status="closed",
        determined_value="42",
        evidence_locators=[broad],
    )
    item = _item("i1", status="closed", covered_units=[unit])
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["earned_exact_with_broad_image_locator_count"] == 1
    assert any(f.startswith("broad_image_locator_for_earned_exact_units:") for f in result["mechanical_flags"])


def test_broad_image_locator_flag_suppressed_for_tight_locator() -> None:
    """Earned unit with a tight locator (area < 5%) does not fire the flag."""
    from harness.mission_state import EvidenceLocator
    # 0.1 × 0.02 = 0.002 < 5%
    tight = EvidenceLocator(ref_id="artifact://x", locator_kind="image_region", box_norm=[0.10, 0.05, 0.20, 0.07])
    unit = _unit("u1", status="closed", determined_value="42", evidence_locators=[tight])
    item = _item("i1", status="closed", covered_units=[unit])
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["earned_exact_with_broad_image_locator_count"] == 0
    assert not any(f.startswith("broad_image_locator_for_earned_exact_units:") for f in result["mechanical_flags"])


def test_broad_image_locator_flag_suppressed_when_no_locators() -> None:
    """Unit with no locators is NOT counted by the broad-locator check (separate debt)."""
    unit = _unit("u1", status="closed", determined_value="42")
    item = _item("i1", status="closed", covered_units=[unit])
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["earned_exact_with_broad_image_locator_count"] == 0


def test_broad_image_locator_flag_suppressed_for_group_unit_without_value() -> None:
    """Group/broad unit without determined_value is excluded from this check."""
    from harness.mission_state import EvidenceLocator
    broad = EvidenceLocator(ref_id="artifact://x", locator_kind="image_region", box_norm=[0.0, 0.0, 1.0, 1.0])
    unit = _unit("u1", status="closed", determined_value=None, evidence_locators=[broad])
    item = _item("i1", status="closed", covered_units=[unit])
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["earned_exact_with_broad_image_locator_count"] == 0


# ---------------------------------------------------------------------------
# Track 3 — HITL answerability pressure flags
# ---------------------------------------------------------------------------

def test_blocked_without_hitl_answerability_flag_fires_for_blocking_item_no_assessment() -> None:
    """Blocking item with no requires_hitl and no human_answerability fires the flag."""
    item = _item("i1", status="open", blocking=True, requires_hitl=False)
    # human_answerability defaults to None → counts as unclassified
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["blocked_without_hitl_answerability_count"] >= 1
    assert any(f.startswith("blocked_without_hitl_answerability:") for f in result["mechanical_flags"])


def test_blocked_without_hitl_answerability_suppressed_when_requires_hitl_set() -> None:
    """Blocking item with requires_hitl=True is already in HITL flow — not counted."""
    item = _item("i1", status="open", blocking=True, requires_hitl=True)
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["blocked_without_hitl_answerability_count"] == 0


def test_human_answerable_blocker_without_hitl_fires() -> None:
    """Item classified likely_answerable but no requires_hitl triggers pressure flag."""
    item = ResolutionItem(
        item_id="i1",
        title="i1",
        kind="work_unit",
        status="open",
        blocking=True,
        requires_hitl=False,
        human_answerability="likely_answerable",
    )
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["human_answerable_blocker_without_hitl_count"] >= 1
    assert any(f.startswith("human_answerable_blocker_without_hitl:") for f in result["mechanical_flags"])


def test_human_answerable_blocker_suppressed_when_hitl_set() -> None:
    """likely_answerable + requires_hitl already in flow → no pressure flag."""
    item = ResolutionItem(
        item_id="i1",
        title="i1",
        kind="work_unit",
        status="open",
        blocking=True,
        requires_hitl=True,
        human_answerability="likely_answerable",
    )
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["human_answerable_blocker_without_hitl_count"] == 0


def test_not_answerable_missing_reason_fires_when_reason_absent() -> None:
    """not_answerable without hitl_not_applicable_reason fires advisory flag."""
    item = ResolutionItem(
        item_id="i1",
        title="i1",
        kind="work_unit",
        status="open",
        blocking=True,
        requires_hitl=False,
        human_answerability="not_answerable",
        hitl_not_applicable_reason=None,
    )
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["not_answerable_missing_reason_count"] >= 1
    assert any(f.startswith("not_answerable_missing_reason:") for f in result["mechanical_flags"])


def test_not_answerable_suppressed_when_reason_provided() -> None:
    """not_answerable with a reason set → no missing-reason advisory."""
    item = ResolutionItem(
        item_id="i1",
        title="i1",
        kind="work_unit",
        status="open",
        blocking=True,
        requires_hitl=False,
        human_answerability="not_answerable",
        hitl_not_applicable_reason="System constraint prevents human input here.",
    )
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["not_answerable_missing_reason_count"] == 0


def test_hitl_answerability_flags_absent_for_non_blocking_item() -> None:
    """Non-blocking, non-stalled items are excluded from HITL answerability checks."""
    item = ResolutionItem(
        item_id="i1",
        title="i1",
        kind="work_unit",
        status="open",
        blocking=False,
        no_further_progress=False,
        requires_hitl=False,
        human_answerability=None,
    )
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["blocked_without_hitl_answerability_count"] == 0
    assert result["human_answerable_blocker_without_hitl_count"] == 0
    assert result["not_answerable_missing_reason_count"] == 0


def test_stalled_no_further_progress_also_triggers_answerability_check() -> None:
    """no_further_progress items are treated the same as blocking for this check."""
    item = _item("i1", status="open", no_further_progress=True, requires_hitl=False)
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["blocked_without_hitl_answerability_count"] >= 1


def test_unit_local_no_further_progress_triggers_answerability_without_parent_stall() -> None:
    unit = ResolutionCoveredUnit(
        unit_id="u1",
        title="u1",
        status="open",
        no_further_progress=True,
    )
    item = _item("i1", status="open", blocking=False, requires_hitl=False, covered_units=[unit])
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["blocked_without_hitl_answerability_count"] >= 1


def test_unit_requires_hitl_suppresses_answerability_pressure_even_if_parent_lacks_flag() -> None:
    unit = ResolutionCoveredUnit(
        unit_id="u1",
        title="u1",
        status="open",
        no_further_progress=True,
        requires_hitl=True,
    )
    item = _item("i1", status="open", blocking=False, requires_hitl=False, covered_units=[unit])
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["blocked_without_hitl_answerability_count"] == 0


# ---------------------------------------------------------------------------
# Track 3 — covered-unit answerability (open units inside blocking items)
# ---------------------------------------------------------------------------

def test_blocked_without_hitl_answerability_fires_for_open_covered_unit() -> None:
    """Open covered unit inside a blocking item without answerability also counts."""
    unit = _unit("u1", status="open")  # no human_answerability
    item = _item("i1", status="open", blocking=True, requires_hitl=False, covered_units=[unit])
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    # Counts both the item itself (answerability unset) AND the open covered unit → >= 2
    assert result["blocked_without_hitl_answerability_count"] >= 2


def test_covered_unit_done_skipped_by_answerability_check() -> None:
    """Closed/earned covered units are not counted — only open atoms matter."""
    unit = _unit("u1", status="closed", determined_value="42")  # earned/closed
    item = _item("i1", status="open", blocking=True, requires_hitl=False, covered_units=[unit])
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    # Only the item itself counts (unit is done); not the covered unit
    assert result["blocked_without_hitl_answerability_count"] == 1


def test_covered_unit_likely_answerable_fires_pressure() -> None:
    """Covered unit with human_answerability='likely_answerable' but no parent HITL fires."""
    unit = ResolutionCoveredUnit(
        unit_id="u1",
        title="u1",
        status="open",
        human_answerability="likely_answerable",
    )
    item = _item("i1", status="open", blocking=True, requires_hitl=False, covered_units=[unit])
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["human_answerable_blocker_without_hitl_count"] >= 1


def test_covered_unit_not_answerable_missing_reason_fires() -> None:
    """Covered unit with not_answerable and no reason fires the missing-reason flag."""
    unit = ResolutionCoveredUnit(
        unit_id="u1",
        title="u1",
        status="open",
        human_answerability="not_answerable",
        hitl_not_applicable_reason=None,
    )
    item = _item("i1", status="open", blocking=True, requires_hitl=False, covered_units=[unit])
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["not_answerable_missing_reason_count"] >= 1


def test_covered_unit_not_answerable_with_reason_suppressed() -> None:
    """Covered unit with not_answerable + reason does not fire missing-reason."""
    unit = ResolutionCoveredUnit(
        unit_id="u1",
        title="u1",
        status="open",
        human_answerability="not_answerable",
        hitl_not_applicable_reason="System constraint applies here.",
    )
    item = _item("i1", status="open", blocking=True, requires_hitl=False, covered_units=[unit])
    mem = _mem(resolution_items=[item])
    result = build_prompt_observability_summary(mem)
    assert result["not_answerable_missing_reason_count"] == 0


# ---------------------------------------------------------------------------
# Typed projection — new counters surface via _prompt_observability_summary_from_payload
# ---------------------------------------------------------------------------

def test_action_turn_shape_counters_typed_projection() -> None:
    """Action-sequence turn-shape counters surface in typed PromptObservabilitySummary."""
    from harness.observability.summary.prompt_observability import (
        _prompt_observability_summary_from_payload,
    )

    summary = _prompt_observability_summary_from_payload(
        {
            "prompt_observability_summary": {
                "multi_action_turn_count": 2,
                "single_action_turn_count": 7,
                "max_actions_in_turn": 3,
            }
        }
    )
    assert summary.multi_action_turn_count == 2
    assert summary.single_action_turn_count == 7
    assert summary.max_actions_in_turn == 3


def test_earned_before_local_evidence_count_typed_projection() -> None:
    """earned_before_local_evidence_count surfaces in the typed PromptObservabilitySummary."""
    from harness.observability.summary.prompt_observability import (
        _prompt_observability_summary_from_payload,
    )
    summary = _prompt_observability_summary_from_payload(
        {"prompt_observability_summary": {"earned_before_local_evidence_count": 3}}
    )
    assert summary.earned_before_local_evidence_count == 3


def test_posthoc_recheck_needed_count_typed_projection() -> None:
    from harness.observability.summary.prompt_observability import (
        _prompt_observability_summary_from_payload,
    )
    summary = _prompt_observability_summary_from_payload(
        {"prompt_observability_summary": {"posthoc_recheck_needed_count": 2}}
    )
    assert summary.posthoc_recheck_needed_count == 2


def test_earned_exact_with_broad_image_locator_count_typed_projection() -> None:
    from harness.observability.summary.prompt_observability import (
        _prompt_observability_summary_from_payload,
    )
    summary = _prompt_observability_summary_from_payload(
        {"prompt_observability_summary": {"earned_exact_with_broad_image_locator_count": 1}}
    )
    assert summary.earned_exact_with_broad_image_locator_count == 1


def test_blocked_without_hitl_answerability_count_typed_projection() -> None:
    from harness.observability.summary.prompt_observability import (
        _prompt_observability_summary_from_payload,
    )
    summary = _prompt_observability_summary_from_payload(
        {"prompt_observability_summary": {"blocked_without_hitl_answerability_count": 4}}
    )
    assert summary.blocked_without_hitl_answerability_count == 4


def test_human_answerable_blocker_without_hitl_count_typed_projection() -> None:
    from harness.observability.summary.prompt_observability import (
        _prompt_observability_summary_from_payload,
    )
    summary = _prompt_observability_summary_from_payload(
        {"prompt_observability_summary": {"human_answerable_blocker_without_hitl_count": 2}}
    )
    assert summary.human_answerable_blocker_without_hitl_count == 2


def test_not_answerable_missing_reason_count_typed_projection() -> None:
    from harness.observability.summary.prompt_observability import (
        _prompt_observability_summary_from_payload,
    )
    summary = _prompt_observability_summary_from_payload(
        {"prompt_observability_summary": {"not_answerable_missing_reason_count": 1}}
    )
    assert summary.not_answerable_missing_reason_count == 1


def test_new_counters_zero_when_absent_from_payload() -> None:
    """All new counters default to 0 when not present in the raw payload."""
    from harness.observability.summary.prompt_observability import (
        _prompt_observability_summary_from_payload,
    )
    summary = _prompt_observability_summary_from_payload({"prompt_observability_summary": {}})
    assert summary.earned_before_local_evidence_count == 0
    assert summary.posthoc_recheck_needed_count == 0
    assert summary.earned_exact_with_broad_image_locator_count == 0
    assert summary.blocked_without_hitl_answerability_count == 0
    assert summary.human_answerable_blocker_without_hitl_count == 0
    assert summary.not_answerable_missing_reason_count == 0


# ---------------------------------------------------------------------------
# Compact observability — new counters present/absent as expected
# ---------------------------------------------------------------------------

def test_earned_before_local_evidence_count_in_compact_observability() -> None:
    """earned_before_local_evidence_count appears in compact when non-zero."""
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )
    mem = _mem()
    mem.continuity.earned_before_local_evidence_debt = {"item1//u1": 5}
    full = build_prompt_observability_summary(mem)
    compact = _compact_prompt_observability_summary(full)
    assert "earned_before_local_evidence_count" in compact
    assert compact["earned_before_local_evidence_count"] == 1


def test_earned_before_local_evidence_count_absent_in_compact_when_zero() -> None:
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )
    mem = _mem()
    mem.continuity.earned_before_local_evidence_debt = {}
    full = build_prompt_observability_summary(mem)
    compact = _compact_prompt_observability_summary(full)
    assert "earned_before_local_evidence_count" not in compact


def test_blocked_without_hitl_answerability_count_in_compact_observability() -> None:
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )
    item = _item("i1", status="open", blocking=True, requires_hitl=False)
    mem = _mem(resolution_items=[item])
    full = build_prompt_observability_summary(mem)
    compact = _compact_prompt_observability_summary(full)
    assert "blocked_without_hitl_answerability_count" in compact


def test_posthoc_recheck_needed_count_in_compact_observability() -> None:
    """posthoc_recheck_needed_count appears in compact when non-zero."""
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )
    mem = _mem()
    mem.continuity.posthoc_recheck_needed_debt = {"item1//u1": 25}
    full = build_prompt_observability_summary(mem)
    compact = _compact_prompt_observability_summary(full)
    assert "posthoc_recheck_needed_count" in compact
    assert compact["posthoc_recheck_needed_count"] == 1


def test_earned_exact_with_broad_image_locator_count_in_compact_observability() -> None:
    """earned_exact_with_broad_image_locator_count appears in compact when non-zero."""
    from harness.mission_state import EvidenceLocator
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )
    broad = EvidenceLocator(ref_id="artifact://x", locator_kind="image_region", box_norm=[0.0, 0.0, 0.9, 0.9])
    unit = _unit("u1", status="closed", determined_value="42", evidence_locators=[broad])
    item = _item("i1", status="closed", covered_units=[unit])
    mem = _mem(resolution_items=[item])
    full = build_prompt_observability_summary(mem)
    compact = _compact_prompt_observability_summary(full)
    assert "earned_exact_with_broad_image_locator_count" in compact
    assert compact["earned_exact_with_broad_image_locator_count"] >= 1


def test_human_answerable_blocker_without_hitl_count_in_compact_observability() -> None:
    """human_answerable_blocker_without_hitl_count appears in compact when non-zero."""
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )
    item = ResolutionItem(
        item_id="i1",
        title="i1",
        kind="work_unit",
        status="open",
        blocking=True,
        requires_hitl=False,
        human_answerability="likely_answerable",
    )
    mem = _mem(resolution_items=[item])
    full = build_prompt_observability_summary(mem)
    compact = _compact_prompt_observability_summary(full)
    assert "human_answerable_blocker_without_hitl_count" in compact


def test_not_answerable_missing_reason_count_in_compact_observability() -> None:
    """not_answerable_missing_reason_count appears in compact when non-zero."""
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )
    item = ResolutionItem(
        item_id="i1",
        title="i1",
        kind="work_unit",
        status="open",
        blocking=True,
        requires_hitl=False,
        human_answerability="not_answerable",
        hitl_not_applicable_reason=None,
    )
    mem = _mem(resolution_items=[item])
    full = build_prompt_observability_summary(mem)
    compact = _compact_prompt_observability_summary(full)
    assert "not_answerable_missing_reason_count" in compact


def test_new_optional_counters_absent_in_compact_when_zero() -> None:
    """All six new counters are absent from compact when zero (no unnecessary noise)."""
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )
    mem = _mem()
    full = build_prompt_observability_summary(mem)
    compact = _compact_prompt_observability_summary(full)
    for key in (
        "earned_before_local_evidence_count",
        "posthoc_recheck_needed_count",
        "earned_exact_with_broad_image_locator_count",
        "blocked_without_hitl_answerability_count",
        "human_answerable_blocker_without_hitl_count",
        "not_answerable_missing_reason_count",
    ):
        assert key not in compact, f"Expected {key!r} absent from compact when zero"


# ---------------------------------------------------------------------------
# HITL exchange ledger — Track 4 mechanical flags + Track 3 prompt projection
# ---------------------------------------------------------------------------

def _ledger_entry(prompt_id: str, status: str, **fields) -> dict:
    base = {
        "exchange_id": f"hitl:{prompt_id}",
        "prompt_id": prompt_id,
        "blocking": False,
        "issued_at_iteration": 1,
        "request": {"message": f"Q-{prompt_id}"},
        "response": None,
        "received_at_iteration": None,
        "consumed_at_iteration": None,
        "status": status,
    }
    base.update(fields)
    return base


def test_answered_hitl_unconsumed_count_reflects_ledger() -> None:
    mem = _mem()
    mem.continuity.hitl_exchange_ledger = [
        _ledger_entry("p1", "pending"),
        _ledger_entry("p2", "answered", response={"choice": "yes"}, received_at_iteration=2),
        _ledger_entry("p3", "answered", response={"choice": "no"}, received_at_iteration=3),
        _ledger_entry("p4", "consumed", response={"choice": "ok"}, consumed_at_iteration=4),
    ]
    result = build_prompt_observability_summary(mem)
    assert result["answered_hitl_unconsumed_count"] == 2


def test_answered_hitl_unconsumed_flag_fires_when_nonzero() -> None:
    mem = _mem()
    mem.continuity.hitl_exchange_ledger = [
        _ledger_entry("p1", "answered", response={"choice": "yes"}),
    ]
    result = build_prompt_observability_summary(mem)
    assert any(f.startswith("answered_hitl_unconsumed:") for f in result["mechanical_flags"])


def test_complete_with_unconsumed_hitl_fires_on_complete_run_with_unconsumed() -> None:
    mem = _mem(step_records=[_step_record(1, action_type="complete_run")])
    mem.continuity.hitl_exchange_ledger = [
        _ledger_entry("p1", "answered", response={"choice": "yes"}),
    ]
    result = build_prompt_observability_summary(mem)
    assert result["complete_with_unconsumed_hitl_count"] == 1
    assert any(f.startswith("complete_with_unconsumed_hitl:") for f in result["mechanical_flags"])


def test_complete_with_unconsumed_hitl_zero_when_no_unconsumed() -> None:
    mem = _mem(step_records=[_step_record(1, action_type="complete_run")])
    mem.continuity.hitl_exchange_ledger = [
        _ledger_entry("p1", "consumed", consumed_at_iteration=1),
    ]
    result = build_prompt_observability_summary(mem)
    assert result["complete_with_unconsumed_hitl_count"] == 0


def test_complete_with_unconsumed_hitl_zero_when_last_action_not_complete_run() -> None:
    mem = _mem(step_records=[_step_record(1, action_type="hydrate_artifact_refs")])
    mem.continuity.hitl_exchange_ledger = [
        _ledger_entry("p1", "answered", response={"choice": "yes"}),
    ]
    result = build_prompt_observability_summary(mem)
    assert result["complete_with_unconsumed_hitl_count"] == 0


def test_hitl_consumed_unknown_prompt_count_reflects_continuity() -> None:
    mem = _mem()
    mem.continuity.hitl_consumed_unknown_prompt_count = 3
    result = build_prompt_observability_summary(mem)
    assert result["hitl_consumed_unknown_prompt_count"] == 3
    assert any(f.startswith("hitl_consumed_unknown_prompt:") for f in result["mechanical_flags"])


def test_recent_hitl_exchanges_in_summary_includes_pending_and_answered() -> None:
    mem = _mem()
    mem.continuity.hitl_exchange_ledger = [
        _ledger_entry("p1", "pending"),
        _ledger_entry("p2", "answered", response={"choice": "yes", "note": "ok"}, received_at_iteration=2),
    ]
    result = build_prompt_observability_summary(mem)
    exchanges = result["recent_hitl_exchanges"]
    assert len(exchanges) == 2
    by_pid = {e["prompt_id"]: e for e in exchanges}
    assert by_pid["p1"]["status"] == "pending"
    assert by_pid["p2"]["status"] == "answered"
    assert by_pid["p2"]["response"]["choice"] == "yes"


def test_recent_hitl_exchanges_in_compact_when_nonempty() -> None:
    """Compact projection includes ledger view when ledger has entries."""
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )
    mem = _mem()
    mem.continuity.hitl_exchange_ledger = [
        _ledger_entry("p1", "answered", response={"choice": "yes"}, received_at_iteration=2),
    ]
    full = build_prompt_observability_summary(mem)
    compact = _compact_prompt_observability_summary(full)
    assert "recent_hitl_exchanges" in compact
    assert compact["recent_hitl_exchanges"][0]["prompt_id"] == "p1"


def test_recent_hitl_exchanges_absent_in_compact_when_empty() -> None:
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )
    mem = _mem()  # no ledger entries
    full = build_prompt_observability_summary(mem)
    compact = _compact_prompt_observability_summary(full)
    assert "recent_hitl_exchanges" not in compact


def test_hitl_ledger_counters_typed_projection() -> None:
    """All three new HITL ledger counters surface in PromptObservabilitySummary."""
    from harness.observability.summary.prompt_observability import (
        _prompt_observability_summary_from_payload,
    )
    summary = _prompt_observability_summary_from_payload({
        "prompt_observability_summary": {
            "answered_hitl_unconsumed_count": 2,
            "complete_with_unconsumed_hitl_count": 1,
            "hitl_consumed_unknown_prompt_count": 4,
            "recent_hitl_exchanges": [
                {"prompt_id": "p1", "status": "answered", "request": {"message": "q"}, "response": {"choice": "y"}},
            ],
        },
    })
    assert summary.answered_hitl_unconsumed_count == 2
    assert summary.complete_with_unconsumed_hitl_count == 1
    assert summary.hitl_consumed_unknown_prompt_count == 4
    assert len(summary.recent_hitl_exchanges) == 1
    assert summary.recent_hitl_exchanges[0]["prompt_id"] == "p1"


def test_recent_user_messages_in_summary_includes_pending_and_terminal() -> None:
    mem = _mem()
    mem.continuity.user_message_ledger = [
        {"message_id": "um-1", "status": "pending", "text": "Please fix x", "source": "tester"},
        {"message_id": "um-2", "status": "consumed", "text": "Older note", "source": "tester"},
        {"message_id": "um-3", "status": "deferred", "text": "Later note", "source": "tester"},
    ]
    mem.continuity.user_message_consumed_unknown_count = 1
    result = build_prompt_observability_summary(mem)
    assert result["user_message_pending_count"] == 1
    assert result["user_message_consumed_count"] == 1
    assert result["user_message_deferred_count"] == 1
    assert result["user_message_consumed_unknown_count"] == 1
    assert [row["message_id"] for row in result["recent_user_messages"]] == [
        "um-1",
        "um-2",
        "um-3",
    ]


def test_recent_user_messages_in_compact_when_nonempty() -> None:
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )
    mem = _mem()
    mem.continuity.user_message_ledger = [
        {"message_id": "um-1", "status": "pending", "text": "Please fix x", "source": "tester"},
    ]
    full = build_prompt_observability_summary(mem)
    compact = _compact_prompt_observability_summary(full)
    assert compact["user_message_pending_count"] == 1
    assert compact["recent_user_messages"][0]["message_id"] == "um-1"


def test_recent_user_messages_absent_in_compact_when_empty() -> None:
    from harness.runtime.orchestration.prompt_packet_builder import (
        _compact_prompt_observability_summary,
    )
    compact = _compact_prompt_observability_summary(build_prompt_observability_summary(_mem()))
    assert "recent_user_messages" not in compact
    assert "user_message_pending_count" not in compact


def test_user_message_counters_typed_projection() -> None:
    from harness.observability.summary.prompt_observability import (
        _prompt_observability_summary_from_payload,
    )
    summary = _prompt_observability_summary_from_payload({
        "prompt_observability_summary": {
            "user_message_pending_count": 2,
            "user_message_consumed_count": 3,
            "user_message_deferred_count": 4,
            "user_message_consumed_unknown_count": 5,
            "recent_user_messages": [
                {"message_id": "um-1", "status": "pending", "text": "exact human text"},
            ],
        },
    })
    assert summary.user_message_pending_count == 2
    assert summary.user_message_consumed_count == 3
    assert summary.user_message_deferred_count == 4
    assert summary.user_message_consumed_unknown_count == 5
    assert summary.recent_user_messages[0]["message_id"] == "um-1"
