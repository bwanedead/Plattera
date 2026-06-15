from __future__ import annotations

import json

from harness.runtime.orchestration.action_batch import build_batch_item_result_row
from harness.runtime.orchestration.recent_result_projection import (
    project_recent_action_sequence_for_prompt,
    project_recent_result_for_prompt,
    project_recent_tool_result_slices_for_prompt,
)


def test_newest_slice_keeps_detail_older_strips_excerpt() -> None:
    slices = [
        {
            "kernel_turn_index": 1,
            "action_type": "read_artifact",
            "outputs_excerpt": {"text": "old detail"},
            "artifact_refs": ["artifact://old"],
        },
        {
            "kernel_turn_index": 5,
            "action_type": "write_artifact",
            "outputs_excerpt": {"text": "fresh detail"},
            "artifact_refs": ["artifact://fresh"],
        },
    ]
    projected = project_recent_tool_result_slices_for_prompt(
        slices,
        current_turn=5,
        hot_refs=frozenset(),
    )
    assert "outputs_excerpt" not in projected[0]
    assert projected[0]["action_type"] == "read_artifact"
    assert projected[1]["outputs_excerpt"] == {"text": "fresh detail"}
    assert projected[1]["action_type"] == "write_artifact"
    assert projected[1]["artifact_refs"] == ["artifact://fresh"]


def test_pinned_ref_keeps_older_slice_hot() -> None:
    row = {
        "kernel_turn_index": 1,
        "action_type": "transform_artifact",
        "outputs_excerpt": {"crop": "detail"},
        "artifact_refs": ["artifact://pinned"],
    }
    projected = project_recent_tool_result_slices_for_prompt(
        [row],
        current_turn=4,
        hot_refs=frozenset({"artifact://pinned"}),
    )
    assert projected[0]["outputs_excerpt"] == {"crop": "detail"}


def test_recent_action_sequence_projection_keeps_point_crop_master_overlay_ref() -> None:
    from harness.runtime.orchestration.recent_result_projection import (
        project_recent_action_sequence_for_prompt,
    )

    record = {
        "sequence_id": "req:iter:6:actions",
        "source_turn_index": 6,
        "items": [
            {
                "alias": "seed_packet",
                "action_type": "transform_artifact",
                "execution_state": "executed",
                "outputs": {
                    "derived_ref_id": "image:derived:master-1",
                    "overlay_role": "point_crop_master",
                },
                "point_crop_set_summary": {
                    "kind": "point_crop_set",
                    "sub_action": "point_crops",
                    "overlay_role": "point_crop_master",
                    "master_overlay_ref": "image:derived:master-1",
                    "coordinate_lattice": {"major_step_norm": 0.1, "minor_step_norm": 0.025},
                    "points": [{"alias": "a", "crop_ref": "image:derived:crop-a"}],
                },
            }
        ],
    }
    projected = project_recent_action_sequence_for_prompt(
        record,
        current_turn=6,
        hot_refs=frozenset(),
    )
    item = projected["items"][0]
    assert item["outputs"]["derived_ref_id"] == "image:derived:master-1"
    assert item["outputs"]["overlay_role"] == "point_crop_master"
    assert item["point_crop_set_summary"]["master_overlay_ref"] == "image:derived:master-1"
    assert item["point_crop_set_summary"]["overlay_role"] == "point_crop_master"
    assert item["point_crop_set_summary"]["coordinate_lattice"]["major_step_norm"] == 0.1


