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


def test_roundtrip_hitl_pending_and_answered_lists() -> None:
    executor = ExecutionExecutor()
    sm = ExecutionSessionManager(executor=executor)
    sm.start_session(ExecutionSessionStartRequest(run_id="run-h", session_id="sess-h"))
    lm = LoopMemoryState()
    lm.continuity.mission_state = new_mission_state(mission_id="m1", loop_family="orchestration_kernel")
    lm.continuity.resolution_state = new_resolution_state()
    lm.hitl.hitl_state = "async_prompts_pending"
    lm.hitl.pending_hitl_requests.append(
        {
            "prompt_id": "p1",
            "message": "m1",
            "choices": [],
            "context": {},
            "opaque_payload": {},
            "issued_at_iteration": 2,
        }
    )
    lm.hitl.answered_hitl_responses.append(
        {"prompt_id": "p0", "feedback": {"choice": "yes", "submitted_at_epoch_seconds": 99}}
    )
    lm.hitl.blocking_prompt_id = None
    snap = build_kernel_resume_snapshot(
        loop_memory=lm,
        session_manager=sm,
        session_id="sess-h",
        next_iteration=3,
    )
    mem2, next_it, err = parse_kernel_resume_snapshot(snap)
    assert err is None
    assert next_it == 3
    assert len(mem2.hitl.pending_hitl_requests) == 1
    assert mem2.hitl.pending_hitl_requests[0]["prompt_id"] == "p1"
    assert len(mem2.hitl.answered_hitl_responses) == 1
    assert mem2.hitl.answered_hitl_responses[0]["prompt_id"] == "p0"


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


# ---------------------------------------------------------------------------
# Sequencing debt round-trip (earned_before_local_evidence_debt / posthoc)
# ---------------------------------------------------------------------------

def test_roundtrip_sequencing_debt_preserved() -> None:
    """earned_before_local_evidence_debt and posthoc_recheck_needed_debt survive snapshot round-trip."""
    executor = ExecutionExecutor()
    sm = ExecutionSessionManager(executor=executor)
    sm.start_session(ExecutionSessionStartRequest(run_id="run-sd", session_id="sess-sd"))
    lm = LoopMemoryState()
    lm.continuity.mission_state = new_mission_state(mission_id="m1", loop_family="orchestration_kernel")
    lm.continuity.resolution_state = new_resolution_state()
    lm.continuity.earned_before_local_evidence_debt = {"item1//u1": 23, "item1//u2": 24}
    lm.continuity.posthoc_recheck_needed_debt = {"item1//u1": 25}

    snap = build_kernel_resume_snapshot(
        loop_memory=lm, session_manager=sm, session_id="sess-sd", next_iteration=30
    )
    assert snap["continuity"]["earned_before_local_evidence_debt"] == {"item1//u1": 23, "item1//u2": 24}
    assert snap["continuity"]["posthoc_recheck_needed_debt"] == {"item1//u1": 25}

    mem2, next_it, err = parse_kernel_resume_snapshot(snap)
    assert err is None
    assert next_it == 30
    assert mem2.continuity.earned_before_local_evidence_debt == {"item1//u1": 23, "item1//u2": 24}
    assert mem2.continuity.posthoc_recheck_needed_debt == {"item1//u1": 25}


def test_roundtrip_sequencing_debt_absent_defaults_to_empty() -> None:
    """Snapshot without debt keys (old snapshot) restores to empty dicts without error."""
    rs = new_resolution_state()
    ms = new_mission_state(mission_id="m1", loop_family="orchestration_kernel", resolution_state=rs)
    base = {
        "schema_version": "kernel_resume.v1",
        "next_iteration": 5,
        "continuity": {
            "latest_refs": {},
            "mission_state": ms.model_dump(mode="json"),
            "resolution_state": rs.model_dump(mode="json"),
            "active_item_id": None,
            # No earned_before_local_evidence_debt / posthoc_recheck_needed_debt keys
        },
        "hitl": {"hitl_state": "no_prompt"},
        "telemetry": {"llm_contact_count": 0, "prompt_event_count": 0},
        "execution_session": None,
    }
    mem2, _, err = parse_kernel_resume_snapshot(base)
    assert err is None
    assert mem2.continuity.earned_before_local_evidence_debt == {}
    assert mem2.continuity.posthoc_recheck_needed_debt == {}


