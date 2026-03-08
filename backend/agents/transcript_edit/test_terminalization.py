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


def test_terminal_summary_includes_human_resolution_ticket_lifecycle_counts() -> None:
    progress_log = [
        {
            "phase": "audit_result",
            "detail": {
                "error_count": 0,
                "decision_ledger": {
                    "items": [],
                    "summary": {"blocking_open_count": 0},
                },
            },
        }
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s9",
        iterations=2,
        status="needs_review",
        reason_code="tx_agent_no_progress",
        latest_refs={},
        review_required=True,
        runtime_hitl_state={
            "used_human_feedback": True,
            "feedback_received_count": 2,
            "feedback_consumed_count": 2,
            "feedback_stale_count": 0,
            "feedback_superseded_count": 0,
            "pending_feedback_prompt_id": None,
            "superseded_prompt_ids": [],
            "hitl_lifecycle_log": [],
            "human_resolution_tickets": [
                {
                    "type": "human_resolution_ticket",
                    "ticket_id": "hitl_range_1_a",
                    "decision_key": "range",
                    "lifecycle_state": "answered_unintegrated",
                },
                {
                    "type": "human_resolution_ticket",
                    "ticket_id": "hitl_range_2_b",
                    "decision_key": "range",
                    "lifecycle_state": "integration_attempted_failed",
                },
                {
                    "type": "human_resolution_ticket",
                    "ticket_id": "hitl_range_3_c",
                    "decision_key": "range",
                    "lifecycle_state": "integrated",
                },
            ],
        },
    )
    summary = terminal_summary(progress_log, result, critical_events=[])
    assert summary["answered_unintegrated_ticket_count"] == 1
    assert summary["integration_failed_ticket_count"] == 1
    assert summary["integrated_ticket_count"] == 1
    assert len(summary["human_resolution_tickets"]) == 3


def test_terminal_summary_classifies_post_feedback_resolver_invalid_exhausted() -> None:
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
                            "closure_requirement": {"block_reason": "ambiguity", "mapping_blocking": True},
                        }
                    ],
                    "summary": {"blocking_open_count": 1},
                },
            },
        }
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s10",
        iterations=3,
        status="needs_review",
        reason_code="tx_agent_post_feedback_resolver_invalid_exhausted:resolver_invalid:ValidationError:invalid_move",
        latest_refs={},
        review_required=True,
    )
    summary = terminal_summary(progress_log, result, critical_events=[])
    assert summary["terminal_classification"] == "blocked_post_feedback_resolver_invalid"


def test_terminal_classification_precedence_keeps_dependency_over_blocker_fallback() -> None:
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
        session_id="s_dep_precedence",
        iterations=2,
        status="needs_review",
        reason_code="tx_agent_closure_requirements_unresolved",
        latest_refs={},
        review_required=True,
    )
    summary = terminal_summary(
        progress_log,
        result,
        runtime_hitl_state={
            "blocker_registry": {
                "counts": {"waiting_feedback": 1, "answered_unintegrated": 1, "open": 1},
                "active_blocker_id": "blocker:closure_or_pob",
                "rows": [
                    {
                        "blocker_id": "blocker:closure_or_pob",
                        "decision_key": "closure_or_pob",
                        "state": "open",
                        "scope_status": "in_target",
                    }
                ],
            }
        },
    )
    assert summary["terminal_classification"] == "blocked_dependency_evidence_missing"


def test_terminal_classification_precedence_keeps_post_feedback_resolver_invalid_over_blocker_fallback() -> None:
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s_resolver_precedence",
        iterations=3,
        status="needs_review",
        reason_code="tx_agent_post_feedback_resolver_invalid_exhausted:resolver_invalid:ValidationError:invalid_move",
        latest_refs={},
        review_required=True,
    )
    summary = terminal_summary(
        [],
        result,
        runtime_hitl_state={
            "blocker_registry": {
                "counts": {"answered_unintegrated": 1, "waiting_feedback": 0, "open": 0},
                "active_blocker_id": "blocker:range",
                "rows": [
                    {
                        "blocker_id": "blocker:range",
                        "decision_key": "range",
                        "state": "answered_unintegrated",
                        "scope_status": "in_target",
                    }
                ],
            }
        },
    )
    assert summary["terminal_classification"] == "blocked_post_feedback_resolver_invalid"


