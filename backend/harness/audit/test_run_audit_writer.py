from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from harness.audit.run_audit_writer import RunAuditWriter, _extract_tool_sequence
from harness.runtime.orchestration.contracts import ActionPlan


# ---------------------------------------------------------------------------
# RunAuditWriter – no-op path (run_dir=None)
# ---------------------------------------------------------------------------


def test_run_audit_writer_noop_when_no_dir() -> None:
    writer = RunAuditWriter(None)
    writer.observe_llm_io({"turn_index": 1, "raw_prompt_text": "hello"})
    writer.finalize(
        terminal_class="completed",
        reason_code="complete_run",
        iterations=1,
        latest_refs={},
        trace_events=[],
        run_id="test-run",
    )
    # No error — nothing was written, nothing to assert beyond no exception.


def test_run_audit_writer_noop_buffers_nothing_when_no_dir() -> None:
    writer = RunAuditWriter(None)
    writer.observe_llm_io({"turn_index": 1})
    writer.observe_llm_io({"turn_index": 2})
    assert writer._turns == []  # buffer stays empty when dir is None


# ---------------------------------------------------------------------------
# RunAuditWriter – happy path
# ---------------------------------------------------------------------------


def test_on_llm_io_buffers_turns(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "raw_prompt_text": "prompt1"})
    writer.observe_llm_io({"turn_index": 2, "raw_prompt_text": "prompt2"})
    assert len(writer._turns) == 2
    assert writer._turns[0]["turn_index"] == 1
    assert writer._turns[1]["raw_prompt_text"] == "prompt2"


def test_on_llm_io_writes_turn_file_immediately(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({
        "turn_index": 1,
        "raw_prompt_text": "prompt1",
        "repair_records": [],
    })

    turn_path = tmp_path / "run1" / "audit" / "turn_0001.json"
    assert turn_path.exists()
    turn = json.loads(turn_path.read_text())
    assert turn["raw_prompt_text"] == "prompt1"


def test_on_llm_io_preserves_identity_fields_for_turn_lineage(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io(
        {
            "turn_index": 3,
            "iteration_index": 3,
            "session_id": "sess-1",
            "request_id": "req-1",
            "prompt_event_id": "req-1:iter3:kernel_llm",
            "prompt_mode": "resume",
        }
    )
    writer.finalize(terminal_class="completed", reason_code="done", iterations=3, latest_refs={}, trace_events=[])

    turn = json.loads((tmp_path / "run1" / "audit" / "turn_0003.json").read_text())
    assert turn["turn_index"] == 3
    assert turn["iteration_index"] == 3
    assert turn["session_id"] == "sess-1"
    assert turn["request_id"] == "req-1"
    assert turn["prompt_event_id"] == "req-1:iter3:kernel_llm"
    assert turn["prompt_mode"] == "resume"


def test_on_llm_io_normalizes_non_json_payloads(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({
        "turn_index": 1,
        "repair_attempted": True,
        "repair_records": [
            {
                "repair_prompt_text": "prompt",
                "repair_raw_response_text": "response",
                "repair_parse_ok": True,
                "repair_parse_reason_code": None,
                "repair_parsed_action_plan": ActionPlan(
                    action_type="noop",
                    continuity_journal_entry={"kind": "test"},
                ),
            }
        ],
    })

    turn = json.loads((tmp_path / "run1" / "audit" / "turn_0001.json").read_text())
    rec = turn["repair_records"][0]
    assert rec["repair_parsed_action_plan"]["action_type"] == "noop"
    assert rec["repair_parsed_action_plan"]["continuity_journal_entry"] == {"kind": "test"}


def test_finalize_writes_turn_files(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "parse_ok": True, "raw_prompt_text": "p1"})
    writer.observe_llm_io({"turn_index": 2, "parse_ok": False, "raw_prompt_text": "p2"})
    writer.finalize(terminal_class="completed", reason_code="done", iterations=2, latest_refs={}, trace_events=[])

    audit_dir = tmp_path / "run1" / "audit"
    assert (audit_dir / "turn_0001.json").exists()
    assert (audit_dir / "turn_0002.json").exists()

    t1 = json.loads((audit_dir / "turn_0001.json").read_text())
    assert t1["parse_ok"] is True
    assert t1["raw_prompt_text"] == "p1"


def test_finalize_writes_index(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "repair_attempted": False})
    writer.observe_llm_io({"turn_index": 2, "repair_attempted": True})
    writer.finalize(
        terminal_class="failed",
        reason_code="model_call_failed",
        iterations=2,
        latest_refs={"doc": "ref://doc"},
        trace_events=[],
        run_id="r-123",
    )

    idx = json.loads((tmp_path / "run1" / "audit" / "index.json").read_text())
    assert idx["run_id"] == "r-123"
    assert idx["terminal_class"] == "failed"
    assert idx["reason_code"] == "model_call_failed"
    assert idx["turn_count"] == 2
    assert idx["repairs_attempted"] == 1
    assert idx["latest_refs"] == {"doc": "ref://doc"}


def test_finalize_writes_review_md(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1})
    trace = [
        {"event_kind": "tool_execution", "iteration_index": 1,
         "payload": {"action_type": "my_tool", "execution_state": "executed"}},
    ]
    writer.finalize(
        terminal_class="completed", reason_code="complete_run",
        iterations=1, latest_refs={"x": "y"}, trace_events=trace,
    )

    review = (tmp_path / "run1" / "audit" / "review.md").read_text()
    assert "completed" in review
    assert "complete_run" in review
    assert "my_tool" in review
    assert "executed" in review
    assert "`x`" in review


