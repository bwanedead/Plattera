"""Unit tests for shared progress evaluation (Phase 21: outcome-based progress)."""

from __future__ import annotations

from harness.orchestration_kernel.contracts import ProgressMetrics
from harness.orchestration_kernel.progress import evaluate_progress


def test_pending_refresh_without_baselines_does_not_grant_grace() -> None:
    """Audit-only execute sets pending_refresh but no post-apply baselines — not progress."""
    m = ProgressMetrics(
        previous_finding_signature="a",
        current_finding_signature="a",
        previous_blocking_signature="b",
        current_blocking_signature="b",
        previous_blocking_count=2,
        current_blocking_count=2,
        new_evidence_signal=False,
        pending_feedback_prompt_id=None,
        pending_refresh=True,
        refresh_baseline_blocking_count=None,
        refresh_baseline_blocking_signature=None,
    )
    delta = evaluate_progress(m)
    assert delta.made_progress is False
    assert delta.reason_code == "no_material_change"


def test_pending_refresh_with_baselines_grants_grace_when_no_delta_yet() -> None:
    m = ProgressMetrics(
        previous_finding_signature="a",
        current_finding_signature="a",
        previous_blocking_signature="b",
        current_blocking_signature="b",
        previous_blocking_count=2,
        current_blocking_count=2,
        new_evidence_signal=False,
        pending_feedback_prompt_id=None,
        pending_refresh=True,
        refresh_baseline_blocking_count=2,
        # Must match current so the "signature changed vs baseline" branch does not fire first.
        refresh_baseline_blocking_signature="b",
    )
    delta = evaluate_progress(m)
    assert delta.made_progress is True
    assert delta.reason_code == "refresh_pending_reaudit_grace"
