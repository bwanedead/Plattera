"""Tests for deterministic point-crop target mapping helpers."""

from __future__ import annotations

import pytest

from tooling.mapping.transcript_edit.point_crop_target_mapping import (
    DEFAULT_TARGET_HINT_ROLE,
    apply_target_mapping_to_point,
    copy_target_mapping_fields,
    format_target_mapping_parts,
    normalize_target_mapping_fields,
)
from tooling.mapping.transcript_edit.point_crops import PointCropParamError


def test_normalize_target_mapping_defaults_hint_role() -> None:
    out = normalize_target_mapping_fields(
        {
            "target_atom_id": "p1_call1_distance",
            "target_hint": "542 feet",
        },
        field_prefix="params.points[0]",
    )
    assert out["target_atom_id"] == "p1_call1_distance"
    assert out["target_hint"] == "542 feet"
    assert out["target_hint_role"] == DEFAULT_TARGET_HINT_ROLE


def test_apply_target_mapping_allows_clear_on_adjust() -> None:
    point = {
        "target_atom_id": "p1_call1_distance",
        "target_hint": "542 feet",
        "target_hint_role": DEFAULT_TARGET_HINT_ROLE,
    }
    apply_target_mapping_to_point(
        point,
        {"target_hint": None, "target_hint_role": None},
        field_prefix="params.adjust[0]",
        allow_clear=True,
    )
    assert "target_hint" not in point
    assert "target_hint_role" not in point
    assert point["target_atom_id"] == "p1_call1_distance"


def test_format_target_mapping_parts_escapes_hint() -> None:
    parts = format_target_mapping_parts(
        {
            "target_atom_id": "p1_call1_distance",
            "target_hint": '542 "feet"',
        }
    )
    assert parts[0] == "target=p1_call1_distance"
    assert parts[1] == 'hint="542 \\"feet\\""'


def test_copy_target_mapping_fields_is_bounded() -> None:
    copied = copy_target_mapping_fields(
        {
            "target_atom_id": "p1_call1_distance",
            "target_context_id": "parcel_1_t0_shape",
            "target_hint": "542 feet",
            "target_hint_role": DEFAULT_TARGET_HINT_ROLE,
            "alias": "ignored",
        }
    )
    assert copied["target_atom_id"] == "p1_call1_distance"
    assert copied["target_context_id"] == "parcel_1_t0_shape"
    assert "alias" not in copied


def test_rejects_multiline_target_hint() -> None:
    with pytest.raises(PointCropParamError):
        normalize_target_mapping_fields(
            {"target_hint": "line1\nline2"},
            field_prefix="params.points[0]",
        )
