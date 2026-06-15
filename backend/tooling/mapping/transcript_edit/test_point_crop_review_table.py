"""Unit tests for point-crop review table helpers."""

from __future__ import annotations

import json

from tooling.mapping.transcript_edit.coordinate_lattice import nearest_lattice_anchor
from tooling.mapping.transcript_edit.point_crop_review_table import (
    attach_review_table_to_crop_set,
    build_crop_set_review_table,
    build_review_row,
    render_review_line,
    review_table_from_crop_set,
)


def _sample_point(**overrides) -> dict:
    base = {
        "letter": "B",
        "alias": "parcel_1_call_1_bearing",
        "crop_ref": "image:derived:crop-b",
        "point_norm": [0.732, 0.684],
        "box_norm": [0.652, 0.604, 0.812, 0.764],
        "size": "small_plus",
        "shape": "wide",
        "zoom_factor": 2.75,
    }
    base.update(overrides)
    return base


def test_nearest_major_anchor_and_offset_example() -> None:
    anchor = nearest_lattice_anchor([0.732, 0.684])
    assert anchor == [0.7, 0.7]
    from tooling.mapping.transcript_edit.coordinate_lattice import offset_from_anchor

    assert offset_from_anchor([0.732, 0.684], anchor) == [0.032, -0.016]


def test_rendered_line_includes_span_line_intent() -> None:
    row = build_review_row(_sample_point(size="span_line", shape="wide", crop_intent="span_line"))
    line = render_review_line(row)
    assert "size=span_line/wide" in line
    assert "intent=span_line" in line


def test_rendered_line_includes_trim_status() -> None:
    row = build_review_row(
        _sample_point(
            size="span_line",
            shape="wide",
            crop_intent="span_line",
            trim_to_text_block=True,
            trim_axis="x",
            trim_applied=True,
            trim_padding_norm=0.02,
        )
    )
    line = render_review_line(row)
    assert "trim=x applied" in line
    assert "padding=0.02" in line


def test_rendered_line_includes_crop_frame_room_and_edge() -> None:
    row = build_review_row(
        _sample_point(
            box_norm=[0.28, 0.875, 1.0, 1.0],
            crop_frame_room_norm={
                "x_minus": 0.28,
                "x_plus": 0.0,
                "y_minus": 0.875,
                "y_plus": 0.0,
            },
            crop_frame_touches_edge={
                "x_minus": False,
                "x_plus": True,
                "y_minus": False,
                "y_plus": True,
            },
            crop_frame_can_expand={
                "x_minus": True,
                "x_plus": False,
                "y_minus": True,
                "y_plus": False,
            },
        )
    )
    line = render_review_line(row)
    assert "edge=x+,y+" in line
    assert "room=[x-0.28 x+0.0 y-0.875 y+0.0]" in line


def test_review_row_includes_crop_frame_fields() -> None:
    row = build_review_row(_sample_point(box_norm=[0.2, 0.3, 0.6, 0.7]))
    assert "crop_frame_room_norm" in row
    assert row["crop_frame_touches_edge"]["y_plus"] is False
    assert row["crop_frame_can_expand"]["y_plus"] is True


def test_rendered_line_includes_signed_offsets() -> None:
    row = build_review_row(_sample_point())
    line = render_review_line(row)
    assert "offset=[+0.032,-0.016]" in line
    assert "anchor=[0.7,0.7]" in line
    assert "crop=image:derived:crop-b" in line


def test_build_crop_set_review_table_bounded_ordered() -> None:
    points = [_sample_point(letter=chr(ord("A") + i), alias=f"p{i}") for i in range(20)]
    table = build_crop_set_review_table(points)
    assert len(table["review_rows"]) == 16
    assert len(table["review_lines"]) == 16
    assert table["review_rows"][0]["letter"] == "A"
    assert table["review_rows"][-1]["letter"] == "P"


def test_review_rows_exclude_b64_paths_and_prompt_fields() -> None:
    point = _sample_point(
        b64="secret",
        absolute_path="C:\\tmp\\x.png",
        prompt="do not include",
        crop_img=b"bytes",
    )
    row = build_review_row(point)
    dumped = json.dumps(row).lower()
    assert "b64" not in dumped
    assert "c:\\" not in dumped
    assert "prompt" not in dumped
    assert "bytes" not in dumped


def test_attach_and_reconstruct_from_crop_set() -> None:
    crop_set = {
        "points": [_sample_point()],
        "coordinate_lattice": {"major_step_norm": 0.1},
        "grid": {"major_step_norm": 0.2},
    }
    attach_review_table_to_crop_set(crop_set)
    assert crop_set["review_lines"]
    reconstructed = review_table_from_crop_set(
        {
            "points": crop_set["points"],
            "coordinate_lattice": crop_set["coordinate_lattice"],
            "grid": crop_set["grid"],
        }
    )
    assert reconstructed["review_lines"] == crop_set["review_lines"]


def test_review_table_uses_coordinate_lattice_major_step() -> None:
    point = _sample_point(point_norm=[0.23, 0.27])
    table = build_crop_set_review_table(
        [point],
        overlay_metadata={
            "coordinate_lattice": {"major_step_norm": 0.05},
            "grid": {"major_step_norm": 0.10},
        },
    )
    row = table["review_rows"][0]
    assert row["nearest_major_anchor"] == [0.25, 0.25]
