from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.review.tool import (
    build_multi_run_review,
    build_multi_run_review_bundle,
    build_multi_run_review_bundle_from_paths,
    build_multi_run_review_from_paths,
    build_single_run_review,
    build_single_run_review_bundle,
    build_single_run_review_bundle_from_path,
    build_single_run_review_from_path,
    maybe_write_review_output,
)


def _controller_payload() -> dict:
    return {
        "controller_transcript": {
            "events": [
                {
                    "event_type": "run_header",
                    "detail": "controller_run_started",
                    "timestamp_epoch_seconds": 10,
                    "payload": {"request_id": "request-tool-1", "session_id": "request-tool-1::run-tool-1"},
                },
                {
                    "event_type": "kernel_step_result",
                    "detail": "executed",
                    "timestamp_epoch_seconds": 11,
                    "payload": {
                        "iteration": 1,
                        "action_type": "declare_done",
                        "terminal": {
                            "terminal_outcome": "SUCCESS",
                            "stop_reason": "completed",
                            "success": True,
                            "reason_code": "done_verified",
                        },
                    },
                },
            ]
        },
        "run_artifact": {
            "run_id": "run-tool-1",
            "request_id": "request-tool-1",
            "session_id": "request-tool-1::run-tool-1",
            "created_at_epoch_seconds": 10,
            "steps": [],
        },
    }


def _tx_payload() -> dict:
    return {
        "run_id": "tx-tool-1",
        "status": "waiting_feedback",
        "request": {"mode": "audit_then_repair", "trigger": "manual"},
        "snapshot": {
            "run_id": "tx-tool-1",
            "status": "waiting_feedback",
            "reason_code": "tx_agent_closure_requirements_unresolved",
            "iterations": 3,
            "session_id": "tx-tool-session-1",
            "latest_refs": {"tx_source_transcript_ref": {"artifact_path": "artifact://source"}},
            "progress_log": [
                {"timestamp_epoch_seconds": 100, "iteration": 0, "phase": "starting"},
                {
                    "timestamp_epoch_seconds": 101,
                    "iteration": 1,
                    "phase": "audit_result",
                    "detail": {"decision_ledger": {"summary": {"unresolved_count": 2}}},
                },
            ],
            "critical_events": [],
            "runtime_hitl_state": {
                "blocker_registry": {
                    "active_blocker_id": "blocker:range",
                    "counts": {"waiting_feedback": 1, "total": 1},
                    "rows": [
                        {
                            "blocker_id": "blocker:range",
                            "decision_key": "range",
                            "state": "waiting_feedback",
                            "linked_prompt_id": "hitl_range_3",
                        }
                    ],
                    "history": [],
                },
                "hitl_lifecycle_log": [],
            },
            "terminal_summary": {
                "terminal_classification": "blocked_waiting_feedback",
                "human_feedback_pending": True,
                "decision_ledger": {"summary": {"unresolved_count": 2}},
            },
        },
    }


def _mission_payload() -> dict:
    return {
        "mission_runtime": {
            "mission_id": "mission-tool-1",
            "objective": "cross-mode story",
            "request_id": "mission-request-tool-1",
            "active_mode": "deed_to_ir",
            "mode_history": ["deed_to_ir", "transcript_edit", "deed_to_ir"],
            "transition_history": [
                {
                    "prior_mode": "deed_to_ir",
                    "next_mode": "transcript_edit",
                    "reason": "handoff_to_review",
                    "status": "applied",
                    "order_anchor": 1,
                    "timestamp_epoch_seconds": 101,
                    "handed_forward_artifact_refs": ["artifact://handoff/1"],
                },
                {
                    "prior_mode": "transcript_edit",
                    "next_mode": "deed_to_ir",
                    "reason": "review_complete",
                    "status": "applied",
                    "order_anchor": 2,
                    "timestamp_epoch_seconds": 103,
                    "handed_forward_artifact_refs": ["artifact://handoff/2"],
                },
            ],
            "cycles": [
                {
                    "cycle_index": 1,
                    "executed_mode": "deed_to_ir",
                    "resulting_active_mode": "transcript_edit",
                    "summary": "deed cycle",
                    "timestamp_epoch_seconds": 100,
                    "transition": {
                        "prior_mode": "deed_to_ir",
                        "next_mode": "transcript_edit",
                        "reason": "handoff_to_review",
                        "status": "applied",
                        "order_anchor": 1,
                        "timestamp_epoch_seconds": 101,
                        "handed_forward_artifact_refs": ["artifact://handoff/1"],
                    },
                },
                {
                    "cycle_index": 2,
                    "executed_mode": "transcript_edit",
                    "resulting_active_mode": "deed_to_ir",
                    "summary": "review cycle",
                    "timestamp_epoch_seconds": 102,
                    "transition": {
                        "prior_mode": "transcript_edit",
                        "next_mode": "deed_to_ir",
                        "reason": "review_complete",
                        "status": "applied",
                        "order_anchor": 2,
                        "timestamp_epoch_seconds": 103,
                        "handed_forward_artifact_refs": ["artifact://handoff/2"],
                    },
                },
            ],
            "mission_status": {"terminal": False, "terminal_class": "in_progress", "reason_code": None},
            "resumability_summary": {"resumable": True, "resume_reason": "ready_for_deed_resume"},
            "blocker_posture_summary": {"waiting_human": False, "open_blocker_count": 0},
            "verification_posture_summary": {"status": "closure_clear", "last_verification_kind": "tx_ledger"},
            "created_at_epoch_seconds": 100,
            "updated_at_epoch_seconds": 103,
            "cycle_index": 2,
            "high_signal_artifact_refs": ["artifact://handoff/1", "artifact://handoff/2"],
        }
    }


