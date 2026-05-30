"""Tests for generic harness performance evaluation metrics."""

from __future__ import annotations

from harness.mission_state import ResolutionCoveredUnit, ResolutionItem, new_resolution_state
from harness.runtime.memory import LoopMemoryState
from harness.audit.performance_evaluation_timeline import render_performance_evaluation_timeline
from harness.runtime.memory.performance_evaluation import (
    ACCURACY_STATUS,
    build_performance_evaluation,
)
from harness.runtime.orchestration.loop_health_summary import build_prompt_observability_summary
from harness.runtime.orchestration.prompt_packet_builder import _compact_prompt_observability_summary


def _item(
    item_id: str,
    *,
    status: str = "open",
    blocking: bool | None = None,
    determined_value: str | None = None,
    determination: str | None = None,
    covered_units: list[ResolutionCoveredUnit] | None = None,
) -> ResolutionItem:
    return ResolutionItem(
        item_id=item_id,
        title=item_id,
        kind="work_unit",
        status=status,
        blocking=blocking,
        determined_value=determined_value,
        determination=determination,
        covered_units=list(covered_units or []),
    )


def _unit(
    unit_id: str,
    *,
    status: str | None = "open",
    determined_value: str | None = None,
    determination: str | None = None,
) -> ResolutionCoveredUnit:
    return ResolutionCoveredUnit(
        unit_id=unit_id,
        title=unit_id,
        status=status,
        determined_value=determined_value,
        determination=determination,
    )


def _mem(*, items: list[ResolutionItem] | None = None, iterations: int = 0) -> LoopMemoryState:
    mem = LoopMemoryState()
    mem.iterations = iterations
    rs = new_resolution_state()
    if items:
        rs = rs.model_copy(update={"items": list(items)})
    mem.continuity.resolution_state = rs
    return mem


def test_empty_memory_returns_minimal_block_with_accuracy_status() -> None:
    result = build_performance_evaluation(LoopMemoryState())
    assert result["schema_version"] == 1
    assert result["scope"] == "generic_harness"
    assert result["accuracy_status"] == ACCURACY_STATUS
    assert "accuracy_note" in result
    assert "accuracy_not_live_scored" in result["current_pressure"]


def test_work_graph_counts_top_level_items_and_covered_units() -> None:
    items = [
        _item("i1", covered_units=[_unit("u1"), _unit("u2")]),
        _item("i2"),
    ]
    mem = _mem(items=items)
    graph = build_performance_evaluation(mem)["work_graph"]
    assert graph["resolution_items_total"] == 2
    assert graph["covered_units_total"] == 2
    assert graph["work_units_total"] == 4


def test_work_graph_closed_open_blocked_determined_counts() -> None:
    items = [
        _item("i1", status="closed", determined_value="yes"),
        _item(
            "i2",
            status="open",
            blocking=True,
            covered_units=[_unit("u1", status="blocked"), _unit("u2", determination="earned")],
        ),
    ]
    graph = build_performance_evaluation(_mem(items=items))["work_graph"]
    assert graph["closed_units"] == 1
    assert graph["open_units"] == 3
    assert graph["blocked_units"] == 2
    assert graph["determined_units"] == 2


def test_determination_and_closure_transitions_counted_across_turn_records() -> None:
    before = {
        "items": [
            {"item_id": "i1", "status": "open", "determined_value": "", "determination": ""},
            {"item_id": "i2", "status": "open", "determined_value": "old", "determination": ""},
        ]
    }
    after = {
        "items": [
            {"item_id": "i1", "status": "closed", "determined_value": "new", "determination": ""},
            {"item_id": "i2", "status": "open", "determined_value": "new", "determination": ""},
        ]
    }
    turn_records = [
        {
            "turn_index": 1,
            "resolution_state_before": before,
            "resolution_state_after": after,
            "raw_prompt_text": "a" * 100,
            "started_at_epoch_seconds": 0.0,
            "finished_at_epoch_seconds": 10.0,
        }
    ]
    mem = _mem(iterations=1)
    metrics = build_performance_evaluation(mem, turn_records=turn_records)
    assert metrics["productivity"]["determinations_changed_total"] == 2
    assert metrics["productivity"]["units_closed_total"] == 1


def test_delegate_totals_and_delegates_since_last_determination() -> None:
    before = {"items": [{"item_id": "i1", "status": "open"}]}
    after_det = {"items": [{"item_id": "i1", "status": "open", "determined_value": "x"}]}
    turn_records = [
        {
            "turn_index": 1,
            "resolution_state_before": before,
            "resolution_state_after": after_det,
            "tool_request": {
                "actions": [{"action_type": "delegate_subtask"}, {"action_type": "read"}]
            },
        },
        {
            "turn_index": 2,
            "tool_request": {"actions": [{"action_type": "delegate_subtask"}]},
        },
        {
            "turn_index": 3,
            "tool_request": {"actions": [{"action_type": "delegate_subtask"}]},
        },
    ]
    metrics = build_performance_evaluation(_mem(iterations=3), turn_records=turn_records)
    assert metrics["delegate_yield"]["delegates_total"] == 3
    assert metrics["delegate_yield"]["delegates_since_last_determination"] == 2


