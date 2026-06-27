"""Tests for deep-merge patch behavior."""

from __future__ import annotations

from tooling.mapping.deed_to_ir.patch_deep_merge import deep_merge_patch


def test_deep_merge_preserves_nested_siblings() -> None:
    base = {
        "op_expr": {
            "op_name": "CourseTraverse",
            "operands": ["parcel_1_pob"],
            "params": {"courses": [{"bearing": 1.0, "distance": 2.0}]},
        }
    }
    patch = {
        "op_expr": {
            "params": {
                "courses": [{"bearing": 68.5, "distance": 542.0}],
            }
        }
    }
    merged = deep_merge_patch(base, patch)
    assert merged["op_expr"]["op_name"] == "CourseTraverse"
    assert merged["op_expr"]["operands"] == ["parcel_1_pob"]
    assert merged["op_expr"]["params"]["courses"] == [{"bearing": 68.5, "distance": 542.0}]


def test_deep_merge_null_clears_scalar_field() -> None:
    merged = deep_merge_patch({"label": "keep"}, {"label": None})
    assert merged["label"] is None
