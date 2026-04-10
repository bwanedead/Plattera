from __future__ import annotations

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

    summary = build_prompt_observability_summary(loop_memory)

    assert summary["prompt_event_count"] == 5
    assert summary["last_prompt_event_id"] == "pe-5"
    assert summary["consecutive_no_dispatch_turns"] == 2
    assert summary["turns_since_last_tool_execution"] == 2
    assert summary["turns_since_latest_refs_change"] == 2
    assert summary["last_state_patch_outcome"] == "rejected"