def test_single_controller_run_review_flow() -> None:
    output = build_single_run_review(payload=_controller_payload())
    assert output["trace"]["loop_family"] == "controller_kernel"
    assert output["run_state"]["loop_family"] == "controller_kernel"
    assert output["review"]["terminal_class"] == "completed"
    assert output["review"]["event_count"] >= 1


def test_single_transcript_edit_run_review_flow() -> None:
    output = build_single_run_review(payload=_tx_payload())
    assert output["trace"]["loop_family"] == "transcript_edit"
    assert output["run_state"]["loop_family"] == "transcript_edit"
    assert output["review"]["terminal_class"] == "waiting_human"
    assert output["review"]["waiting_human_present"] is True


def test_single_mission_runtime_run_review_flow() -> None:
    output = build_single_run_review(payload=_mission_payload())
    assert output["trace"]["loop_family"] == "mission_runtime"
    assert output["run_state"]["loop_family"] == "mission_runtime"
    assert output["review"]["active_mode"] == "deed_to_ir"
    assert output["review"]["transition_count"] == 2
    assert output["review"]["mode_history"] == ["deed_to_ir", "transcript_edit", "deed_to_ir"]


def test_multi_run_aggregate_review_flow() -> None:
    output = build_multi_run_review(payloads=[_controller_payload(), _tx_payload()])
    assert output["run_count"] == 2
    assert len(output["runs"]) == 2
    aggregate = output["aggregate"]
    assert aggregate["loop_family_distribution"]["controller_kernel"] == 1
    assert aggregate["loop_family_distribution"]["transcript_edit"] == 1
    assert aggregate["terminal_class_distribution"]["completed"] == 1
    assert aggregate["terminal_class_distribution"]["waiting_human"] == 1


def test_explicit_loop_family_path_and_ambiguous_error() -> None:
    output = build_single_run_review(payload=_controller_payload(), loop_family="controller_kernel")
    assert output["trace"]["loop_family"] == "controller_kernel"

    ambiguous = _controller_payload()
    ambiguous["snapshot"] = {"run_id": "tx-like"}
    with pytest.raises(ValueError, match="ambiguous canonical trace payload"):
        build_single_run_review(payload=ambiguous)


def test_unsupported_payload_fails_clearly() -> None:
    with pytest.raises(ValueError, match="unsupported canonical trace payload shape"):
        build_single_run_review(payload={})
    with pytest.raises(ValueError, match="unsupported loop_family"):
        build_single_run_review(payload=_controller_payload(), loop_family="unknown")


def test_path_and_output_write_flow_is_json_friendly_and_deterministic(tmp_path: Path) -> None:
    controller_path = tmp_path / "controller_payload.json"
    controller_path.write_text(json.dumps(_controller_payload()), encoding="utf-8")

    first = build_single_run_review_from_path(payload_path=str(controller_path))
    second = build_single_run_review_from_path(payload_path=str(controller_path))
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    tx_path = tmp_path / "tx_payload.json"
    tx_path.write_text(json.dumps(_tx_payload()), encoding="utf-8")
    multi = build_multi_run_review_from_paths(payload_paths=[str(controller_path), str(tx_path)])
    out_path = tmp_path / "review_output.json"
    maybe_write_review_output(review_output=multi, output_path=str(out_path))
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["run_count"] == 2
    assert "aggregate" in loaded


