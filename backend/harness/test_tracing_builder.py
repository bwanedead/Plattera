from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.tracing.builder import build_canonical_trace
from harness.tracing.schema import TRACE_VERSION


def _event(
    *,
    timestamp: int | None,
    sequence_index: int,
    event_kind: str = "iteration",
    payload: dict | None = None,
) -> dict:
    return {
        "timestamp_epoch_seconds": timestamp,
        "event_kind": event_kind,
        "phase": "phase",
        "iteration_index": 0,
        "actor": "harness",
        "status": "running",
        "reason_code": None,
        "refs_delta": {},
        "payload": dict(payload or {}),
        "source_origin": {
            "kind": "fixture",
            "ref": "fixture://source",
            "local_id": f"row-{sequence_index}",
            "sequence_index": sequence_index,
        },
    }


def _terminal() -> dict:
    return {"terminal_class": "completed", "terminal_reason_code": "ok", "success": True}


def test_builder_sorts_events_by_timestamp() -> None:
    trace = build_canonical_trace(
        trace_id="trace-1",
        run_id="run-1",
        session_id="s1",
        request_id="r1",
        loop_family="controller_kernel",
        request_metadata={},
        start_context_summary={},
        started_at_epoch_seconds=100,
        events=[
            _event(timestamp=300, sequence_index=2),
            _event(timestamp=100, sequence_index=1),
            _event(timestamp=200, sequence_index=0),
        ],
        terminal=_terminal(),
        trace_version=TRACE_VERSION,
    )
    assert [e.timestamp_epoch_seconds for e in trace.events] == [100, 200, 300]


def test_builder_equal_timestamps_use_stable_fallback_ordering() -> None:
    trace = build_canonical_trace(
        trace_id="trace-1",
        run_id="run-1",
        session_id="s1",
        request_id="r1",
        loop_family="controller_kernel",
        request_metadata={},
        start_context_summary={},
        started_at_epoch_seconds=100,
        events=[
            _event(timestamp=100, sequence_index=3, payload={"marker": "third"}),
            _event(timestamp=100, sequence_index=1, payload={"marker": "first"}),
            _event(timestamp=100, sequence_index=2, payload={"marker": "second"}),
        ],
        terminal=_terminal(),
    )
    markers = [e.payload["marker"] for e in trace.events]
    assert markers == ["first", "second", "third"]


def test_builder_equal_timestamp_and_sequence_prefers_request_start() -> None:
    trace = build_canonical_trace(
        trace_id="trace-1",
        run_id="run-1",
        session_id="s1",
        request_id="r1",
        loop_family="controller_kernel",
        request_metadata={},
        start_context_summary={},
        started_at_epoch_seconds=100,
        events=[
            _event(timestamp=100, sequence_index=0, event_kind="iteration", payload={"marker": "iteration"}),
            _event(timestamp=100, sequence_index=0, event_kind="request_start", payload={"marker": "request_start"}),
        ],
        terminal=_terminal(),
    )
    markers = [e.payload["marker"] for e in trace.events]
    assert markers == ["request_start", "iteration"]


def test_builder_derives_missing_timestamps_deterministically() -> None:
    trace = build_canonical_trace(
        trace_id="trace-1",
        run_id="run-1",
        session_id="s1",
        request_id="r1",
        loop_family="transcript_edit",
        request_metadata={},
        start_context_summary={},
        started_at_epoch_seconds=500,
        events=[
            _event(timestamp=None, sequence_index=0),
            _event(timestamp=None, sequence_index=1),
        ],
        terminal=_terminal(),
    )
    assert [e.timestamp_epoch_seconds for e in trace.events] == [500, 501]
    assert all(e.payload.get("timestamp_source") == "derived_sequence" for e in trace.events)


def test_builder_derives_missing_timestamps_from_started_at_plus_source_sequence() -> None:
    trace = build_canonical_trace(
        trace_id="trace-1",
        run_id="run-1",
        session_id="s1",
        request_id="r1",
        loop_family="transcript_edit",
        request_metadata={},
        start_context_summary={},
        started_at_epoch_seconds=500,
        events=[
            _event(timestamp=None, sequence_index=4, payload={"marker": "later_sequence"}),
            _event(timestamp=None, sequence_index=1, payload={"marker": "earlier_sequence"}),
        ],
        terminal=_terminal(),
    )
    assert [e.timestamp_epoch_seconds for e in trace.events] == [501, 504]
    assert [e.payload["marker"] for e in trace.events] == ["earlier_sequence", "later_sequence"]