def test_parse_rejects_earned_debt_wrong_type() -> None:
    """earned_before_local_evidence_debt must be a mapping, not a list."""
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
            "earned_before_local_evidence_debt": ["not", "a", "mapping"],
        },
        "hitl": {"hitl_state": "no_prompt"},
        "telemetry": {"llm_contact_count": 0, "prompt_event_count": 0},
        "execution_session": None,
    }
    _, _, err = parse_kernel_resume_snapshot(base)
    assert err == "resume_snapshot_earned_before_local_evidence_debt_invalid"


def test_roundtrip_hitl_exchange_ledger_preserved() -> None:
    """HITL exchange ledger pending/answered/consumed entries survive snapshot round-trip."""
    executor = ExecutionExecutor()
    sm = ExecutionSessionManager(executor=executor)
    sm.start_session(ExecutionSessionStartRequest(run_id="run-led", session_id="sess-led"))
    lm = LoopMemoryState()
    lm.continuity.mission_state = new_mission_state(mission_id="m1", loop_family="orchestration_kernel")
    lm.continuity.resolution_state = new_resolution_state()
    lm.continuity.hitl_exchange_ledger = [
        {
            "exchange_id": "hitl:p1",
            "prompt_id": "p1",
            "blocking": True,
            "issued_at_iteration": 5,
            "request": {"message": "Pick", "choices": ["a", "b"]},
            "response": None,
            "received_at_iteration": None,
            "consumed_at_iteration": None,
            "status": "pending",
        },
        {
            "exchange_id": "hitl:p2",
            "prompt_id": "p2",
            "blocking": False,
            "issued_at_iteration": 6,
            "request": {"message": "Confirm"},
            "response": {"choice": "yes", "note": "ok"},
            "received_at_iteration": 7,
            "consumed_at_iteration": None,
            "status": "answered",
        },
        {
            "exchange_id": "hitl:p3",
            "prompt_id": "p3",
            "blocking": False,
            "issued_at_iteration": 1,
            "request": {"message": "Old"},
            "response": {"choice": "x"},
            "received_at_iteration": 2,
            "consumed_at_iteration": 3,
            "status": "consumed",
        },
    ]
    lm.continuity.hitl_consumed_unknown_prompt_count = 4

    snap = build_kernel_resume_snapshot(
        loop_memory=lm, session_manager=sm, session_id="sess-led", next_iteration=10
    )
    assert len(snap["continuity"]["hitl_exchange_ledger"]) == 3
    assert snap["continuity"]["hitl_consumed_unknown_prompt_count"] == 4

    mem2, _, err = parse_kernel_resume_snapshot(snap)
    assert err is None
    led = mem2.continuity.hitl_exchange_ledger
    assert len(led) == 3
    assert led[0]["status"] == "pending"
    assert led[1]["status"] == "answered"
    assert led[1]["response"] == {"choice": "yes", "note": "ok"}
    assert led[2]["status"] == "consumed"
    assert led[2]["consumed_at_iteration"] == 3
    assert mem2.continuity.hitl_consumed_unknown_prompt_count == 4


def test_roundtrip_hitl_ledger_absent_defaults_to_empty() -> None:
    """Old snapshots without ledger key restore to empty list (backward compat)."""
    rs = new_resolution_state()
    ms = new_mission_state(mission_id="m1", loop_family="orchestration_kernel", resolution_state=rs)
    base = {
        "schema_version": "kernel_resume.v1",
        "next_iteration": 5,
        "continuity": {
            "latest_refs": {},
            "mission_state": ms.model_dump(mode="json"),
            "resolution_state": rs.model_dump(mode="json"),
            "active_item_id": None,
            # No hitl_exchange_ledger / hitl_consumed_unknown_prompt_count keys
        },
        "hitl": {"hitl_state": "no_prompt"},
        "telemetry": {"llm_contact_count": 0, "prompt_event_count": 0},
        "execution_session": None,
    }
    mem2, _, err = parse_kernel_resume_snapshot(base)
    assert err is None
    assert mem2.continuity.hitl_exchange_ledger == []
    assert mem2.continuity.hitl_consumed_unknown_prompt_count == 0


