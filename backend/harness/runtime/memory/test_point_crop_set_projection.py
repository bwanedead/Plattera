"""Tests for compact point crop set prompt projection."""

from __future__ import annotations

import json

from harness.runtime.memory.point_crop_set_projection import project_point_crop_set_summary
from harness.runtime.memory.tool_result_slices import build_recent_tool_result_slices
from harness.runtime.orchestration.recent_result_projection import (
    project_recent_tool_result_slices_for_prompt,
)


def _crop_set_outputs(*, sub_action: str = "point_crops", previous: str | None = None) -> dict:
    outputs = {
        "derived_ref_id": "image:derived:master-1",
        "parent_ref_id": "image:assoc:tx-1:original",
        "sub_action": sub_action,
        "crop_set": {
            "master_overlay_ref": "image:derived:master-1",
            "source_ref": "image:assoc:tx-1:original",
            "points": [
                {
                    "letter": "A",
                    "alias": "parcel_1_tie_bearing",
                    "crop_ref": "image:derived:crop-a",
                    "point_norm": [0.42, 0.58],
                    "size": "medium",
                    "shape": "wide",
                    "box_px": [10, 20, 30, 40],
                    "absolute_path": "C:\\secret\\crop-a.png",
                }
            ],
        },
    }
    if previous:
        outputs["previous_crop_set_overlay_ref"] = previous
        outputs["crop_set"]["previous_crop_set_overlay_ref"] = previous
    return outputs


def test_project_point_crops_result_as_compact_summary() -> None:
    summary = project_point_crop_set_summary(_crop_set_outputs())
    assert summary is not None
    assert summary["kind"] == "point_crop_set"
    assert summary["master_overlay_ref"] == "image:derived:master-1"
    assert summary["source_ref"] == "image:assoc:tx-1:original"
    point = summary["points"][0]
    assert point["alias"] == "parcel_1_tie_bearing"
    assert point["crop_ref"] == "image:derived:crop-a"
    assert "absolute_path" not in point
    assert summary["delegation_lines"] == ["A parcel_1_tie_bearing -> image:derived:crop-a"]


def test_project_point_crops_adjust_includes_previous_overlay_ref() -> None:
    summary = project_point_crop_set_summary(
        _crop_set_outputs(sub_action="point_crops_adjust", previous="image:derived:master-old")
    )
    assert summary is not None
    assert summary["previous_crop_set_overlay_ref"] == "image:derived:master-old"


def test_project_includes_graph_ref_when_present() -> None:
    outputs = _crop_set_outputs()
    outputs["crop_set"]["points"][0]["graph_ref"] = {
        "item_id": "parcel_1_description",
        "covered_unit_id": "p1_tie_bearing",
    }
    summary = project_point_crop_set_summary(outputs)
    assert summary is not None
    assert summary["points"][0]["graph_ref"]["item_id"] == "parcel_1_description"


def test_tool_result_slices_include_point_crop_set_summary() -> None:
    records = [
        {
            "kernel_turn_index": 2,
            "action_type": "transform_artifact",
            "execution_state": "executed",
            "artifact_refs": ["image:derived:master-1", "image:derived:crop-a"],
            "outputs_for_continuity": _crop_set_outputs(),
        }
    ]
    slices = build_recent_tool_result_slices(records)
    assert "point_crop_set_summary" in slices[0]
    assert slices[0]["point_crop_set_summary"]["points"][0]["crop_ref"] == "image:derived:crop-a"


def test_stale_projection_keeps_crop_set_summary_without_excerpt() -> None:
    row = {
        "kernel_turn_index": 1,
        "action_type": "transform_artifact",
        "outputs_excerpt": {"crop_set": "verbose"},
        "point_crop_set_summary": project_point_crop_set_summary(_crop_set_outputs()),
        "artifact_refs": ["image:derived:master-1"],
    }
    projected = project_recent_tool_result_slices_for_prompt(
        [row],
        current_turn=5,
        hot_refs=frozenset(),
    )
    assert "outputs_excerpt" not in projected[0]
    assert projected[0]["point_crop_set_summary"]["master_overlay_ref"] == "image:derived:master-1"


def test_projection_has_no_b64_or_absolute_paths() -> None:
    summary = project_point_crop_set_summary(_crop_set_outputs())
    dumped = json.dumps(summary).lower()
    assert "b64" not in dumped
    assert "c:\\" not in dumped
    assert "absolute_path" not in dumped
