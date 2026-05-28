"""Tests for per-turn action flag timeline rendering."""

from __future__ import annotations

from harness.audit.human_timeline import render_timeline
from harness.audit.turn_action_flags import compute_turn_action_flags, _compute_resolution_graph_delta
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
    assert "b64" not in body.lower()


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


def test_action_flags_render_hydrate_next_and_pinned_refs() -> None:
    turn = {
        "turn_index": 3,
        "tool_request": {
            "actions": [
                {
                    "alias": "crop_a",
                    "action_type": "transform_artifact",
                    "action_inputs": {"ref_id": "image:assoc:tx-1", "sub_action": "crop"},
                    "hydrate_next": ["@this.result.derived_ref_id"],
                }
            ],
            "pin_refs": ["image:derived:master-1"],
            "unpin_refs": ["image:derived:old-crop"],
        },
        "pin_refs_this_turn": ["image:derived:master-1"],
        "unpin_refs_this_turn": ["image:derived:old-crop"],
    }
    body = render_timeline([{"turn_index": 3, "parse_ok": True, **turn}])
    assert "- hydrate_next: yes (1 refs)" in body
    assert "  - @this.result.derived_ref_id" in body
    assert "- pinned_refs: yes (1 refs)" in body
    assert "  - image:derived:master-1" in body
    assert "- unpin_refs: yes (1 refs)" in body
    assert "  - image:derived:old-crop" in body


def test_resolution_graph_delta_counts_determinations_closed_and_added() -> None:
    before = {
        "items": [
            {
                "item_id": "group-1",
                "status": "open",
                "determined_value": None,
                "covered_units": [
                    {
                        "unit_id": "u-open",
                        "status": "open",
                        "determined_value": None,
                    },
                    {
                        "unit_id": "u-close",
                        "status": "open",
                        "determined_value": "old",
                    },
                ],
            }
        ]
    }
    after = {
        "items": [
            {
                "item_id": "group-1",
                "status": "open",
                "determined_value": None,
                "covered_units": [
                    {
                        "unit_id": "u-open",
                        "status": "open",
                        "determined_value": "earned",
                    },
                    {
                        "unit_id": "u-close",
                        "status": "closed",
                        "determined_value": "new",
                    },
                    {
                        "unit_id": "u-new",
                        "status": "open",
                        "determined_value": None,
                    },
                ],
            },
            {
                "item_id": "item-new",
                "status": "open",
                "determined_value": None,
            },
        ]
    }
    delta = _compute_resolution_graph_delta(before, after)
    assert delta.determinations_changed == 2
    assert delta.units_closed == 1
    assert delta.items_or_units_added == 2


def test_resolution_graph_delta_scopes_covered_units_by_parent_item() -> None:
    before = {
        "items": [
            {
                "item_id": "group-1",
                "covered_units": [{"unit_id": "shared", "status": "open"}],
            },
            {
                "item_id": "group-2",
                "covered_units": [{"unit_id": "shared", "status": "open"}],
            },
        ]
    }
    after = {
        "items": [
            {
                "item_id": "group-1",
                "covered_units": [
                    {"unit_id": "shared", "status": "closed", "determined_value": "A"}
                ],
            },
            {
                "item_id": "group-2",
                "covered_units": [
                    {"unit_id": "shared", "status": "closed", "determined_value": "B"}
                ],
            },
        ]
    }
    delta = _compute_resolution_graph_delta(before, after)
    assert delta.determinations_changed == 2
    assert delta.units_closed == 2


def test_timeline_renders_graph_delta_flags() -> None:
    turn = {
        "turn_index": 4,
        "resolution_state_before": {
            "items": [
                {
                    "item_id": "bearing-1",
                    "status": "open",
                    "determined_value": None,
                }
            ]
        },
        "resolution_state_after": {
            "items": [
                {
                    "item_id": "bearing-1",
                    "status": "closed",
                    "determined_value": "N. 4° 00' W.",
                }
            ]
        },
    }
    body = render_timeline([{"turn_index": 4, "parse_ok": True, **turn}])
    assert "- determinations_changed: 1" in body
    assert "- units_closed: 1" in body
