from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
from typing import Any

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.endpoints import agent_viewer


def _parse_sse_chunk(chunk: str) -> dict[str, Any]:
    assert "data: " in chunk
    raw = chunk.split("data: ", maxsplit=1)[1].strip()
    return json.loads(raw)


def test_agent_loop_viewer_stream_emits_both_agent_and_viewer_events_same_tick() -> None:
    run_id = "run_multiplex_test"
    stream_key = f"agent_loop:{run_id}"

    async def _case() -> None:
        q = await agent_viewer.agent_loop_event_bus.subscribe(run_id)  # type: ignore[attr-defined]
        stream = agent_viewer._agent_loop_sse_stream(run_id, q)  # type: ignore[attr-defined]
        try:
            first_chunk_task = asyncio.create_task(stream.__anext__())
            await asyncio.sleep(0)
            agent_viewer.agent_loop_event_bus.publish_sync(  # type: ignore[attr-defined]
                run_id,
                {"event_type": "run_started", "run": {"run_id": run_id, "status": "running"}},
            )
            agent_viewer.viewer_event_bus.publish_sync(  # type: ignore[attr-defined]
                stream_key,
                {
                    "protocol": "agent_viewer_event_v1",
                    "run_id": run_id,
                    "loop_kind": "agent_loop",
                    "seq": 999,
                    "iteration": None,
                    "timestamp_epoch_seconds": 123456,
                    "event_type": "human_feedback",
                    "status": {"stage": "human_feedback", "line1": "Human feedback submitted", "line2": "Range 75"},
                    "artifact_refs": {},
                    "payload": {"prompt_id": "p1", "choice": "Range 75"},
                },
            )

            chunk1 = await asyncio.wait_for(first_chunk_task, timeout=1.0)
            chunk2 = await asyncio.wait_for(stream.__anext__(), timeout=1.0)
            payloads = [_parse_sse_chunk(chunk1), _parse_sse_chunk(chunk2)]
            event_types = {p.get("event_type") for p in payloads}
            assert "human_feedback" in event_types
            assert "status" in event_types
        finally:
            await stream.aclose()

    asyncio.run(_case())


def test_feedback_endpoint_validation_rules(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []

    def _append_entry(**kwargs):
        entry = {
            "submitted_at_epoch_seconds": 1,
            "prompt_id": kwargs.get("prompt_id"),
            "choice": kwargs.get("choice"),
            "note": kwargs.get("note"),
            "metadata": kwargs.get("metadata") or {},
        }
        captured.append(entry)
        return entry

    monkeypatch.setattr(agent_viewer.feedback_store, "append_entry", _append_entry)
    monkeypatch.setattr(agent_viewer.feedback_store, "list_entries", lambda **_: list(captured))

    # choice without prompt_id is invalid
    try:
        asyncio.run(
            agent_viewer.post_agent_viewer_feedback(
                loop_kind="transcript_edit",
                run_id="tx_agent_1",
                request=agent_viewer.AgentViewerFeedbackRequest(choice="Range 75"),
            )
        )
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "prompt_id" in str(exc.detail)

    # prompt_id without choice/note is invalid
    try:
        asyncio.run(
            agent_viewer.post_agent_viewer_feedback(
                loop_kind="transcript_edit",
                run_id="tx_agent_1",
                request=agent_viewer.AgentViewerFeedbackRequest(prompt_id="p-1"),
            )
        )
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "choice_or_note" in str(exc.detail)

    # actionable prompt response is accepted
    out = asyncio.run(
        agent_viewer.post_agent_viewer_feedback(
            loop_kind="transcript_edit",
            run_id="tx_agent_1",
            request=agent_viewer.AgentViewerFeedbackRequest(prompt_id="p-1", choice="Range 75"),
        )
    )
    assert out["ok"] is True
    assert out["entry"]["prompt_id"] == "p-1"
    assert out["entry"]["choice"] == "Range 75"
