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
    build_multi_run_review_from_paths,
    build_single_run_review,
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

