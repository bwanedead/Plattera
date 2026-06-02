"""Tests for shared coordinate lattice helpers."""

from __future__ import annotations

import json

from tooling.mapping.transcript_edit.coordinate_lattice import (
    build_coordinate_lattice_metadata,
    build_compat_grid_metadata,
    major_step_from_metadata,
    nearest_lattice_anchor,
    offset_from_anchor,
)


def test_build_coordinate_lattice_metadata_shape() -> None:
    lattice = build_coordinate_lattice_metadata()
    assert lattice["major_step_norm"] == 0.10
    assert lattice["minor_step_norm"] == 0.025
    assert lattice["major_labels"] == [
        "0.10",
        "0.20",
        "0.30",
        "0.40",
        "0.50",
        "0.60",
        "0.70",
        "0.80",
        "0.90",
    ]
    assert lattice["minor_labels"] is False
    assert lattice["coordinate_space"] == "normalized_source_image"
    assert lattice["origin"] == "top_left"
    assert lattice["x_increases"] == "right"
    assert lattice["y_increases"] == "down"
    assert lattice["label_style"]["background"] is True
    assert lattice["label_style"]["opposite_margins"] is True


def test_compat_grid_metadata_mirrors_lattice_steps() -> None:
    lattice = build_coordinate_lattice_metadata()
    grid = build_compat_grid_metadata(lattice, enabled=True, cols=10, rows=10, cell_labels=True)
    assert grid["major_step_norm"] == lattice["major_step_norm"]
    assert grid["minor_step_norm"] == lattice["minor_step_norm"]
    assert grid["coordinate_space"] == "source_image_norm"
    assert grid["cols"] == 10
    assert grid["cell_labels"] is True


def test_major_step_prefers_coordinate_lattice_over_grid() -> None:
    container = {
        "coordinate_lattice": {"major_step_norm": 0.05},
        "grid": {"major_step_norm": 0.10},
    }
    assert major_step_from_metadata(container) == 0.05


def test_nearest_lattice_anchor_and_offset() -> None:
    anchor = nearest_lattice_anchor([0.732, 0.684])
    assert anchor == [0.7, 0.7]
    assert offset_from_anchor([0.732, 0.684], anchor) == [0.032, -0.016]


def test_lattice_metadata_has_no_paths_or_b64() -> None:
    lattice = build_coordinate_lattice_metadata()
    dumped = json.dumps(lattice).lower()
    assert "b64" not in dumped
    assert "c:\\" not in dumped
    assert "absolute_path" not in dumped
