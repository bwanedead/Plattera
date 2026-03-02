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
    )
    assert payload["event_type"] == "human_feedback_needed"
    assert payload["phase"] == "human_feedback_needed"
    assert payload["prompt_id"] == "hitl_1"
    assert isinstance(payload["choices"], list)
    assert payload["blocking"] is True


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
    )
    assert payload["phase"] == "plan_result"
    assert payload["detail"]["op_count"] == 2
    assert isinstance(payload["detail"]["ops_preview"], list)


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
        has_disagreements=True,
        latest_refs={},
    )
    assert payload["phase"] == "starting"
    assert payload["execution_state"] == "starting"
    assert "message" in payload
