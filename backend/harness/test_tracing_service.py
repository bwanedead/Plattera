from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.tracing.adapters.controller_kernel import build_controller_kernel_trace
from harness.tracing.adapters.transcript_edit import build_transcript_edit_trace
from harness.tracing.schema import CanonicalTraceRecord
from harness.tracing.service import (
    build_canonical_trace_from_payload,
    build_controller_kernel_canonical_trace,
    build_mission_runtime_canonical_trace,
    build_transcript_edit_canonical_trace,
)


def _controller_payload() -> dict:
    return {
        "controller_transcript": {
            "events": [
                {
                    "event_type": "run_header",
                    "detail": "controller_run_started",
                    "timestamp_epoch_seconds": 10,
                    "payload": {
                        "request_id": "request-svc-1",
                        "session_id": "request-svc-1::run-svc-1",
                    },
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
            "run_id": "run-svc-1",
            "request_id": "request-svc-1",
            "session_id": "request-svc-1::run-svc-1",
            "created_at_epoch_seconds": 10,
            "steps": [],
        },
        "controller_transcript_ref": "artifact://svc-controller-transcript",
        "run_artifact_ref": "artifact://svc-run-artifact",
    }


def _transcript_edit_payload() -> dict:
    return {
        "run_id": "tx_agent_svc_1",
        "status": "completed",
        "request": {"mode": "audit_then_repair", "trigger": "manual"},
        "snapshot": {
            "run_id": "tx_agent_svc_1",
            "status": "completed",
            "reason_code": "tx_agent_transcript_clean_promoted",
            "iterations": 1,
            "session_id": "tx-agent-svc-kernel::tx-agent-svc-kernel-session-1",
            "progress_log": [
                {"timestamp_epoch_seconds": 100, "iteration": 0, "phase": "starting", "message": "starting"},
                {
                    "timestamp_epoch_seconds": 101,
                    "iteration": 1,
                    "phase": "audit_result",
                    "message": "audit result",
                    "detail": {
                        "decision_ledger": {
                            "summary": {
                                "unresolved_count": 0,
                                "mapping_blocking_unresolved_count": 0,
                            },
                            "source_completeness": "complete",
                        }
                    },
                },
            ],
            "critical_events": [],
            "runtime_hitl_state": {
                "hitl_lifecycle_log": [],
                "blocker_registry": {"updated_at": 101, "rows": [], "history": [], "counts": {"total": 0}},
            },
            "terminal_summary": {
                "terminal_classification": "mapping_ready",
                "human_feedback_pending": False,
                "decision_ledger": {
                    "summary": {
                        "unresolved_count": 0,
                        "mapping_blocking_unresolved_count": 0,
                    },
                    "source_completeness": "complete",
                },
            },
            "waiting_feedback": False,
            "resumable": False,
        },
    }


def _mission_runtime_payload() -> dict:
    return {
        "mission_runtime": {
            "mission_id": "mission-svc-1",
            "objective": "multi-mode mission",
            "request_id": "mission-request-1",
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
                }
            ],
            "cycles": [
                {
                    "cycle_index": 1,
                    "executed_mode": "deed_to_ir",
                    "resulting_active_mode": "transcript_edit",
                    "summary": "deed cycle done",
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
                }
            ],
            "mission_status": {"terminal": False, "terminal_class": "in_progress", "reason_code": None},
            "resumability_summary": {"resumable": True, "resume_reason": "mode_transition_pending"},
            "created_at_epoch_seconds": 100,
            "updated_at_epoch_seconds": 101,
            "cycle_index": 1,
            "high_signal_artifact_refs": ["artifact://handoff/1"],
        }
    }


def test_service_dispatches_controller_payload_with_detection() -> None:
    payload = _controller_payload()
    trace = build_canonical_trace_from_payload(payload=payload)
    direct = build_controller_kernel_trace(
        controller_transcript=payload["controller_transcript"],
        run_artifact=payload["run_artifact"],
        transcript_ref=payload["controller_transcript_ref"],
        run_artifact_ref=payload["run_artifact_ref"],
    )
    assert isinstance(trace, CanonicalTraceRecord)
    assert trace.loop_family == "controller_kernel"
    assert json.dumps(trace.model_dump(mode="json"), sort_keys=True) == json.dumps(
        direct.model_dump(mode="json"), sort_keys=True
    )


def test_service_dispatches_transcript_edit_payload_with_detection() -> None:
    payload = _transcript_edit_payload()
    trace = build_canonical_trace_from_payload(payload=payload)
    direct = build_transcript_edit_trace(run_snapshot=payload)
    assert isinstance(trace, CanonicalTraceRecord)
    assert trace.loop_family == "transcript_edit"
    assert json.dumps(trace.model_dump(mode="json"), sort_keys=True) == json.dumps(
        direct.model_dump(mode="json"), sort_keys=True
    )


def test_service_explicit_loop_family_path_works() -> None:
    payload = _controller_payload()
    trace = build_canonical_trace_from_payload(payload=payload, loop_family="controller_kernel")
    assert trace.loop_family == "controller_kernel"


def test_service_ambiguous_payload_fails_clearly() -> None:
    payload = _controller_payload()
    payload["snapshot"] = {"run_id": "tx-like"}
    with pytest.raises(ValueError, match="ambiguous canonical trace payload"):
        build_canonical_trace_from_payload(payload=payload)


def test_service_unsupported_payload_fails_clearly() -> None:
    with pytest.raises(ValueError, match="unsupported canonical trace payload shape"):
        build_canonical_trace_from_payload(payload={})


def test_service_malformed_transcript_edit_like_payload_fails_clearly() -> None:
    with pytest.raises(ValueError, match="unsupported canonical trace payload shape"):
        build_canonical_trace_from_payload(payload={"progress_log": []})
    with pytest.raises(ValueError, match="invalid transcript_edit payload"):
        build_canonical_trace_from_payload(payload={"snapshot": {}}, loop_family="transcript_edit")


def test_service_direct_family_functions_return_canonical_trace_type() -> None:
    controller_payload = _controller_payload()
    controller_trace = build_controller_kernel_canonical_trace(
        controller_transcript=controller_payload["controller_transcript"],
        run_artifact=controller_payload["run_artifact"],
    )
    tx_payload = _transcript_edit_payload()
    tx_trace = build_transcript_edit_canonical_trace(run_snapshot=tx_payload)
    mission_payload = _mission_runtime_payload()["mission_runtime"]
    mission_trace = build_mission_runtime_canonical_trace(mission_runtime_payload=mission_payload)
    assert isinstance(controller_trace, CanonicalTraceRecord)
    assert isinstance(tx_trace, CanonicalTraceRecord)
    assert isinstance(mission_trace, CanonicalTraceRecord)


def test_service_dispatches_mission_runtime_payload_with_detection() -> None:
    payload = _mission_runtime_payload()
    trace = build_canonical_trace_from_payload(payload=payload)
    assert trace.loop_family == "mission_runtime"
    assert trace.mission_id == "mission-svc-1"
    assert trace.transition_events
    assert any(event.event_kind == "mission_transition" for event in trace.events)
