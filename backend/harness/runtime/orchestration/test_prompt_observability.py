from __future__ import annotations

from harness.mission_state import new_mission_state, new_resolution_state
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.loop_health_summary import build_prompt_observability_summary


def test_build_prompt_observability_summary_reports_loop_health_facts() -> None:
    loop_memory = LoopMemoryState()
    loop_memory.telemetry.prompt_event_count = 5
    loop_memory.telemetry.last_prompt_event_id = "pe-5"
    loop_memory.telemetry.last_prompt_event_surface = "orchestration_kernel_llm_turn"
    loop_memory.continuity.kernel_step_records.extend(
        [
            {
                "kernel_turn_index": 1,
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {},
                "idempotency_key": "ik-1",
                "rationale": "hydrate",
                "latest_refs_snapshot": {"working": "ref-1"},
                "skip_execution": False,
                "wait_for_human": False,
                "complete_run": False,
                "execution_state": "executed",
                "execution_reason_code": None,
            },
            {
                "kernel_turn_index": 2,
                "action_type": None,
                "action_inputs": {},
                "idempotency_key": "ik-2",
                "rationale": "record posture",
                "latest_refs_snapshot": {"working": "ref-1"},
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": False,
                "execution_state": "skipped",
                "execution_reason_code": None,
            },
            {
                "kernel_turn_index": 3,
                "action_type": None,
                "action_inputs": {},
                "idempotency_key": "ik-3",
                "rationale": "record posture again",
                "latest_refs_snapshot": {"working": "ref-1"},
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": False,
                "execution_state": "skipped",
                "execution_reason_code": None,
            },
        ]
    )
    loop_memory.continuity.state_patch_feedback = {
        "outcome": "rejected",
        "reason_code": "mission_unknown_keys",
    }
    loop_memory.continuity.resolution_state = new_resolution_state(
        items=[
            {
                "item_id": "i-open",
                "title": "Open item",
                "kind": "work_unit",
                "status": "blocked",
                "structure_kind": "group",
                "sequence_scope": "lane-a",
                "sequence_index": 1,
                "blocking": True,
                "requires_hitl": True,
                "no_further_progress": True,
                "evidence_refs": ["artifact://ref-1"],
                "verification_basis": "Compared against the source excerpt.",
            },
            {
                "item_id": "i-closed-thin",
                "title": "Closed item without full proof",
                "kind": "work_unit",
                "status": "closed",
                "materiality": "critical",
                "sequence_index": 2,
            },
            {
                "item_id": "i-closed-earned",
                "title": "Closed item with full proof",
                "kind": "work_unit",
                "status": "closed",
                "structure_kind": "atomic",
                "sequence_scope": "lane-a",
                "sequence_index": 3,
                "determination": "earned",
                "verification_basis": "Resolved against source evidence.",
                "completion_criteria": "The disputed span matches the source.",
                "evidence_refs": ["artifact://ref-2"],
            },
        ]
    )
    loop_memory.continuity.mission_state = new_mission_state(
        mission_id="m-proof",
        loop_family="orchestration_kernel",
        work_universe_posture="partial",
        resolution_state=loop_memory.continuity.resolution_state,
        success_conditions=[
            {
                "condition_id": "c1",
                "title": "Visible claims reviewed",
                "status": "in_review",
                "determination": "provisional",
            },
            {
                "condition_id": "c2",
                "title": "Closure posture is earned",
                "status": "satisfied",
                "determination": "earned",
                "verification_basis": "All required dimensions carry explicit basis.",
            },
        ],
        closure_state={
            "dimensions": [
                {
                    "dimension_id": "layer_1",
                    "title": "Layer 1",
                    "status": "closed",
                },
                {
                    "dimension_id": "layer_2",
                    "title": "Layer 2",
                    "status": "closed",
                    "determination": "earned",
                    "verification_basis": "Source contradiction check completed.",
                },
            ]
        },
    )

    summary = build_prompt_observability_summary(loop_memory)

    assert summary["prompt_event_count"] == 5
    assert summary["last_prompt_event_id"] == "pe-5"
    assert summary["consecutive_no_dispatch_turns"] == 2
    assert summary["turns_since_last_tool_execution"] == 2
    assert summary["turns_since_latest_refs_change"] == 2
    assert summary["last_state_patch_outcome"] == "rejected"
    assert summary["success_condition_count"] == 2
    assert summary["success_conditions_with_earned_determination_count"] == 1
    assert summary["resolution_item_count"] == 3
    assert summary["sequenced_item_count"] == 2
    assert summary["sequenced_items_missing_scope_count"] == 1
    assert summary["sequenced_items_missing_index_count"] == 0
    assert summary["duplicate_sequence_positions_count"] == 0
    assert summary["sequence_scope_order_gaps_count"] == 1
    assert summary["atomic_item_count"] == 1
    assert summary["group_item_count"] == 1
    assert summary["group_items_without_subclaims_count"] == 1
    assert summary["items_with_evidence_count"] == 2
    assert summary["items_with_verification_basis_count"] == 2
    assert summary["items_blocking_count"] == 1
    assert summary["items_requires_hitl_count"] == 1
    assert summary["items_no_further_progress_count"] == 1
    assert summary["covered_units_requires_hitl_count"] == 0
    assert summary["covered_units_no_further_progress_count"] == 0
    assert summary["closed_items_count"] == 2
    assert summary["closed_items_without_earned_determination_count"] == 1
    assert summary["closed_items_without_basis_count"] == 1
    assert summary["closed_items_without_completion_criteria_count"] == 1
    assert summary["critical_closed_items_without_evidence_count"] == 1
    assert summary["critical_closed_items_without_verification_basis_count"] == 1
    assert summary["blocking_items_without_relations_count"] == 1
    assert summary["closure_dimension_count"] == 2
    assert summary["closure_dimensions_with_earned_determination_count"] == 1
    assert summary["closed_dimensions_without_earned_determination_count"] == 1
    assert summary["closed_dimensions_without_basis_count"] == 1
    assert summary["work_universe_posture"] == "partial"


