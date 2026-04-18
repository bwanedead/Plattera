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
            },
            {
                "item_id": "i-closed-earned",
                "title": "Closed item with full proof",
                "kind": "work_unit",
                "status": "closed",
                "determination": "earned",
                "verification_basis": "Resolved against source evidence.",
                "completion_criteria": "The disputed span matches the source.",
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
    assert summary["items_with_evidence_count"] == 1
    assert summary["items_with_verification_basis_count"] == 2
    assert summary["items_blocking_count"] == 1
    assert summary["items_requires_hitl_count"] == 1
    assert summary["items_no_further_progress_count"] == 1
    assert summary["closed_items_count"] == 2
    assert summary["closed_items_without_earned_determination_count"] == 1
    assert summary["closed_items_without_basis_count"] == 1
    assert summary["closed_items_without_completion_criteria_count"] == 1
    assert summary["closure_dimension_count"] == 2
    assert summary["closure_dimensions_with_earned_determination_count"] == 1
    assert summary["closed_dimensions_without_earned_determination_count"] == 1
    assert summary["closed_dimensions_without_basis_count"] == 1
    assert summary["work_universe_posture"] == "partial"
