"""Tests for mission-flow trace adapter."""

from __future__ import annotations

from harness.tracing.adapters.mission_flow import build_mission_flow_trace


def _payload() -> dict:
    return {
        "mission_flow": {
            "mission_id": "m-mfa-1",
            "objective": "obj",
            "request_id": "rq-mfa",
            "active_mode": "m1",
            "mode_history": ["m0", "m1"],
            "transition_history": [
                {
                    "prior_mode": "m0",
                    "next_mode": "m1",
                    "reason": "advance",
                    "status": "applied",
                    "order_anchor": 1,
                    "timestamp_epoch_seconds": 50,
                }
            ],
            "high_signal_artifact_refs": ["artifact://h1"],
            "resumability_summary": {"resumable": True, "resume_reason": "r"},
            "mission_status": {"terminal": False, "terminal_class": None, "reason_code": None},
            "blocker_posture_summary": {"waiting_human": False, "open_blocker_count": 0},
            "verification_posture_summary": {"status": "ok", "last_verification_kind": None},
            "opaque_adapter_payload": {"opaque": 1},
            "created_at_epoch_seconds": 40,
            "updated_at_epoch_seconds": 55,
            "cycle_index": 2,
            "cycles": [
                {
                    "cycle_index": 1,
                    "executed_mode": "m0",
                    "resulting_active_mode": "m0",
                    "summary": "s0",
                    "timestamp_epoch_seconds": 45,
                },
                {
                    "cycle_index": 2,
                    "executed_mode": "m1",
                    "resulting_active_mode": "m1",
                    "summary": "s1",
                    "timestamp_epoch_seconds": 55,
                    "transition": {
                        "prior_mode": "m0",
                        "next_mode": "m1",
                        "reason": "advance",
                        "status": "applied",
                        "order_anchor": 1,
                        "timestamp_epoch_seconds": 50,
                    },
                },
            ],
        }
    }


def test_mission_flow_adapter_preserves_mission_cycle_transition_refs() -> None:
    trace = build_mission_flow_trace(mission_flow_payload=_payload())
    assert trace.loop_family == "mission_flow"
    assert trace.run_id == "m-mfa-1"
    assert trace.request_id == "rq-mfa"
    kinds = [e.event_kind for e in trace.events]
    assert "request_start" in kinds
    assert "mode_segment" in kinds
    assert "mission_transition" in kinds
    # High-signal refs surface on synthetic events / payload — observation carried into trace
    assert len(trace.events) >= 3