def test_terminal_classification_blocker_fallback_applies_without_more_specific_reason() -> None:
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s_blocker_fallback",
        iterations=1,
        status="needs_review",
        reason_code="tx_agent_closure_requirements_unresolved",
        latest_refs={},
        review_required=True,
    )
    summary = terminal_summary(
        [],
        result,
        runtime_hitl_state={
            "blocker_registry": {
                "counts": {"waiting_feedback": 1, "answered_unintegrated": 0, "open": 0},
                "active_blocker_id": "blocker:range",
                "rows": [
                    {
                        "blocker_id": "blocker:range",
                        "decision_key": "range",
                        "state": "waiting_feedback",
                        "scope_status": "in_target",
                    }
                ],
            }
        },
    )
    assert summary["terminal_classification"] == "blocked_waiting_feedback"


def test_terminal_summary_scoped_success_with_incomplete_source_context() -> None:
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
                            "state": "verified",
                            "blocking": True,
                            "scope_id": "target_scope",
                            "in_target_scope": True,
                            "closure_requirement": None,
                        },
                        {
                            "key": "closure_or_pob",
                            "label": "Closure / POB",
                            "state": "disputed",
                            "blocking": True,
                            "scope_id": "outside_target_scope",
                            "in_target_scope": False,
                                "closure_requirement": {
                                    "block_reason": "ambiguity",
                                    "mapping_blocking": True,
                                    "operational_impact": "mapping_blocking",
                                    "scope_status": "outside_target",
                                    "scope_proof": ["source_truncation_boundary"],
                                    "required_information": "Missing lower-page closure text.",
                                    "minimal_user_action": "Provide uncropped source.",
                                    "evidence_refs": [],
                                },
                        },
                    ],
                    "summary": {"blocking_open_count": 1},
                    "source_completeness": "partial_truncated",
                    "source_completeness_reason": "Lower page is cut off.",
                    "source_limitations": ["Lower-page deed content unavailable."],
                    "scope_summaries": {
                        "target_scope": {"scope_closure_state": "achieved"},
                        "outside_target_scope": {"scope_closure_state": "partial"},
                        "unknown_scope": {"scope_closure_state": "not_attempted"},
                    },
                },
            },
        }
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s11",
        iterations=2,
        status="completed",
        reason_code="tx_agent_clean_no_promote",
        latest_refs={},
        review_required=False,
    )
    summary = terminal_summary(progress_log, result, critical_events=[])
    assert summary["target_scope_status"] == "achieved"
    assert summary["outside_target_scope_status"] in {"partial", "blocked"}
    assert summary["source_completeness"] == "partial_truncated"
    assert summary["terminal_classification"] == "target_scope_complete_with_incomplete_source_context"
    assert summary["mapping_ready"] is True
    assert any(str(item.get("key")) == "closure_or_pob" for item in summary["unresolved_outside_target_scope_items"])


def test_terminal_summary_classifies_blocked_target_scope_ambiguity() -> None:
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
                            "scope_id": "target_scope",
                            "in_target_scope": True,
                            "closure_requirement": {
                                "block_reason": "ambiguity",
                                "mapping_blocking": True,
                                "operational_impact": "mapping_blocking",
                                "required_information": "Resolve target range token.",
                                "minimal_user_action": "Choose range token.",
                                "evidence_refs": ["orient_llm"],
                            },
                        }
                    ],
                    "summary": {"blocking_open_count": 1},
                    "source_completeness": "complete",
                    "scope_summaries": {
                        "target_scope": {"scope_closure_state": "blocked"},
                        "outside_target_scope": {"scope_closure_state": "not_attempted"},
                        "unknown_scope": {"scope_closure_state": "not_attempted"},
                    },
                },
            },
        }
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s12",
        iterations=2,
        status="needs_review",
        reason_code="tx_agent_closure_requirements_unresolved",
        latest_refs={},
        review_required=True,
    )
    summary = terminal_summary(progress_log, result, critical_events=[])
    assert summary["terminal_classification"] == "blocked_target_scope_ambiguity"


