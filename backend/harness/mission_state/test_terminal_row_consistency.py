"""Pure terminal-row consistency predicate tests."""

from __future__ import annotations

from harness.mission_state import (
    MAX_TERMINAL_ROW_CONFLICTS,
    REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
    ResolutionCoveredUnit,
    ResolutionItem,
    evaluate_addressed_terminal_row_consistency,
    is_resolved_like,
    live_work_fields_present,
    new_resolution_state,
)


def test_is_resolved_like_uses_closed_like_status_and_earned_determination() -> None:
    assert is_resolved_like(status="closed") is True
    assert is_resolved_like(status="Earned") is True
    assert is_resolved_like(status="resolved") is True
    assert is_resolved_like(status="complete") is True
    assert is_resolved_like(determination="earned") is True
    assert is_resolved_like(status="open") is False
    assert is_resolved_like(status="in_review", determination="provisional") is False
    assert is_resolved_like(status=None, determination=None) is False
    assert is_resolved_like(status=0) is False
    assert is_resolved_like(determination=True) is False


def test_live_work_fields_order_and_exact_bools() -> None:
    assert live_work_fields_present(
        {
            "next_needed_step": "verify",
            "requires_hitl": True,
            "no_further_progress": True,
        }
    ) == ("next_needed_step", "requires_hitl", "no_further_progress")
    assert live_work_fields_present({"requires_hitl": 1}) == ()
    assert live_work_fields_present({"next_needed_step": "  "}) == ()
    assert live_work_fields_present({"next_needed_step": 12}) == ()


def test_open_rows_may_retain_next_step() -> None:
    rs = new_resolution_state(
        items=[
            ResolutionItem(
                item_id="item-1",
                title="Open work",
                kind="claim",
                status="open",
                next_needed_step="Keep verifying",
            )
        ]
    )
    assert (
        evaluate_addressed_terminal_row_consistency(
            resolution_state=rs,
            addressed_item_ids=["item-1"],
            addressed_unit_ids_by_item={},
        )
        is None
    )


def test_conflicts_are_bounded_with_omitted_count() -> None:
    items = []
    addressed = []
    for i in range(MAX_TERMINAL_ROW_CONFLICTS + 5):
        item_id = f"item-{i}"
        addressed.append(item_id)
        items.append(
            ResolutionItem(
                item_id=item_id,
                title=f"Item {i}",
                kind="claim",
                status="closed",
                next_needed_step="stale",
            )
        )
    result = evaluate_addressed_terminal_row_consistency(
        resolution_state=new_resolution_state(items=items),
        addressed_item_ids=addressed,
        addressed_unit_ids_by_item={},
    )
    assert result is not None
    assert result.reason_code == REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK
    assert len(result.conflicts) == MAX_TERMINAL_ROW_CONFLICTS
    assert result.conflicts_omitted_count == 5
    assert result.conflicts[0].coordinate == "resolution.items[item-0]"
    assert result.conflicts[0].fields == ("next_needed_step",)


def test_untouched_sibling_not_evaluated() -> None:
    rs = new_resolution_state(
        items=[
            ResolutionItem(
                item_id="legacy",
                title="Legacy contradictory",
                kind="claim",
                status="closed",
                next_needed_step="still open work",
            ),
            ResolutionItem(
                item_id="target",
                title="Target",
                kind="claim",
                status="open",
                next_needed_step="ok",
            ),
        ]
    )
    assert (
        evaluate_addressed_terminal_row_consistency(
            resolution_state=rs,
            addressed_item_ids=["target"],
            addressed_unit_ids_by_item={},
        )
        is None
    )


def test_covered_unit_conflict_coordinate() -> None:
    rs = new_resolution_state(
        items=[
            ResolutionItem(
                item_id="item-1",
                title="Parent",
                kind="group",
                status="open",
                covered_units=[
                    ResolutionCoveredUnit(
                        unit_id="unit-2",
                        title="Unit",
                        status="closed",
                        requires_hitl=True,
                    )
                ],
            )
        ]
    )
    result = evaluate_addressed_terminal_row_consistency(
        resolution_state=rs,
        addressed_item_ids=[],
        addressed_unit_ids_by_item={"item-1": ["unit-2"]},
    )
    assert result is not None
    assert result.conflicts[0].coordinate == (
        "resolution.items[item-1].covered_units[unit-2]"
    )
    assert result.conflicts[0].fields == ("requires_hitl",)
