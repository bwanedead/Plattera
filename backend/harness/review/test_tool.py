"""Tests for review bundle assembly and prompt extraction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.review.tool import (
    build_multi_run_review_bundle,
    build_single_run_review_bundle,
    extract_prompt_events_from_trace,
    maybe_write_review_output,
)
from harness.tracing.service import build_canonical_trace_from_payload


def _orch_payload_with_prompt() -> dict:
    return {
        "orchestration_kernel": {
            "trace_events": [
                {
                    "timestamp_epoch_seconds": 1,
                    "event_kind": "request_start",
                    "phase": "bootstrap",
                    "iteration_index": None,
                    "actor": "kernel",
                    "status": "started",
                    "refs_delta": {},
                    "payload": {"session_id": "s", "request_id": "r"},
                    "source_origin": {"kind": "k", "ref": "r", "sequence_index": 0},
                },
                {
                    "timestamp_epoch_seconds": 2,
                    "event_kind": "model_proposal",
                    "phase": "prompt_event",
                    "iteration_index": None,
                    "actor": "kernel",
                    "status": "completed",
                    "refs_delta": {},
                    "payload": {
                        "prompt_event": {
                            "metadata": {
                                "prompt_event_id": "pe-x",
                                "surface": "surf",
                                "pack_id": "pack-z",
                            },
                            "outcome_kind": "ok",
                        }
                    },
                    "source_origin": {"kind": "k", "ref": "r", "sequence_index": 1},
                },
                {
                    "timestamp_epoch_seconds": 3,
                    "event_kind": "terminal_outcome",
                    "phase": "terminal",
                    "iteration_index": 1,
                    "actor": "kernel",
                    "status": "completed",
                    "refs_delta": {},
                    "payload": {"terminal_class": "completed", "reason_code": "d"},
                    "source_origin": {"kind": "k", "ref": "r", "sequence_index": 2},
                },
            ],
            "run_artifact": {
                "run_id": "run-tool-1",
                "session_id": "s::run-tool-1",
                "request_id": "r",
                "created_at_epoch_seconds": 1,
            },
        }
    }


def test_single_run_review_bundle_shape() -> None:
    bundle = build_single_run_review_bundle(payload=_orch_payload_with_prompt())
    assert bundle["metadata"]["mode"] == "single_run"
    run0 = bundle["runs"][0]
    assert "trace" in run0
    assert "run_summary" in run0
    assert "review" in run0
    assert "prompt_events" in run0
    assert len(run0["prompt_events"]) == 1
    assert run0["prompt_events"][0]["pack_id"] == "pack-z"
    assert run0["prompt_events"][0]["prompt_event_id"] == "pe-x"


def test_multi_run_bundle_mixed_aggregate() -> None:
    p1 = _orch_payload_with_prompt()
    p2 = {
        "mission_flow": {
            "mission_id": "m-tool-2",
            "objective": "o",
            "request_id": None,
            "active_mode": "a",
            "mode_history": ["a"],
            "transition_history": [],
            "high_signal_artifact_refs": [],
            "resumability_summary": {"resumable": False},
            "mission_status": {"terminal": True, "terminal_class": "completed", "reason_code": "c"},
            "blocker_posture_summary": {"waiting_human": False, "open_blocker_count": 0},
            "verification_posture_summary": {"status": None, "last_verification_kind": None},
            "opaque_adapter_payload": {},
            "created_at_epoch_seconds": 1,
            "updated_at_epoch_seconds": 2,
            "cycle_index": 1,
            "cycles": [
                {
                    "cycle_index": 1,
                    "executed_mode": "a",
                    "resulting_active_mode": "a",
                    "summary": "s",
                    "timestamp_epoch_seconds": 2,
                }
            ],
        }
    }
    bundle = build_multi_run_review_bundle(payloads=[p1, p2])
    assert bundle["metadata"]["loop_family"] == "mixed"
    assert bundle["metadata"]["run_count"] == 2
    assert bundle["aggregate"]["run_count"] == 2


def test_extract_prompt_events_preserves_pack_id() -> None:
    trace = build_canonical_trace_from_payload(payload=_orch_payload_with_prompt())
    events = extract_prompt_events_from_trace(trace=trace)
    assert len(events) == 1
    assert events[0]["pack_id"] == "pack-z"
    assert events[0]["surface"] == "surf"


def test_maybe_write_review_output_deterministic(tmp_path: Path) -> None:
    out = {"a": 1, "b": {"c": 2}}
    path = tmp_path / "review.json"
    maybe_write_review_output(review_output=out, output_path=str(path))
    text = path.read_text(encoding="utf-8")
    again = json.loads(text)
    assert again == out
    # stable key order from sort_keys
    assert text.index('"a"') < text.index('"b"')