def test_finalize_noop_on_error_does_not_raise(tmp_path: Path) -> None:
    """finalize must not propagate exceptions even if directory creation fails."""
    writer = RunAuditWriter(tmp_path / "run1")
    writer._dir = Path("/nonexistent_root_xyz/audit")  # force an OS error
    writer.observe_llm_io({"turn_index": 1})
    writer.finalize(terminal_class="completed", reason_code="done", iterations=1, latest_refs={}, trace_events=[])
    # Asserts that no exception propagated.


# ---------------------------------------------------------------------------
# _extract_tool_sequence
# ---------------------------------------------------------------------------


def test_extract_tool_sequence_returns_ordered_entries() -> None:
    events: list[dict[str, Any]] = [
        {"event_kind": "iteration", "iteration_index": 1, "payload": {}},
        {"event_kind": "tool_execution", "iteration_index": 1,
         "payload": {"action_type": "alpha", "execution_state": "executed"}},
        {"event_kind": "tool_execution", "iteration_index": 2,
         "payload": {"action_type": "beta", "execution_state": "refused"}},
    ]
    seq = _extract_tool_sequence(events)
    assert len(seq) == 2
    assert "alpha" in seq[0]
    assert "executed" in seq[0]
    assert "beta" in seq[1]


def test_extract_tool_sequence_skips_non_tool_events() -> None:
    events: list[dict[str, Any]] = [
        {"event_kind": "request_start", "payload": {}},
        {"event_kind": "terminal_outcome", "iteration_index": 1,
         "payload": {"action_type": "x", "execution_state": "executed"}},
    ]
    seq = _extract_tool_sequence(events)
    assert seq == []


def test_extract_tool_sequence_empty_on_no_events() -> None:
    assert _extract_tool_sequence([]) == []


# ---------------------------------------------------------------------------
# Repair I/O capture
# ---------------------------------------------------------------------------