def test_builder_assigns_monotonic_event_index_and_deterministic_event_id() -> None:
    trace = build_canonical_trace(
        trace_id="trace-xyz",
        run_id="run-1",
        session_id="s1",
        request_id="r1",
        loop_family="controller_kernel",
        request_metadata={},
        start_context_summary={},
        started_at_epoch_seconds=0,
        events=[
            _event(timestamp=2, sequence_index=0),
            _event(timestamp=1, sequence_index=1),
        ],
        terminal=_terminal(),
    )
    assert [e.event_index for e in trace.events] == [0, 1]
    assert [e.event_id for e in trace.events] == ["trace-xyz:e0000", "trace-xyz:e0001"]


def test_builder_preserves_completeness_metadata_and_auto_partial() -> None:
    trace = build_canonical_trace(
        trace_id="trace-1",
        run_id="run-1",
        session_id="s1",
        request_id="r1",
        loop_family="transcript_edit",
        request_metadata={},
        start_context_summary={},
        started_at_epoch_seconds=100,
        events=[_event(timestamp=100, sequence_index=0)],
        terminal=_terminal(),
        completeness_status="complete",
        missing_components=["progress_log"],
        normalization_warnings=["preexisting_warning"],
    )
    assert trace.completeness_status == "partial"
    assert trace.missing_components == ["progress_log"]
    assert "preexisting_warning" in trace.normalization_warnings


def test_builder_warnings_are_bounded_and_components_attached() -> None:
    warnings = [f"w{i}" for i in range(60)]
    components = [f"c{i}" for i in range(50)]
    trace = build_canonical_trace(
        trace_id="trace-1",
        run_id="run-1",
        session_id="s1",
        request_id="r1",
        loop_family="controller_kernel",
        request_metadata={},
        start_context_summary={},
        started_at_epoch_seconds=100,
        events=[_event(timestamp=100, sequence_index=0)],
        terminal=_terminal(),
        normalization_warnings=warnings,
        missing_components=components,
    )
    assert len(trace.normalization_warnings) <= 32
    assert len(trace.missing_components) <= 32


def test_builder_preserves_synthesized_marker_in_payload() -> None:
    trace = build_canonical_trace(
        trace_id="trace-1",
        run_id="run-1",
        session_id="s1",
        request_id="r1",
        loop_family="controller_kernel",
        request_metadata={},
        start_context_summary={},
        started_at_epoch_seconds=100,
        events=[
            _event(
                timestamp=100,
                sequence_index=0,
                event_kind="blocker_transition",
                payload={"synthesized": True},
            )
        ],
        terminal=_terminal(),
    )
    assert trace.events[0].payload["synthesized"] is True


def test_builder_does_not_fabricate_absent_semantic_payload_data() -> None:
    trace = build_canonical_trace(
        trace_id="trace-1",
        run_id="run-1",
        session_id="s1",
        request_id="r1",
        loop_family="transcript_edit",
        request_metadata={},
        start_context_summary={},
        started_at_epoch_seconds=100,
        events=[_event(timestamp=100, sequence_index=0, payload={"custom_field": "x"})],
        terminal=_terminal(),
        missing_components=["decision_ledger"],
    )
    payload = trace.events[0].payload
    assert payload["custom_field"] == "x"
    assert "timestamp_source" in payload
    assert "closure_state" not in payload


def test_builder_partial_trace_behavior_with_missing_components() -> None:
    trace = build_canonical_trace(
        trace_id="trace-1",
        run_id="run-1",
        session_id="s1",
        request_id="r1",
        loop_family="transcript_edit",
        request_metadata={},
        start_context_summary={},
        started_at_epoch_seconds=100,
        events=[_event(timestamp=100, sequence_index=0)],
        terminal=_terminal(),
        completeness_status="partial",
        missing_components=["critical_events"],
    )
    assert trace.completeness_status == "partial"
    assert trace.missing_components == ["critical_events"]
