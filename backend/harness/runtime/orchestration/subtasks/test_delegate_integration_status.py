"""Tests for delegate ref integration visibility (M14)."""

from __future__ import annotations

from harness.audit.delegate_subtask_timeline import (
    render_delegate_subtask_section,
    render_delegate_turn_integration_summary,
)
from harness.audit.human_timeline import render_timeline
from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE
from harness.runtime.orchestration.subtasks.delegate_integration_status import (
    STATUS_INTEGRATED_VIA_CONTEXT_REF,
    STATUS_REFERENCED_IN_REPAIR_BUNDLE,
    STATUS_REFERENCED_IN_STATE,
    STATUS_UNREFERENCED_RECENT,
    STATUS_UNREFERENCED_STALE,
    compute_delegate_observation_integration_status,
    compute_delegate_ref_integration_status,
    should_show_delegate_integration_repair_note,
)


def test_ref_in_evidence_refs_is_referenced_in_state() -> None:
    ref_id = "subtask:turn8:read_parcel1_bearing"
    status = compute_delegate_ref_integration_status(
        ref_id=ref_id,
        record_turn_index=8,
        current_turn=9,
        resolution_state={
            "items": [
                {
                    "item_id": "item-a",
                    "covered_units": [
                        {"evidence_refs": [ref_id, "image:derived:abc"]},
                    ],
                }
            ]
        },
    )
    assert status == STATUS_REFERENCED_IN_STATE


def test_ref_in_repair_bundle_is_referenced_in_repair_bundle() -> None:
    ref_id = "subtask:turn8:read_parcel1_bearing"
    status = compute_delegate_ref_integration_status(
        ref_id=ref_id,
        record_turn_index=8,
        current_turn=9,
        repair_bundle={
            "fragments": [
                {
                    "fragment_path": "resolution.items[item-a].covered_units[u1]",
                    "evidence_refs": [ref_id],
                }
            ]
        },
    )
    assert status == STATUS_REFERENCED_IN_REPAIR_BUNDLE


def test_state_takes_priority_over_repair_bundle() -> None:
    ref_id = "subtask:turn8:read_parcel1_bearing"
    status = compute_delegate_ref_integration_status(
        ref_id=ref_id,
        record_turn_index=8,
        current_turn=9,
        resolution_state={"items": [{"evidence_refs": [ref_id]}]},
        repair_bundle={"fragments": [{"evidence_refs": [ref_id]}]},
    )
    assert status == STATUS_REFERENCED_IN_STATE


def test_recent_unreferenced_ref_is_unreferenced_recent() -> None:
    status = compute_delegate_ref_integration_status(
        ref_id="subtask:turn8:read_parcel1_bearing",
        record_turn_index=8,
        current_turn=8,
    )
    assert status == STATUS_UNREFERENCED_RECENT


def test_old_unreferenced_ref_is_stale() -> None:
    status = compute_delegate_ref_integration_status(
        ref_id="subtask:turn5:read_parcel1_bearing",
        record_turn_index=5,
        current_turn=9,
    )
    assert status == STATUS_UNREFERENCED_STALE


def test_exact_string_scan_does_not_match_similar_text() -> None:
    ref_id = "subtask:turn8:read_parcel1_bearing"
    status = compute_delegate_ref_integration_status(
        ref_id=ref_id,
        record_turn_index=8,
        current_turn=10,
        resolution_state={
            "notes": "see subtask:turn8:read_parcel1_bearing:extra for detail",
            "evidence_refs": ["subtask:turn8:read"],
        },
    )
    assert status == STATUS_UNREFERENCED_STALE


def test_context_crop_ref_in_state_is_integrated_via_context_ref() -> None:
    crop_ref = "image:derived:crop-p1"
    status = compute_delegate_observation_integration_status(
        ref_id="subtask:turn14:read_p1",
        context_refs=[crop_ref],
        record_turn_index=14,
        current_turn=15,
        resolution_state={"items": [{"evidence_refs": [crop_ref]}]},
    )
    assert status == STATUS_INTEGRATED_VIA_CONTEXT_REF


def test_context_crop_ref_in_repair_bundle_matches_repair_status() -> None:
    crop_ref = "image:derived:crop-p1"
    status = compute_delegate_observation_integration_status(
        ref_id="subtask:turn14:read_p1",
        context_refs=[crop_ref],
        record_turn_index=14,
        current_turn=15,
        repair_bundle={"fragments": [{"evidence_refs": [crop_ref]}]},
    )
    assert status == STATUS_REFERENCED_IN_REPAIR_BUNDLE


def test_should_show_repair_note_helper() -> None:
    assert should_show_delegate_integration_repair_note(
        repair_bundle={"fragments": [{}]},
        integration_by_ref={"subtask:turn8:a": STATUS_UNREFERENCED_RECENT},
    )
    assert not should_show_delegate_integration_repair_note(
        repair_bundle={"fragments": [{}]},
        integration_by_ref={"subtask:turn8:a": STATUS_REFERENCED_IN_STATE},
    )


def test_timeline_renders_integration_status() -> None:
    lines = render_delegate_subtask_section(
        alias="read_parcel1_bearing",
        inputs={"profile": "p", "task": "t", "context_refs": ["image:derived:a"]},
        item={
            "delegate_result_ref": "subtask:turn8:read_parcel1_bearing",
            "delegate_subtask": {
                "status": "completed",
                "result": {"source_visible_text": "N. 4° 00' W."},
            },
        },
        integration_status=STATUS_REFERENCED_IN_REPAIR_BUNDLE,
    )
    assert any("integration: referenced_in_repair_bundle" in line for line in lines)


def test_timeline_turn_summary_lists_delegate_refs() -> None:
    body = render_timeline(
        [
            {
                "turn_index": 8,
                "parse_ok": True,
                "tool_request": {
                    "actions": [
                        {
                            "alias": "read_bearing",
                            "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
                            "action_inputs": {
                                "profile": "p",
                                "task": "Read bearing",
                                "context_refs": ["image:derived:a"],
                            },
                        }
                    ],
                },
                "recent_action_sequence_result": {
                    "source_turn_index": 8,
                    "items": [
                        {
                            "alias": "read_bearing",
                            "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
                            "execution_state": "executed",
                            "delegate_result_ref": "subtask:turn8:read_bearing",
                            "delegate_subtask": {
                                "status": "completed",
                                "result": {"source_visible_text": "N. 4° 00' W."},
                            },
                        }
                    ],
                },
                "state_patch_feedback": {
                    "state_patch_repair_bundle": {
                        "fragments": [{"evidence_refs": ["subtask:turn8:read_bearing"]}],
                    }
                },
            }
        ]
    )
    assert "Delegate result refs:" in body
    assert "subtask:turn8:read_bearing" in body
    assert "referenced_in_repair_bundle" in body
    assert "hydrate_hint:" in body


def test_turn_summary_via_helper() -> None:
    lines = render_delegate_turn_integration_summary(
        {
            "turn_index": 8,
            "recent_action_sequence_result": {
                "source_turn_index": 8,
                "items": [
                    {
                        "alias": "read_bearing",
                        "delegate_result_ref": "subtask:turn8:read_bearing",
                        "action_inputs": {"context_refs": ["image:derived:a"]},
                    }
                ],
            },
            "state_patch_feedback": {
                "state_patch_repair_bundle": {
                    "fragments": [{"evidence_refs": ["subtask:turn8:read_bearing"]}],
                }
            },
        }
    )
    assert lines
    assert "referenced_in_repair_bundle" in lines[1]