def test_repair_records_written_in_turn_file(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({
        "turn_index": 1,
        "parse_ok": False,
        "parse_reason_code": "invalid_model_action_json",
        "repair_attempted": True,
        "repair_records": [
            {
                "repair_prompt_text": "original prompt\n\n---\nPrevious response failed",
                "repair_raw_response_text": '{"action_type": "noop"}',
                "repair_parse_ok": True,
                "repair_parse_reason_code": None,
                "repair_parsed_action_plan": {"action_type": "noop"},
            }
        ],
    })
    writer.finalize(terminal_class="completed", reason_code="done", iterations=1, latest_refs={}, trace_events=[])

    turn = json.loads((tmp_path / "run1" / "audit" / "turn_0001.json").read_text())
    assert turn["repair_attempted"] is True
    assert len(turn["repair_records"]) == 1
    rec = turn["repair_records"][0]
    assert "repair_prompt_text" in rec
    assert rec["repair_parse_ok"] is True
    assert rec["repair_parse_reason_code"] is None
    assert rec["repair_parsed_action_plan"]["action_type"] == "noop"


def test_repair_failed_written_in_turn_file(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({
        "turn_index": 1,
        "parse_ok": False,
        "repair_attempted": True,
        "repair_records": [
            {
                "repair_prompt_text": "prompt",
                "repair_raw_response_text": "bad json",
                "repair_parse_ok": False,
                "repair_parse_reason_code": "invalid_model_action_json",
                "repair_parsed_action_plan": None,
            }
        ],
    })
    writer.finalize(terminal_class="failed", reason_code="invalid_model_action_json", iterations=1, latest_refs={}, trace_events=[])

    turn = json.loads((tmp_path / "run1" / "audit" / "turn_0001.json").read_text())
    assert turn["repair_attempted"] is True
    rec = turn["repair_records"][0]
    assert rec["repair_parse_ok"] is False
    assert rec["repair_parse_reason_code"] == "invalid_model_action_json"
    assert rec["repair_parsed_action_plan"] is None


# ---------------------------------------------------------------------------
# Tool request / result capture
# ---------------------------------------------------------------------------


def test_tool_request_and_result_written_via_turn_completion_observer(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 2, "parse_ok": True})
    writer.observe_turn_completed({
        "turn_index": 2,
        "tool_request": {"action_type": "my_tool", "action_inputs": {"x": 1}, "skip_execution": False,
                         "wait_for_human": False, "complete_run": False, "rationale": None, "idempotency_key": "ik"},
        "tool_result_raw": {"execution_state": "executed", "outputs": {"y": 2}, "artifact_refs": ["ref://a"], "refusal": None},
        "mission_state_after": None,
        "resolution_state_after": None,
        "latest_refs_after": {"ref_a": "artifact://a"},
        "state_patch_feedback": {},
        "terminal_decision": None,
    })
    writer.finalize(terminal_class="completed", reason_code="done", iterations=2, latest_refs={}, trace_events=[])

    turn = json.loads((tmp_path / "run1" / "audit" / "turn_0002.json").read_text())
    assert turn["tool_request"]["action_type"] == "my_tool"
    assert turn["tool_result_raw"]["execution_state"] == "executed"
    assert turn["tool_result_raw"]["outputs"] == {"y": 2}
    assert turn["latest_refs_after"] == {"ref_a": "artifact://a"}


def test_on_turn_completed_writes_turn_file_immediately(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 2, "parse_ok": True})
    writer.observe_turn_completed({
        "turn_index": 2,
        "tool_request": {"action_type": "my_tool", "action_inputs": {}},
        "tool_result_raw": {"execution_state": "executed"},
        "mission_state_after": {"mission_id": "m1"},
        "resolution_state_after": {"items": []},
        "latest_refs_after": {"ref_a": "artifact://a"},
        "state_patch_feedback": {"outcome": "applied"},
        "terminal_decision": None,
    })

    turn = json.loads((tmp_path / "run1" / "audit" / "turn_0002.json").read_text())
    assert turn["mission_state_after"]["mission_id"] == "m1"
    assert turn["state_patch_feedback"]["outcome"] == "applied"


def test_finalize_failure_does_not_erase_earlier_turn_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "raw_prompt_text": "p1"})
    writer.observe_llm_io({"turn_index": 2, "raw_prompt_text": "p2"})

    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(writer, "_write_index", boom)

    writer.finalize(
        terminal_class="failed",
        reason_code="runner_exception",
        iterations=2,
        latest_refs={},
        trace_events=[],
    )

    audit_dir = tmp_path / "run1" / "audit"
    assert (audit_dir / "turn_0001.json").exists()
    assert (audit_dir / "turn_0002.json").exists()
    assert (audit_dir / "events.jsonl").exists()


