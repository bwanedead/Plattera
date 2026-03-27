from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.emergent_lifecycle_runtime import (
    sync_focused_emergent_item_from_resolver_outcome,
)
from backend.agents.transcript_edit.loop_state import TranscriptEditLoopState


def _one_emergent() -> dict:
    return {
        "item_id": "harness:emergent:abc123def456",
        "title": "Scan integrity branch for mapping closure",
        "kind": "transcript_edit.scan_integrity",
        "state": "open",
        "materiality": "high",
        "blocking_impact": "mapping_blocking",
        "dependencies": [],
        "evidence_refs": ["e1"],
        "alternatives": [],
        "resolution_condition": "Confirm edge",
        "scope": {},
        "context_notes": [],
        "provenance": "harness.emergent.v1",
        "domain_payload": {"harness_lifecycle": {"created_at_epoch": 1, "last_event_at_epoch": 1}},
    }


def test_sync_open_to_investigating_on_gather() -> None:
    st = TranscriptEditLoopState(
        harness_emergent_board_items=[_one_emergent()],
        continuity_log=[],
    )
    obs = sync_focused_emergent_item_from_resolver_outcome(
        st,
        focus_key="harness:emergent:abc123def456",
        move="gather_more_evidence",
        resolver_outcome=None,
        policy_signals={"repeat_without_signal": False},
        now_epoch=10_000,
    )
    assert st.harness_emergent_board_items[0]["state"] == "investigating"
    assert isinstance(obs, dict)
    assert obs.get("board_state_before") == "open"
    assert obs.get("board_state_after") == "investigating"
    assert obs.get("event") == "lifecycle_transition"


def test_sync_keeps_repeat_gather_observational_without_auto_blocked() -> None:
    st = TranscriptEditLoopState(
        harness_emergent_board_items=[{**_one_emergent(), "state": "investigating"}],
        continuity_log=[
            {"decision_key": "harness:emergent:abc123def456", "move": "gather_more_evidence"},
            {"decision_key": "harness:emergent:abc123def456", "move": "gather_more_evidence"},
        ],
    )
    obs = sync_focused_emergent_item_from_resolver_outcome(
        st,
        focus_key="harness:emergent:abc123def456",
        move="gather_more_evidence",
        resolver_outcome=None,
        policy_signals={"repeat_without_signal": True},
    )
    assert st.harness_emergent_board_items[0]["state"] == "investigating"
    assert obs is None


def test_explicit_mark_blocked_still_transitions_and_reports_observations() -> None:
    st = TranscriptEditLoopState(
        harness_emergent_board_items=[{**_one_emergent(), "state": "investigating"}],
        continuity_log=[
            {"decision_key": "harness:emergent:abc123def456", "move": "gather_more_evidence"},
            {"decision_key": "harness:emergent:abc123def456", "move": "gather_more_evidence"},
        ],
    )
    obs = sync_focused_emergent_item_from_resolver_outcome(
        st,
        focus_key="harness:emergent:abc123def456",
        move="mark_blocked",
        resolver_outcome=None,
        policy_signals={"repeat_without_signal": True},
    )
    assert st.harness_emergent_board_items[0]["state"] == "blocked"
    assert isinstance(obs, dict)
    assert obs.get("repeat_without_signal_observed") is True
    assert obs.get("consecutive_gather_tail") == 2


def test_ignores_non_emergent_focus_key() -> None:
    st = TranscriptEditLoopState(
        harness_emergent_board_items=[_one_emergent()],
        continuity_log=[],
    )
    sync_focused_emergent_item_from_resolver_outcome(
        st,
        focus_key="range",
        move="gather_more_evidence",
        resolver_outcome=None,
        policy_signals={},
    )
    assert st.harness_emergent_board_items[0]["state"] == "open"
