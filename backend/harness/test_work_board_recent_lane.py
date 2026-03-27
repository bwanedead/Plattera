from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.mission_state import RECENT_ACTIVITY_LANE_VERSION, build_recent_activity_lane


def test_recent_lane_groups_by_iteration_newest_first() -> None:
    log = [
        {"decision_key": "range", "move": "a", "outcome": "o1", "iteration": 1},
        {"decision_key": "range", "move": "b", "outcome": "o2", "iteration": 2},
        {"decision_key": "section", "move": "c", "outcome": "o3", "iteration": 2},
        {"decision_key": "section", "move": "d", "outcome": "o4", "iteration": 3},
    ]
    lane = build_recent_activity_lane(log, current_iteration=3)
    assert lane["schema_version"] == RECENT_ACTIVITY_LANE_VERSION
    rich = lane["rich_capsules"]
    assert rich
    assert rich[0]["iteration"] == 3
    assert len(rich[0]["steps"]) == 1
    assert rich[0]["steps"][0]["move_chosen"] == "d"


def test_rich_capsule_state_delta_flows_through_without_future_motion_hint() -> None:
    log = [
        {
            "decision_key": "range",
            "move": "apply_edit_plan",
            "outcome": "planned",
            "iteration": 1,
            "state_delta_hint": "move=apply_edit_plan; carry_edit_plan",
            "next_open_move_hint": "posture_allows_repair_when_evidence_supports_safe_edit",
        }
    ]
    lane = build_recent_activity_lane(log, current_iteration=1)
    step = lane["rich_capsules"][0]["steps"][0]
    assert "apply_edit_plan" in (step.get("state_changes_hint") or "")
    assert "next_move_more_likely" not in step


def test_rich_capsule_includes_extended_fields() -> None:
    log = [
        {
            "decision_key": "range",
            "move": "gather_more_evidence",
            "outcome": "added_spans",
            "iteration": 4,
            "focus_source": "legacy_fallback",
            "gate_posture": {"repair_eligible": True},
            "evidence_kind": "open_spans:mode_x",
        }
    ]
    lane = build_recent_activity_lane(log, current_iteration=4)
    step = lane["rich_capsules"][0]["steps"][0]
    assert step["focus_source"] == "legacy_fallback"
    assert step["evidence_used_or_attempted"] == "open_spans:mode_x"
    assert step["gate_posture"] == {"repair_eligible": True}