def test_input_char_metrics_use_raw_prompt_text_lengths() -> None:
    turn_records = [
        {"turn_index": 1, "raw_prompt_text": "x" * 1000},
        {"turn_index": 2, "raw_prompt_text": "y" * 2000},
        {"turn_index": 3, "raw_prompt_text": "z" * 3000},
    ]
    chars = build_performance_evaluation(_mem(iterations=3), turn_records=turn_records)["input_chars"]
    assert chars["last_turn"] == 3000
    assert chars["cumulative"] == 6000
    assert chars["max_turn"] == 3000
    assert chars["growth_last_turn"] == 1000
    assert chars["avg_last_3"] == 2000


def test_wall_clock_metrics_use_epoch_durations() -> None:
    turn_records = [
        {"turn_index": 1, "started_at_epoch_seconds": 0.0, "finished_at_epoch_seconds": 30.0},
        {"turn_index": 2, "started_at_epoch_seconds": 100.0, "finished_at_epoch_seconds": 190.0},
    ]
    turns = build_performance_evaluation(_mem(iterations=2), turn_records=turn_records)["turns"]
    assert turns["wall_seconds_total"] == 120.0
    assert turns["wall_seconds_last_turn"] == 90.0
    assert turns["avg_wall_seconds_last_5"] == 60.0


def test_turn_contact_finalization_updates_finish_to_full_active_turn_time() -> None:
    mem = _mem(iterations=1)
    mem.telemetry.register_turn_contact(
        turn_index=1,
        prompt_char_count=100,
        started_at_epoch_seconds=10.0,
        finished_at_epoch_seconds=12.0,
    )
    mem.telemetry.finalize_turn_contact(
        turn_index=1,
        finished_at_epoch_seconds=25.0,
        resolution_state_after=None,
    )

    turns = build_performance_evaluation(mem)["turns"]
    assert turns["wall_seconds_total"] == 15.0
    assert turns["wall_seconds_last_turn"] == 15.0


def test_pressure_flags_only_when_thresholds_met() -> None:
    turn_records = [
        {
            "turn_index": 24,
            "raw_prompt_text": "a" * 1000,
            "started_at_epoch_seconds": 0.0,
            "finished_at_epoch_seconds": 10.0,
        },
        {
            "turn_index": 25,
            "raw_prompt_text": "b" * 7000,
            "started_at_epoch_seconds": 100.0,
            "finished_at_epoch_seconds": 200.0,
            "tool_request": {"actions": [{"action_type": "delegate_subtask"}]},
        },
    ]
    before = {"items": [{"item_id": "i1", "status": "open", "determined_value": "old"}]}
    after = {"items": [{"item_id": "i1", "status": "open", "determined_value": "new"}]}
    turn_records[0]["resolution_state_before"] = before
    turn_records[0]["resolution_state_after"] = after

    metrics = build_performance_evaluation(_mem(iterations=25), turn_records=turn_records)
    pressure = metrics["current_pressure"]
    assert "accuracy_not_live_scored" in pressure
    assert "turns_after_20:5" in pressure
    assert "input_chars_growth_high:6000" in pressure
    assert "high_last_turn_wall_seconds:100.0" in pressure


def test_build_prompt_observability_summary_includes_performance_evaluation() -> None:
    summary = build_prompt_observability_summary(_mem(iterations=2))
    assert "performance_evaluation" in summary
    assert summary["performance_evaluation"]["accuracy_status"] == ACCURACY_STATUS


def test_compact_prompt_observability_summary_keeps_performance_evaluation() -> None:
    full = build_prompt_observability_summary(_mem(iterations=1))
    compact = _compact_prompt_observability_summary(full)
    assert "performance_evaluation" in compact
    assert compact["performance_evaluation"]["accuracy_status"] == ACCURACY_STATUS


def test_timeline_renders_section_and_omits_missing_values_gracefully() -> None:
    turn = {
        "prompt_observability_summary": {
            "performance_evaluation": {
                "accuracy_status": "not_live_scored",
                "work_graph": {
                    "work_units_total": 4,
                    "closed_units": 1,
                    "open_units": 3,
                    "blocked_units": 0,
                },
                "current_pressure": ["accuracy_not_live_scored"],
            }
        }
    }
    lines = render_performance_evaluation_timeline(turn)
    assert lines[0] == "Performance evaluation:"
    assert any("work graph:" in line for line in lines)
    assert any("accuracy:" in line for line in lines)
    assert render_performance_evaluation_timeline({}) == []


def test_no_action_blocking_helpers_in_module() -> None:
    import harness.runtime.memory.performance_evaluation as module

    source = open(module.__file__, encoding="utf-8").read()
    assert "block_action" not in source
    assert "enforce" not in source.lower() or "enforcement" not in source.lower()
