"""Tests for mission-flow run summary builder."""

from __future__ import annotations

import pytest

from harness.run_summary.build import build_mission_flow_run_summary
from harness.run_summary.models import RUN_SUMMARY_ENVELOPE_VERSION, RequestSummary


def _native_mission_flow() -> dict:
    return {
        "mission_flow": {
            "mission_id": "m-rs-mf-1",
            "objective": "objective",
            "request_id": "req-mf",
            "active_mode": "plan",
            "mode_history": ["plan"],
            "transition_history": [],
            "high_signal_artifact_refs": [],
            "resumability_summary": {"resumable": False},
            "mission_status": {
                "terminal": True,
                "terminal_class": "completed",
                "reason_code": "done",
            },
            "blocker_posture_summary": {"waiting_human": False, "open_blocker_count": 0},
            "verification_posture_summary": {"status": "verified", "last_verification_kind": "declare_done"},
            "opaque_adapter_payload": {"adapter": "opaque"},
            "created_at_epoch_seconds": 10,
            "updated_at_epoch_seconds": 20,
            "cycle_index": 1,
            "cycles": [
                {
                    "cycle_index": 1,
                    "executed_mode": "plan",
                    "resulting_active_mode": "plan",
                    "summary": "done",
                    "timestamp_epoch_seconds": 20,
                }
            ],
        }
    }


def test_mission_flow_builds_native_envelope() -> None:
    env = build_mission_flow_run_summary(mission_flow_payload=_native_mission_flow())
    assert env.loop_family == "mission_flow"
    assert env.run_id == "m-rs-mf-1"
    assert env.envelope_version == RUN_SUMMARY_ENVELOPE_VERSION
    assert env.terminal_summary.terminal_class == "completed"


def test_mission_state_generic_surface() -> None:
    env = build_mission_flow_run_summary(mission_flow_payload=_native_mission_flow())
    assert isinstance(env.mission_state.opaque_payload, dict)
    assert env.mission_state.opaque_payload.get("adapter") == "opaque"
    rs_fields = RequestSummary.model_fields.keys()
    assert "dossier_id" not in rs_fields
    assert "mapping_ready" not in env.verification_summary.model_fields


def test_malformed_payload_not_dict_raises() -> None:
    with pytest.raises((TypeError, AttributeError)):
        build_mission_flow_run_summary(mission_flow_payload=[])  # type: ignore[arg-type]