def test_parse_rejects_hitl_ledger_wrong_type() -> None:
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
            "hitl_exchange_ledger": "not-a-list",
        },
        "hitl": {"hitl_state": "no_prompt"},
        "telemetry": {"llm_contact_count": 0, "prompt_event_count": 0},
        "execution_session": None,
    }
    _, _, err = parse_kernel_resume_snapshot(base)
    assert err == "resume_snapshot_hitl_exchange_ledger_invalid"


def test_roundtrip_hitl_ledger_preserves_bounded_feedback_and_truncation_markers() -> None:
    """Bounded inbound feedback (with _bounds truncation markers) survives round-trip."""
    executor = ExecutionExecutor()
    sm = ExecutionSessionManager(executor=executor)
    sm.start_session(ExecutionSessionStartRequest(run_id="run-bnd", session_id="sess-bnd"))
    lm = LoopMemoryState()
    lm.continuity.mission_state = new_mission_state(mission_id="m1", loop_family="orchestration_kernel")
    lm.continuity.resolution_state = new_resolution_state()
    lm.continuity.hitl_exchange_ledger = [
        {
            "exchange_id": "hitl:p1",
            "prompt_id": "p1",
            "blocking": True,
            "issued_at_iteration": 5,
            "request": {"message": "Q"},
            "response": {
                "choice": "yes",
                "note": "n" * 16_384,  # admission-bounded
                "metadata": {"_truncated": True, "_prefix": "..."},
                "submitted_at_epoch_seconds": 1.0,
                "_bounds": {"note_truncated": True, "metadata_truncated": True},
            },
            "received_at_iteration": 6,
            "consumed_at_iteration": None,
            "status": "answered",
        },
    ]
    snap = build_kernel_resume_snapshot(
        loop_memory=lm, session_manager=sm, session_id="sess-bnd", next_iteration=10
    )
    mem2, _, err = parse_kernel_resume_snapshot(snap)
    assert err is None
    led = mem2.continuity.hitl_exchange_ledger
    assert len(led) == 1
    response = led[0]["response"]
    assert response["_bounds"] == {"note_truncated": True, "metadata_truncated": True}
    assert len(response["note"]) == 16_384
    assert response["metadata"] == {"_truncated": True, "_prefix": "..."}


def test_parse_rejects_hitl_ledger_with_malformed_entry() -> None:
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
            "hitl_exchange_ledger": [{"prompt_id": "p1", "status": "garbage"}],
        },
        "hitl": {"hitl_state": "no_prompt"},
        "telemetry": {"llm_contact_count": 0, "prompt_event_count": 0},
        "execution_session": None,
    }
    _, _, err = parse_kernel_resume_snapshot(base)
    assert err == "resume_snapshot_hitl_exchange_ledger_invalid"


def test_parse_rejects_posthoc_debt_wrong_type() -> None:
    """posthoc_recheck_needed_debt must be a mapping, not a list."""
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
            "posthoc_recheck_needed_debt": "not-a-mapping",
        },
        "hitl": {"hitl_state": "no_prompt"},
        "telemetry": {"llm_contact_count": 0, "prompt_event_count": 0},
        "execution_session": None,
    }
    _, _, err = parse_kernel_resume_snapshot(base)
    assert err == "resume_snapshot_posthoc_recheck_needed_debt_invalid"


# ---------------------------------------------------------------------------
# User-message ledger round-trip
# ---------------------------------------------------------------------------