def test_on_turn_completed_without_prior_llm_io_creates_stub(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    # No on_llm_io call — turn_completed arrives orphaned (e.g. choose_action was skipped).
    writer.observe_turn_completed({
        "turn_index": 5,
        "tool_request": None,
        "tool_result_raw": None,
        "mission_state_after": None,
        "resolution_state_after": None,
        "latest_refs_after": {},
        "state_patch_feedback": {},
        "terminal_decision": "complete_run",
    })
    writer.finalize(terminal_class="completed", reason_code="done", iterations=5, latest_refs={}, trace_events=[])

    turn = json.loads((tmp_path / "run1" / "audit" / "turn_0005.json").read_text())
    assert turn["turn_index"] == 5
    assert turn["terminal_decision"] == "complete_run"


# ---------------------------------------------------------------------------
# State snapshots
# ---------------------------------------------------------------------------


def test_state_snapshots_before_written(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({
        "turn_index": 1,
        "parse_ok": True,
        "mission_state_before": {"mission_id": "m1"},
        "resolution_state_before": {"items": []},
        "latest_refs_before": {"prior_ref": "artifact://old"},
    })
    writer.finalize(terminal_class="completed", reason_code="done", iterations=1, latest_refs={}, trace_events=[])

    turn = json.loads((tmp_path / "run1" / "audit" / "turn_0001.json").read_text())
    assert turn["mission_state_before"]["mission_id"] == "m1"
    assert turn["latest_refs_before"] == {"prior_ref": "artifact://old"}


def test_state_snapshots_after_written_via_turn_completion_observer(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "parse_ok": True, "latest_refs_before": {}})
    writer.observe_turn_completed({
        "turn_index": 1,
        "tool_request": None,
        "tool_result_raw": None,
        "mission_state_after": {"mission_id": "m1", "version": 2},
        "resolution_state_after": {"items": ["x"]},
        "latest_refs_after": {"new_ref": "artifact://new"},
        "state_patch_feedback": {"outcome": "applied"},
        "terminal_decision": None,
    })
    writer.finalize(terminal_class="completed", reason_code="done", iterations=1, latest_refs={}, trace_events=[])

    turn = json.loads((tmp_path / "run1" / "audit" / "turn_0001.json").read_text())
    assert turn["mission_state_after"]["mission_id"] == "m1"
    assert turn["resolution_state_after"]["items"] == ["x"]
    assert turn["latest_refs_after"]["new_ref"] == "artifact://new"
    assert turn["state_patch_feedback"]["outcome"] == "applied"


# ---------------------------------------------------------------------------
# Failure-path audit
# ---------------------------------------------------------------------------


def test_failed_run_still_writes_turn_with_raw_llm_io(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({
        "turn_index": 1,
        "raw_prompt_text": "the prompt",
        "raw_llm_response_text": "not-json",
        "parse_ok": False,
        "parse_reason_code": "invalid_model_action_json",
        "repair_attempted": False,
        "repair_records": [],
        "mission_state_before": {"mission_id": "m-fail"},
        "resolution_state_before": None,
        "latest_refs_before": {},
    })
    writer.finalize(
        terminal_class="failed",
        reason_code="invalid_model_action_json",
        iterations=1,
        latest_refs={},
        trace_events=[],
    )

    turn = json.loads((tmp_path / "run1" / "audit" / "turn_0001.json").read_text())
    assert turn["raw_prompt_text"] == "the prompt"
    assert turn["parse_ok"] is False
    assert turn["mission_state_before"]["mission_id"] == "m-fail"


# ---------------------------------------------------------------------------
# Review artifact enrichment
# ---------------------------------------------------------------------------


def test_review_md_includes_per_turn_tool_summary(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "parse_ok": True, "latest_refs_before": {}, "repair_attempted": False, "repair_records": []})
    writer.observe_turn_completed({
        "turn_index": 1,
        "tool_request": {"action_type": "fetch_doc", "action_inputs": {}, "skip_execution": False,
                         "wait_for_human": False, "complete_run": False, "rationale": None, "idempotency_key": ""},
        "tool_result_raw": {"execution_state": "executed", "outputs": {}, "artifact_refs": [], "refusal": None},
        "mission_state_after": None,
        "resolution_state_after": None,
        "latest_refs_after": {"doc": "artifact://d1"},
        "state_patch_feedback": {},
        "terminal_decision": None,
    })
    writer.finalize(terminal_class="completed", reason_code="done", iterations=1, latest_refs={}, trace_events=[])

    review = (tmp_path / "run1" / "audit" / "review.md").read_text()
    assert "fetch_doc" in review
    assert "refs+" in review  # new ref appeared


def test_review_md_flags_repairs(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "parse_ok": False, "repair_attempted": True,
                      "repair_records": [{"repair_parse_ok": True}],
                      "latest_refs_before": {}})
    writer.observe_turn_completed({
        "turn_index": 1, "tool_request": None, "tool_result_raw": None,
        "mission_state_after": None, "resolution_state_after": None,
        "latest_refs_after": {}, "state_patch_feedback": {}, "terminal_decision": "complete_run",
    })
    writer.finalize(terminal_class="completed", reason_code="done", iterations=1, latest_refs={}, trace_events=[])

    review = (tmp_path / "run1" / "audit" / "review.md").read_text()
    assert "[repaired]" in review
    assert "[complete_run]" in review


