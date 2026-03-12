from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TerminalClass = Literal[
    "completed",
    "blocked",
    "waiting_human",
    "waiting_evidence",
    "exhausted",
    "failed",
]


@dataclass(frozen=True)
class TerminalTaxonomyResult:
    terminal_class: TerminalClass
    reason_code: str | None = None
    raw_status: str | None = None
    raw_stop_reason: str | None = None
    raw_terminal_outcome: str | None = None
    raw_terminal_classification: str | None = None


def classify_controller_terminal(
    *,
    stop_reason: str | None,
    terminal_outcome: str | None,
    success: Any,
    reason_code: str | None = None,
) -> TerminalTaxonomyResult:
    normalized_reason = _lower(stop_reason)
    if normalized_reason == "completed" and success is True:
        return TerminalTaxonomyResult(
            terminal_class="completed",
            reason_code=reason_code,
            raw_stop_reason=stop_reason,
            raw_terminal_outcome=terminal_outcome,
        )
    if normalized_reason == "needs_user_choice":
        terminal_class: TerminalClass = "waiting_human"
    elif normalized_reason == "needs_upload":
        terminal_class = "waiting_evidence"
    elif normalized_reason in {"needs_capability", "worker_unavailable", "validation_failed"}:
        terminal_class = "blocked"
    elif normalized_reason in {"budget_exceeded", "no_progress"}:
        terminal_class = "exhausted"
    elif normalized_reason in {"internal_error", "error", "cancelled"}:
        terminal_class = "failed"
    else:
        normalized_outcome = (terminal_outcome or "").strip().upper()
        if normalized_outcome == "SUCCESS":
            terminal_class = "completed"
        elif normalized_outcome == "NEEDS_USER_CHOICE":
            terminal_class = "waiting_human"
        elif normalized_outcome == "NEEDS_UPLOAD":
            terminal_class = "waiting_evidence"
        elif normalized_outcome == "FAILED":
            terminal_class = "failed"
        else:
            terminal_class = "blocked"
    return TerminalTaxonomyResult(
        terminal_class=terminal_class,
        reason_code=reason_code,
        raw_stop_reason=stop_reason,
        raw_terminal_outcome=terminal_outcome,
    )


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
        terminal_class = "waiting_human" if _needs_human(
            human_feedback_pending=human_feedback_pending,
            terminal_classification=normalized_classification,
        ) else "failed"
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