def test_roundtrip_user_message_ledger_preserves_pending_consumed_deferred() -> None:
    """All three user-message ledger statuses survive the snapshot round-trip."""
    executor = ExecutionExecutor()
    sm = ExecutionSessionManager(executor=executor)
    sm.start_session(ExecutionSessionStartRequest(run_id="run-um", session_id="sess-um"))
    lm = LoopMemoryState()
    lm.continuity.mission_state = new_mission_state(mission_id="m1", loop_family="orchestration_kernel")
    lm.continuity.resolution_state = new_resolution_state()
    lm.continuity.user_message_ledger = [
        {
            "message_id": "user-msg-pending",
            "created_at_epoch_seconds": 100,
            "source": "cli",
            "text": "fix this",
            "metadata": {"item_id": "i-1"},
            "status": "pending",
            "received_at_iteration": 5,
            "consumed_iteration": None,
            "deferred_iteration": None,
            "defer_reason": None,
            "_bounds": {"text_truncated": True},
        },
        {
            "message_id": "user-msg-consumed",
            "created_at_epoch_seconds": 200,
            "source": "viewer",
            "text": "done one",
            "metadata": {},
            "status": "consumed",
            "received_at_iteration": 3,
            "consumed_iteration": 7,
            "deferred_iteration": None,
            "defer_reason": None,
        },
        {
            "message_id": "user-msg-deferred",
            "created_at_epoch_seconds": 300,
            "source": None,
            "text": "wait",
            "metadata": {},
            "status": "deferred",
            "received_at_iteration": 4,
            "consumed_iteration": None,
            "deferred_iteration": 6,
            "defer_reason": "scope X paused",
        },
    ]
    lm.continuity.user_message_consumed_unknown_count = 2

    snap = build_kernel_resume_snapshot(
        loop_memory=lm, session_manager=sm, session_id="sess-um", next_iteration=10,
    )
    mem2, _, err = parse_kernel_resume_snapshot(snap)
    assert err is None
    ledger = mem2.continuity.user_message_ledger
    assert len(ledger) == 3
    assert {e["status"] for e in ledger} == {"pending", "consumed", "deferred"}
    pending = next(e for e in ledger if e["status"] == "pending")
    assert pending["_bounds"] == {"text_truncated": True}
    deferred = next(e for e in ledger if e["status"] == "deferred")
    assert deferred["defer_reason"] == "scope X paused"
    assert mem2.continuity.user_message_consumed_unknown_count == 2


def test_roundtrip_user_message_ledger_absent_defaults_to_empty() -> None:
    """Old snapshots without the user_message_ledger key restore to empty."""
    rs = new_resolution_state()
    ms = new_mission_state(mission_id="m1", loop_family="orchestration_kernel", resolution_state=rs)
    base = {
        "schema_version": "kernel_resume.v1",
        "next_iteration": 5,
        "continuity": {
            "latest_refs": {},
            "mission_state": ms.model_dump(mode="json"),
            "resolution_state": rs.model_dump(mode="json"),
            "active_item_id": None,
        },
        "hitl": {"hitl_state": "no_prompt"},
        "telemetry": {"llm_contact_count": 0, "prompt_event_count": 0},
        "execution_session": None,
    }
    mem2, _, err = parse_kernel_resume_snapshot(base)
    assert err is None
    assert mem2.continuity.user_message_ledger == []
    assert mem2.continuity.user_message_consumed_unknown_count == 0


def test_parse_rejects_user_message_ledger_wrong_type() -> None:
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
            "user_message_ledger": "not-a-list",
        },
        "hitl": {"hitl_state": "no_prompt"},
        "telemetry": {"llm_contact_count": 0, "prompt_event_count": 0},
        "execution_session": None,
    }
    _, _, err = parse_kernel_resume_snapshot(base)
    assert err == "resume_snapshot_user_message_ledger_invalid"


def test_parse_rejects_user_message_ledger_with_malformed_entry() -> None:
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
            "user_message_ledger": [{"text": "no message_id", "status": "pending"}],
        },
        "hitl": {"hitl_state": "no_prompt"},
        "telemetry": {"llm_contact_count": 0, "prompt_event_count": 0},
        "execution_session": None,
    }
    _, _, err = parse_kernel_resume_snapshot(base)
    assert err == "resume_snapshot_user_message_ledger_invalid"


# ---------------------------------------------------------------------------
# pending_agent_hydration round-trip (agent-authored hydrate_next)
# ---------------------------------------------------------------------------

