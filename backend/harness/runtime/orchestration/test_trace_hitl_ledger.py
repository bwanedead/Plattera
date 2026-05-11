"""Tests for HITL exchange ledger trace events.

Pins event_kind, payload shape, and actor for the three ledger-related events:
  - hitl_request_outbound (extended with full request payload)
  - hitl_response_inbound (new)
  - hitl_response_consumed (new)
"""

from __future__ import annotations

from harness.runtime.orchestration.trace_collector import KernelTraceCollector


def _events_of_kind(tracer: KernelTraceCollector, kind: str) -> list[dict]:
    return [e for e in tracer.build_raw_events() if e.get("event_kind") == kind]


# ---------------------------------------------------------------------------
# hitl_request_outbound — extended payload
# ---------------------------------------------------------------------------

def test_outbound_trace_includes_full_request_payload() -> None:
    tracer = KernelTraceCollector(session_id="s", request_id="r", run_id="run1")
    request = {
        "prompt_id": "p1",
        "message": "Confirm",
        "choices": ["yes", "no"],
        "context": {"foo": "bar"},
        "evidence_refs": ["artifact://x"],
    }
    tracer.emit_hitl_request_outbound(
        iteration=5, prompt_id="p1", blocking=True, request_payload=request,
    )
    events = _events_of_kind(tracer, "hitl_request_outbound")
    assert len(events) == 1
    payload = events[0]["payload"]
    assert payload["prompt_id"] == "p1"
    assert payload["blocking"] is True
    # Full normalized request payload is included verbatim for audit.
    assert payload["request"] == request


def test_outbound_trace_omits_request_when_payload_absent() -> None:
    """Backward-compatible: when no request payload is supplied, key is omitted."""
    tracer = KernelTraceCollector(session_id="s", request_id="r", run_id="run1")
    tracer.emit_hitl_request_outbound(iteration=2, prompt_id="p1", blocking=False)
    events = _events_of_kind(tracer, "hitl_request_outbound")
    assert events[0]["payload"].get("request") is None or "request" not in events[0]["payload"]


# ---------------------------------------------------------------------------
# hitl_response_inbound — new event
# ---------------------------------------------------------------------------

def test_inbound_trace_emitted_with_full_response_payload() -> None:
    tracer = KernelTraceCollector(session_id="s", request_id="r", run_id="run1")
    response = {"choice": "yes", "note": "exact text", "submitted_at_epoch_seconds": 1000.0}
    tracer.emit_hitl_response_inbound(iteration=6, prompt_id="p1", response_payload=response)
    events = _events_of_kind(tracer, "hitl_response_inbound")
    assert len(events) == 1
    e = events[0]
    assert e["payload"]["prompt_id"] == "p1"
    assert e["payload"]["response"] == response
    assert e["actor"] == "human"
    assert e["status"] == "completed"


# ---------------------------------------------------------------------------
# hitl_response_consumed — new event
# ---------------------------------------------------------------------------

def test_consumed_trace_emitted_with_matched_and_unknown_ids() -> None:
    tracer = KernelTraceCollector(session_id="s", request_id="r", run_id="run1")
    tracer.emit_hitl_response_consumed(
        iteration=10,
        consumed_prompt_ids=["p1", "p2"],
        unknown_prompt_ids=["ghost"],
    )
    events = _events_of_kind(tracer, "hitl_response_consumed")
    assert len(events) == 1
    payload = events[0]["payload"]
    assert payload["consumed_prompt_ids"] == ["p1", "p2"]
    assert payload["unknown_prompt_ids"] == ["ghost"]
    assert events[0]["actor"] == "kernel"


def test_consumed_trace_omits_unknown_when_empty() -> None:
    tracer = KernelTraceCollector(session_id="s", request_id="r", run_id="run1")
    tracer.emit_hitl_response_consumed(iteration=10, consumed_prompt_ids=["p1"])
    events = _events_of_kind(tracer, "hitl_response_consumed")
    assert "unknown_prompt_ids" not in events[0]["payload"]


def test_inbound_trace_carries_normalized_response_with_truncation_markers() -> None:
    """Trace must record the bounded payload (post-normalization), with _bounds visible.

    The orchestrator hands this trace the same dict the on_inbound callback
    receives from ``hitl_poll_feedback_store``, which is already normalized.
    Pin the shape so trace stays faithful to what the harness admitted.
    """
    from harness.runtime.hitl.feedback_shape import normalize_hitl_feedback

    tracer = KernelTraceCollector(session_id="s", request_id="r", run_id="run1")
    raw_response = {"prompt_id": "p1", "choice": "yes", "note": "n" * 30_000}
    normalized = normalize_hitl_feedback(raw_response)

    tracer.emit_hitl_response_inbound(iteration=6, prompt_id="p1", response_payload=normalized)
    events = _events_of_kind(tracer, "hitl_response_inbound")
    payload = events[0]["payload"]["response"]
    assert len(payload["note"]) == 16_384
    assert payload["_bounds"]["note_truncated"] is True