def test_single_run_review_bundle_shape_and_metadata() -> None:
    bundle = build_single_run_review_bundle(payload=_controller_payload())
    assert bundle["metadata"]["artifact_version"] == "review_bundle.v1"
    assert bundle["metadata"]["mode"] == "single_run"
    assert bundle["metadata"]["loop_family"] == "controller_kernel"
    assert bundle["metadata"]["run_count"] == 1
    assert isinstance(bundle["metadata"]["generated_at"], str)
    assert len(bundle["runs"]) == 1
    run = bundle["runs"][0]
    assert sorted(run.keys()) == ["input", "loop_family", "review", "run_id", "run_state", "trace"]
    assert run["trace"]["loop_family"] == "controller_kernel"
    assert run["run_state"]["loop_family"] == "controller_kernel"
    assert run["review"]["loop_family"] == "controller_kernel"


def test_multi_run_review_bundle_includes_aggregate_and_mixed_loop_family() -> None:
    bundle = build_multi_run_review_bundle(payloads=[_controller_payload(), _tx_payload()])
    assert bundle["metadata"]["mode"] == "multi_run"
    assert bundle["metadata"]["loop_family"] == "mixed"
    assert bundle["metadata"]["run_count"] == 2
    assert len(bundle["runs"]) == 2
    aggregate = bundle["aggregate"]
    assert aggregate["loop_family_distribution"]["controller_kernel"] == 1
    assert aggregate["loop_family_distribution"]["transcript_edit"] == 1
    assert aggregate["terminal_class_distribution"]["completed"] == 1
    assert aggregate["terminal_class_distribution"]["waiting_human"] == 1


def test_bundle_write_is_explicit_opt_in(tmp_path: Path) -> None:
    bundle = build_single_run_review_bundle(payload=_controller_payload())
    no_write_path = tmp_path / "no_write.json"
    maybe_write_review_output(review_output=bundle, output_path=None)
    assert not no_write_path.exists()

    write_path = tmp_path / "write.json"
    maybe_write_review_output(review_output=bundle, output_path=str(write_path))
    assert write_path.exists()
    loaded = json.loads(write_path.read_text(encoding="utf-8"))
    assert loaded["metadata"]["artifact_version"] == "review_bundle.v1"


def test_bundle_from_paths_tracks_input_paths_and_is_deterministic_except_timestamp(tmp_path: Path) -> None:
    controller_path = tmp_path / "controller_payload.json"
    tx_path = tmp_path / "tx_payload.json"
    controller_path.write_text(json.dumps(_controller_payload()), encoding="utf-8")
    tx_path.write_text(json.dumps(_tx_payload()), encoding="utf-8")

    first = build_multi_run_review_bundle_from_paths(payload_paths=[str(controller_path), str(tx_path)])
    second = build_multi_run_review_bundle_from_paths(payload_paths=[str(controller_path), str(tx_path)])
    assert first["metadata"]["input_payload_paths"] == [str(controller_path), str(tx_path)]
    assert second["metadata"]["input_payload_paths"] == [str(controller_path), str(tx_path)]

    first_copy = json.loads(json.dumps(first))
    second_copy = json.loads(json.dumps(second))
    first_copy["metadata"]["generated_at"] = "<normalized>"
    second_copy["metadata"]["generated_at"] = "<normalized>"
    assert first_copy == second_copy


def test_bundle_marks_partial_trace_honestly() -> None:
    tx_payload = _tx_payload()
    tx_payload["snapshot"]["progress_log"] = tx_payload["snapshot"]["progress_log"] * 120
    bundle = build_single_run_review_bundle(payload=tx_payload)
    note = bundle["metadata"]["partial_trace_note"]
    assert note["contains_partial_traces"] is True
    assert note["partial_run_count"] == 1
    assert bundle["runs"][0]["trace"]["completeness_status"] == "partial"
    assert "tx_progress_log_bounded" in bundle["runs"][0]["trace"]["normalization_warnings"]


def test_single_run_bundle_from_path_includes_payload_path(tmp_path: Path) -> None:
    controller_path = tmp_path / "controller_payload.json"
    controller_path.write_text(json.dumps(_controller_payload()), encoding="utf-8")
    bundle = build_single_run_review_bundle_from_path(payload_path=str(controller_path))
    assert bundle["metadata"]["input_payload_paths"] == [str(controller_path)]
    assert bundle["runs"][0]["input"]["payload_path"] == str(controller_path)
