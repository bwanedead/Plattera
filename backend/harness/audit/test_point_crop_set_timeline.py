"""Timeline rendering tests for point crop set outputs."""

from __future__ import annotations

from harness.audit.human_timeline import render_timeline
from harness.audit.point_crop_set_timeline import render_point_crop_set_tool_output


def _outputs(*, sub_action: str = "point_crops") -> dict:
    return {
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
                    "box_px": [10, 20, 30, 40],
                    "size": "medium",
                    "shape": "wide",
                    "zoom_factor": 2.25,
                    "box_norm": [0.1, 0.25, 0.4, 0.5],
                    "projection_available": True,
                    "root_source_ref": "image:assoc:tx-1:original",
                    "root_point_norm": [0.51, 0.63],
                    "root_box_norm": [0.47, 0.6, 0.56, 0.66],
                }
            ],
            "grid": {"enabled": True, "divisions": 4},
            "legend": {"size_colors": {"small": [1, 2, 3]}},
        },
    }


def test_timeline_renders_point_crop_set_creation() -> None:
    body = render_timeline(
        [
            {
                "turn_index": 2,
                "parse_ok": True,
                "tool_result_raw": {
                    "execution_state": "executed",
                    "artifact_refs": ["image:derived:master-1", "image:derived:crop-a"],
                    "outputs": _outputs(),
                },
            }
        ]
    )
    assert "Point Crop Set" in body
    assert "sub_action: point_crops" in body
    assert "master_overlay_ref: image:derived:master-1" in body
    assert "A | parcel_1_tie_bearing" in body
    assert "zoom=2.25" in body
    assert "root_point_norm:" in body
    assert "overlay_grid:" in body
    assert "b64" not in body.lower()
    assert "C:\\" not in body


def test_timeline_renders_projection_unavailable_reason() -> None:
    outputs = _outputs()
    outputs["crop_set"]["points"][0]["projection_available"] = False
    outputs["crop_set"]["points"][0]["projection_unavailable_reason"] = (
        "parent transform reference_overlay does not preserve source-coordinate mapping"
    )
    body = render_timeline(
        [
            {
                "turn_index": 2,
                "parse_ok": True,
                "tool_result_raw": {"execution_state": "executed", "outputs": outputs},
            }
        ]
    )
    assert "projection_unavailable:" in body
    assert "reference_overlay" in body


def test_timeline_renders_adjustment_zoom_lineage() -> None:
    outputs = _outputs(sub_action="point_crops_adjust")
    outputs["previous_crop_set_overlay_ref"] = "image:derived:master-old"
    outputs["adjustments_applied"] = [
        {
            "target": {"letter": "A"},
            "prior_point_norm": [0.4, 0.5],
            "new_point_norm": [0.42, 0.58],
            "prior_size": "small",
            "new_size": "medium",
            "prior_shape": "square",
            "new_shape": "wide",
            "prior_zoom_factor": 3.0,
            "new_zoom_factor": 2.25,
        }
    ]
    body = render_timeline(
        [
            {
                "turn_index": 3,
                "parse_ok": True,
                "tool_result_raw": {"execution_state": "executed", "outputs": outputs},
            }
        ]
    )
    assert "zoom: 3.0->2.25" in body


def test_timeline_renders_graph_ref_when_present() -> None:
    outputs = _outputs()
    outputs["crop_set"]["points"][0]["graph_ref"] = {
        "item_id": "parcel_1_description",
        "covered_unit_id": "p1_tie_bearing",
    }
    body = render_timeline(
        [
            {
                "turn_index": 2,
                "parse_ok": True,
                "tool_result_raw": {"execution_state": "executed", "outputs": outputs},
            }
        ]
    )
    assert "graph_ref:" in body
    assert "parcel_1_description" in body


def test_timeline_renders_point_crop_set_adjustment_lineage() -> None:
    outputs = _outputs(sub_action="point_crops_adjust")
    outputs["previous_crop_set_overlay_ref"] = "image:derived:master-old"
    outputs["adjustments_applied"] = [
        {
            "target": {"letter": "A"},
            "prior_point_norm": [0.4, 0.5],
            "new_point_norm": [0.42, 0.58],
            "prior_size": "small",
            "new_size": "medium",
            "prior_shape": "square",
            "new_shape": "wide",
            "shift_norm": [0.02, 0.08],
        }
    ]
    body = render_timeline(
        [
            {
                "turn_index": 3,
                "parse_ok": True,
                "tool_result_raw": {"execution_state": "executed", "outputs": outputs},
            }
        ]
    )
    assert "previous_crop_set_overlay_ref: image:derived:master-old" in body
    assert "adjustments_applied:" in body
    assert "shift_norm:" in body


def test_point_crop_timeline_helper_bounds_sixteen_points() -> None:
    points = [
        {
            "letter": chr(ord("A") + i),
            "alias": f"p{i}",
            "crop_ref": f"image:derived:c{i}",
            "size": "small",
            "shape": "square",
        }
        for i in range(20)
    ]
    lines = render_point_crop_set_tool_output(
        {
            "sub_action": "point_crops",
            "crop_set": {"points": points},
        }
    )
    rendered_points = [line for line in lines if line.strip().startswith("- ") and "crop_ref:" in line]
    assert len(rendered_points) == 16
