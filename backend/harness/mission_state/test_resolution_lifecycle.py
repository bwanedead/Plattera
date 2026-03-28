from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.harness.mission_state.resolution_lifecycle import (
    compute_emergent_state_after_resolver_move,
    count_tail_resolver_moves,
    edit_plan_has_ops,
    emergent_recency_rank,
    is_allowed_manual_emergent_transition,
    stamp_harness_lifecycle_domain,
)
from backend.harness.mission_state.resolution_projection import resolution_item_row_dict
from backend.harness.mission_state.resolution_updates import apply_resolution_changes, normalize_resolution_change


def test_gather_opens_then_investigating_without_auto_blocked_repeat_transition() -> None:
    assert compute_emergent_state_after_resolver_move(
        "open",
        "gather_more_evidence",
        repeat_without_signal=False,
        consecutive_gather_tail=1,
        edit_plan_has_ops_flag=False,
    ) == "investigating"
    assert compute_emergent_state_after_resolver_move(
        "investigating",
        "gather_more_evidence",
        repeat_without_signal=True,
        consecutive_gather_tail=2,
        edit_plan_has_ops_flag=False,
    ) is None


def test_request_human_feedback_sets_waiting_human() -> None:
    assert compute_emergent_state_after_resolver_move(
        "investigating",
        "request_human_feedback",
        repeat_without_signal=False,
        consecutive_gather_tail=0,
        edit_plan_has_ops_flag=False,
    ) == "waiting_human"


def test_apply_edit_plan_narrows_when_ops_present() -> None:
    assert compute_emergent_state_after_resolver_move(
        "investigating",
        "apply_edit_plan",
        repeat_without_signal=False,
        consecutive_gather_tail=0,
        edit_plan_has_ops_flag=True,
    ) == "narrowed"


def test_mark_resolved_and_blocked_moves() -> None:
    assert compute_emergent_state_after_resolver_move(
        "open",
        "mark_resolved_no_edit",
        repeat_without_signal=False,
        consecutive_gather_tail=0,
        edit_plan_has_ops_flag=False,
    ) == "resolved"
    assert compute_emergent_state_after_resolver_move(
        "investigating",
        "mark_blocked",
        repeat_without_signal=False,
        consecutive_gather_tail=0,
        edit_plan_has_ops_flag=False,
    ) == "blocked"


def test_count_tail_resolver_moves() -> None:
    assert count_tail_resolver_moves(
        [
            {"decision_key": "harness:emergent:abc", "move": "gather_more_evidence"},
            {"decision_key": "harness:emergent:abc", "move": "gather_more_evidence"},
            {"decision_key": "other", "move": "x"},
        ],
        decision_key="harness:emergent:abc",
        move="gather_more_evidence",
    ) == 0
    assert count_tail_resolver_moves(
        [
            {"decision_key": "harness:emergent:abc", "move": "gather_more_evidence"},
            {"decision_key": "harness:emergent:abc", "move": "gather_more_evidence"},
        ],
        decision_key="harness:emergent:abc",
        move="gather_more_evidence",
    ) == 2


def test_edit_plan_has_ops_helper() -> None:
    assert edit_plan_has_ops({"edit_plan": {"ops": [{"op_id": "1"}]}}) is True
    assert edit_plan_has_ops({"edit_plan": {"ops": []}}) is False


def test_emergent_recency_rank() -> None:
    row = {"domain_payload": {"harness_lifecycle": {"last_event_at_epoch": 1000, "created_at_epoch": 900}}}
    assert emergent_recency_rank(row, now_epoch=1000) == 0
    assert emergent_recency_rank(row, now_epoch=100_000) == 2


def test_stamp_harness_lifecycle_domain_merges() -> None:
    first = stamp_harness_lifecycle_domain({}, new_state="open", reason_code="promoted", now_epoch=50)
    assert first["harness_lifecycle"]["created_at_epoch"] == 50
    second = stamp_harness_lifecycle_domain(first, new_state="investigating", reason_code="move", now_epoch=60)
    assert second["harness_lifecycle"]["created_at_epoch"] == 50
    assert second["harness_lifecycle"]["last_transition_at_epoch"] == 60


def test_is_allowed_manual_emergent_transition() -> None:
    assert is_allowed_manual_emergent_transition("open", "superseded") is True
    assert is_allowed_manual_emergent_transition("resolved", "open") is False


def test_normalize_update_item_state() -> None:
    row = normalize_resolution_change(
        {
            "op": "update_item_state",
            "target_item_id": "harness:emergent:deadbeef01",
            "new_state": "superseded",
            "reason": "absorbed",
        }
    )
    assert row["op"] == "update_item_state"
    assert row["new_state"] == "superseded"


def test_apply_update_item_state_on_emergent() -> None:
    out = apply_resolution_changes(
        [
            normalize_resolution_change(
                {
                    "op": "update_item_state",
                    "target_item_id": "harness:emergent:abc123",
                    "new_state": "superseded",
                    "reason": "dup",
                }
            )
        ],
        source_ledger={"items": []},
        emergent_items=[
            resolution_item_row_dict(
                item_id="harness:emergent:abc123",
                title="t",
                kind="k",
                state="open",
                materiality="high",
                blocking_impact="domain_owned_label",
                evidence_refs=["e"],
                resolution_condition="rc",
                provenance="harness.emergent.v1",
            )
        ],
        context_notes_by_item_id={},
        projected_source_items=[],
    )
    assert any(str(x.get("op")) == "update_item_state" for x in out.get("accepted") or [])
    assert (out["emergent_items"] or [])[0].get("state") == "superseded"
