from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.progress_evaluation import (
    blocking_signature,
    blocking_unresolved_count,
    classify_iteration_progress,
)


def _ledger(state: str = "disputed", *, block_reason: str = "ambiguity") -> dict:
    return {
        "items": [
            {
                "key": "range",
                "state": state,
                "blocking": True,
                "closure_requirement": {
                    "mapping_blocking": True,
                    "block_reason": block_reason,
                    "resolution_options": ["Range 75 West"],
                    "evidence_refs": ["x"],
                },
            }
        ]
    }


def test_blocking_signature_changes_when_state_changes() -> None:
    sig1 = blocking_signature(_ledger("unknown"))
    sig2 = blocking_signature(_ledger("verified"))
    assert sig1 != sig2
    assert blocking_unresolved_count(_ledger("unknown")) == 1
    assert blocking_unresolved_count(_ledger("verified")) == 0


def test_classify_iteration_progress_requires_apply_reaudit_improvement() -> None:
    progressed, reason, clear_pending = classify_iteration_progress(
        previous_finding_signature="a",
        current_finding_signature="a",
        previous_blocking_signature="range:disputed:ambiguity:",
        current_blocking_signature="range:disputed:ambiguity:",
        previous_blocking_count=1,
        current_blocking_count=1,
        previous_signal_counter=1,
        current_signal_counter=1,
        pending_feedback_prompt_id=None,
        pending_reaudit_after_apply=True,
        apply_reaudit_baseline_blocking_count=1,
    )
    assert progressed is False
    assert reason == "apply_reaudit_no_blocking_improvement"
    assert clear_pending is True


def test_classify_iteration_progress_pending_feedback_is_not_progress_without_signal() -> None:
    progressed, reason, _ = classify_iteration_progress(
        previous_finding_signature="a",
        current_finding_signature="a",
        previous_blocking_signature="range:disputed:ambiguity:",
        current_blocking_signature="range:disputed:ambiguity:",
        previous_blocking_count=1,
        current_blocking_count=1,
        previous_signal_counter=2,
        current_signal_counter=2,
        pending_feedback_prompt_id="hitl_range_1_x",
        pending_reaudit_after_apply=False,
        apply_reaudit_baseline_blocking_count=None,
    )
    assert progressed is False
    assert reason == "pending_human_feedback_no_new_signal"
