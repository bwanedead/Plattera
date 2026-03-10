from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit import run_reporting


def test_audit_result_payload_contract_shape() -> None:
    payload = run_reporting.audit_result_payload(
        iteration=2,
        finding_count=3,
        error_count=1,
        warning_count=2,
        top_findings_display=[{"finding_id": "f1", "message": "m1"}],
        summary_text="m1",
        latest_refs={"tx_validator_report_ref": {"artifact_path": "in-memory://report"}},
        execution_state="executed",
    )
    assert payload["phase"] == "audit_result"
    assert payload["detail"]["finding_count"] == 3
    assert isinstance(payload["detail"]["top_findings"], list)
    assert "summary_text" in payload["detail"]
    assert payload["stream_kind"] == "narration"


def test_image_verify_result_payload_contract_shape() -> None:
    payload = run_reporting.image_verify_result_payload(
        iteration=1,
        latest_refs={},
        iv_payload={"summary": {"total_checks": 2}},
        iv_results=[{"check_id": "c1", "status": "match", "observed_text": "Range 75 West"}],
        iv_confirmed=1,
        iv_rejected=0,
        iv_total=1,
    )
    assert payload["phase"] == "image_verify_result"
    assert "image_verification" in payload
    assert payload["detail"]["confirmed"] == 1
    assert isinstance(payload["detail"]["results"], list)


def test_image_verify_progress_payload_includes_call_accounting() -> None:
    payload = run_reporting.image_verify_progress_payload(
        iteration=2,
        latest_refs={},
        decision_key="acreage",
        evidence_kind="image_verify",
        check_id="1/1:plss_range_conflict_001",
        check_decision_key="range",
        llm_call_seq=7,
        phase_attempt=2,
        stage="long_running",
        elapsed_seconds=61,
        wait_reason="awaiting_image_verify_step_response",
        phase_started_at_epoch_seconds=1773000001,
        timeout_seconds=90,
        max_attempts_per_check=1,
        check_index=1,
        check_total=1,
    )
    assert payload["iteration"] == 2
    assert payload["phase"] == "image_verify"
    detail = payload.get("detail") or {}
    assert detail.get("llm_call_seq") == 7
    assert detail.get("phase_attempt") == 2
    assert detail.get("decision_key") == "acreage"
    assert detail.get("check_decision_key") == "range"
    assert detail.get("wait_reason") == "awaiting_image_verify_step_response"
    assert detail.get("phase_started_at_epoch_seconds") == 1773000001
    assert detail.get("timeout_seconds") == 90
    assert detail.get("max_attempts_per_check") == 1
    assert detail.get("check_index") == 1
    assert detail.get("check_total") == 1


def test_image_verify_result_payload_includes_accounting_and_diagnostics() -> None:
    payload = run_reporting.image_verify_result_payload(
        iteration=1,
        latest_refs={},
        iv_payload={"summary": {"total_checks": 1}, "image_evidence_regions": [{"check_id": "c1"}]},
        iv_results=[{"check_id": "c1", "status": "error"}],
        iv_confirmed=0,
        iv_rejected=0,
        iv_total=1,
        decision_key="range",
        evidence_kind="image_verify",
        llm_call_seq_end=4,
        diagnostics=[{"error_code": "upstream_500"}],
    )
    detail = payload.get("detail") or {}
    assert detail.get("decision_key") == "range"
    assert detail.get("evidence_kind") == "image_verify"
    assert detail.get("llm_call_seq_end") == 4
    assert isinstance(detail.get("diagnostics"), list)
    assert isinstance(detail.get("image_evidence_regions"), list)


def test_human_feedback_needed_payload_contract_shape() -> None:
    prompt = {
        "prompt_id": "hitl_1",
        "line1": "Confirm range token for this deed",
        "choices": ["Range 74 West", "Range 75 West"],
        "default_choice": "Range 74 West",
        "context": {"range_values": [{"value": "r74w"}]},
    }
    payload = run_reporting.human_feedback_needed_payload(
        iteration=1,
        latest_refs={},
        feedback_prompt=prompt,
        evidence_attempts={"open_spans_count": 3, "image_verify_count": 2, "retrieval_count": 0},
    )
    assert payload["event_type"] == "human_feedback_needed"
    assert payload["phase"] == "human_feedback_needed"
    assert payload["prompt_id"] == "hitl_1"
    assert isinstance(payload["choices"], list)
    assert payload["blocking"] is False
    assert payload["evidence_attempts"]["open_spans_count"] == 3
    assert payload["evidence_attempts"]["image_verify_count"] == 2