def test_review_md_includes_duration_and_final_artifact_posture(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io(
        {
            "turn_index": 1,
            "parse_ok": True,
            "started_at_epoch_seconds": 10.0,
            "finished_at_epoch_seconds": 16.0,
            "latest_refs_before": {},
        }
    )
    writer.observe_turn_completed(
        {
            "turn_index": 1,
            "tool_request": {
                "action_type": "save_workspace_artifact",
                "action_inputs": {},
                "skip_execution": False,
                "wait_for_human": False,
                "complete_run": False,
                "rationale": None,
                "idempotency_key": "",
            },
            "tool_result_raw": {
                "execution_state": "executed",
                "outputs": {},
                "artifact_refs": ["transcript_edit:working:rev:0001"],
                "refusal": None,
            },
            "mission_state_after": None,
            "resolution_state_after": None,
            "latest_refs_after": {"transcript_edit:working": "transcript_edit:working:rev:0001"},
            "state_patch_feedback": {},
            "terminal_decision": None,
        }
    )
    writer.finalize(terminal_class="completed", reason_code="done", iterations=1, latest_refs={}, trace_events=[])

    review = (tmp_path / "run1" / "audit" / "review.md").read_text()
    assert "**Total observed duration:** 6.0s" in review
    assert "**Final artifact posture:** `working`" in review


def test_review_md_omits_final_artifact_posture_for_failed_save_attempt(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io(
        {
            "turn_index": 1,
            "parse_ok": True,
            "started_at_epoch_seconds": 10.0,
            "finished_at_epoch_seconds": 12.0,
            "latest_refs_before": {},
        }
    )
    writer.observe_turn_completed(
        {
            "turn_index": 1,
            "tool_request": {
                "action_type": "save_workspace_artifact",
                "action_inputs": {},
                "skip_execution": False,
                "wait_for_human": False,
                "complete_run": False,
                "rationale": None,
                "idempotency_key": "",
            },
            "tool_result_raw": {
                "execution_state": "refused",
                "outputs": {},
                "artifact_refs": [],
                "refusal": {"reason_code": "write_blocked"},
            },
            "mission_state_after": None,
            "resolution_state_after": None,
            "latest_refs_after": {"older": "artifact://older"},
            "state_patch_feedback": {},
            "terminal_decision": None,
        }
    )
    writer.finalize(terminal_class="failed", reason_code="write_blocked", iterations=1, latest_refs={}, trace_events=[])

    review = (tmp_path / "run1" / "audit" / "review.md").read_text()
    assert "**Total observed duration:** 2.0s" in review
    assert "**Final artifact posture:**" not in review


# ---------------------------------------------------------------------------
# image_evidence in tool_result_raw
# ---------------------------------------------------------------------------


def test_image_evidence_persisted_in_tool_result_raw(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "parse_ok": True})
    writer.observe_turn_completed({
        "turn_index": 1,
        "tool_request": {"action_type": "hydrate_artifact_refs"},
        "tool_result_raw": {
            "execution_state": "executed",
            "outputs": {},
            "artifact_refs": [],
            "refusal": None,
            "image_evidence": [
                {"ref_id": "image:assoc:tx-1:original", "media_type": "image/jpeg", "data": "base64data=="},
                {"ref_id": "image:assoc:tx-1:processed", "media_type": "image/jpeg", "data": "base64proc=="},
            ],
        },
        "mission_state_after": None,
        "resolution_state_after": None,
        "latest_refs_after": {},
        "state_patch_feedback": {},
        "terminal_decision": None,
    })
    writer.finalize(terminal_class="completed", reason_code="done", iterations=1, latest_refs={}, trace_events=[])

    turn = json.loads((tmp_path / "run1" / "audit" / "turn_0001.json").read_text())
    evidence = turn["tool_result_raw"]["image_evidence"]
    assert len(evidence) == 2
    assert evidence[0]["ref_id"] == "image:assoc:tx-1:original"
    assert evidence[1]["ref_id"] == "image:assoc:tx-1:processed"


def test_image_evidence_empty_list_when_absent(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "parse_ok": True})
    writer.observe_turn_completed({
        "turn_index": 1,
        "tool_request": {"action_type": "save_workspace_artifact"},
        "tool_result_raw": {
            "execution_state": "executed",
            "outputs": {},
            "artifact_refs": ["transcript_edit:working"],
            "refusal": None,
            "image_evidence": [],
        },
        "mission_state_after": None,
        "resolution_state_after": None,
        "latest_refs_after": {},
        "state_patch_feedback": {},
        "terminal_decision": None,
    })
    writer.finalize(terminal_class="completed", reason_code="done", iterations=1, latest_refs={}, trace_events=[])

    turn = json.loads((tmp_path / "run1" / "audit" / "turn_0001.json").read_text())
    assert turn["tool_result_raw"]["image_evidence"] == []

