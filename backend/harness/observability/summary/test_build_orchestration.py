"""Tests for orchestration-kernel run summary builder."""

from __future__ import annotations

import pytest

from harness.observability.summary.build import build_orchestration_kernel_run_summary
from harness.observability.summary.models import RUN_SUMMARY_ENVELOPE_VERSION


def _payload_with_prompt_event() -> dict:
    return {
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
                "iteration_index": 1,
                "actor": "kernel",
                "status": "completed",
                "refs_delta": {},
                "payload": {
                    "prompt_event": {
                        "metadata": {
                            "prompt_event_id": "pe-1",
                            "surface": "test_surface",
                            "pack_id": "pack-a",
                        }
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
                "payload": {"terminal_class": "completed", "reason_code": "done"},
                "source_origin": {"kind": "k", "ref": "r", "sequence_index": 2},
            },
        ],
        "run_artifact": {
            "run_id": "run-rs-1",
            "session_id": "s::run-rs-1",
            "request_id": "r",
            "objective": "obj",
            "created_at_epoch_seconds": 1,
        },
    }


def test_orchestration_builds_native_envelope() -> None:
    env = build_orchestration_kernel_run_summary(orchestration_kernel_payload=_payload_with_prompt_event())
    assert env.loop_family == "orchestration_kernel"
    assert env.run_id == "run-rs-1"
    assert env.envelope_version == RUN_SUMMARY_ENVELOPE_VERSION
    assert env.mission_state.loop_family == "orchestration_kernel"
    assert env.mission_state.opaque_payload is not None


def test_prompt_observability_from_trace_events() -> None:
    env = build_orchestration_kernel_run_summary(orchestration_kernel_payload=_payload_with_prompt_event())
    assert env.prompt_observability_summary.prompt_event_count == 1
    assert env.prompt_observability_summary.last_prompt_event_id == "pe-1"
    assert env.prompt_observability_summary.last_prompt_event_surface == "test_surface"


def test_prompt_observability_fallback_without_prompt_in_trace() -> None:
    p = {
        "trace_events": [
            {
                "timestamp_epoch_seconds": 1,
                "event_kind": "request_start",
                "phase": "bootstrap",
                "iteration_index": None,
                "actor": "kernel",
                "status": "started",
                "refs_delta": {},
                "payload": {},
                "source_origin": {"kind": "k", "ref": "r", "sequence_index": 0},
            }
        ],
        "run_artifact": {
            "run_id": "r2",
            "session_id": "s",
            "request_id": "r",
            "active_mode": "mode_x",
            "created_at_epoch_seconds": 1,
        },
        "prompt_observability_summary": {
            "prompt_event_count": 2,
            "last_prompt_event_id": "from-payload",
            "last_prompt_event_surface": "payload_surface",
            "consecutive_no_dispatch_turns": 3,
            "turns_since_last_tool_execution": 4,
            "turns_since_latest_refs_change": 2,
            "last_state_patch_outcome": "rejected",
            "last_state_patch_reason_code": "mission_unknown_keys",
            "resolution_item_count": 4,
            "closed_items_without_basis_count": 2,
        },
    }
    env = build_orchestration_kernel_run_summary(orchestration_kernel_payload=p)
    assert env.prompt_observability_summary.prompt_event_count == 2
    assert env.prompt_observability_summary.last_prompt_event_id == "from-payload"
    assert env.prompt_observability_summary.consecutive_no_dispatch_turns == 3
    assert env.prompt_observability_summary.turns_since_last_tool_execution == 4
    assert env.prompt_observability_summary.last_state_patch_reason_code == "mission_unknown_keys"
    assert env.prompt_observability_summary.resolution_item_count == 4
    assert env.prompt_observability_summary.closed_items_without_basis_count == 2


def test_prompt_observability_merges_trace_metadata_with_payload_coverage() -> None:
    payload = _payload_with_prompt_event()
    payload["prompt_observability_summary"] = {
        "resolution_item_count": 5,
        "closed_items_without_basis_count": 1,
        "success_condition_count": 2,
    }
    env = build_orchestration_kernel_run_summary(orchestration_kernel_payload=payload)
    assert env.prompt_observability_summary.prompt_event_count == 1
    assert env.prompt_observability_summary.last_prompt_event_id == "pe-1"
    assert env.prompt_observability_summary.resolution_item_count == 5
    assert env.prompt_observability_summary.closed_items_without_basis_count == 1
    assert env.prompt_observability_summary.success_condition_count == 2


def test_malformed_not_dict_raises() -> None:
    with pytest.raises((TypeError, ValueError, AttributeError)):
        build_orchestration_kernel_run_summary(orchestration_kernel_payload="bad")  # type: ignore[arg-type]


def test_brief_2_locator_and_long_value_counters_project_into_typed_summary() -> None:
    """Brief 2 follow-up: new covered-units counters must survive the typed projection."""
    payload = _payload_with_prompt_event()
    payload["prompt_observability_summary"] = {
        "earned_units_missing_locator_count": 3,
        "long_determined_value_units_count": 2,
    }
    env = build_orchestration_kernel_run_summary(orchestration_kernel_payload=payload)
    assert env.prompt_observability_summary.earned_units_missing_locator_count == 3
    assert env.prompt_observability_summary.long_determined_value_units_count == 2


def test_notebook_shaped_graph_rows_counter_projects_into_typed_summary() -> None:
    payload = _payload_with_prompt_event()
    payload["prompt_observability_summary"] = {
        "notebook_shaped_graph_rows_count": 4,
        "mechanical_flags": ["notebook_shaped_graph_rows:4"],
    }
    env = build_orchestration_kernel_run_summary(orchestration_kernel_payload=payload)
    assert env.prompt_observability_summary.notebook_shaped_graph_rows_count == 4
    assert "notebook_shaped_graph_rows:4" in env.prompt_observability_summary.mechanical_flags


def test_artifact_claim_inventory_suspect_counter_projects_into_typed_summary() -> None:
    payload = _payload_with_prompt_event()
    payload["prompt_observability_summary"] = {
        "artifact_claim_inventory_suspect_count": 2,
        "mechanical_flags": ["artifact_claim_inventory_suspect:2"],
    }
    env = build_orchestration_kernel_run_summary(orchestration_kernel_payload=payload)
    assert env.prompt_observability_summary.artifact_claim_inventory_suspect_count == 2
    assert "artifact_claim_inventory_suspect:2" in env.prompt_observability_summary.mechanical_flags


def test_shared_unlocated_evidence_counter_projects_into_typed_summary() -> None:
    """Typed projection must not drop shared_unlocated_evidence_for_earned_units_count."""
    payload = _payload_with_prompt_event()
    payload["prompt_observability_summary"] = {
        "shared_unlocated_evidence_for_earned_units_count": 2,
        "mechanical_flags": ["shared_unlocated_evidence_for_earned_units:2"],
    }
    env = build_orchestration_kernel_run_summary(orchestration_kernel_payload=payload)
    assert env.prompt_observability_summary.shared_unlocated_evidence_for_earned_units_count == 2
    assert (
        "shared_unlocated_evidence_for_earned_units:2"
        in env.prompt_observability_summary.mechanical_flags
    )
