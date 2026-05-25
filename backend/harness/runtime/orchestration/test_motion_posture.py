"""Focused tests for generic ``motion_posture`` mission state."""

from __future__ import annotations

import pytest

from harness.audit.human_timeline import render_timeline
from harness.execution.contracts import ExecutionSessionStartRequest
from harness.execution.executor import ExecutionExecutor
from harness.execution.session import ExecutionSessionManager
from harness.mission_state import MissionState, new_mission_state, new_resolution_state
from harness.runtime.memory import LoopMemoryState
from harness.runtime.memory.resume_snapshot import (
    build_kernel_resume_snapshot,
    parse_kernel_resume_snapshot,
)
from harness.runtime.orchestration.loop_health_summary import build_prompt_observability_summary
from harness.runtime.orchestration.state_patch_apply import StatePatchError, apply_state_patch


def _base_states():
    rs = new_resolution_state()
    ms = new_mission_state(
        mission_id="m1",
        loop_family="orchestration_kernel",
        resolution_state=rs,
    )
    return ms, rs


def test_mission_defaults_motion_posture_to_inventory() -> None:
    ms, _ = _base_states()
    assert ms.motion_posture == "inventory"
    assert ms.motion_posture_basis is None


def test_mission_patch_accepts_motion_posture_inventory() -> None:
    ms, rs = _base_states()
    ms2, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "mission": {
                "motion_posture": "inventory",
                "motion_posture_basis": "Still naming mission-critical atoms.",
            }
        },
    )
    assert ms2.motion_posture == "inventory"
    assert ms2.motion_posture_basis == "Still naming mission-critical atoms."


def test_mission_patch_accepts_motion_posture_resolution() -> None:
    ms, rs = _base_states()
    ms2, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "mission": {
                "work_universe_posture": "believed_adequate",
                "motion_posture": "resolution",
                "motion_posture_basis": "No mission-critical atom I can name remains unrepresented.",
            }
        },
    )
    assert ms2.work_universe_posture == "believed_adequate"
    assert ms2.motion_posture == "resolution"
    assert ms2.motion_posture_basis == "No mission-critical atom I can name remains unrepresented."


def test_mission_patch_rejects_invalid_motion_posture() -> None:
    ms, rs = _base_states()
    with pytest.raises(StatePatchError) as excinfo:
        apply_state_patch(
            mission_state=ms,
            resolution_state=rs,
            state_patch={"mission": {"motion_posture": "explore"}},
        )
    assert excinfo.value.reason_code == "motion_posture_invalid"


def test_mission_patch_rejects_non_string_motion_posture_basis() -> None:
    ms, rs = _base_states()
    with pytest.raises(StatePatchError) as excinfo:
        apply_state_patch(
            mission_state=ms,
            resolution_state=rs,
            state_patch={"mission": {"motion_posture_basis": 42}},
        )
    assert excinfo.value.reason_code == "motion_posture_basis_invalid"


def test_mission_patch_trims_and_bounds_motion_posture_basis() -> None:
    ms, rs = _base_states()
    ms2, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={"mission": {"motion_posture_basis": "  " + ("x" * 600) + "  "}},
    )
    assert ms2.motion_posture_basis is not None
    assert len(ms2.motion_posture_basis) == 500


def test_mission_patch_clears_stale_basis_when_motion_posture_changes_to_inventory() -> None:
    ms, rs = _base_states()
    ms = ms.model_copy(
        update={
            "motion_posture": "resolution",
            "motion_posture_basis": "No mission-critical atom remains unrepresented.",
        }
    )
    ms2, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={"mission": {"motion_posture": "inventory"}},
    )
    assert ms2.motion_posture == "inventory"
    assert ms2.motion_posture_basis is None


def test_mission_patch_clears_stale_basis_when_motion_posture_changes_to_resolution() -> None:
    ms, rs = _base_states()
    ms = ms.model_copy(
        update={
            "motion_posture": "inventory",
            "motion_posture_basis": "Still naming mission-critical atoms.",
        }
    )
    ms2, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={"mission": {"motion_posture": "resolution"}},
    )
    assert ms2.motion_posture == "resolution"
    assert ms2.motion_posture_basis is None


