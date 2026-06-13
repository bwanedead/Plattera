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
                    "box_norm": [0.1, 0.25, 0.4, 0.5],
                    "zoom_factor": 2.25,
                    "projection_available": True,
                    "root_source_ref": "image:assoc:tx-1:original",
                    "root_point_norm": [0.51, 0.63],
                    "root_box_norm": [0.47, 0.6, 0.56, 0.66],
                    "absolute_path": "C:\\secret\\crop-a.png",
                }
            ],
            "overlay_role": "point_crop_master",
            "coordinate_lattice": {"major_step_norm": 0.10, "minor_step_norm": 0.025},
            "grid": {"enabled": True, "divisions": 4, "coordinate_space": "source_image_norm"},
            "legend": {"size_colors": {"small": [1, 2, 3], "medium": [4, 5, 6], "large": [7, 8, 9]}},
            "review_lines": [
                "A parcel_1_tie_bearing -> crop=image:derived:crop-a point=[0.420,0.580] anchor=[0.4,0.6] offset=[+0.020,-0.020]"
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
    assert summary["overlay_role"] == "point_crop_master"
    assert summary["coordinate_lattice"] == {"major_step_norm": 0.10, "minor_step_norm": 0.025}
    assert summary["master_overlay_ref"] == "image:derived:master-1"
    assert summary["source_ref"] == "image:assoc:tx-1:original"
    point = summary["points"][0]
    assert point["alias"] == "parcel_1_tie_bearing"
    assert point["crop_ref"] == "image:derived:crop-a"
    assert "absolute_path" not in point
    assert point["zoom_factor"] == 2.25
    assert point["box_norm"] == [0.1, 0.25, 0.4, 0.5]
    assert point["root_point_norm"] == [0.51, 0.63]
    assert point["root_box_norm"] == [0.47, 0.6, 0.56, 0.66]
    assert "projection_chain" not in point
    assert summary["grid"]["enabled"] is True
    assert summary["delegation_lines"] == [
        "A parcel_1_tie_bearing -> image:derived:crop-a root=[0.51,0.63] zoom=2.25"
    ]
    assert summary["review_lines"]
    assert "offset=[" in summary["review_lines"][0]
    assert "anchor=[" in summary["review_lines"][0]
    assert summary["point_key_lines"]
    assert summary["point_key_lines"][0].startswith("A ")
    assert "point=[" in summary["point_key_lines"][0]


def test_projection_includes_overlay_role_for_view() -> None:
    outputs = _crop_set_outputs(sub_action="point_crops_view")
    outputs["overlay_role"] = "point_crop_view"
    outputs["crop_set"]["overlay_role"] = "point_crop_view"
    summary = project_point_crop_set_summary(outputs)
    assert summary is not None
    assert summary["overlay_role"] == "point_crop_view"


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


def test_projection_includes_unavailable_reason_when_projection_false() -> None:
    outputs = _crop_set_outputs()
    outputs["crop_set"]["points"][0]["projection_available"] = False
    outputs["crop_set"]["points"][0]["projection_unavailable_reason"] = (
        "parent transform reference_overlay does not preserve source-coordinate mapping"
    )
    outputs["crop_set"]["points"][0].pop("root_point_norm", None)
    summary = project_point_crop_set_summary(outputs)
    assert summary is not None
    point = summary["points"][0]
    assert point["projection_available"] is False
    assert "reference_overlay" in point["projection_unavailable_reason"]


def test_projection_caps_review_lines_at_sixteen() -> None:
    outputs = _crop_set_outputs()
    outputs["crop_set"]["review_lines"] = [f"line-{i}" for i in range(20)]
    summary = project_point_crop_set_summary(outputs)
    assert summary is not None
    assert len(summary["review_lines"]) == 16


def test_projection_caps_points_at_sixteen() -> None:
    outputs = _crop_set_outputs()
    outputs["crop_set"]["points"] = [
        {
            "letter": chr(ord("A") + i),
            "alias": f"p{i}",
            "crop_ref": f"image:derived:c{i}",
            "point_norm": [0.1, 0.1],
            "size": "small",
            "shape": "square",
        }
        for i in range(20)
    ]
    summary = project_point_crop_set_summary(outputs)
    assert summary is not None
    assert len(summary["points"]) == 16
