from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.tracing.adapters.controller_kernel import (
    build_controller_kernel_trace,
    build_controller_kernel_trace_from_paths,
)


def _happy_transcript() -> dict:
    return {
        "events": [
            {
                "event_type": "run_header",
                "detail": "controller_run_started",
                "timestamp_epoch_seconds": 100,
                "payload": {
                    "request_id": "request-1",
                    "session_id": "request-1::run-1",
                    "run_artifact_ref": "artifact://run-1",
                    "model": "gpt-5-mini",
                    "tool_menu": ["retrieve_evidence", "compile", "declare_done"],
                    "budgets": {"max_steps": 20},
                    "dossier_id": "dossier-1",
                    "source_entry_ref": "entry-1",
                    "bootstrap_context": {"deed_text_artifact_ref": "artifact://deed-text"},
                },
            },
            {
                "event_type": "agent_proposed_step",
                "detail": "retrieve_evidence",
                "timestamp_epoch_seconds": 101,
                "payload": {
                    "iteration": 1,
                    "action_type": "retrieve_evidence",
                    "args": {"query": "grantor chain"},
                    "proposal_source": "model",
                    "why": "Need evidence",
                },
            },
            {
                "event_type": "retrieval_degradation",
                "detail": "fallback_to_keyword",
                "timestamp_epoch_seconds": 102,
                "payload": {"reason_code": "retrieval_sparse_context", "fallback": "open_text_spans"},
            },
            {
                "event_type": "kernel_step_result",
                "detail": "executed",
                "timestamp_epoch_seconds": 103,
                "payload": {
                    "iteration": 1,
                    "execution_state": "executed",
                    "action_type": "retrieve_evidence",
                    "idempotency_key": "idemp-1",
                    "refusal": None,
                    "terminal": None,
                    "dashboard_failure_classification": {},
                    "latest_refs": {"retrieval_ref": "artifact://retrieval-1"},
                },
            },
            {
                "event_type": "kernel_step_result",
                "detail": "executed",
                "timestamp_epoch_seconds": 104,
                "payload": {
                    "iteration": 2,
                    "execution_state": "executed",
                    "action_type": "declare_done",
                    "idempotency_key": "idemp-2",
                    "refusal": None,
                    "terminal": {
                        "terminal_outcome": "SUCCESS",
                        "stop_reason": "completed",
                        "success": True,
                        "reason_code": "done_verified",
                    },
                    "dashboard_failure_classification": {},
                    "latest_refs": {"bundle_ref": "artifact://bundle-1"},
                },
            },
        ]
    }


def _happy_run_artifact() -> dict:
    return {
        "run_id": "run-1",
        "request_id": "request-1",
        "session_id": "request-1::run-1",
        "created_at_epoch_seconds": 100,
        "requires_global_placement": False,
        "render_required": False,
        "session_budgets": {"max_steps": 20},
        "steps": [
            {
                "step_id": "step-001",
                "action": "retrieve_evidence",
                "inputs": {"query": "grantor chain"},
                "outputs": {"retrieval_artifact_ref": {"artifact_path": "artifact://retrieval-1"}},
                "reason_codes": ["retrieval_executed"],
            },
            {
                "step_id": "step-002",
                "action": "declare_done",
                "inputs": {},
                "outputs": {"bundle_artifact_ref": {"artifact_path": "artifact://bundle-1"}},
                "reason_codes": ["done_verified"],
            },
        ],
        "idempotency_ledger": {},
    }


def test_controller_kernel_adapter_happy_path_mapping() -> None:
    trace = build_controller_kernel_trace(
        controller_transcript=_happy_transcript(),
        run_artifact=_happy_run_artifact(),
        transcript_ref="artifact://controller-transcript-1",
        run_artifact_ref="artifact://run-artifact-1",
    )
    kinds = [event.event_kind for event in trace.events]
    assert "request_start" in kinds
    assert "model_proposal" in kinds
    assert "tool_execution" in kinds
    assert "retrieval_evidence" in kinds
    assert "terminal_outcome" in kinds
    assert "blocker_transition" not in kinds
    assert len([event for event in trace.events if event.event_kind == "tool_execution"]) == 2
    assert trace.terminal.terminal_class == "completed"
    assert trace.terminal.terminal_reason_code == "done_verified"


def test_controller_kernel_adapter_refusal_heavy_mapping() -> None:
    transcript = {
        "events": [
            {
                "event_type": "run_header",
                "detail": "controller_run_started",
                "timestamp_epoch_seconds": 10,
                "payload": {"request_id": "request-r", "session_id": "request-r::run-r"},
            },
            {
                "event_type": "agent_proposed_step",
                "detail": "compile",
                "timestamp_epoch_seconds": 11,
                "payload": {"iteration": 1, "action_type": "compile", "args": {}},
            },
            {
                "event_type": "kernel_step_result",
                "detail": "refused",
                "timestamp_epoch_seconds": 12,
                "payload": {
                    "iteration": 1,
                    "execution_state": "refused",
                    "action_type": "compile",
                    "idempotency_key": "idemp-r",
                    "refusal": {"reason_code": "missing_ir", "retryable": True},
                    "terminal": {
                        "terminal_outcome": "FAILED",
                        "stop_reason": "validation_failed",
                        "success": False,
                        "reason_code": "missing_ir",
                    },
                    "dashboard_failure_classification": {"reason_code": "missing_ir"},
                    "latest_refs": {},
                },
            },
        ]
    }
    run_artifact = {
        "run_id": "run-r",
        "request_id": "request-r",
        "session_id": "request-r::run-r",
        "created_at_epoch_seconds": 10,
        "steps": [],
        "idempotency_ledger": {},
    }
    trace = build_controller_kernel_trace(
        controller_transcript=transcript,
        run_artifact=run_artifact,
        transcript_ref="artifact://controller-transcript-r",
        run_artifact_ref="artifact://run-artifact-r",
    )
    refused_tool_events = [
        event for event in trace.events if event.event_kind == "tool_execution" and event.status == "refused"
    ]
    assert refused_tool_events
    assert refused_tool_events[0].reason_code == "missing_ir"
    assert trace.terminal.terminal_class == "blocked"
    assert trace.terminal.terminal_reason_code == "missing_ir"


