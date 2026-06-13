"""Tests for point-crop master overlay key band helpers."""

from __future__ import annotations

from tooling.mapping.transcript_edit.point_crop_key_band import (
    MAX_POINT_KEY_ROWS,
    build_point_key_lines,
    compact_size_shape_label,
    compute_point_key_band_height,
    render_point_key_line,
)


def test_render_point_key_line_includes_letter_alias_and_point() -> None:
    line = render_point_key_line(
        {
            "letter": "A",
            "alias": "deed_range75",
            "point_norm": [0.65, 0.4],
            "size": "small_plus",
            "shape": "wide",
        }
    )
    assert line == "A deed_range75 point=[0.650,0.400] small+/wide"


def test_build_point_key_lines_caps_at_sixteen_and_adds_overflow_marker() -> None:
    points = [
        {
            "letter": chr(ord("A") + i),
            "alias": f"p{i}",
            "point_norm": [0.1, 0.2],
            "size": "small",
            "shape": "square",
        }
        for i in range(20)
    ]
    table = build_point_key_lines(points)
    assert len(table["point_key_lines"]) == MAX_POINT_KEY_ROWS + 1
    assert table["point_key_lines"][-1] == "+4 more"
    assert table["point_key_overflow_count"] == 4


def test_compact_size_shape_prefers_crop_intent() -> None:
    assert compact_size_shape_label("medium", "wide", crop_intent="span_line") == "span_line"


def test_compute_point_key_band_height_zero_without_points() -> None:
    assert compute_point_key_band_height(0) == 0
