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
        sequenced_items_missing_scope_count=0,
        sequenced_items_missing_index_count=0,
        duplicate_sequence_positions_count=0,
        sequence_scope_order_gaps_count=0,
        group_items_without_subclaims_count=0,
        critical_closed_items_without_evidence_count=0,
        critical_closed_items_without_verification_basis_count=0,
        blocking_items_without_relations_count=0,
        complete_run_blockers=[],
    )
    base.update(kwargs)
    return _mechanical_flags(**base)


def test_flags_empty_by_default() -> None:
    assert _flags() == []


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


def test_flags_capped_at_eight() -> None:
    """Output never exceeds 8 flags even when all conditions fire."""
    result = _flags(
        feedback={"reason_code": "r"},
        repeated_state_patch_reason_code_streak=3,
        consecutive_same_active_item_turns=5,
        turns_since_resolution_item_count_change=6,
        new_resolution_items_since_last_complete_run_attempt=3,
        repeated_complete_run_without_state_change_count=1,
        resolution_item_count=10,
        success_condition_count=1,
        closure_ready_to_close=False,
        complete_run_blockers=["ready_to_close_false"],
    )
    assert len(result) <= 8


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
