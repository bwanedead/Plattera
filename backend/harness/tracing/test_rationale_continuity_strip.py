"""Tests for execution-only rationale continuity strip."""

from __future__ import annotations

from harness.tracing.rationale_continuity_strip import build_rationale_continuity_strip


def test_rationale_strip_derives_from_execution_phase_only() -> None:
    raw = [
        {
            "phase": "execution",
            "iteration_index": 1,
            "payload": {"execution_state": "executed", "action_type": "noop"},
            "reason_code": None,
        },
        {
            "phase": "focus_selection",
            "iteration_index": 1,
            "payload": {"focus_key": "should_ignore"},
        },
    ]
    strip = build_rationale_continuity_strip(raw, max_entries=5)
    assert len(strip) == 1
    assert strip[0]["iteration_index"] == 1
    assert strip[0]["outcome_summary"] == "executed"


def test_rationale_strip_refused_iteration() -> None:
    raw = [
        {
            "phase": "execution",
            "iteration_index": 0,
            "payload": {"execution_state": "refused", "action_type": "x", "retryable": False},
            "reason_code": "inv",
        }
    ]
    strip = build_rationale_continuity_strip(raw)
    assert strip[0]["carry_forward_hint"] != ""
    assert "refused" in strip[0]["outcome_summary"]
