"""Tests for mission observation native wire and round-trip."""

from __future__ import annotations

import pytest

from harness.runtime.mission.observability import MissionObservation, parse_mission_observation_payload


def _full_native_root() -> dict:
    return {
        "mission_id": "m-obs-1",
        "objective": "o",
        "request_id": "rq-obs",
        "active_mode": "mode_a",
        "mode_history": ["mode_a"],
        "transition_history": [
            {
                "prior_mode": "m0",
                "next_mode": "mode_a",
                "reason": "r",
                "status": "applied",
                "order_anchor": 1,
                "timestamp_epoch_seconds": 5,
            }
        ],
        "high_signal_artifact_refs": ["artifact://h"],
        "resumability_summary": {"resumable": False},
        "mission_status": {"terminal": False, "terminal_class": None, "reason_code": None},
        "blocker_posture_summary": {"waiting_human": False, "open_blocker_count": 0},
        "verification_posture_summary": {"status": None, "last_verification_kind": None},
        "opaque_adapter_payload": {"opaque_key": "opaque_val"},
        "created_at_epoch_seconds": 1,
        "updated_at_epoch_seconds": 6,
        "cycle_index": 1,
        "cycles": [
            {
                "cycle_index": 1,
                "executed_mode": "mode_a",
                "resulting_active_mode": "mode_a",
                "summary": "c",
                "timestamp_epoch_seconds": 6,
            }
        ],
    }


def test_to_payload_native_mission_flow_shape_only() -> None:
    obs = parse_mission_observation_payload({"mission_flow": _full_native_root()})
    payload = obs.to_payload()
    assert "mission_flow" in payload
    assert set(payload["mission_flow"].keys()) >= {
        "mission_id",
        "cycles",
        "transition_history",
        "opaque_adapter_payload",
    }


def test_parse_round_trip_preserves_opaque_and_cycles() -> None:
    root = _full_native_root()
    obs = parse_mission_observation_payload({"mission_flow": root})
    obs2 = parse_mission_observation_payload(obs.to_payload())
    assert obs2.mission_id == obs.mission_id
    assert obs2.opaque_adapter_payload == {"opaque_key": "opaque_val"}
    assert len(obs2.cycles) == 1
    assert len(obs2.transition_history) == 1


def test_parse_top_level_mission_shape() -> None:
    obs = parse_mission_observation_payload(_full_native_root())
    assert obs.mission_id == "m-obs-1"


def test_malformed_payload_missing_cycles_list_coerces_empty() -> None:
    bad = {
        "mission_id": "x",
        "active_mode": "a",
        "mode_history": ["a"],
        # cycles missing — parser uses empty cycles
    }
    obs = parse_mission_observation_payload({"mission_flow": bad})
    assert obs.cycles == ()


def test_mission_observation_dataclass_to_payload_types() -> None:
    obs = parse_mission_observation_payload({"mission_flow": _full_native_root()})
    assert isinstance(obs, MissionObservation)