def test_recent_action_sequence_projection_keeps_point_crop_scaffold_ref() -> None:
    from harness.runtime.orchestration.action_batch import build_batch_item_result_row
    from harness.runtime.orchestration.recent_result_projection import (
        project_recent_action_sequence_for_prompt,
    )

    outputs = {
        "derived_ref_id": "image:derived:scaffold-1",
        "parent_ref_id": "image:assoc:tx-1:original",
        "sub_action": "point_crops_scaffold",
        "overlay_role": "point_crop_placement_scaffold",
        "point_count": 0,
        "coordinate_lattice": {"major_step_norm": 0.10, "minor_step_norm": 0.025},
        "crop_set": {
            "master_overlay_ref": "image:derived:scaffold-1",
            "source_ref": "image:assoc:tx-1:original",
            "overlay_role": "point_crop_placement_scaffold",
            "coordinate_lattice": {"major_step_norm": 0.10, "minor_step_norm": 0.025},
            "grid": {"enabled": True},
            "points": [],
            "point_count": 0,
        },
        "crop_records": [],
    }
    record = {
        "batch_id": "req:iter:3:actions",
        "source_turn_index": 3,
        "items": [
            build_batch_item_result_row(
                alias="placement_scaffold",
                action_type="transform_artifact",
                execution_state="executed",
                outputs=outputs,
                artifact_refs=["image:derived:scaffold-1"],
            )
        ],
    }
    projected = project_recent_action_sequence_for_prompt(
        record,
        current_turn=3,
        hot_refs=frozenset(),
    )
    item = projected["items"][0]
    assert item["outputs"]["derived_ref_id"] == "image:derived:scaffold-1"
    assert item["outputs"]["overlay_role"] == "point_crop_placement_scaffold"
    assert item["point_crop_set_summary"]["master_overlay_ref"] == "image:derived:scaffold-1"
    assert item["point_crop_set_summary"]["point_count"] == 0
    assert item["point_crop_set_summary"]["coordinate_lattice"]["major_step_norm"] == 0.10


def test_tool_result_slices_preserve_source_window_summary() -> None:
    from harness.runtime.memory.tool_result_slices import build_recent_tool_result_slices

    records = [
        {
            "kernel_turn_index": 2,
            "action_type": "transform_artifact",
            "execution_state": "executed",
            "artifact_refs": ["image:derived:crop-1"],
            "outputs_for_continuity": {
                "derived_ref_id": "image:derived:crop-1",
                "parent_ref_id": "image:assoc:tx-1:original",
                "sub_action": "crop",
                "source_window": {
                    "position_label": "bottom_full_width",
                    "touches_source_edge": {"bottom": True},
                    "can_expand": {"down": False},
                    "room_to_source_edge_norm": {"bottom": 0.0},
                },
            },
        }
    ]
    slices = build_recent_tool_result_slices(records)
    assert slices[0]["source_window"]["touches_source_edge"]["bottom"] is True
    assert slices[0]["source_window"]["can_expand"]["down"] is False


def test_stale_projection_keeps_source_window_summary() -> None:
    from harness.runtime.memory.tool_result_slices import build_recent_tool_result_slices

    outputs = {
        "derived_ref_id": "image:derived:crop-1",
        "parent_ref_id": "image:assoc:tx-1:original",
        "sub_action": "crop",
        "source_window": {
            "local_box_norm": [0.0, 0.8, 1.0, 1.0],
            "touches_source_edge": {
                "left": True,
                "top": False,
                "right": True,
                "bottom": True,
            },
            "room_to_source_edge_norm": {
                "left": 0.0,
                "top": 0.8,
                "right": 0.0,
                "bottom": 0.0,
            },
            "can_expand": {
                "left": False,
                "up": True,
                "right": False,
                "down": False,
            },
            "position_label": "bottom_full_width",
            "edge_summary": "Touches bottom edge of available source image; cannot expand farther down from this source artifact.",
        },
    }
    row = {
        "kernel_turn_index": 1,
        "action_type": "transform_artifact",
        "outputs_excerpt": {"crop": "verbose"},
        "source_window": outputs["source_window"],
        "artifact_refs": ["image:derived:crop-1"],
    }
    projected = project_recent_tool_result_slices_for_prompt(
        [row],
        current_turn=5,
        hot_refs=frozenset(),
    )
    assert "outputs_excerpt" not in projected[0]
    assert projected[0]["source_window"]["touches_source_edge"]["bottom"] is True
    assert projected[0]["source_window"]["can_expand"]["down"] is False


def test_no_b64_in_projected_results() -> None:
    row = {
        "kernel_turn_index": 3,
        "action_type": "noop",
        "outputs_excerpt": {"image_b64": "abc"},
    }
    compact = project_recent_result_for_prompt(row, age=3, keep_hot=False)
    dumped = json.dumps(compact).lower()
    assert "b64" not in dumped or "excerpt_omitted" in dumped
