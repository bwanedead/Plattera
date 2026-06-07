"""Tests for delegate observation worklist timeline rendering."""

from __future__ import annotations

from harness.audit.delegate_observation_worklist_timeline import (
    render_delegate_observation_worklist_timeline,
)
from harness.audit.human_timeline import render_timeline


def _worklist_block() -> dict:
    return {
        "counts": {"unintegrated_completed": 1},
        "reminder": (
            "Completed delegate observations are available. "
            "Before making new crops or rerunning delegates, integrate target reads."
        ),
        "rows": [
            {
                "ref_id": "subtask:turn14:read_p1_call3",
                "alias": "read_p1_call3",
                "turn_index": 14,
                "status": "completed",
                "context_refs": ["image:derived:crop-p1"],
                "task_response_preview": "thence S. 4° 00' E.",
                "source_visible_text_preview": "said parcel of land",
                "subtask_trace": {
                    "total_seconds": 132.2,
                    "model_call_seconds": 132.0,
                    "retry_count": 0,
                    "prompt_char_count": 4195,
                    "image_attachment_count": 1,
                },
            }
        ],
    }


def test_timeline_renders_delegate_observation_worklist_rows_and_timing() -> None:
    turn = {
        "turn_index": 15,
        "prompt_observability_summary": {
            "delegate_observation_worklist": _worklist_block(),
        },
    }
    lines = render_delegate_observation_worklist_timeline(turn)
    body = "\n".join(lines)
    assert "Delegate observation worklist:" in body
    assert "unintegrated_completed: 1" in body
    assert "subtask:turn14:read_p1_call3" in body
    assert "context_refs:" in body
    assert "task_response:" in body
    assert "source_visible_text:" in body
    assert "timing:" in body
    assert "wall=132.2s" in body
    assert "model=132.0s" in body
    assert "b64" not in body.lower()


def test_human_timeline_includes_delegate_observation_worklist_section() -> None:
    turn = {
        "turn_index": 15,
        "parse_ok": True,
        "prompt_observability_summary": {
            "delegate_observation_worklist": _worklist_block(),
        },
    }
    body = render_timeline([turn])
    assert "Delegate observation worklist:" in body
    assert "reminder:" in body
