"""Tests for source-window edge metadata helpers."""

from __future__ import annotations

from tooling.mapping.transcript_edit.root_projection import ProjectionContext
from tooling.mapping.transcript_edit.source_window import (
    build_crop_frame_edge_room,
    build_source_window,
    compact_source_window_for_projection,
    format_crop_frame_edge_room_compact,
    render_source_window_timeline_line,
)


def _ctx(
    *,
    available: bool = True,
    root_ref: str = "image:assoc:tx-1:original",
    chain: list[dict] | None = None,
) -> ProjectionContext:
    return ProjectionContext(
        local_source_ref="image:assoc:tx-1:original",
        root_source_ref=root_ref if available else None,
        local_width_height=[100, 80],
        root_width_height=[100, 80],
        projection_available=available,
        projection_unavailable_reason=None if available else "unsupported",
        projection_chain=chain or [],
    )


def test_bottom_crop_touches_source_edge_and_cannot_expand_down() -> None:
    window = build_source_window(
        local_source_ref="image:assoc:tx-1:original",
        local_box_norm=[0.0, 0.8, 1.0, 1.0],
        projection_ctx=_ctx(),
    )
    assert window["touches_source_edge"]["bottom"] is True
    assert window["can_expand"]["down"] is False
    assert window["room_to_source_edge_norm"]["bottom"] == 0.0
    assert window["position_label"] == "bottom_full_width"
    assert "available source image" in window["edge_summary"]


def test_middle_crop_has_room_on_all_sides() -> None:
    window = build_source_window(
        local_source_ref="image:assoc:tx-1:original",
        local_box_norm=[0.2, 0.3, 0.6, 0.7],
        projection_ctx=_ctx(),
    )
    assert window["touches_source_edge"] == {
        "left": False,
        "top": False,
        "right": False,
        "bottom": False,
    }
    assert window["can_expand"] == {
        "left": True,
        "up": True,
        "right": True,
        "down": True,
    }
    assert window["position_label"] == "middle"


def test_derived_crop_composes_root_box_norm_and_root_edge_facts() -> None:
    chain = [
        {
            "ref_id": "image:derived:parent",
            "sub_action": "crop",
            "parent_ref_id": "image:assoc:tx-1:original",
            "transform_metadata": {
                "resolved_geometry": {"box_norm": [0.0, 0.25, 1.0, 0.75]},
            },
        }
    ]
    window = build_source_window(
        local_source_ref="image:derived:parent",
        local_box_norm=[0.0, 0.5, 1.0, 1.0],
        projection_ctx=ProjectionContext(
            local_source_ref="image:derived:parent",
            root_source_ref="image:assoc:tx-1:original",
            local_width_height=[100, 40],
            root_width_height=[100, 80],
            projection_available=True,
            projection_unavailable_reason=None,
            projection_chain=chain,
        ),
    )
    assert window["local_box_norm"] == [0.0, 0.5, 1.0, 1.0]
    assert window["root_box_norm"] == [0.0, 0.5, 1.0, 0.75]
    assert window["touches_source_edge"]["bottom"] is True
    assert window["touches_root_source_edge"]["bottom"] is False
    assert window["room_to_root_source_edge_norm"]["bottom"] == 0.25


def test_compact_projection_keeps_edge_fields_only() -> None:
    window = build_source_window(
        local_source_ref="image:assoc:tx-1:original",
        local_box_norm=[0.0, 0.8, 1.0, 1.0],
        projection_ctx=_ctx(),
    )
    compact = compact_source_window_for_projection(window)
    assert compact is not None
    assert compact["touches_source_edge"]["bottom"] is True
    assert "local_source_ref" not in compact
    assert "absolute_path" not in compact


def test_timeline_line_for_bottom_edge_crop() -> None:
    window = build_source_window(
        local_source_ref="image:assoc:tx-1:original",
        local_box_norm=[0.0, 0.8, 1.0, 1.0],
        projection_ctx=_ctx(),
    )
    line = render_source_window_timeline_line(window)
    assert line is not None
    assert "source_window:" in line
    assert "bottom" in line
    assert "can_expand_down=false" in line


def test_build_crop_frame_edge_room_interior_has_room_all_directions() -> None:
    frame = build_crop_frame_edge_room(box_norm=[0.2, 0.3, 0.6, 0.7])
    assert frame["crop_frame_touches_edge"] == {
        "x_minus": False,
        "x_plus": False,
        "y_minus": False,
        "y_plus": False,
    }
    assert frame["crop_frame_can_expand"] == {
        "x_minus": True,
        "x_plus": True,
        "y_minus": True,
        "y_plus": True,
    }
    assert frame["crop_frame_room_norm"]["y_plus"] == 0.3


def test_build_crop_frame_edge_room_bottom_right_edge() -> None:
    frame = build_crop_frame_edge_room(box_norm=[0.28, 0.875, 1.0, 1.0])
    assert frame["crop_frame_room_norm"]["y_plus"] == 0.0
    assert frame["crop_frame_touches_edge"]["y_plus"] is True
    assert frame["crop_frame_can_expand"]["y_plus"] is False
    assert frame["crop_frame_touches_edge"]["x_plus"] is True


def test_build_crop_frame_edge_room_root_equivalents() -> None:
    frame = build_crop_frame_edge_room(
        box_norm=[0.0, 0.5, 1.0, 1.0],
        root_box_norm=[0.0, 0.625, 1.0, 0.75],
    )
    assert frame["crop_frame_touches_edge"]["y_plus"] is True
    assert frame["root_crop_frame_touches_edge"]["y_plus"] is False
    assert frame["root_crop_frame_room_norm"]["y_plus"] == 0.25


def test_format_crop_frame_edge_room_compact() -> None:
    frame = build_crop_frame_edge_room(box_norm=[0.28, 0.875, 1.0, 1.0])
    text = format_crop_frame_edge_room_compact(
        room=frame["crop_frame_room_norm"],
        touches=frame["crop_frame_touches_edge"],
    )
    assert text is not None
    assert "edge=x+,y+" in text
    assert "y+0.0" in text