def test_controller_kernel_adapter_truncated_transcript_marks_partial() -> None:
    transcript = _happy_transcript()
    transcript["events"].insert(
        0,
        {
            "event_type": "transcript_truncated",
            "detail": "dropped_oldest_events_count=12",
            "timestamp_epoch_seconds": 99,
            "payload": {},
        },
    )
    trace = build_controller_kernel_trace(
        controller_transcript=transcript,
        run_artifact=_happy_run_artifact(),
        transcript_ref="artifact://controller-transcript-truncated",
        run_artifact_ref="artifact://run-artifact-truncated",
    )
    assert trace.completeness_status == "partial"
    assert "controller_transcript_history" in trace.missing_components
    assert "controller_transcript_truncated" in trace.normalization_warnings


def test_controller_kernel_adapter_preserves_provenance() -> None:
    trace = build_controller_kernel_trace(
        controller_transcript=_happy_transcript(),
        run_artifact=_happy_run_artifact(),
        transcript_ref="artifact://controller-transcript-prov",
        run_artifact_ref="artifact://run-artifact-prov",
    )
    assert all(event.source_origin.kind != "unknown" for event in trace.events)
    transcript_events = [event for event in trace.events if event.source_origin.kind == "controller_transcript"]
    step_events = [event for event in trace.events if event.source_origin.kind == "kernel_step_record"]
    assert transcript_events
    assert step_events
    assert step_events[0].payload.get("step_id") == "step-001"
    assert transcript_events[0].source_origin.sequence_index == 0


def test_controller_kernel_adapter_bounds_payload_fields() -> None:
    transcript = _happy_transcript()
    transcript["events"][1]["payload"]["display_delta"] = "x" * 600
    transcript["events"][2]["payload"]["fallback"] = "y" * 600
    trace = build_controller_kernel_trace(
        controller_transcript=transcript,
        run_artifact=_happy_run_artifact(),
        transcript_ref="artifact://controller-transcript-bounds",
        run_artifact_ref="artifact://run-artifact-bounds",
    )
    proposal_event = next(event for event in trace.events if event.event_kind == "model_proposal")
    retrieval_event = next(event for event in trace.events if event.event_kind == "retrieval_evidence")
    assert len(proposal_event.payload.get("display_delta_excerpt", "")) <= 240
    assert len(retrieval_event.payload.get("fallback_excerpt", "")) <= 180


def test_controller_kernel_adapter_marks_partial_on_step_alignment_mismatch() -> None:
    transcript = _happy_transcript()
    run_artifact = _happy_run_artifact()
    run_artifact["steps"][0]["action"] = "compile"
    run_artifact["steps"][1]["action"] = "validate"
    trace = build_controller_kernel_trace(
        controller_transcript=transcript,
        run_artifact=run_artifact,
        transcript_ref="artifact://controller-transcript-mismatch",
        run_artifact_ref="artifact://run-artifact-mismatch",
    )
    assert trace.completeness_status == "partial"
    assert "kernel_step_alignment" in trace.missing_components
    assert "kernel_step_alignment_missing" in trace.normalization_warnings
    kernel_source_events = [event for event in trace.events if event.source_origin.kind == "kernel_step_record"]
    assert not kernel_source_events


def test_controller_kernel_adapter_is_deterministic_for_same_inputs() -> None:
    transcript = _happy_transcript()
    run_artifact = _happy_run_artifact()
    trace_a = build_controller_kernel_trace(
        controller_transcript=copy.deepcopy(transcript),
        run_artifact=copy.deepcopy(run_artifact),
        transcript_ref="artifact://controller-transcript-det",
        run_artifact_ref="artifact://run-artifact-det",
    )
    trace_b = build_controller_kernel_trace(
        controller_transcript=copy.deepcopy(transcript),
        run_artifact=copy.deepcopy(run_artifact),
        transcript_ref="artifact://controller-transcript-det",
        run_artifact_ref="artifact://run-artifact-det",
    )
    assert [event.event_id for event in trace_a.events] == [event.event_id for event in trace_b.events]
    assert [event.event_index for event in trace_a.events] == [event.event_index for event in trace_b.events]
    assert json.dumps(trace_a.model_dump(mode="json"), sort_keys=True) == json.dumps(
        trace_b.model_dump(mode="json"), sort_keys=True
    )


def test_controller_kernel_adapter_path_loader_reads_payloads(tmp_path: Path) -> None:
    transcript_path = tmp_path / "controller_transcript.json"
    run_artifact_path = tmp_path / "run_artifact.json"
    transcript_path.write_text(json.dumps(_happy_transcript()), encoding="utf-8")
    run_artifact_path.write_text(json.dumps(_happy_run_artifact()), encoding="utf-8")
    trace = build_controller_kernel_trace_from_paths(
        controller_transcript_path=str(transcript_path),
        run_artifact_path=str(run_artifact_path),
    )
    assert trace.run_id == "run-1"
    assert trace.request_id == "request-1"
