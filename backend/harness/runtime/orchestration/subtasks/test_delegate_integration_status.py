"""Tests for delegate ref integration visibility (M14)."""

from __future__ import annotations

from harness.audit.delegate_subtask_timeline import (
    render_delegate_subtask_section,
    render_delegate_turn_integration_summary,
)
from harness.audit.human_timeline import render_timeline
from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE
from harness.runtime.orchestration.subtasks.delegate_integration_status import (
    STATUS_REFERENCED_IN_REPAIR_BUNDLE,
    STATUS_REFERENCED_IN_STATE,
    STATUS_UNREFERENCED_RECENT,
    STATUS_UNREFERENCED_STALE,
    compute_delegate_ref_integration_status,
    should_show_delegate_integration_repair_note,
)
from harness.runtime.orchestration.subtasks.delegate_result_refs import (
    build_delegate_result_record,
    project_recent_delegate_results_for_prompt,
)


def _sample_outputs() -> dict:
    return {
        "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
        "subtask_id": "read_bearing",
        "profile": "p",
        "status": "completed",
        "input_refs": ["image:derived:a"],
        "result": {"source_visible_text": "N. 4° 00' W."},
    }


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


def test_prompt_projection_includes_integration_status() -> None:
    record = build_delegate_result_record(
        ref_id="subtask:turn8:read_parcel1_bearing",
        turn_index=8,
        alias="read_parcel1_bearing",
        action_index=1,
        action_inputs={"profile": "p", "task": "t", "context_refs": ["image:derived:a"]},
        outputs=_sample_outputs(),
    )
    projected = project_recent_delegate_results_for_prompt(
        [record],
        current_turn=8,
        resolution_state={"items": [{"evidence_refs": ["subtask:turn8:read_parcel1_bearing"]}]},
    )
    assert projected is not None
    row = projected["items"][0]
    assert row["integration_status"] == STATUS_REFERENCED_IN_STATE


def test_repair_note_only_when_repair_bundle_and_unreferenced_refs() -> None:
    record = build_delegate_result_record(
        ref_id="subtask:turn8:read_parcel1_bearing",
        turn_index=8,
        alias="read_parcel1_bearing",
        action_index=1,
        action_inputs={"profile": "p", "task": "t", "context_refs": ["image:derived:a"]},
        outputs=_sample_outputs(),
    )
    repair_bundle = {"fragments": [{"evidence_refs": ["image:derived:other"]}]}

    with_note = project_recent_delegate_results_for_prompt(
        [record],
        current_turn=8,
        repair_bundle=repair_bundle,
    )
    assert with_note is not None
    assert "repair_note" in with_note

    integrated = project_recent_delegate_results_for_prompt(
        [record],
        current_turn=8,
        repair_bundle=repair_bundle,
        resolution_state={"items": [{"evidence_refs": ["subtask:turn8:read_parcel1_bearing"]}]},
    )
    assert integrated is not None
    assert "repair_note" not in integrated

    no_bundle = project_recent_delegate_results_for_prompt(
        [record],
        current_turn=8,
    )
    assert no_bundle is not None
    assert "repair_note" not in no_bundle


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
