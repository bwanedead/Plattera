"""Tests for ``tracing.service`` family detection and canonical trace dispatch."""

from __future__ import annotations

import pytest

from harness.tracing.service import build_canonical_trace_from_payload


def _minimal_mission_flow_payload() -> dict:
    return {
        "mission_flow": {
            "mission_id": "m-svc-1",
            "objective": "test objective",
            "request_id": "req-1",
            "active_mode": "alpha",
            "mode_history": ["alpha"],
            "transition_history": [],
            "high_signal_artifact_refs": ["artifact://sig-1"],
            "resumability_summary": {"resumable": False},
            "mission_status": {"terminal": False, "terminal_class": None, "reason_code": None},
            "blocker_posture_summary": {"waiting_human": False, "open_blocker_count": 0},
            "verification_posture_summary": {"status": None, "last_verification_kind": None},
            "opaque_adapter_payload": {"k": "v"},
            "created_at_epoch_seconds": 1000,
            "updated_at_epoch_seconds": 1001,
            "cycle_index": 1,
            "cycles": [
                {
                    "cycle_index": 1,
                    "executed_mode": "alpha",
                    "resulting_active_mode": "alpha",
                    "summary": "c1",
                    "timestamp_epoch_seconds": 1001,
                }
            ],
        }
    }


def _minimal_orchestration_payload() -> dict:
    return {
        "orchestration_kernel": {
            "trace_events": [
                {
                    "timestamp_epoch_seconds": 10,
                    "event_kind": "request_start",
                    "phase": "bootstrap",
                    "iteration_index": None,
                    "actor": "kernel",
                    "status": "started",
                    "refs_delta": {},
                    "payload": {"session_id": "s1", "request_id": "r1"},
                    "source_origin": {"kind": "k", "ref": "ref", "sequence_index": 0},
                },
                {
                    "timestamp_epoch_seconds": 20,
                    "event_kind": "terminal_outcome",
                    "phase": "terminal",
                    "iteration_index": 1,
                    "actor": "kernel",
                    "status": "completed",
                    "refs_delta": {},
                    "payload": {"terminal_class": "completed", "reason_code": "done"},
                    "source_origin": {"kind": "k", "ref": "ref", "sequence_index": 1},
                },
            ],
            "run_artifact": {
                "run_id": "run-svc-1",
                "session_id": "s1::run-svc-1",
                "request_id": "r1",
                "created_at_epoch_seconds": 10,
            },
        }
    }


def test_build_canonical_trace_detects_mission_flow() -> None:
    trace = build_canonical_trace_from_payload(payload=_minimal_mission_flow_payload())
    assert trace.loop_family == "mission_flow"
    assert trace.run_id == "m-svc-1"
    assert len(trace.events) >= 1


def test_build_canonical_trace_detects_orchestration_kernel() -> None:
    trace = build_canonical_trace_from_payload(payload=_minimal_orchestration_payload())
    assert trace.loop_family == "orchestration_kernel"
    assert trace.run_id == "run-svc-1"
    assert trace.terminal.terminal_class == "completed"


def test_build_canonical_trace_explicit_loop_family_overrides_detection() -> None:
    p = _minimal_mission_flow_payload()
    trace = build_canonical_trace_from_payload(payload=p, loop_family="mission_flow")
    assert trace.loop_family == "mission_flow"


def test_ambiguous_payload_raises() -> None:
    """Both native shapes present at top level → ambiguity."""
    bad = {
        "mission_id": "m",
        "active_mode": "a",
        "mode_history": ["a"],
        "cycles": [],
        "trace_events": [],
        "run_artifact": {},
    }
    with pytest.raises(ValueError, match="ambiguous"):
        build_canonical_trace_from_payload(payload=bad)


def test_unknown_shape_raises() -> None:
    with pytest.raises(ValueError, match="unsupported canonical trace payload"):
        build_canonical_trace_from_payload(payload={"foo": "bar"})


def test_non_dict_payload_raises() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        build_canonical_trace_from_payload(payload=[])  # type: ignore[arg-type]
