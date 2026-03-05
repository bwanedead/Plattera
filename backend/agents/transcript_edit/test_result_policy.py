from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.result_policy import (
    TranscriptEditFacts,
    clean_no_promote_decision,
    clean_promoted_decision,
    max_iterations_decision,
    must_verify_before_terminal,
    should_attempt_promote,
    should_run_stabilization_pass,
)


def _facts(**overrides):
    base = TranscriptEditFacts(
        iterations=2,
        mode="audit_then_repair_then_promote",
        auto_promote=True,
        error_count=0,
        applied_any_edits=True,
        applied_non_normalization=False,
        applied_requires_review=False,
        used_human_feedback=False,
        has_disagreements=True,
        has_images=False,
        min_iterations_before_complete=3,
        unresolved_mapping_blocking_closure=False,
    )
    values = {**base.__dict__, **overrides}
    return TranscriptEditFacts(**values)


def test_must_verify_before_terminal_when_edits_or_disagreements() -> None:
    assert must_verify_before_terminal(_facts(applied_any_edits=True)) is True
    assert must_verify_before_terminal(_facts(applied_any_edits=False, has_disagreements=True)) is True
    assert must_verify_before_terminal(_facts(applied_any_edits=False, has_disagreements=False, used_human_feedback=True)) is True
    assert must_verify_before_terminal(_facts(applied_any_edits=False, has_disagreements=False, used_human_feedback=False)) is False
    assert must_verify_before_terminal(_facts(applied_any_edits=False, has_disagreements=False, used_human_feedback=False, has_images=True)) is True


def test_should_run_stabilization_pass_before_min_iterations() -> None:
    assert should_run_stabilization_pass(_facts(iterations=2, min_iterations_before_complete=3)) is True
    assert should_run_stabilization_pass(_facts(iterations=3, min_iterations_before_complete=3)) is False


def test_should_attempt_promote_matches_mode_and_flags() -> None:
    assert should_attempt_promote(_facts(), "audit_then_repair_then_promote") is True
    assert should_attempt_promote(_facts(mode="audit_then_repair"), "audit_then_repair_then_promote") is False
    assert should_attempt_promote(_facts(applied_requires_review=True), "audit_then_repair_then_promote") is False
    unresolved_states = {"unknown", "candidate_found", "disputed", "accepted_with_risk"}
    for state in unresolved_states:
        unresolved = state in unresolved_states
        assert should_attempt_promote(
            _facts(unresolved_mapping_blocking_closure=unresolved),
            "audit_then_repair_then_promote",
        ) is False


def test_clean_decisions_and_max_iteration_decision() -> None:
    clean = clean_no_promote_decision(_facts(error_count=0, applied_requires_review=False))
    assert clean.status == "completed"
    assert clean.reason_code == "tx_agent_clean_no_promote"
    assert clean.review_required is False

    unresolved_states = {"unknown", "candidate_found", "disputed", "accepted_with_risk"}
    for state in unresolved_states:
        unresolved = state in unresolved_states
        blocked = clean_no_promote_decision(
            _facts(error_count=0, unresolved_mapping_blocking_closure=unresolved)
        )
        assert blocked.status == "needs_review"
        assert blocked.reason_code == "tx_agent_closure_requirements_unresolved"
        assert blocked.review_required is True

    promoted = clean_promoted_decision()
    assert promoted.status == "completed"
    assert promoted.reason_code == "tx_agent_clean_promoted"
    assert promoted.review_required is False

    maxed = max_iterations_decision("tx_agent_not_started")
    assert maxed.status == "needs_review"
    assert maxed.reason_code == "tx_agent_max_iterations_reached"
    assert maxed.review_required is True
