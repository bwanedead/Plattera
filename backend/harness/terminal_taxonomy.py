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
def _lower(value: str | None) -> str:
    return (value or "").strip().lower()