def test_terminal_summary_partial_source_with_unknown_scope_blocker_not_scoped_success() -> None:
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
                            "state": "verified",
                            "blocking": True,
                            "closure_requirement": None,
                        },
                        {
                            "key": "closure_or_pob",
                            "label": "Closure / POB",
                            "state": "disputed",
                            "blocking": True,
                            "closure_requirement": {
                                "block_reason": "ambiguity",
                                "mapping_blocking": True,
                                "scope_status": "unknown",
                                "scope_proof": [],
                            },
                        },
                    ],
                    "source_completeness": "partial_truncated",
                    "scope_summaries": {
                        "target_scope": {"scope_closure_state": "achieved"},
                        "outside_target_scope": {"scope_closure_state": "not_attempted"},
                        "unknown_scope": {"scope_closure_state": "blocked"},
                    },
                },
            },
        }
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s13",
        iterations=2,
        status="needs_review",
        reason_code="tx_agent_closure_requirements_unresolved",
        latest_refs={},
        review_required=True,
    )
    summary = terminal_summary(progress_log, result, critical_events=[])
    assert summary["scoped_success_eligible"] is False
    assert summary["terminal_classification"] != "target_scope_complete_with_incomplete_source_context"


def test_terminal_summary_run_failed_blocks_scoped_success() -> None:
    progress_log = [
        {
            "phase": "audit_result",
            "detail": {
                "error_count": 0,
                "decision_ledger": {
                    "items": [
                        {"key": "range", "label": "Range", "state": "verified", "blocking": True, "closure_requirement": None},
                        {
                            "key": "closure_or_pob",
                            "label": "Closure / POB",
                            "state": "disputed",
                            "blocking": True,
                            "closure_requirement": {
                                "mapping_blocking": True,
                                "scope_status": "outside_target",
                                "scope_proof": ["source_truncation_boundary"],
                            },
                        },
                    ],
                    "source_completeness": "partial_truncated",
                    "scope_summaries": {
                        "target_scope": {"scope_closure_state": "achieved"},
                        "outside_target_scope": {"scope_closure_state": "partial"},
                        "unknown_scope": {"scope_closure_state": "not_attempted"},
                    },
                },
            },
        }
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s14",
        iterations=2,
        status="failed",
        reason_code="tx_apply_refused",
        latest_refs={},
        review_required=True,
    )
    summary = terminal_summary(progress_log, result, critical_events=[])
    assert summary["run_healthy_for_scoped_success"] is False
    assert summary["scoped_success_eligible"] is False
    assert summary["terminal_classification"] != "target_scope_complete_with_incomplete_source_context"


def test_terminal_summary_validator_dirty_blocks_scoped_success() -> None:
    progress_log = [
        {
            "phase": "audit_result",
            "detail": {
                "error_count": 2,
                "decision_ledger": {
                    "items": [
                        {"key": "range", "label": "Range", "state": "verified", "blocking": True, "closure_requirement": None},
                        {
                            "key": "closure_or_pob",
                            "label": "Closure / POB",
                            "state": "disputed",
                            "blocking": True,
                            "closure_requirement": {
                                "mapping_blocking": True,
                                "scope_status": "outside_target",
                                "scope_proof": ["explicit_outside_target_text"],
                            },
                        },
                    ],
                    "source_completeness": "partial_truncated",
                    "scope_summaries": {
                        "target_scope": {"scope_closure_state": "achieved"},
                        "outside_target_scope": {"scope_closure_state": "partial"},
                        "unknown_scope": {"scope_closure_state": "not_attempted"},
                    },
                },
            },
        }
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s15",
        iterations=2,
        status="needs_review",
        reason_code="tx_agent_closure_requirements_unresolved",
        latest_refs={},
        review_required=True,
    )
    summary = terminal_summary(progress_log, result, critical_events=[])
    assert summary["validator_clean"] is False
    assert summary["scoped_success_eligible"] is False
    assert summary["terminal_classification"] != "target_scope_complete_with_incomplete_source_context"


