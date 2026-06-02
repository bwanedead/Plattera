"""Timeline rendering tests for point crop set outputs."""

from __future__ import annotations

from pathlib import Path

from harness.audit.artifact_ref_links import ArtifactLinkContext, build_ref_path_index
from harness.audit.human_timeline import render_timeline
from harness.audit.delegate_subtask_timeline import render_delegate_subtask_section
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
    assert "Point crop set:" in body
    assert "master overlay: `image:derived:master-1`" in body
    assert "A `parcel_1_tie_bearing`" in body
    assert "zoom=2.25" in body
    assert "root=[" in body
    assert "overlay grid: yes" in body
    assert "Review table:" in body
    assert "anchor=[" in body
    assert "offset=[" in body
    assert "b64" not in body.lower()
    assert "C:\\" not in body


def test_point_crop_renders_clickable_links_when_paths_resolvable(tmp_path: Path) -> None:
    images = tmp_path / "images"
    images.mkdir()
    master = images / "master.png"
    crop = images / "crop-a.png"
    master.write_bytes(b"png")
    crop.write_bytes(b"png")

    timeline_path = tmp_path / "audit" / "human" / "timeline.md"
    timeline_path.parent.mkdir(parents=True)
    turn = {
        "tool_result_raw": {
            "outputs": {
                **_outputs(),
                "absolute_path": str(master),
                "crop_set": {
                    **_outputs()["crop_set"],
                    "points": [
                        {
                            **_outputs()["crop_set"]["points"][0],
                            "absolute_path": str(crop),
                        }
                    ],
                },
            }
        }
    }
    index = build_ref_path_index(turn=turn)
    assert "image:derived:master-1" in index
    assert "image:derived:crop-a" in index
    context = ArtifactLinkContext(timeline_path=timeline_path, ref_path_index=index)
    outputs = turn["tool_result_raw"]["outputs"]
    lines = render_point_crop_set_tool_output(outputs, link_context=context)
    rendered = "\n".join(lines)

    assert "[open overlay](../../images/master.png)" in rendered
    assert "[open crop](../../images/crop-a.png)" in rendered
    assert "b64" not in rendered.lower()


def test_point_crop_falls_back_to_ref_only_when_paths_missing() -> None:
    lines = render_point_crop_set_tool_output(_outputs())
    rendered = "\n".join(lines)
    assert "`image:derived:master-1`" in rendered
    assert "[open overlay]" not in rendered


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
    assert "previous_crop_set_overlay_ref:" in body
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
    rendered_points = [line for line in lines if line.strip().startswith("- ") and "`p" in line]
    assert len(rendered_points) == 16


def test_inline_image_cap_uses_links_for_overflow(tmp_path: Path) -> None:
    images = tmp_path / "images"
    images.mkdir()
    paths = {}
    for idx in range(4):
        path = images / f"crop-{idx}.png"
        path.write_bytes(b"png")
        paths[f"image:derived:crop-{idx}"] = str(path)

    timeline_path = tmp_path / "audit" / "human" / "timeline.md"
    timeline_path.parent.mkdir(parents=True)
    context = ArtifactLinkContext(timeline_path=timeline_path, ref_path_index=paths, inline_budget=1)
    lines = render_delegate_subtask_section(
        alias="read_many",
        inputs={
            "profile": "transcript_edit.visual_source_observation",
            "task": "Read each crop.",
            "context_refs": [f"image:derived:crop-{idx}" for idx in range(4)],
        },
        item=None,
        link_context=context,
        include_result=False,
    )
    rendered = "\n".join(lines)
    assert rendered.count("![") == 1
    assert "inline image cap reached" in rendered
    assert rendered.count("[open crop]") == 4
