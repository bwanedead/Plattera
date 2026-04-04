"""Tests for mechanical ``kernel_resume.v1`` snapshot parse/build (no semantic inference)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.execution.contracts import ExecutionSessionStartRequest
from harness.execution.executor import ExecutionExecutor
from harness.execution.session import ExecutionSessionManager
from harness.mission_state import new_mission_state, new_resolution_state
from harness.runtime.memory.continuity_journal import wrap_journal_entry
from harness.runtime.memory.loop_state import LoopMemoryState
from harness.runtime.memory.resume_snapshot import (
    build_kernel_resume_snapshot,
    hydrate_session_manager_from_resume_payload,
    load_kernel_resume_snapshot_from_path,
    merge_launch_latest_refs_with_resume_continuity,
    parse_kernel_resume_snapshot,
)
from harness.runtime.runner import RuntimeRunner, RuntimeRunnerError


def test_parse_rejects_continuity_latest_refs_wrong_type() -> None:
    rs = new_resolution_state()
    ms = new_mission_state(mission_id="m1", loop_family="orchestration_kernel", resolution_state=rs)
    base = {
        "schema_version": "kernel_resume.v1",
        "next_iteration": 1,
        "continuity": {
            "latest_refs": "not-a-mapping",
            "mission_state": ms.model_dump(mode="json"),
            "resolution_state": rs.model_dump(mode="json"),
            "active_item_id": None,
        },
        "hitl": {"hitl_state": "no_prompt", "pending_feedback_prompt_id": None},
        "telemetry": {
            "llm_contact_count": 0,
            "prompt_event_count": 0,
            "last_prompt_event_id": None,
            "last_prompt_event_surface": None,
        },
        "execution_session": None,
    }
    _, _, err = parse_kernel_resume_snapshot(base)
    assert err == "resume_snapshot_continuity_latest_refs_invalid"


def test_parse_rejects_active_item_id_non_string() -> None:
    rs = new_resolution_state()
    ms = new_mission_state(mission_id="m1", loop_family="orchestration_kernel", resolution_state=rs)
    base = {
        "schema_version": "kernel_resume.v1",
        "next_iteration": 1,
        "continuity": {
            "latest_refs": {},
            "mission_state": ms.model_dump(mode="json"),
            "resolution_state": rs.model_dump(mode="json"),
            "active_item_id": ["not-a-string"],
        },
        "hitl": {"hitl_state": "no_prompt"},
        "telemetry": {
            "llm_contact_count": 0,
            "prompt_event_count": 0,
        },
        "execution_session": None,
    }
    _, _, err = parse_kernel_resume_snapshot(base)
    assert err == "resume_snapshot_continuity_active_item_id_invalid"


def test_parse_rejects_telemetry_last_prompt_event_id_non_string() -> None:
    rs = new_resolution_state()
    ms = new_mission_state(mission_id="m1", loop_family="orchestration_kernel", resolution_state=rs)
    base = {
        "schema_version": "kernel_resume.v1",
        "next_iteration": 1,
        "continuity": {
            "latest_refs": {},
            "mission_state": ms.model_dump(mode="json"),
            "resolution_state": rs.model_dump(mode="json"),
        },
        "hitl": {"hitl_state": "no_prompt"},
        "telemetry": {
            "llm_contact_count": 0,
            "prompt_event_count": 0,
            "last_prompt_event_id": 99,
        },
        "execution_session": None,
    }
    _, _, err = parse_kernel_resume_snapshot(base)
    assert err == "resume_snapshot_telemetry_last_prompt_event_id_invalid"


def test_parse_rejects_continuity_state_patch_feedback_wrong_type() -> None:
    rs = new_resolution_state()
    ms = new_mission_state(mission_id="m1", loop_family="orchestration_kernel", resolution_state=rs)
    base = {
        "schema_version": "kernel_resume.v1",
        "next_iteration": 1,
        "continuity": {
            "latest_refs": {},
            "mission_state": ms.model_dump(mode="json"),
            "resolution_state": rs.model_dump(mode="json"),
            "active_item_id": None,
            "state_patch_feedback": 42,
        },
        "hitl": {"hitl_state": "no_prompt", "pending_feedback_prompt_id": None},
        "telemetry": {
            "llm_contact_count": 0,
            "prompt_event_count": 0,
            "last_prompt_event_id": None,
            "last_prompt_event_surface": None,
        },
        "execution_session": None,
    }
    _, _, err = parse_kernel_resume_snapshot(base)
    assert err == "resume_snapshot_continuity_state_patch_feedback_invalid"


def test_parse_rejects_hitl_pending_feedback_wrong_type() -> None:
    rs = new_resolution_state()
    ms = new_mission_state(mission_id="m1", loop_family="orchestration_kernel", resolution_state=rs)
    base = {
        "schema_version": "kernel_resume.v1",
        "next_iteration": 1,
        "continuity": {
            "latest_refs": {},
            "mission_state": ms.model_dump(mode="json"),
            "resolution_state": rs.model_dump(mode="json"),
            "active_item_id": None,
        },
        "hitl": {
            "hitl_state": "no_prompt",
            "pending_feedback_prompt_id": None,
            "pending_feedback_response": [],
        },
        "telemetry": {
            "llm_contact_count": 0,
            "prompt_event_count": 0,
            "last_prompt_event_id": None,
            "last_prompt_event_surface": None,
        },
        "execution_session": None,
    }
    _, _, err = parse_kernel_resume_snapshot(base)
    assert err == "resume_snapshot_hitl_pending_feedback_response_invalid"


def test_merge_launch_refs_prefers_launch_on_collision() -> None:
    lm = LoopMemoryState()
    lm.continuity.latest_refs = {"a": 1, "b": 2}
    merged = merge_launch_latest_refs_with_resume_continuity({"b": 9, "c": 3}, initial_loop_memory=lm)
    assert merged == {"a": 1, "b": 9, "c": 3}


def test_merge_launch_refs_without_memory_is_launch_only() -> None:
    assert merge_launch_latest_refs_with_resume_continuity({"x": 1}, initial_loop_memory=None) == {"x": 1}


def test_parse_rejects_schema_mismatch() -> None:
    mem, it, err = parse_kernel_resume_snapshot({"schema_version": "other.v9"})
    assert err == "resume_snapshot_schema_mismatch"
    assert it == 1


def test_parse_rejects_invalid_mission_state() -> None:
    base = {
        "schema_version": "kernel_resume.v1",
        "next_iteration": 1,
        "continuity": {
            "latest_refs": {},
            "mission_state": {"mission_id": ""},
            "resolution_state": new_resolution_state().model_dump(mode="json"),
            "active_item_id": None,
            "state_patch_feedback": {},
        },
        "hitl": {"hitl_state": "no_prompt", "pending_feedback_prompt_id": None, "pending_feedback_response": None},
        "telemetry": {
            "llm_contact_count": 0,
            "prompt_event_count": 0,
            "last_prompt_event_id": None,
            "last_prompt_event_surface": None,
        },
        "execution_session": None,
    }
    _, _, err = parse_kernel_resume_snapshot(base)
    assert err == "resume_snapshot_mission_resolution_invalid"


def test_roundtrip_continuity_journal_progress_and_compacted_summary() -> None:
    executor = ExecutionExecutor()
    sm = ExecutionSessionManager(executor=executor)
    sm.start_session(ExecutionSessionStartRequest(run_id="run-j", session_id="sess-j"))
    lm = LoopMemoryState()
    lm.continuity.mission_state = new_mission_state(mission_id="m1", loop_family="orchestration_kernel")
    lm.continuity.resolution_state = new_resolution_state()
    lm.continuity.continuity_journal_entries.append(
        wrap_journal_entry(kernel_turn_index=1, author_payload={"note": "a"})
    )
    lm.continuity.operator_progress_message = "doing work"
    lm.continuity.compacted_continuity_summary = "older material folded"
    lm.continuity.kernel_step_records.append(
        {
            "kernel_turn_index": 1,
            "action_type": "noop",
            "action_inputs": {"a": 1},
            "idempotency_key": "ik-j",
            "rationale": None,
            "latest_refs_snapshot": {"ref": "x"},
            "skip_execution": True,
            "wait_for_human": False,
            "complete_run": False,
            "execution_state": "skipped",
            "execution_reason_code": None,
        }
    )
    lm.continuity.kernel_compaction_covered_through_turn_index = 7
    snap = build_kernel_resume_snapshot(
        loop_memory=lm,
        session_manager=sm,
        session_id="sess-j",
        next_iteration=2,
    )
    mem2, next_it, err = parse_kernel_resume_snapshot(snap)
    assert err is None
    assert next_it == 2
    assert len(mem2.continuity.continuity_journal_entries) == 1
    assert mem2.continuity.continuity_journal_entries[0]["author_payload"]["note"] == "a"
    assert mem2.continuity.operator_progress_message == "doing work"
    assert mem2.continuity.compacted_continuity_summary == "older material folded"
    assert len(mem2.continuity.kernel_step_records) == 1
    assert mem2.continuity.kernel_step_records[0]["idempotency_key"] == "ik-j"
    assert mem2.continuity.kernel_step_records[0]["latest_refs_snapshot"] == {"ref": "x"}
    assert mem2.continuity.kernel_compaction_covered_through_turn_index == 7


def test_roundtrip_kernel_step_result_records() -> None:
    executor = ExecutionExecutor()
    sm = ExecutionSessionManager(executor=executor)
    sm.start_session(ExecutionSessionStartRequest(run_id="run-r", session_id="sess-r"))
    lm = LoopMemoryState()
    lm.continuity.mission_state = new_mission_state(mission_id="m1", loop_family="orchestration_kernel")
    lm.continuity.resolution_state = new_resolution_state()
    lm.continuity.kernel_step_result_records.append(
        {
            "kernel_turn_index": 3,
            "action_type": "noop",
            "execution_state": "executed",
            "execution_reason_code": None,
            "artifact_refs": ["ref-a"],
            "latest_refs_snapshot": {"k": 1},
            "outputs_for_continuity": {"out": True},
            "result_truncated": False,
        }
    )
    snap = build_kernel_resume_snapshot(
        loop_memory=lm,
        session_manager=sm,
        session_id="sess-r",
        next_iteration=4,
    )
    assert snap["continuity"]["kernel_step_result_records"][0]["kernel_turn_index"] == 3
    mem2, next_it, err = parse_kernel_resume_snapshot(snap)
    assert err is None
    assert next_it == 4
    assert len(mem2.continuity.kernel_step_result_records) == 1
    assert mem2.continuity.kernel_step_result_records[0]["outputs_for_continuity"] == {"out": True}


def test_roundtrip_loop_memory_and_execution_session() -> None:
    executor = ExecutionExecutor()
    sm = ExecutionSessionManager(executor=executor)
    sm.start_session(ExecutionSessionStartRequest(run_id="run-a", session_id="sess-a"))
    lm = LoopMemoryState()
    lm.continuity.mission_state = new_mission_state(mission_id="m1", loop_family="orchestration_kernel")
    lm.continuity.resolution_state = new_resolution_state()
    lm.continuity.active_item_id = "focus-1"
    lm.continuity.state_patch_feedback = {"outcome": "applied", "iteration": 1, "gate": "step_executed"}

    snap = build_kernel_resume_snapshot(
        loop_memory=lm,
        session_manager=sm,
        session_id="sess-a",
        next_iteration=4,
    )
    mem2, next_it, perr = parse_kernel_resume_snapshot(snap)
    assert perr is None
    assert next_it == 4
    assert mem2.continuity.active_item_id == "focus-1"
    assert mem2.continuity.state_patch_feedback["outcome"] == "applied"

    mgr2, herr = hydrate_session_manager_from_resume_payload(snap, executor=executor)
    assert herr is None
    assert mgr2 is not None
    assert "sess-a" in mgr2.sessions


def test_kernel_resume_rehydrates_resolution_for_subsequent_sync() -> None:
    from harness.runtime.orchestration.orchestrator import run_orchestration_kernel_loop
    from harness.runtime.orchestration.test_orchestrator import FakeSessionManager, MechanicalInheritSyncPack

    sm = FakeSessionManager()
    r1 = run_orchestration_kernel_loop(
        orchestration_adapter=MechanicalInheritSyncPack(),
        session_manager=sm,
        session_id="sess-rehydrate",
        run_artifact_ref=None,
        request_id_prefix="req-rehydrate",
        opaque_run_context={},
        max_iterations=8,
    )
    assert r1.terminal_class == "completed"
    snap = r1.kernel_resume_snapshot
    assert snap is not None
    mem, next_it, err = parse_kernel_resume_snapshot(snap)
    assert err is None
    assert len(mem.continuity.resolution_state.items) == 1
    assert mem.continuity.resolution_state.items[0].status == "closed"

    sm2 = FakeSessionManager()
    r2 = run_orchestration_kernel_loop(
        orchestration_adapter=MechanicalInheritSyncPack(),
        session_manager=sm2,
        session_id="sess-rehydrate",
        run_artifact_ref=None,
        request_id_prefix="req-rehydrate-2",
        opaque_run_context={},
        max_iterations=4,
        initial_loop_memory=mem,
        resume_start_iteration=next_it,
    )
    assert r2.terminal_class == "completed"
    rs2 = r2.runtime_state["resolution_state"]
    assert len(rs2.items) == 1
    assert rs2.items[0].item_id == "work-1"
    assert rs2.items[0].status == "closed"


def test_load_snapshot_from_path_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "snap.json"
    doc = {"schema_version": "kernel_resume.v1", "next_iteration": 1}
    p.write_text(json.dumps(doc), encoding="utf-8")
    loaded, err = load_kernel_resume_snapshot_from_path(p)
    assert err is None
    assert loaded == doc


def test_runner_rejects_resume_path_and_inline_together(tmp_path: Path) -> None:
    from harness.runtime.composition import TurnBlock, TurnSurface
    from harness.runtime.runner.contracts import RuntimeArtifactTargets

    class _A:
        def build_turn_surface(self, lc: dict) -> TurnSurface:
            return TurnSurface(
                surface_id="s",
                blocks=(TurnBlock(content="x", metadata={}),),
                payload={},
                tool_bindings=(),
            )

    targets = RuntimeArtifactTargets(done_file=tmp_path / "done.json", result_file=tmp_path / "result.json")
    runner = RuntimeRunner(adapter=_A(), targets=targets)
    with pytest.raises(RuntimeRunnerError, match="resume_snapshot_conflict"):
        runner.run(
            launch_context={
                "kernel_resume_snapshot_path": str(tmp_path / "nope.json"),
                "kernel_resume_snapshot": {"schema_version": "kernel_resume.v1"},
            }
        )
