"""Unit tests for the stripped generic mechanical progress evaluator."""

from __future__ import annotations

from harness.runtime.orchestration.contracts import ProgressMetrics
from harness.runtime.orchestration.progress import evaluate_progress


def test_refresh_reports_progress_when_state_changes_from_baseline() -> None:
    metrics = ProgressMetrics(
        previous_state_signature="same",
        current_state_signature="changed",
        previous_open_item_count=3,
        current_open_item_count=2,
        pending_refresh=True,
        refresh_baseline_state_signature="same",
        refresh_baseline_open_item_count=3,
    )
    delta = evaluate_progress(metrics)
    assert delta.made_progress is True
    assert delta.reason_code == "refresh_state_changed"
    assert delta.reset_refresh is True


def test_new_artifact_signal_counts_as_mechanical_progress() -> None:
    metrics = ProgressMetrics(
        previous_state_signature="same",
        current_state_signature="same",
        previous_open_item_count=1,
        current_open_item_count=1,
        new_artifact_signal=True,
    )
    delta = evaluate_progress(metrics)
    assert delta.made_progress is True
    assert delta.reason_code == "new_artifact_signal"


def test_awaiting_human_without_change_is_not_progress() -> None:
    metrics = ProgressMetrics(
        previous_state_signature="same",
        current_state_signature="same",
        previous_open_item_count=1,
        current_open_item_count=1,
        pending_human_input=True,
    )
    delta = evaluate_progress(metrics)
    assert delta.made_progress is False
    assert delta.reason_code == "awaiting_human"
