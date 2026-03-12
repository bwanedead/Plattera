from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.review.tool import build_multi_run_review_bundle, build_single_run_review_bundle

_FIXTURE_ROOT = Path(__file__).with_name("test_fixtures") / "harness_regression_pack"


def _load_case(case_name: str) -> dict:
    path = _FIXTURE_ROOT / case_name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("fixture_name", "expected"),
    [
        (
            "controller_completed.json",
            {
                "loop_family": "controller_kernel",
                "terminal_class": "completed",
                "reason_code": "done_verified",
                "waiting": False,
                "verification_present": False,
                "partial_trace": False,
                "required_flag": "missing_verification_before_completion",
            },
        ),
        (
            "controller_waiting_evidence.json",
            {
                "loop_family": "controller_kernel",
                "terminal_class": "waiting_evidence",
                "reason_code": "missing_uploaded_document",
                "waiting": True,
                "waiting_kind": "evidence",
                "verification_present": False,
                "partial_trace": False,
                "required_flag": "waiting_evidence_without_retrieval_signal",
            },
        ),
        (
            "transcript_edit_completed_promoted.json",
            {
                "loop_family": "transcript_edit",
                "terminal_class": "completed",
                "reason_code": "tx_agent_transcript_clean_promoted",
                "waiting": False,
                "verification_present": True,
                "partial_trace": False,
            },
        ),
        (
            "transcript_edit_waiting_feedback.json",
            {
                "loop_family": "transcript_edit",
                "terminal_class": "waiting_human",
                "reason_code": "tx_agent_closure_requirements_unresolved",
                "waiting": True,
                "waiting_kind": "human_feedback",
                "resumable": True,
                "verification_present": False,
                "partial_trace": False,
            },
        ),
        (
            "transcript_edit_partial_history.json",
            {
                "loop_family": "transcript_edit",
                "terminal_class": "completed",
                "reason_code": "tx_agent_transcript_clean_promoted",
                "waiting": False,
                "verification_present": True,
                "partial_trace": True,
                "required_flag": "partial_trace_needs_caution",
                "required_warning": "tx_progress_log_bounded",
            },
        ),
    ],
)
def test_regression_case_normalized_outputs_are_stable(fixture_name: str, expected: dict) -> None:
    payload = _load_case(fixture_name)
    bundle = build_single_run_review_bundle(payload=payload)
    run = bundle["runs"][0]
    trace = run["trace"]
    run_state = run["run_state"]
    review = run["review"]

    assert trace["loop_family"] == expected["loop_family"]
    assert run_state["loop_family"] == expected["loop_family"]
    assert review["loop_family"] == expected["loop_family"]

    assert trace["terminal"]["terminal_class"] == expected["terminal_class"]
    assert run_state["terminal_summary"]["terminal_class"] == expected["terminal_class"]
    assert review["terminal_class"] == expected["terminal_class"]

    assert trace["terminal"]["terminal_reason_code"] == expected["reason_code"]
    assert run_state["terminal_summary"]["reason_code"] == expected["reason_code"]
    assert review["reason_code"] == expected["reason_code"]

    assert run_state["waiting_summary"]["waiting"] is expected["waiting"]
    assert review["verification_present"] is expected["verification_present"]
    assert review["partial_trace"] is expected["partial_trace"]
    assert trace["completeness_status"] == ("partial" if expected["partial_trace"] else "complete")

    waiting_kind = expected.get("waiting_kind")
    if waiting_kind:
        assert run_state["waiting_summary"]["waiting_kind"] == waiting_kind
    resumable = expected.get("resumable")
    if isinstance(resumable, bool):
        assert run_state["waiting_summary"]["resumable"] is resumable

    required_flag = expected.get("required_flag")
    if required_flag:
        assert required_flag in review["review_flags"]
    required_warning = expected.get("required_warning")
    if required_warning:
        assert required_warning in trace["normalization_warnings"]


def test_regression_pack_mixed_run_aggregate_is_stable() -> None:
    payloads = [
        _load_case("controller_completed.json"),
        _load_case("controller_waiting_evidence.json"),
        _load_case("transcript_edit_completed_promoted.json"),
        _load_case("transcript_edit_waiting_feedback.json"),
        _load_case("transcript_edit_partial_history.json"),
    ]
    bundle = build_multi_run_review_bundle(payloads=payloads)
    aggregate = bundle["aggregate"]

    assert bundle["metadata"]["run_count"] == 5
    assert bundle["metadata"]["loop_family"] == "mixed"
    assert bundle["metadata"]["partial_trace_note"]["contains_partial_traces"] is True
    assert bundle["metadata"]["partial_trace_note"]["partial_run_count"] == 1

    assert aggregate["loop_family_distribution"]["controller_kernel"] == 2
    assert aggregate["loop_family_distribution"]["transcript_edit"] == 3
    assert aggregate["terminal_class_distribution"]["completed"] == 3
    assert aggregate["terminal_class_distribution"]["waiting_human"] == 1
    assert aggregate["terminal_class_distribution"]["waiting_evidence"] == 1
    assert aggregate["partial_trace_rate"] == 0.2
    assert aggregate["waiting_human_rate"] == 0.2
    assert aggregate["waiting_evidence_rate"] == 0.2
    assert aggregate["verification_missing_on_completion_count"] == 1
