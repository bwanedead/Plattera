"""Tests for per-turn action flag timeline rendering."""

from __future__ import annotations

from harness.audit.human_timeline import render_timeline
from harness.audit.turn_action_flags import compute_turn_action_flags
from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE


def test_action_flags_batch_delegate_point_crops_and_images() -> None:
    turn = {
        "turn_index": 2,
        "tool_request": {
            "actions": [
                {
                    "alias": "crops",
                    "action_type": "transform_artifact",
                    "action_inputs": {"ref_id": "image:assoc:tx-1", "sub_action": "point_crops"},
                },
                {
                    "alias": "read_a",
                    "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
                    "action_inputs": {
                        "profile": "transcript_edit.visual_source_observation",
                        "task": "Read crop A.",
                        "context_refs": ["image:derived:crop-a"],
                    },
                },
            ]
        },
        "tool_result_raw": {
            "execution_state": "executed",
            "artifact_refs": ["image:derived:master-1", "image:derived:crop-a"],
            "outputs": {
                "sub_action": "point_crops",
                "derived_ref_id": "image:derived:master-1",
                "crop_set": {
                    "points": [{"crop_ref": "image:derived:crop-a"}],
                },
            },
        },
    }
    flags = compute_turn_action_flags(turn)
    assert flags.batch is True
    assert flags.delegate is True
    assert flags.point_crops is True
    assert flags.image_refs >= 3

    body = render_timeline([{"turn_index": 2, "parse_ok": True, **turn}])
    assert "Action flags:" in body
    assert "batch: yes (2 rows)" in body
    assert "delegate: yes (1 subtasks)" in body
    assert "point_crops: yes" in body
    assert "image_refs:" in body


def test_action_flags_hitl_yes() -> None:
    turn = {
        "turn_index": 1,
        "parsed_action_plan": {"wait_for_human": True, "hitl_request": {"message": "Confirm?"}},
        "tool_request": {},
    }
    flags = compute_turn_action_flags(turn)
    assert flags.hitl is True
    body = render_timeline([{"turn_index": 1, "parse_ok": True, **turn}])
    assert "- HITL: yes" in body


def test_action_flags_single_action_not_batch() -> None:
    turn = {
        "turn_index": 1,
        "tool_request": {
            "actions": [
                {
                    "alias": "save",
                    "action_type": "save_workspace_artifact",
                    "action_inputs": {"draft_payload": {"text": "x"}},
                }
            ]
        },
    }
    flags = compute_turn_action_flags(turn)
    assert flags.batch is False
    assert flags.save is True
    body = render_timeline([{"turn_index": 1, "parse_ok": True, **turn}])
    assert "- batch: no" in body
    assert "- save: yes" in body
