from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.harness.review.tool import extract_prompt_events_from_trace
from backend.harness.tracing.builder import build_canonical_trace
from backend.harness.tracing.schema import RawTraceEvent, TerminalSnapshot


def test_extract_prompt_events_from_trace_returns_prompt_event_artifacts() -> None:
    trace = build_canonical_trace(
        trace_id="trace-1",
        run_id="run-1",
        session_id="session-1",
        request_id="request-1",
        loop_family="transcript_edit",
        request_metadata={},
        start_context_summary={},
        started_at_epoch_seconds=0,
        events=[
            RawTraceEvent(
                event_kind="model_proposal",
                phase="prompt_event",
                iteration_index=1,
                actor="kernel",
                status="completed",
                payload={
                    "prompt_event": {
                        "metadata": {
                            "prompt_event_id": "prompt_event:run-1:i01:tx_planner",
                            "surface": "tx_planner",
                            "domain": "transcript_edit",
                            "model": "gpt-5.2",
                        },
                        "outcome_kind": "plan_valid",
                        "outcome_ref": "plan-1",
                    }
                },
            )
        ],
        terminal=TerminalSnapshot(terminal_class="completed", success=True),
    )

    prompt_events = extract_prompt_events_from_trace(trace=trace)

    assert len(prompt_events) == 1
    event = prompt_events[0]
    assert event["prompt_event_id"] == "prompt_event:run-1:i01:tx_planner"
    assert event["surface"] == "tx_planner"
    assert event["outcome_kind"] == "plan_valid"
    assert event["prompt_event"]["metadata"]["domain"] == "transcript_edit"
