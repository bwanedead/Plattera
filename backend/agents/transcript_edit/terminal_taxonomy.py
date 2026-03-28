from __future__ import annotations

from harness.terminal_taxonomy import TerminalClass, TerminalTaxonomyResult


def classify_transcript_edit_terminal(
    *,
    status: str | None,
    reason_code: str | None,
    terminal_classification: str | None,
    human_feedback_pending: bool,
) -> TerminalTaxonomyResult:
    normalized_status = _lower(status)
    normalized_classification = _lower(terminal_classification)
    normalized_reason = _lower(reason_code)

    if normalized_status == "completed":
        terminal_class: TerminalClass = "completed"
    elif normalized_status == "waiting_feedback":
        terminal_class = "waiting_human"
    elif normalized_status == "needs_review":
        if _needs_human(
            human_feedback_pending=human_feedback_pending,
            terminal_classification=normalized_classification,
        ):
            terminal_class = "waiting_human"
        elif _needs_evidence(normalized_classification):
            terminal_class = "waiting_evidence"
        elif _is_exhausted(
            reason_code=normalized_reason,
            terminal_classification=normalized_classification,
        ):
            terminal_class = "exhausted"
        else:
            terminal_class = "blocked"
    elif normalized_status == "failed":
        terminal_class = (
            "waiting_human"
            if _needs_human(
                human_feedback_pending=human_feedback_pending,
                terminal_classification=normalized_classification,
            )
            else "failed"
        )
    else:
        if _needs_human(
            human_feedback_pending=human_feedback_pending,
            terminal_classification=normalized_classification,
        ):
            terminal_class = "waiting_human"
        elif _is_exhausted(
            reason_code=normalized_reason,
            terminal_classification=normalized_classification,
        ):
            terminal_class = "exhausted"
        else:
            terminal_class = "failed"

    return TerminalTaxonomyResult(
        terminal_class=terminal_class,
        reason_code=reason_code,
        raw_status=status,
        raw_terminal_classification=terminal_classification,
    )


def _needs_human(*, human_feedback_pending: bool, terminal_classification: str) -> bool:
    return (
        human_feedback_pending
        or "waiting_feedback" in terminal_classification
        or "human_feedback" in terminal_classification
    )


def _needs_evidence(terminal_classification: str) -> bool:
    return any(
        signal in terminal_classification
        for signal in ("dependency", "evidence", "source_blocking", "needs_upload")
    )


def _is_exhausted(*, reason_code: str, terminal_classification: str) -> bool:
    return any(
        signal in reason_code or signal in terminal_classification
        for signal in ("max_iteration", "iteration_limit", "no_progress", "budget", "exhausted")
    )


def _lower(value: str | None) -> str:
    return (value or "").strip().lower()
