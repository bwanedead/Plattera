from __future__ import annotations

from .contracts import ProgressDelta, ProgressMetrics


def evaluate_progress(metrics: ProgressMetrics) -> ProgressDelta:
    """Return a mechanical progress signal from generic state tokens only."""
    if metrics.pending_refresh and metrics.refresh_baseline_state_signature is not None:
        if metrics.current_state_signature != metrics.refresh_baseline_state_signature:
            return ProgressDelta(
                made_progress=True,
                reason_code="refresh_state_changed",
                reset_refresh=True,
            )
        return ProgressDelta(
            made_progress=True,
            reason_code="refresh_reaudit_pending",
            reset_refresh=False,
        )

    if metrics.new_artifact_signal:
        return ProgressDelta(made_progress=True, reason_code="new_artifact_signal", reset_refresh=False)

    if metrics.previous_state_signature is None:
        return ProgressDelta(made_progress=True, reason_code="initial_baseline", reset_refresh=False)

    if metrics.current_state_signature != metrics.previous_state_signature:
        return ProgressDelta(made_progress=True, reason_code="state_changed", reset_refresh=False)

    if metrics.pending_human_input:
        return ProgressDelta(made_progress=False, reason_code="awaiting_human", reset_refresh=False)

    return ProgressDelta(made_progress=False, reason_code="no_material_change", reset_refresh=False)
