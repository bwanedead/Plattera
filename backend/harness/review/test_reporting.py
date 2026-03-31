"""Tests for review reporting aggregates and run summaries."""

from __future__ import annotations

from harness.review.reporting import build_review_aggregate, build_run_review_summary
from harness.tracing.adapters.kernel_direct import build_kernel_direct_trace


def _trace_complete() -> object:
    events, artifact = (
        [
            {
                "timestamp_epoch_seconds": 1,
                "event_kind": "request_start",
                "phase": "bootstrap",
                "iteration_index": None,
                "actor": "kernel",
                "status": "started",
                "refs_delta": {},
                "payload": {},
                "source_origin": {"kind": "k", "ref": "r", "sequence_index": 0},
            },
            {
                "timestamp_epoch_seconds": 2,
                "event_kind": "terminal_outcome",
                "phase": "terminal",
                "iteration_index": 1,
                "actor": "kernel",
                "status": "completed",
                "refs_delta": {},
                "payload": {"terminal_class": "completed", "reason_code": "x"},
                "source_origin": {"kind": "k", "ref": "r", "sequence_index": 1},
            },
        ],
        {"run_id": "r-rep-1", "session_id": "s", "request_id": "q", "created_at_epoch_seconds": 1},
    )
    return build_kernel_direct_trace(trace_events=events, run_artifact=artifact)


def test_build_run_review_summary_from_trace() -> None:
    trace = _trace_complete()
    summary = build_run_review_summary(trace=trace)
    assert summary.run_id == "r-rep-1"
    assert summary.loop_family == "orchestration_kernel"
    assert summary.event_count == 2
    assert summary.partial_trace is False


def test_build_review_aggregate_multi_family() -> None:
    t1 = _trace_complete()
    s1 = build_run_review_summary(trace=t1)
    t2 = build_kernel_direct_trace(
        trace_events=[],
        run_artifact={"run_id": "r-partial", "request_id": "q"},
    )
    s2 = build_run_review_summary(trace=t2)
    agg = build_review_aggregate(summaries=[s1, s2])
    assert agg.run_count == 2
    assert agg.loop_family_distribution.get("orchestration_kernel", 0) >= 1
    assert agg.partial_trace_rate > 0


def test_partial_trace_flag() -> None:
    trace = build_kernel_direct_trace(trace_events=[], run_artifact={"run_id": "rp", "request_id": "q"})
    summary = build_run_review_summary(trace=trace)
    assert summary.partial_trace is True
