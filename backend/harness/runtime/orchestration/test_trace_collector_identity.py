"""Tests for canonical event identity in KernelTraceCollector (Phase 4).

Invariants protected here:
- run_id is carried in the request_start payload
- source_origin ref embeds run_id when provided
- collector exposes run_id as a readable property
- backward-compat: absence of run_id does not raise
"""

from __future__ import annotations

import pytest

from harness.runtime.orchestration.trace_collector import KernelTraceCollector


def _request_start_payload(tracer: KernelTraceCollector) -> dict:
    tracer.emit_request_start(
        opaque_run_context={},
        max_iterations=5,
        run_artifact_ref="ref://run1",
    )
    events = tracer.build_raw_events()
    assert events, "expected at least one event"
    rs = next((e for e in events if e.get("event_kind") == "request_start"), None)
    assert rs is not None, "request_start event missing"
    return rs.get("payload") or {}


def test_run_id_embedded_in_request_start_payload() -> None:
    tracer = KernelTraceCollector(session_id="s-1", request_id="r-1", run_id="run-abc")
    payload = _request_start_payload(tracer)
    assert payload.get("run_id") == "run-abc"


def test_session_id_and_request_id_in_request_start_payload() -> None:
    tracer = KernelTraceCollector(session_id="s-2", request_id="r-2", run_id="run-xyz")
    payload = _request_start_payload(tracer)
    assert payload.get("session_id") == "s-2"
    assert payload.get("request_id") == "r-2"


def test_run_id_property_readable() -> None:
    tracer = KernelTraceCollector(session_id="s", request_id="r", run_id="myrun")
    assert tracer.run_id == "myrun"


def test_run_id_property_empty_string_when_omitted() -> None:
    tracer = KernelTraceCollector(session_id="s", request_id="r")
    assert tracer.run_id == ""


def test_source_ref_includes_run_id_when_provided() -> None:
    tracer = KernelTraceCollector(session_id="sess-x", request_id="req-x", run_id="run-x")
    tracer.emit_request_start(opaque_run_context={}, max_iterations=1, run_artifact_ref=None)
    events = tracer.build_raw_events()
    rs = next(e for e in events if e.get("event_kind") == "request_start")
    ref = (rs.get("source_origin") or {}).get("ref", "")
    assert "run:run-x" in ref
    assert "session:sess-x" in ref


def test_source_ref_falls_back_to_session_only_without_run_id() -> None:
    tracer = KernelTraceCollector(session_id="sess-y", request_id="req-y")
    tracer.emit_request_start(opaque_run_context={}, max_iterations=1, run_artifact_ref=None)
    events = tracer.build_raw_events()
    rs = next(e for e in events if e.get("event_kind") == "request_start")
    ref = (rs.get("source_origin") or {}).get("ref", "")
    assert "session:sess-y" in ref
    assert "run:" not in ref


def test_backward_compat_no_run_id_does_not_raise() -> None:
    # All existing call sites that omit run_id must still work.
    tracer = KernelTraceCollector(session_id="s", request_id="r")
    tracer.emit_request_start(opaque_run_context={}, max_iterations=3, run_artifact_ref=None)
    tracer.emit_iteration_start(iteration=1, hitl_state="idle")
    events = tracer.build_raw_events()
    assert len(events) == 2


def test_request_start_run_id_is_none_when_omitted() -> None:
    """When run_id is not set, payload['run_id'] should be None (not an empty string)."""
    tracer = KernelTraceCollector(session_id="s", request_id="r")
    payload = _request_start_payload(tracer)
    # run_id key should be None, not a non-empty string
    assert payload.get("run_id") is None
