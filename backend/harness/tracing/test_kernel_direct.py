"""Tests for kernel-direct trace adapter."""

from __future__ import annotations

from harness.tracing.adapters.kernel_direct import build_kernel_direct_trace


def _events_and_artifact() -> tuple[list[dict], dict]:
    events = [
        {
            "timestamp_epoch_seconds": 1,
            "event_kind": "request_start",
            "phase": "bootstrap",
            "iteration_index": None,
            "actor": "kernel",
            "status": "started",
            "refs_delta": {},
            "payload": {"session_id": "sx", "request_id": "rx"},
            "source_origin": {"kind": "kernel_live", "ref": "session:sx", "sequence_index": 0},
        },
        {
            "timestamp_epoch_seconds": 2,
            "event_kind": "terminal_outcome",
            "phase": "terminal",
            "iteration_index": 1,
            "actor": "kernel",
            "status": "completed",
            "refs_delta": {},
            "payload": {"terminal_class": "completed", "reason_code": "ok"},
            "source_origin": {"kind": "kernel_live", "ref": "session:sx", "sequence_index": 1},
        },
    ]
    artifact = {
        "run_id": "run-kd-1",
        "session_id": "sx::run-kd-1",
        "request_id": "rx",
        "created_at_epoch_seconds": 1,
        "source_entry_ref": "entry://1",
    }
    return events, artifact


def test_kernel_direct_preserves_ids_terminal_and_event_count() -> None:
    events, artifact = _events_and_artifact()
    trace = build_kernel_direct_trace(
        trace_events=events,
        run_artifact=artifact,
        run_artifact_ref="path/to/artifact.json",
    )
    assert trace.run_id == "run-kd-1"
    assert trace.session_id == "sx::run-kd-1"
    assert trace.request_id == "rx"
    assert trace.loop_family == "orchestration_kernel"
    assert trace.terminal.terminal_class == "completed"
    assert trace.terminal.terminal_reason_code == "ok"
    assert len(trace.events) == 2


def test_kernel_direct_empty_events_partial_completeness() -> None:
    trace = build_kernel_direct_trace(trace_events=[], run_artifact={"run_id": "r0", "request_id": "q0"})
    assert trace.completeness_status == "partial"
    assert "kernel_live_trace_events" in trace.missing_components
