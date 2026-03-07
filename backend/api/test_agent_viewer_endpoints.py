from __future__ import annotations

import asyncio
import base64
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
    monkeypatch.setattr(
        "api.endpoints.transcript_edit_agent.request_run_resume_if_waiting",
        lambda **kwargs: {"resumed": True, "status": "running", "run_id": kwargs.get("run_id")},
    )
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
    assert isinstance(out.get("auto_resume"), dict)
    assert out["auto_resume"]["resumed"] is True


def test_artifact_image_endpoint_serves_image_under_dossiers_root(monkeypatch, tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    views_root = tmp_path / "views" / "transcriptions"
    dossiers_root = tmp_path
    image_root = dossiers_root / "images" / "original"
    image_root.mkdir(parents=True, exist_ok=True)
    png_path = image_root / "tiny.png"
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7gY5kAAAAASUVORK5CYII="
    )
    png_path.write_bytes(png_bytes)

    monkeypatch.setattr(agent_viewer, "dossiers_artifacts_root", lambda: artifacts_root)
    monkeypatch.setattr(agent_viewer, "dossiers_views_root", lambda: views_root)
    monkeypatch.setattr(agent_viewer, "dossiers_root", lambda: dossiers_root)

    response = asyncio.run(agent_viewer.agent_viewer_artifact_image(artifact_ref=str(png_path)))
    assert response.status_code == 200
    assert str(response.path).endswith("tiny.png")


def test_normalize_agent_loop_upstream_correction_request_event() -> None:
    normalized = agent_viewer._normalize_agent_loop_event(  # type: ignore[attr-defined]
        run_id="run_1",
        payload={
            "event_type": "upstream_correction_request",
            "request": {
                "request_id": "r1",
                "reason_code": "georef_range_mismatch",
                "message": "Range token appears inconsistent with geometry.",
            },
        },
    )
    assert isinstance(normalized, dict)
    assert normalized["event_type"] == "upstream_correction_request"
    assert normalized["status"]["stage"] == "upstream_correction_request"
    assert normalized["payload"]["request"]["request_id"] == "r1"


def test_timing_summary_endpoint_aggregates_backend_and_frontend_markers(monkeypatch, tmp_path: Path) -> None:
    run_id = "tx_post_t0_demo123"
    log_path = tmp_path / "app_test.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-03-04 10:00:00,000 INFO x: AGENT_VIEWER_TIMING ► tx_run_created run_id=tx_post_t0_demo123 stream_key=transcript_edit:tx_post_t0_demo123",
                "2026-03-04 10:00:00,100 INFO x: AGENT_VIEWER_TIMING ► tx_first_progress_emitted run_id=tx_post_t0_demo123 phase=starting elapsed_ms=100",
                "2026-03-04 10:00:00,150 INFO x: AGENT_VIEWER_TIMING ► tx_first_viewer_publish run_id=tx_post_t0_demo123 event_type=status phase=starting elapsed_ms=150",
                "2026-03-04 10:00:00,300 INFO x: AGENT_VIEWER_TIMING ► sse_first_delivery stream_key=transcript_edit:tx_post_t0_demo123 event_type=status phase=starting seq=1",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(agent_viewer, "get_active_log_file", lambda: str(log_path))
    monkeypatch.setattr(
        agent_viewer,
        "get_frontend_logs_snapshot",
        lambda limit=5000: [
            {
                "ts": 1762279200.500,
                "level": "INFO",
                "source": "agent_viewer_timing",
                "message": f"AGENT_VIEWER_TIMING ► first_event_received loop=transcript_edit run={run_id} elapsed_ms=500",
                "meta": {"run_id": run_id},
            },
            {
                "ts": 1762279200.900,
                "level": "INFO",
                "source": "agent_viewer_timing",
                "message": f"AGENT_VIEWER_TIMING ► prompt_rendered loop=transcript_edit run={run_id} prompt_id=p1",
                "meta": {"run_id": run_id, "prompt_id": "p1"},
            },
        ],
    )

    result = asyncio.run(
        agent_viewer.get_agent_viewer_timing_summary(
            run_id=run_id,
            max_backend_lines=5000,
            max_frontend_entries=2000,
        )
    )
    assert result["run_id"] == run_id
    assert result["backend_count"] >= 4
    assert result["frontend_count"] >= 2
    assert "tx_run_created_to_first_progress" in result["deltas_ms"]
