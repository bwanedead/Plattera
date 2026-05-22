from __future__ import annotations

import json

from harness.runtime.orchestration.recent_result_projection import (
    project_recent_result_for_prompt,
    project_recent_tool_result_slices_for_prompt,
)


def test_newest_slice_keeps_detail_older_strips_excerpt() -> None:
    slices = [
        {
            "kernel_turn_index": 1,
            "action_type": "read_artifact",
            "outputs_excerpt": {"text": "old detail"},
            "artifact_refs": ["artifact://old"],
        },
        {
            "kernel_turn_index": 5,
            "action_type": "write_artifact",
            "outputs_excerpt": {"text": "fresh detail"},
            "artifact_refs": ["artifact://fresh"],
        },
    ]
    projected = project_recent_tool_result_slices_for_prompt(
        slices,
        current_turn=5,
        hot_refs=frozenset(),
    )
    assert "outputs_excerpt" not in projected[0]
    assert projected[0]["action_type"] == "read_artifact"
    assert projected[1]["outputs_excerpt"] == {"text": "fresh detail"}
    assert projected[1]["action_type"] == "write_artifact"
    assert projected[1]["artifact_refs"] == ["artifact://fresh"]


def test_pinned_ref_keeps_older_slice_hot() -> None:
    row = {
        "kernel_turn_index": 1,
        "action_type": "transform_artifact",
        "outputs_excerpt": {"crop": "detail"},
        "artifact_refs": ["artifact://pinned"],
    }
    projected = project_recent_tool_result_slices_for_prompt(
        [row],
        current_turn=4,
        hot_refs=frozenset({"artifact://pinned"}),
    )
    assert projected[0]["outputs_excerpt"] == {"crop": "detail"}


def test_no_b64_in_projected_results() -> None:
    row = {
        "kernel_turn_index": 3,
        "action_type": "noop",
        "outputs_excerpt": {"image_b64": "abc"},
    }
    compact = project_recent_result_for_prompt(row, age=3, keep_hot=False)
    dumped = json.dumps(compact).lower()
    assert "b64" not in dumped or "excerpt_omitted" in dumped
