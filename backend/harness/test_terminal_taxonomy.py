from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.terminal_taxonomy import (
    classify_controller_terminal,
    classify_transcript_edit_terminal,
)


def test_controller_success_maps_completed() -> None:
    result = classify_controller_terminal(
        stop_reason="completed",
        terminal_outcome="SUCCESS",
        success=True,
        reason_code="done_verified",
    )
    assert result.terminal_class == "completed"
    assert result.reason_code == "done_verified"


def test_controller_refusal_like_validation_maps_blocked() -> None:
    result = classify_controller_terminal(
        stop_reason="validation_failed",
        terminal_outcome="FAILED",
        success=False,
        reason_code="missing_ir",
    )
    assert result.terminal_class == "blocked"
    assert result.reason_code == "missing_ir"


def test_controller_exhaustion_maps_exhausted() -> None:
    result = classify_controller_terminal(
        stop_reason="budget_exceeded",
        terminal_outcome="FAILED",
        success=False,
        reason_code="budget_exceeded",
    )
    assert result.terminal_class == "exhausted"


def test_controller_internal_error_maps_failed() -> None:
    result = classify_controller_terminal(
        stop_reason="internal_error",
        terminal_outcome="FAILED",
        success=False,
        reason_code="internal_error",
    )
    assert result.terminal_class == "failed"


def test_transcript_edit_completed_maps_completed() -> None:
    result = classify_transcript_edit_terminal(
        status="completed",
        reason_code="tx_agent_transcript_clean_promoted",
        terminal_classification="mapping_ready",
        human_feedback_pending=False,
    )
    assert result.terminal_class == "completed"
    assert result.reason_code == "tx_agent_transcript_clean_promoted"


def test_transcript_edit_waiting_feedback_maps_waiting_human() -> None:
    result = classify_transcript_edit_terminal(
        status="waiting_feedback",
        reason_code="tx_agent_closure_requirements_unresolved",
        terminal_classification="blocked_waiting_feedback",
        human_feedback_pending=True,
    )
    assert result.terminal_class == "waiting_human"


def test_transcript_edit_source_blocked_maps_waiting_evidence() -> None:
    result = classify_transcript_edit_terminal(
        status="needs_review",
        reason_code="tx_agent_source_blocking",
        terminal_classification="source_blocking_missing_evidence",
        human_feedback_pending=False,
    )
    assert result.terminal_class == "waiting_evidence"


def test_transcript_edit_exhausted_and_failed_mappings() -> None:
    exhausted = classify_transcript_edit_terminal(
        status="needs_review",
        reason_code="tx_agent_max_iteration_reached",
        terminal_classification="iteration_limit_exhausted",
        human_feedback_pending=False,
    )
    failed = classify_transcript_edit_terminal(
        status="failed",
        reason_code="tx_agent_internal_error",
        terminal_classification="runtime_failure",
        human_feedback_pending=False,
    )
    assert exhausted.terminal_class == "exhausted"
    assert failed.terminal_class == "failed"