def test_mission_patch_keeps_basis_when_motion_posture_unchanged() -> None:
    ms, rs = _base_states()
    ms = ms.model_copy(
        update={
            "motion_posture": "resolution",
            "motion_posture_basis": "Ready for item-level resolution motion.",
        }
    )
    ms2, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={"mission": {"motion_posture": "resolution"}},
    )
    assert ms2.motion_posture == "resolution"
    assert ms2.motion_posture_basis == "Ready for item-level resolution motion."


def test_mission_patch_motion_posture_change_with_basis_in_same_patch() -> None:
    ms, rs = _base_states()
    ms = ms.model_copy(
        update={
            "motion_posture": "resolution",
            "motion_posture_basis": "Old resolution basis.",
        }
    )
    ms2, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "mission": {
                "motion_posture": "inventory",
                "motion_posture_basis": "Returning to inventory motion.",
            }
        },
    )
    assert ms2.motion_posture == "inventory"
    assert ms2.motion_posture_basis == "Returning to inventory motion."


def test_resume_snapshot_round_trips_motion_posture_fields() -> None:
    executor = ExecutionExecutor()
    session_manager = ExecutionSessionManager(executor=executor)
    session_manager.start_session(
        ExecutionSessionStartRequest(run_id="run-motion", session_id="sess-motion")
    )
    rs = new_resolution_state()
    ms = new_mission_state(
        mission_id="m1",
        loop_family="orchestration_kernel",
        motion_posture="resolution",
        motion_posture_basis="Baseline inventory appears complete enough.",
        resolution_state=rs,
    )
    loop_memory = LoopMemoryState()
    loop_memory.continuity.mission_state = ms
    loop_memory.continuity.resolution_state = rs
    snapshot = build_kernel_resume_snapshot(
        loop_memory=loop_memory,
        session_manager=session_manager,
        session_id="sess-motion",
        next_iteration=2,
    )
    restored, _, err = parse_kernel_resume_snapshot(snapshot)
    assert err is None
    assert restored.continuity.mission_state.motion_posture == "resolution"
    assert restored.continuity.mission_state.motion_posture_basis == "Baseline inventory appears complete enough."


def test_prompt_observability_summary_includes_motion_posture_fields() -> None:
    loop_memory = LoopMemoryState()
    loop_memory.continuity.mission_state = new_mission_state(
        mission_id="m1",
        loop_family="orchestration_kernel",
        motion_posture="resolution",
        motion_posture_basis="Ready for item-level resolution motion.",
        resolution_state=new_resolution_state(),
    )
    summary = build_prompt_observability_summary(loop_memory)
    assert summary["motion_posture"] == "resolution"
    assert summary["motion_posture_basis"] == "Ready for item-level resolution motion."


def test_timeline_renders_motion_posture_snapshot_and_transition() -> None:
    body = render_timeline(
        [
            {
                "turn_index": 3,
                "parse_ok": True,
                "mission_state_before": {
                    "motion_posture": "inventory",
                    "work_universe_posture": "partial",
                },
                "mission_state_after": {
                    "motion_posture": "resolution",
                    "work_universe_posture": "believed_adequate",
                    "motion_posture_basis": "No mission-critical atom remains unrepresented.",
                },
                "state_patch_feedback": {"outcome": "applied"},
                "prompt_observability_summary": {
                    "motion_posture": "resolution",
                    "motion_posture_basis": "No mission-critical atom remains unrepresented.",
                    "work_universe_posture": "believed_adequate",
                },
            }
        ]
    )
    assert "motion_posture: resolution" in body
    assert "work_universe_posture: believed_adequate" in body
    assert "motion_posture: inventory -> resolution" in body
    assert "No mission-critical atom remains unrepresented." in body


def test_orchestrator_policy_does_not_gate_tools_on_motion_posture() -> None:
    from pathlib import Path

    policy_path = Path(__file__).resolve().parent / "orchestrator_policy.py"
    source = policy_path.read_text(encoding="utf-8")
    assert "motion_posture" not in source


def test_legacy_mission_state_without_motion_posture_defaults_on_validate() -> None:
    ms = MissionState.model_validate(
        {
            "mission_id": "m1",
            "loop_family": "orchestration_kernel",
            "work_universe_posture": "partial",
        }
    )
    assert ms.motion_posture == "inventory"