def test_human_feedback_consumed_payload_contract_shape() -> None:
    payload = run_reporting.human_feedback_consumed_payload(
        iteration=2,
        latest_refs={},
        prompt_id="hitl_range_2_resolver",
        decision_key="range",
        selected_value="Range 75 West",
    )
    assert payload["event_type"] == "human_feedback"
    assert payload["phase"] == "human_feedback_consumed"
    assert payload["prompt_id"] == "hitl_range_2_resolver"
    assert payload["decision_key"] == "range"


def test_human_feedback_stale_and_superseded_payload_shapes() -> None:
    stale = run_reporting.human_feedback_stale_payload(
        iteration=3,
        latest_refs={},
        prompt_id="hitl_range_1_resolver",
        active_prompt_id="hitl_range_2_resolver",
        reason="stale_prompt_reply",
    )
    superseded = run_reporting.human_feedback_prompt_superseded_payload(
        iteration=3,
        latest_refs={},
        superseded_prompt_id="hitl_range_1_resolver",
        replacement_prompt_id="hitl_range_2_resolver",
        decision_key="range",
        reason="resolver_requested_feedback",
    )
    assert stale["phase"] == "human_feedback_stale"
    assert stale["active_prompt_id"] == "hitl_range_2_resolver"
    assert superseded["phase"] == "human_feedback_prompt_superseded"
    assert superseded["replacement_prompt_id"] == "hitl_range_2_resolver"


def test_resolver_invalid_payload_contract_shape() -> None:
    payload = run_reporting.resolver_invalid_payload(
        iteration=2,
        latest_refs={},
        reason="ValidationError",
        invalid_plan_strikes=2,
        max_invalid_plan_attempts=3,
        exhausted=False,
        decision_key="range",
        post_feedback_ticket_state="answered_unintegrated",
        post_feedback_ticket_id="hitl_range_1_resolver",
        validation_error_class="ValidationError",
        raw_output_excerpt='{"move":"bad"}',
    )
    assert payload["event_type"] == "resolver_invalid"
    assert payload["phase"] == "resolver_invalid"
    detail = payload.get("detail") or {}
    assert detail.get("reason") == "ValidationError"
    assert detail.get("invalid_plan_strikes") == 2
    assert detail.get("decision_key") == "range"
    assert detail.get("post_feedback_ticket_state") == "answered_unintegrated"
    assert detail.get("validation_error_class") == "ValidationError"
    assert "raw_output_excerpt" in detail


def test_resolver_attempt_and_outcome_payload_shapes() -> None:
    attempt = run_reporting.resolver_attempt_payload(
        iteration=2,
        latest_refs={},
        decision_key="range",
        resolver_attempt_number=2,
        is_repair_attempt=True,
        ticket_snapshot={"ticket_id": "hitl_range_1", "ticket_state": "answered_unintegrated"},
    )
    outcome = run_reporting.resolver_outcome_payload(
        iteration=2,
        latest_refs={},
        decision_key="range",
        move="mark_blocked",
        result_category="invalid_schema",
        reason="resolver_move_invalid:resolver_invalid:ValidationError:invalid_move",
        resolver_attempt_number=2,
        is_repair_attempt=True,
        ticket_snapshot={"ticket_id": "hitl_range_1", "ticket_state": "answered_unintegrated"},
        validation_error_class="ValidationError",
        raw_output_excerpt='{"move":"bad"}',
    )
    assert attempt["phase"] == "resolver_attempt"
    assert (attempt.get("detail") or {}).get("resolver_attempt_number") == 2
    assert outcome["phase"] == "resolver_outcome"
    assert (outcome.get("detail") or {}).get("result_category") == "invalid_schema"
    assert (outcome.get("detail") or {}).get("validation_error_class") == "ValidationError"


def test_resolver_move_gate_payload_shape() -> None:
    payload = run_reporting.resolver_move_gate_payload(
        iteration=3,
        latest_refs={},
        decision_key="range",
        move="gather_more_evidence",
        gate_outcome="rejected",
        gate_reason="rejected_repeated_evidence_after_binding_feedback",
        ticket_snapshot={"ticket_id": "hitl_range_1", "ticket_state": "answered_unintegrated"},
    )
    assert payload["phase"] == "resolver_move_gate"
    detail = payload.get("detail") or {}
    assert detail.get("gate_outcome") == "rejected"
    assert detail.get("gate_reason") == "rejected_repeated_evidence_after_binding_feedback"


def test_resolver_move_gate_payload_includes_normalize_diagnostics_when_provided() -> None:
    payload = run_reporting.resolver_move_gate_payload(
        iteration=2,
        latest_refs={},
        decision_key="range",
        move="gather_more_evidence",
        gate_outcome="rejected",
        gate_reason="invalid_evidence_request",
        normalize_reason="image_evidence_verify_region_query_missing",
        evidence_request_kind="image_evidence",
        evidence_request_mode="verify_region",
    )
    detail = payload.get("detail") or {}
    assert detail.get("gate_reason") == "invalid_evidence_request"
    assert detail.get("normalize_reason") == "image_evidence_verify_region_query_missing"
    assert detail.get("evidence_request_kind") == "image_evidence"
    assert detail.get("evidence_request_mode") == "verify_region"


