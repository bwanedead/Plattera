from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.harness.work_board.recent_iteration_lane import build_recent_iteration_lane


def test_rich_capsule_includes_board_progress_compact() -> None:
    log = [
        {
            "iteration": 1,
            "decision_key": "harness:emergent:abc123def456",
            "move": "gather_more_evidence",
            "outcome": "ok",
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
    lane = build_recent_iteration_lane(log, current_iteration=1)
    rich = lane.get("rich_capsules") or []
    assert rich
    steps = rich[0].get("steps") or []
    assert steps
    compact = steps[0].get("board_progress_compact")
    assert isinstance(compact, dict)
    assert compact.get("event") == "lifecycle_transition"
    assert compact.get("after") == "investigating"
