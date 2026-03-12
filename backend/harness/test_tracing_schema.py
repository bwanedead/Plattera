from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.tracing.schema import (
    TRACE_VERSION,
    CanonicalTraceEvent,
    CanonicalTraceRecord,
    SourceOrigin,
    TerminalSnapshot,
)


def _minimal_event() -> dict:
    return {
        "event_id": "t:e0000",
        "event_index": 0,
        "timestamp_epoch_seconds": 100,
        "event_kind": "request_start",
        "phase": "starting",
        "iteration_index": 0,
        "actor": "harness",
        "status": "started",
        "reason_code": None,
        "refs_delta": {},
        "payload": {"timestamp_source": "source"},
        "source_origin": {"kind": "fixture", "ref": "fixture://event", "local_id": None, "sequence_index": 0},
    }


def test_schema_minimal_trace_record_is_valid() -> None:
    event = CanonicalTraceEvent.model_validate(_minimal_event())
    trace = CanonicalTraceRecord(
        trace_id="trace-1",
        run_id="run-1",
        session_id="session-1",
        request_id="request-1",
        loop_family="controller_kernel",
        request_metadata={},
        start_context_summary={},
        started_at_epoch_seconds=100,
        events=[event],
        terminal=TerminalSnapshot(terminal_class="completed"),
        completeness_status="complete",
        missing_components=[],
        normalization_warnings=[],
        trace_version=TRACE_VERSION,
    )
    assert trace.trace_version == TRACE_VERSION
    assert trace.events[0].event_kind == "request_start"


def test_schema_missing_required_top_level_field_fails() -> None:
    with pytest.raises(ValidationError) as exc:
        CanonicalTraceRecord(
            trace_id="trace-1",
            session_id="session-1",
            request_id="request-1",
            loop_family="controller_kernel",
            request_metadata={},
            start_context_summary={},
            started_at_epoch_seconds=100,
            events=[_minimal_event()],
            terminal={"terminal_class": "completed"},
            completeness_status="complete",
            missing_components=[],
            normalization_warnings=[],
            trace_version=TRACE_VERSION,
        )
    assert "run_id" in str(exc.value)


def test_schema_missing_required_event_field_fails() -> None:
    event = _minimal_event()
    event.pop("actor")
    with pytest.raises(ValidationError) as exc:
        CanonicalTraceEvent.model_validate(event)
    assert "actor" in str(exc.value)


def test_schema_event_kind_validation_works() -> None:
    event = _minimal_event()
    event["event_kind"] = "not_a_real_kind"
    with pytest.raises(ValidationError) as exc:
        CanonicalTraceEvent.model_validate(event)
    assert "event_kind" in str(exc.value)


def test_schema_trace_version_field_is_present_and_stable() -> None:
    assert TRACE_VERSION == "trace.v1"
    trace = CanonicalTraceRecord(
        trace_id="trace-1",
        run_id="run-1",
        session_id=None,
        request_id=None,
        loop_family="transcript_edit",
        request_metadata={},
        start_context_summary={},
        started_at_epoch_seconds=1,
        events=[_minimal_event()],
        terminal=TerminalSnapshot(terminal_class="failed"),
        completeness_status="partial",
        missing_components=["progress_log"],
        normalization_warnings=["missing_progress_log"],
        trace_version=TRACE_VERSION,
    )
    assert trace.trace_version == "trace.v1"
    assert isinstance(trace.events[0].source_origin, SourceOrigin)