def test_terminal_summary_includes_detailed_final_decision_rationale_for_needs_review() -> None:
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
                            "closure_requirement": {
                                "block_reason": "ambiguity",
                                "mapping_blocking": True,
                                "required_information": "Confirm exact range token.",
                                "minimal_user_action": "Choose the correct range.",
                            },
                        }
                    ],
                    "summary": {"blocking_open_count": 1},
                },
            },
        },
        {
            "phase": "progress_evaluation",
            "detail": {"progress_reason": "no_material_change"},
        },
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s16",
        iterations=3,
        status="needs_review",
        reason_code="tx_agent_no_progress:no_material_change",
        latest_refs={},
        review_required=True,
    )
    summary = terminal_summary(progress_log, result, critical_events=[])
    rationale = summary.get("final_decision_rationale")
    assert isinstance(rationale, dict)
    assert rationale.get("result_status") == "needs_review"
    assert "Run paused for review" in str(rationale.get("decision_statement") or "")
    assert isinstance(rationale.get("why_this_decision"), str) and rationale.get("why_this_decision")
    assert isinstance(rationale.get("closure_not_reached_reason"), str) and rationale.get("closure_not_reached_reason")
    assert int(rationale.get("blocking_items_count") or 0) >= 1
    assert isinstance(rationale.get("blocking_items_summary"), list)
    assert isinstance(rationale.get("what_was_tried"), dict)
    assert rationale.get("next_action")
    hitl_state = rationale.get("hitl_feedback_state")
    assert isinstance(hitl_state, dict)
    assert hitl_state.get("hitl_feedback_provided") is False
    assert hitl_state.get("hitl_feedback_consumed") is False
    assert isinstance(hitl_state.get("consumed_definition"), str) and hitl_state.get("consumed_definition")


def test_terminal_summary_includes_detailed_final_decision_rationale_for_completed() -> None:
    progress_log = [
        {
            "phase": "audit_result",
            "detail": {
                "error_count": 0,
                "decision_ledger": {
                    "items": [],
                    "summary": {"blocking_open_count": 0},
                },
            },
        }
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s17",
        iterations=1,
        status="completed",
        reason_code="tx_agent_clean_no_promote",
        latest_refs={},
        review_required=False,
    )
    summary = terminal_summary(progress_log, result, critical_events=[])
    rationale = summary.get("final_decision_rationale")
    assert isinstance(rationale, dict)
    assert rationale.get("result_status") == "completed"
    assert rationale.get("closure_not_reached_reason") is None
    assert isinstance(rationale.get("why_this_decision"), str) and rationale.get("why_this_decision")
    assert rationale.get("next_action")


def test_terminal_summary_final_decision_rationale_hitl_state_consumed_but_blockers_remain() -> None:
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
                            "closure_requirement": {"block_reason": "ambiguity", "mapping_blocking": True},
                        }
                    ],
                    "summary": {"blocking_open_count": 1},
                },
            },
        }
    ]
    result = build_run_result(
        run_artifact_ref=None,
        session_id="s18",
        iterations=2,
        status="needs_review",
        reason_code="tx_agent_no_progress:no_material_change",
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
            "hitl_lifecycle_log": [],
        },
    )
    summary = terminal_summary(progress_log, result, critical_events=[])
    rationale = summary.get("final_decision_rationale")
    assert isinstance(rationale, dict)
    hitl_state = rationale.get("hitl_feedback_state")
    assert isinstance(hitl_state, dict)
    assert hitl_state.get("hitl_feedback_provided") is True
    assert hitl_state.get("hitl_feedback_consumed") is True
    assert hitl_state.get("integration_status") == "consumed_but_blockers_remain"


