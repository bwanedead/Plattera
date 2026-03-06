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
    assert summary["unresolved_optional_items"] == []
    assert isinstance(summary["closure_history"], list)


def test_terminal_summary_collects_audit_apply_and_feedback_flags() -> None:
    progress_log = [
        {
            "phase": "audit_result",
            "timestamp_epoch_seconds": 100,
            "detail": {
                "error_count": 2,
                "decision_ledger": {
                    "items": [{"key": "range", "state": "unknown", "evidence_refs": ["f1"]}],
                    "summary": {"blocking_open_count": 3},
                },
            },
        },
        {"phase": "apply_result", "detail": {"plan_op_count": 3}},
        {"phase": "human_feedback_received", "detail": {}},
        {
            "phase": "audit_result",
            "timestamp_epoch_seconds": 200,
            "detail": {
                "error_count": 0,
                "decision_ledger": {
                    "items": [{"key": "range", "state": "verified", "evidence_refs": ["image_check_range_tokens"]}],
                    "summary": {"blocking_open_count": 0},
                },
            },
        },
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
    assert summary["decision_ledger_summary"] == {"blocking_open_count": 0}
    assert any(
        isinstance(item, dict) and item.get("decision_key") == "range"
        for item in summary["closure_history"]
    )


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
    unresolved_blocking = summary["unresolved_mapping_blocking_closure_requirements"]
    assert isinstance(unresolved_blocking, list)
    assert any(str(item.get("key")) == "range" for item in unresolved_blocking if isinstance(item, dict))
    assert isinstance(summary["unresolved_optional_items"], list)


def test_terminal_summary_completed_status_not_mapping_ready_for_unknown_and_candidate_found() -> None:
    for state in ["unknown", "candidate_found"]:
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
                                "state": state,
                                "blocking": True,
                                "provenance": "orient_llm",
                                "closure_requirement": {
                                    "block_reason": "ambiguity",
                                    "mapping_blocking": True,
                                    "resolution_options": ["Range 75 West"],
                                    "evidence_refs": ["orient_llm"],
                                },
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
        assert summary["mapping_ready"] is False
        assert summary["closure_state"] == "blocked"


def test_terminal_summary_includes_unresolved_optional_items() -> None:
    progress_log = [
        {
            "phase": "audit_result",
            "detail": {
                "error_count": 0,
                "decision_ledger": {
                    "items": [
                        {
                            "key": "acreage",
                            "label": "Acreage",
                            "state": "disputed",
                            "blocking": False,
                            "closure_requirement": {
                                "block_reason": "ambiguity",
                                "mapping_blocking": False,
                                "operational_impact": "transcript_quality_only",
                            },
                        }
                    ],
                    "summary": {"blocking_open_count": 0},
                },
            },
        }
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s4",
        iterations=1,
        status="completed",
        reason_code="tx_agent_clean_no_promote",
        latest_refs={},
        review_required=False,
    )
    summary = terminal_summary(progress_log, result)
    optional_items = summary["unresolved_optional_items"]
    assert isinstance(optional_items, list)
    assert any(str(item.get("key")) == "acreage" for item in optional_items if isinstance(item, dict))
    assert summary["mapping_ready"] is True
    assert summary["terminal_classification"] == "optional_quality_remaining_only"


def test_terminal_summary_dependency_blocker_classification() -> None:
    progress_log = [
        {
            "phase": "audit_result",
            "detail": {
                "error_count": 0,
                "decision_ledger": {
                    "items": [
                        {
                            "key": "closure_or_pob",
                            "label": "Closure / POB",
                            "state": "disputed",
                            "blocking": True,
                            "closure_requirement": {
                                "block_reason": "dependency",
                                "mapping_blocking": True,
                                "required_information": "Referenced external deed data.",
                                "minimal_user_action": "Provide external reference.",
                            },
                        }
                    ],
                    "summary": {"blocking_open_count": 1},
                },
            },
        }
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s5",
        iterations=2,
        status="needs_review",
        reason_code="tx_agent_closure_requirements_unresolved",
        latest_refs={},
        review_required=True,
    )
    summary = terminal_summary(progress_log, result)
    assert summary["mapping_ready"] is False
    assert summary["terminal_classification"] == "blocked_dependency_evidence_missing"
    assert any(str(item.get("key")) == "closure_or_pob" for item in summary["unresolved_dependency_items"])


def test_terminal_summary_pending_feedback_classification() -> None:
    progress_log = [
        {
            "event_type": "human_feedback_needed",
            "phase": "human_feedback_needed",
            "prompt_id": "hitl_range_2_abc123",
            "detail": {
                "decision_ledger": {
                    "items": [
                        {
                            "key": "range",
                            "label": "Range",
                            "state": "disputed",
                            "blocking": True,
                            "closure_requirement": {"block_reason": "ambiguity", "mapping_blocking": True},
                        }
                    ],
                    "summary": {"blocking_open_count": 1},
                }
            },
        }
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s6",
        iterations=2,
        status="needs_review",
        reason_code="tx_agent_closure_requirements_unresolved",
        latest_refs={},
        review_required=True,
    )
    summary = terminal_summary(progress_log, result)
    assert summary["human_feedback_pending"] is True
    assert summary["terminal_classification"] == "blocked_human_feedback_needed"
    assert summary["pending_feedback_prompt_ids"] == ["hitl_range_2_abc123"]


def test_terminal_summary_uses_runtime_hitl_state_when_progress_window_drops_feedback_events() -> None:
    progress_log = [
        {
            "phase": "audit_result",
            "detail": {
                "error_count": 0,
                "decision_ledger": {"items": [], "summary": {"blocking_open_count": 0}},
            },
        }
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s7",
        iterations=3,
        status="needs_review",
        reason_code="tx_agent_no_progress",
        latest_refs={},
        review_required=True,
        runtime_hitl_state={
            "used_human_feedback": True,
            "feedback_received_count": 1,
            "feedback_consumed_count": 1,
            "feedback_stale_count": 0,
            "feedback_superseded_count": 0,
            "pending_feedback_prompt_id": None,
            "superseded_prompt_ids": [],
            "hitl_lifecycle_log": [{"phase": "human_feedback_consumed", "prompt_id": "hitl_range_1_resolver"}],
        },
    )
    summary = terminal_summary(progress_log, result, critical_events=[])
    assert summary["used_human_feedback"] is True
    assert summary["feedback_received_count"] == 1
    assert summary["feedback_consumed_count"] == 1
    assert summary["human_feedback_pending"] is False


def test_terminal_summary_prompt_supersession_excludes_old_prompt_from_pending() -> None:
    progress_log = [
        {
            "event_type": "human_feedback_needed",
            "phase": "human_feedback_needed",
            "prompt_id": "hitl_range_1_resolver",
            "detail": {
                "decision_ledger": {
                    "items": [
                        {
                            "key": "range",
                            "label": "Range",
                            "state": "disputed",
                            "blocking": True,
                            "closure_requirement": {"block_reason": "ambiguity", "mapping_blocking": True},
                        }
                    ],
                    "summary": {"blocking_open_count": 1},
                }
            },
        },
        {
            "phase": "human_feedback_prompt_superseded",
            "prompt_id": "hitl_range_1_resolver",
            "replacement_prompt_id": "hitl_range_2_resolver",
        },
        {
            "event_type": "human_feedback_needed",
            "phase": "human_feedback_needed",
            "prompt_id": "hitl_range_2_resolver",
        },
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s8",
        iterations=4,
        status="needs_review",
        reason_code="tx_agent_closure_requirements_unresolved",
        latest_refs={},
        review_required=True,
        runtime_hitl_state={
            "used_human_feedback": False,
            "feedback_received_count": 0,
            "feedback_consumed_count": 0,
            "feedback_stale_count": 1,
            "feedback_superseded_count": 1,
            "pending_feedback_prompt_id": "hitl_range_2_resolver",
            "superseded_prompt_ids": ["hitl_range_1_resolver"],
            "hitl_lifecycle_log": [],
        },
    )
    summary = terminal_summary(progress_log, result, critical_events=[])
    assert summary["pending_feedback_prompt_ids"] == ["hitl_range_2_resolver"]
    assert summary["superseded_feedback_prompt_ids"] == ["hitl_range_1_resolver"]
    assert summary["feedback_superseded_count"] == 1