def test_roundtrip_pending_agent_hydration_preserves_pending_record() -> None:
    """A pending hydrate_next record survives the snapshot round-trip."""
    executor = ExecutionExecutor()
    sm = ExecutionSessionManager(executor=executor)
    sm.start_session(ExecutionSessionStartRequest(run_id="run-hn", session_id="sess-hn"))
    lm = LoopMemoryState()
    lm.continuity.mission_state = new_mission_state(mission_id="m1", loop_family="orchestration_kernel")
    lm.continuity.resolution_state = new_resolution_state()
    lm.continuity.pending_agent_hydration = {
        "source_turn_index": 41,
        "requested_refs": ["@result.revision_ref"],
        "resolved_refs": ["transcript_edit:working:rev:0001"],
        "reason": "inspect saved payload",
        "errors": [],
        "hydrated_results": None,
        "hydration_errors": None,
        "status": "pending",
        "surfaced_iteration": None,
    }

    snap = build_kernel_resume_snapshot(
        loop_memory=lm, session_manager=sm, session_id="sess-hn", next_iteration=42,
    )
    mem2, _, err = parse_kernel_resume_snapshot(snap)
    assert err is None
    rec = mem2.continuity.pending_agent_hydration
    assert rec is not None
    assert rec["status"] == "pending"
    assert rec["source_turn_index"] == 41
    assert rec["resolved_refs"] == ["transcript_edit:working:rev:0001"]


def test_roundtrip_pending_agent_hydration_surfaced_does_not_re_surface_forever() -> None:
    """A surfaced record round-trips; orchestrator drops it on next iter, not the parser."""
    executor = ExecutionExecutor()
    sm = ExecutionSessionManager(executor=executor)
    sm.start_session(ExecutionSessionStartRequest(run_id="run-hn", session_id="sess-hn"))
    lm = LoopMemoryState()
    lm.continuity.mission_state = new_mission_state(mission_id="m1", loop_family="orchestration_kernel")
    lm.continuity.resolution_state = new_resolution_state()
    lm.continuity.pending_agent_hydration = {
        "source_turn_index": 41,
        "requested_refs": ["@result.revision_ref"],
        "resolved_refs": ["r-1"],
        "reason": None,
        "errors": [],
        "hydrated_results": [{"ref_id": "r-1", "kind": "transcript_edit_draft", "payload": {}}],
        "hydration_errors": None,
        "status": "surfaced",
        "surfaced_iteration": 42,
    }

    snap = build_kernel_resume_snapshot(
        loop_memory=lm, session_manager=sm, session_id="sess-hn", next_iteration=43,
    )
    mem2, _, err = parse_kernel_resume_snapshot(snap)
    assert err is None
    rec = mem2.continuity.pending_agent_hydration
    assert rec is not None
    assert rec["status"] == "surfaced"
    assert rec["surfaced_iteration"] == 42


def test_roundtrip_pending_agent_hydration_absent_defaults_to_none() -> None:
    """Old snapshots without the field restore to None (no pending request)."""
    rs = new_resolution_state()
    ms = new_mission_state(mission_id="m1", loop_family="orchestration_kernel", resolution_state=rs)
    base = {
        "schema_version": "kernel_resume.v1",
        "next_iteration": 5,
        "continuity": {
            "latest_refs": {},
            "mission_state": ms.model_dump(mode="json"),
            "resolution_state": rs.model_dump(mode="json"),
            "active_item_id": None,
        },
        "hitl": {"hitl_state": "no_prompt"},
        "telemetry": {"llm_contact_count": 0, "prompt_event_count": 0},
        "execution_session": None,
    }
    mem2, _, err = parse_kernel_resume_snapshot(base)
    assert err is None
    assert mem2.continuity.pending_agent_hydration is None


def test_parse_rejects_pending_agent_hydration_wrong_type() -> None:
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
            "pending_agent_hydration": "not-a-dict",
        },
        "hitl": {"hitl_state": "no_prompt"},
        "telemetry": {"llm_contact_count": 0, "prompt_event_count": 0},
        "execution_session": None,
    }
    _, _, err = parse_kernel_resume_snapshot(base)
    assert err == "resume_snapshot_pending_agent_hydration_invalid"


def test_parse_rejects_pending_agent_hydration_unknown_status() -> None:
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
            "pending_agent_hydration": {
                "source_turn_index": 1,
                "requested_refs": ["a"],
                "resolved_refs": ["a"],
                "status": "weird",
            },
        },
        "hitl": {"hitl_state": "no_prompt"},
        "telemetry": {"llm_contact_count": 0, "prompt_event_count": 0},
        "execution_session": None,
    }
    _, _, err = parse_kernel_resume_snapshot(base)
    assert err == "resume_snapshot_pending_agent_hydration_invalid"