def test_terminal_summary_includes_blocker_registry_waiting_feedback_owner() -> None:
    progress_log = [
        {
            "iteration": 1,
            "phase": "audit_result",
            "detail": {
                "error_count": 0,
                "decision_ledger": {
                    "items": [],
                    "summary": {"blocking_open_count": 1},
                },
            },
        }
    ]
    result = build_run_result(
        run_artifact_ref="ref://run",
        session_id="session-1",
        iterations=1,
        status="needs_review",
        reason_code="tx_agent_closure_requirements_unresolved",
        latest_refs={},
        review_required=True,
    )
    summary = terminal_summary(
        progress_log,
        result,
        runtime_hitl_state={
            "used_human_feedback": False,
            "feedback_received_count": 0,
            "feedback_consumed_count": 0,
            "feedback_stale_count": 0,
            "feedback_superseded_count": 0,
            "pending_feedback_prompt_id": "hitl_range_4_resolver",
            "pending_feedback_decision_key": "range",
            "human_resolution_tickets": [],
            "blocker_registry": {
                "active_blocker_id": "blocker:range",
                "counts": {"waiting_feedback": 1},
                "rows": [
                    {
                        "blocker_id": "blocker:range",
                        "decision_key": "range",
                        "state": "waiting_feedback",
                        "linked_prompt_id": "hitl_range_4_resolver",
                        "scope_status": "in_target",
                    }
                ],
            },
        },
    )
    owner = summary.get("waiting_feedback_owner")
    assert isinstance(owner, dict)
    assert str(owner.get("decision_key") or "") == "range"
    assert str(owner.get("linked_prompt_id") or "") == "hitl_range_4_resolver"
    assert str(summary.get("active_blocker_id") or "") == "blocker:range"


def test_terminal_summary_classifies_blocked_answered_unintegrated_no_safe_plan() -> None:
    result = build_run_result(
        run_artifact_ref="ref://run",
        session_id="session-1",
        iterations=2,
        status="needs_review",
        reason_code="tx_agent_consistent_feedback_no_safe_plan",
        latest_refs={},
        review_required=True,
    )
    summary = terminal_summary(
        [],
        result,
        runtime_hitl_state={
            "blocker_registry": {
                "counts": {"answered_unintegrated": 1, "waiting_feedback": 0, "open": 0},
                "active_blocker_id": "blocker:range",
                "rows": [
                    {
                        "blocker_id": "blocker:range",
                        "decision_key": "range",
                        "state": "answered_unintegrated",
                        "scope_status": "in_target",
                    }
                ],
                "history": [{"iteration": 2, "result": "feedback_present_no_safe_plan"}],
            }
        },
    )
    assert summary["terminal_classification"] == "blocked_answered_unintegrated_no_safe_plan"
    assert summary["actionable_returned_feedback_pending_integration"] is True


def test_terminal_summary_failed_status_not_masked_by_blocker_friendly_state() -> None:
    result = build_run_result(
        run_artifact_ref="ref://run",
        session_id="session-1",
        iterations=2,
        status="failed",
        reason_code="tx_agent_execution_failed",
        latest_refs={},
        review_required=True,
    )
    summary = terminal_summary(
        [],
        result,
        runtime_hitl_state={
            "blocker_registry": {
                "counts": {"answered_unintegrated": 1, "waiting_feedback": 0, "open": 0},
                "active_blocker_id": "blocker:range",
                "rows": [
                    {
                        "blocker_id": "blocker:range",
                        "decision_key": "range",
                        "state": "answered_unintegrated",
                        "scope_status": "in_target",
                    }
                ],
            }
        },
    )
    assert summary["terminal_classification"] == "blocked_execution_failed"
