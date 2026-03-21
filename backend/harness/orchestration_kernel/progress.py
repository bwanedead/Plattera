from __future__ import annotations

from .contracts import ProgressMetrics, ProgressDelta


def evaluate_progress(metrics: ProgressMetrics) -> ProgressDelta:
    """Shared progress evaluator.

    Generic parameter types — no domain-specific field names.
    Promoted from classify_iteration_progress in
    backend/agents/transcript_edit/progress_evaluation.py with generic
    parameter naming so any domain can supply metric inputs via hook 7.

    The kernel owns no_progress_streak and evidence_signal_counter.
    The domain pack owns the metric derivation (signatures, counts, flags).
    """
    # Post-apply refresh path: evaluate relative to the refresh baseline, not prior iteration.
    # Only when the domain captured post-apply reaudit baselines (compile_move for apply).
    # If pending_refresh is set without baselines (e.g. after audit-only execute), do not grant
    # refresh_pending_reaudit_grace — fall through to normal progress rules.
    if metrics.pending_refresh and (
        metrics.refresh_baseline_blocking_count is not None
        or isinstance(metrics.refresh_baseline_blocking_signature, str)
    ):
        baseline = int(
            metrics.refresh_baseline_blocking_count
            if metrics.refresh_baseline_blocking_count is not None
            else metrics.current_blocking_count
        )
        baseline_sig = str(
            metrics.refresh_baseline_blocking_signature
            if isinstance(metrics.refresh_baseline_blocking_signature, str)
            else metrics.current_blocking_signature
        )
        if metrics.current_blocking_count < baseline:
            return ProgressDelta(
                made_progress=True,
                reason_code="refresh_improved_blocking_closure",
                reset_refresh=True,
            )
        if baseline_sig and metrics.current_blocking_signature != baseline_sig:
            return ProgressDelta(
                made_progress=True,
                reason_code="refresh_blocking_signature_changed",
                reset_refresh=True,
            )
        # No improvement detectable yet — but Phase 2 ran BEFORE this edit was applied,
        # so the comparison is premature (pre-edit audit data vs. pre-edit baseline).
        # Grant a grace iteration: keep pending_refresh=True so Phase 2 of the next
        # iteration re-audits the edited transcript, then evaluate properly.
        return ProgressDelta(
            made_progress=True,
            reason_code="refresh_pending_reaudit_grace",
            reset_refresh=False,
        )

    # New evidence arrived this iteration (domain-supplied signal).
    if metrics.new_evidence_signal:
        return ProgressDelta(made_progress=True, reason_code="new_signal_arrived", reset_refresh=False)

    # First iteration baseline — always counts as progress.
    if metrics.previous_finding_signature is None or metrics.previous_blocking_signature is None:
        return ProgressDelta(made_progress=True, reason_code="initial_iteration_baseline", reset_refresh=False)

    prev_count = int(
        metrics.previous_blocking_count
        if metrics.previous_blocking_count is not None
        else metrics.current_blocking_count
    )
    if metrics.current_blocking_count < prev_count:
        return ProgressDelta(made_progress=True, reason_code="blocking_count_reduced", reset_refresh=False)
    if (
        metrics.current_blocking_signature != metrics.previous_blocking_signature
        and metrics.current_blocking_count <= prev_count
    ):
        return ProgressDelta(made_progress=True, reason_code="blocking_state_changed", reset_refresh=False)
    if (
        metrics.current_finding_signature != metrics.previous_finding_signature
        and metrics.current_blocking_count <= prev_count
    ):
        return ProgressDelta(made_progress=True, reason_code="audit_signature_changed", reset_refresh=False)

    if metrics.pending_feedback_prompt_id:
        return ProgressDelta(
            made_progress=False,
            reason_code="pending_human_feedback_no_new_signal",
            reset_refresh=False,
        )
    return ProgressDelta(made_progress=False, reason_code="no_material_change", reset_refresh=False)
