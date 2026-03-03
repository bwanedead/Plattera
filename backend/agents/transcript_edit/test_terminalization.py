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
    summary = terminal_summary(
        [{"phase": "audit_result", "detail": {"error_count": 0}}],
        result,
    )
    assert summary["closure_state"] == "achieved"
    assert summary["layer1_canonical_recovery"] == "satisfied"
    assert summary["layer2_canonical_sanity"] == "satisfied"
    assert summary["layer3_dependency_completeness"] == "satisfied"
    assert summary["unresolved_closure_requirements"] == []


def test_terminal_summary_collects_audit_apply_and_feedback_flags() -> None:
    progress_log = [
        {"phase": "audit_result", "detail": {"error_count": 2, "decision_ledger": {"summary": {"blocking_open_count": 3}}}},
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
    assert summary["initial_findings"]["error_count"] == 2
    assert summary["final_findings"]["error_count"] == 0
    assert summary["validator_clean"] is True
    assert summary["closure_state"] == "blocked"
    assert summary["layer1_canonical_recovery"] == "unknown"
    assert summary["layer2_canonical_sanity"] == "unknown"
    assert summary["layer3_dependency_completeness"] == "unknown"
    assert summary["decision_ledger_summary"] == {"blocking_open_count": 3}


def test_terminal_message_and_summary_for_not_mapping_ready() -> None:
    progress_log = [
        {"phase": "audit_result", "detail": {"error_count": 0}},
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s2",
        iterations=1,
        status="needs_review",
        reason_code="tx_agent_final_image_verify_failed:mismatch",
        latest_refs={},
        review_required=True,
    )
    msg = terminal_message(result)
    assert "validator-clean but not mapping-ready" in msg
    summary = terminal_summary(progress_log, result)
    assert summary["validator_clean"] is True
    assert summary["mapping_ready"] is False
    assert summary["promoted"] is False
    assert summary["readiness_blocker"] == "mapping_critical_image_verification_unresolved"
    assert summary["closure_state"] == "blocked"
    assert summary["layer1_canonical_recovery"] == "blocked"
    assert summary["layer2_canonical_sanity"] == "unknown"
    assert summary["layer3_dependency_completeness"] == "unknown"
    assert isinstance(summary["unresolved_closure_requirements"], list)


def test_terminal_summary_completed_status_not_mapping_ready_when_blocking_closure_open() -> None:
    progress_log = [
        {
            "phase": "audit_result",
            "detail": {
                "error_count": 0,
                "decision_ledger": {
                    "items": [
                        {
                            "key": "range",
                            "label": "Range",
                            "state": "disputed",
                            "blocking": True,
                            "closure_requirement": {"block_reason": "ambiguity"},
                        }
                    ],
                    "summary": {"blocking_open_count": 1},
                },
            },
        }
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s3",
        iterations=2,
        status="completed",
        reason_code="tx_agent_clean_no_promote",
        latest_refs={},
        review_required=False,
    )
    summary = terminal_summary(progress_log, result)
    assert summary["validator_clean"] is True
    assert summary["mapping_ready"] is False
    assert summary["closure_state"] == "blocked"
    unresolved = summary["unresolved_closure_requirements"]
    assert isinstance(unresolved, list)
    assert any(str(item.get("key")) == "range" for item in unresolved if isinstance(item, dict))
