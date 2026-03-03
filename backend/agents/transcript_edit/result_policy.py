from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptEditFacts:
    iterations: int
    mode: str
    auto_promote: bool
    error_count: int
    applied_any_edits: bool
    applied_non_normalization: bool
    applied_requires_review: bool
    used_human_feedback: bool
    has_disagreements: bool
    has_images: bool
    min_iterations_before_complete: int


@dataclass(frozen=True)
class TranscriptEditDecision:
    status: str
    reason_code: str
    review_required: bool


def must_verify_before_terminal(facts: TranscriptEditFacts) -> bool:
    return bool(
        facts.has_images
        or facts.applied_any_edits
        or facts.has_disagreements
        or facts.used_human_feedback
    )


def should_run_stabilization_pass(facts: TranscriptEditFacts) -> bool:
    return bool(
        facts.iterations < facts.min_iterations_before_complete
        and (facts.applied_any_edits or facts.has_disagreements or facts.used_human_feedback)
    )


def should_attempt_promote(facts: TranscriptEditFacts, promote_mode: str) -> bool:
    return bool(
        facts.mode == promote_mode
        and facts.auto_promote
        and not facts.applied_non_normalization
        and not facts.applied_requires_review
        and facts.error_count <= 0
    )


def clean_promoted_decision() -> TranscriptEditDecision:
    return TranscriptEditDecision(
        status="completed",
        reason_code="tx_agent_clean_promoted",
        review_required=False,
    )


def clean_no_promote_decision(facts: TranscriptEditFacts) -> TranscriptEditDecision:
    # Preserve current behavior: in clean branch, reason remains clean_no_promote.
    return TranscriptEditDecision(
        status="completed" if facts.error_count <= 0 and not facts.applied_requires_review else "needs_review",
        reason_code="tx_agent_clean_no_promote" if facts.error_count <= 0 else "tx_agent_blocked_error_findings",
        review_required=(facts.error_count > 0 or facts.applied_requires_review or facts.applied_non_normalization),
    )


def max_iterations_decision(last_reason: str) -> TranscriptEditDecision:
    reason = last_reason if last_reason != "tx_agent_not_started" else "tx_agent_max_iterations_reached"
    return TranscriptEditDecision(
        status="needs_review",
        reason_code=reason,
        review_required=True,
    )
