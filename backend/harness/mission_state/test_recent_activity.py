from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.mission_state import RECENT_ACTIVITY_LANE_VERSION, build_recent_activity_lane


def test_recent_activity_groups_by_iteration_newest_first() -> None:
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


def test_recent_activity_keeps_board_progress_but_not_future_motion_hint() -> None:
    log = [
        {
            "iteration": 1,
            "decision_key": "harness:emergent:abc123def456",
            "move": "gather_more_evidence",
            "outcome": "ok",
            "state_delta_hint": "move=gather_more_evidence; widened evidence",
            "next_open_move_hint": "should_not_surface",
            "board_progress": {
                "event": "lifecycle_transition",
                "board_item_id": "harness:emergent:abc123def456",
                "board_state_before": "open",
                "board_state_after": "investigating",
                "board_transition_reason": "resolver_move:gather_more_evidence",
                "board_recency_rank": 0,
            },
        }
    ]
    lane = build_recent_activity_lane(log, current_iteration=1)
    step = lane["rich_capsules"][0]["steps"][0]
    compact = step["board_progress_compact"]
    assert isinstance(compact, dict)
    assert compact["after"] == "investigating"
    assert "next_move_more_likely" not in step
