from __future__ import annotations

from agents.transcript_edit.terminalization import build_run_result, terminal_message, terminal_summary


def test_build_run_result_and_terminal_message_completed_promoted() -> None:
    result = build_run_result(
        run_artifact_ref="ref://run",
        session_id="s1",
        iterations=3,
        status="completed",
        reason_code="tx_agent_clean_promoted",
        latest_refs={"a": {"artifact_path": "x"}},
        review_required=False,
    )
    assert result.status == "completed"
    assert result.reason_code == "tx_agent_clean_promoted"
    msg = terminal_message(result)
    assert "promoted for mapping" in msg


def test_terminal_summary_collects_audit_apply_and_feedback_flags() -> None:
    progress_log = [
        {"phase": "audit_result", "detail": {"error_count": 2}},
        {"phase": "apply_result", "detail": {"plan_op_count": 3}},
        {"phase": "human_feedback_received", "detail": {}},
        {"phase": "audit_result", "detail": {"error_count": 0}},
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s1",
        iterations=2,
        status="needs_review",
        reason_code="tx_agent_no_progress",
        latest_refs={},
        review_required=True,
    )
    summary = terminal_summary(progress_log, result)
    assert summary["edits_applied_total"] == 3
    assert summary["used_human_feedback"] is True
    assert summary["initial_findings"] == {"error_count": 2}
    assert summary["final_findings"] == {"error_count": 0}