def test_human_resolution_ticket_state_payload_contract_shape() -> None:
    payload = run_reporting.human_resolution_ticket_state_payload(
        iteration=3,
        latest_refs={},
        ticket_id="hitl_range_1_resolver",
        decision_key="range",
        lifecycle_state="integration_attempted_failed",
        strength="binding",
        relevance="active",
        reason="resolver_invalid_exhausted",
    )
    assert payload["event_type"] == "human_resolution_ticket"
    assert payload["phase"] == "ticket_integration_attempted_failed"
    assert payload["ticket_id"] == "hitl_range_1_resolver"
    assert payload["lifecycle_state"] == "integration_attempted_failed"


def test_open_spans_result_payload_contract_shape() -> None:
    payload = run_reporting.open_spans_result_payload(
        iteration=2,
        latest_refs={},
        spans_display=[{"span_id": "s1", "text": "example"}],
    )
    assert payload["phase"] == "open_spans_result"
    assert "detail" in payload
    assert isinstance(payload["detail"]["spans"], list)


def test_plan_result_payload_contract_shape() -> None:
    payload = run_reporting.plan_result_payload(
        iteration=3,
        latest_refs={},
        plan_reason="manual_plan",
        op_count=2,
        ops_preview=[{"op_type": "replace_span"}],
        ticket_lifecycle_snapshot=[
            {
                "ticket_id": "hitl_range_1_resolver",
                "decision_key": "range",
                "lifecycle_state": "answered_unintegrated",
            }
        ],
    )
    assert payload["phase"] == "plan_result"
    assert payload["detail"]["op_count"] == 2
    assert isinstance(payload["detail"]["ops_preview"], list)
    assert isinstance(payload["detail"]["ticket_lifecycle_snapshot"], list)


def test_apply_result_payload_contract_shape() -> None:
    payload = run_reporting.apply_result_payload(
        iteration=3,
        latest_refs={},
        execution_state="executed",
        plan_op_count=2,
        ops_display=[{"op_type": "replace_span"}],
    )
    assert payload["phase"] == "apply_result"
    assert payload["detail"]["plan_op_count"] == 2
    assert isinstance(payload["detail"]["ops"], list)


def test_starting_payload_contract_shape() -> None:
    payload = run_reporting.starting_payload(
        mode="audit_then_repair_then_promote",
        candidate_count=3,
        latest_refs={},
    )
    assert payload["phase"] == "starting"
    assert payload["execution_state"] == "starting"
    assert "message" in payload
    assert payload["stream_kind"] == "narration"
def test_ticker_payload_contract_shape() -> None:
    payload = run_reporting.ticker_payload(
        iteration=2,
        phase="plan",
        message="Drafting plan",
        latest_refs={},
    )
    assert payload["phase"] == "plan"
    assert payload["stream_kind"] == "ticker"


def test_preflight_countdown_payload_contract_shape() -> None:
    payload = run_reporting.preflight_countdown_payload(
        remaining_seconds=60,
        latest_refs={},
    )
    assert payload["phase"] == "preflight_countdown"
    assert payload["stream_kind"] == "ticker"
    assert payload["execution_state"] == "waiting"
    assert "60s remaining" in payload["message"]


def test_investigation_baseline_payload_contract_shape() -> None:
    payload = run_reporting.investigation_baseline_payload(
        iteration=1,
        latest_refs={},
        conflict_map=[{"decision_key": "range", "values": ["r74w", "r75w"], "conflict": True}],
    )
    assert payload["phase"] == "investigation_baseline"
    assert payload["stream_kind"] == "narration"
    assert payload["detail"]["conflict_count"] == 1
    assert isinstance(payload["detail"]["conflict_map"], list)


def test_investigation_baseline_result_payload_contract_shape() -> None:
    payload = run_reporting.investigation_baseline_result_payload(
        iteration=1,
        latest_refs={},
        evidence_attempts=[{"attempt": "open_spans", "status": "completed", "result_count": 4}],
        residual_blockers=[{"decision_key": "range", "mapping_blocking": True}],
        mapping_blocking_count=1,
        optional_count=0,
        next_recommended_action="Range: confirm token.",
        decision_ledger={"items": []},
    )
    assert payload["phase"] == "investigation_baseline_result"
    assert payload["detail"]["mapping_blocking_count"] == 1
    assert isinstance(payload["detail"]["evidence_attempts"], list)
    assert isinstance(payload["detail"]["residual_blockers"], list)