def test_build_prompt_observability_summary_distinguishes_progress_from_true_stall() -> None:
    progress_memory = LoopMemoryState()
    progress_memory.continuity.active_item_id = "item-1"
    progress_memory.continuity.kernel_step_records.extend(
        [
            {
                "kernel_turn_index": 1,
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_slot": "working"},
                "active_item_id_snapshot": "item-1",
                "latest_refs_snapshot": {"working": "ref-1"},
                "work_state_signature": "state-a",
                "skip_execution": False,
                "wait_for_human": False,
                "complete_run": False,
                "execution_state": "executed",
                "execution_reason_code": None,
            },
            {
                "kernel_turn_index": 2,
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_slot": "working"},
                "active_item_id_snapshot": "item-1",
                "latest_refs_snapshot": {"working": "ref-1"},
                "work_state_signature": "state-b",
                "skip_execution": False,
                "wait_for_human": False,
                "complete_run": False,
                "execution_state": "executed",
                "execution_reason_code": None,
            },
            {
                "kernel_turn_index": 3,
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_slot": "working"},
                "active_item_id_snapshot": "item-1",
                "latest_refs_snapshot": {"working": "ref-1"},
                "work_state_signature": "state-c",
                "skip_execution": False,
                "wait_for_human": False,
                "complete_run": False,
                "execution_state": "executed",
                "execution_reason_code": None,
            },
        ]
    )
    progress_summary = build_prompt_observability_summary(progress_memory)
    assert progress_summary["same_ref_bundle_reread_no_gain_streak"] == 1
    assert progress_summary["same_item_same_ref_bundle_stall_streak"] == 1
    assert not any(
        flag.startswith("same_ref_bundle_reread_no_gain:")
        or flag.startswith("same_item_same_ref_bundle_stall:")
        for flag in progress_summary["mechanical_flags"]
    )

    stall_memory = LoopMemoryState()
    stall_memory.continuity.active_item_id = "item-1"
    stall_memory.continuity.kernel_step_records.extend(
        [
            {
                "kernel_turn_index": 1,
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_slot": "working"},
                "active_item_id_snapshot": "item-1",
                "latest_refs_snapshot": {"working": "ref-1"},
                "work_state_signature": "state-a",
                "skip_execution": False,
                "wait_for_human": False,
                "complete_run": False,
                "execution_state": "executed",
                "execution_reason_code": None,
            },
            {
                "kernel_turn_index": 2,
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_slot": "working"},
                "active_item_id_snapshot": "item-1",
                "latest_refs_snapshot": {"working": "ref-1"},
                "work_state_signature": "state-a",
                "skip_execution": False,
                "wait_for_human": False,
                "complete_run": False,
                "execution_state": "executed",
                "execution_reason_code": None,
            },
            {
                "kernel_turn_index": 3,
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_slot": "working"},
                "active_item_id_snapshot": "item-1",
                "latest_refs_snapshot": {"working": "ref-1"},
                "work_state_signature": "state-a",
                "skip_execution": False,
                "wait_for_human": False,
                "complete_run": False,
                "execution_state": "executed",
                "execution_reason_code": None,
            },
        ]
    )
    stall_summary = build_prompt_observability_summary(stall_memory)
    assert stall_summary["same_ref_bundle_reread_no_gain_streak"] == 3
    assert stall_summary["same_item_same_ref_bundle_stall_streak"] == 3
    assert "same_ref_bundle_reread_no_gain:3" in stall_summary["mechanical_flags"]
    assert "same_item_same_ref_bundle_stall:3" in stall_summary["mechanical_flags"]
