from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import tempfile
from typing import Any

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.endpoints import transcript_edit_agent
from agents.transcript_edit.contracts import TranscriptEditAgentRunResult
from transcript_edit.run_registry import TranscriptionEditRunRegistry


def _reset_registry(tmp_state_dir: Path) -> None:
    transcript_edit_agent._registry = TranscriptionEditRunRegistry(state_dir=tmp_state_dir)  # type: ignore[assignment]


def test_run_endpoint_background_false_returns_snapshot(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))

        def _fake_execute(run_id: str, request: Any) -> None:
            del request
            transcript_edit_agent._registry.update_run(  # type: ignore[attr-defined]
                run_id=run_id,
                patch={"status": "completed", "snapshot": {"status": "completed", "reason_code": "ok"}},
            )

        monkeypatch.setattr(transcript_edit_agent, "_execute_run", _fake_execute)
        payload = asyncio.run(
            transcript_edit_agent.start_run(
                transcript_edit_agent.TranscriptEditAgentApiRequest(
                    source_text="Beginning at ...",
                    dossier_id="D1",
                    background=False,
                )
            )
        )
        assert payload["status"] == "completed"
        assert payload["snapshot"]["reason_code"] == "ok"


def test_run_endpoint_background_true_returns_running(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))

        def _fake_execute(run_id: str, request: Any) -> None:
            del request
            transcript_edit_agent._registry.update_run(run_id=run_id, patch={"status": "completed"})  # type: ignore[attr-defined]

        class _ImmediateThread:
            def __init__(self, target, args, daemon) -> None:
                self._target = target
                self._args = args
                self._daemon = daemon

            def start(self) -> None:
                self._target(*self._args)

        monkeypatch.setattr(transcript_edit_agent, "_execute_run", _fake_execute)
        monkeypatch.setattr(transcript_edit_agent, "Thread", _ImmediateThread)

        start = asyncio.run(
            transcript_edit_agent.start_run(
                transcript_edit_agent.TranscriptEditAgentApiRequest(
                    source_text="Beginning at ...",
                    dossier_id="D1",
                    background=True,
                )
            )
        )
        run_id = start["run_id"]
        assert start["status"] == "running"
        polled = asyncio.run(transcript_edit_agent.get_run(run_id))
        assert polled["run_id"] == run_id


def test_run_endpoint_requires_source() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))
        try:
            asyncio.run(
                transcript_edit_agent.start_run(
                    transcript_edit_agent.TranscriptEditAgentApiRequest(
                        dossier_id="D1",
                        background=False,
                    )
                )
            )
            assert False, "expected HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 400


def test_execute_run_emits_terminal_handoff_fields(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))
        captured_events: list[dict[str, Any]] = []

        def _fake_run_loop(**kwargs: Any) -> TranscriptEditAgentRunResult:
            progress_cb = kwargs.get("progress_cb")
            if callable(progress_cb):
                progress_cb(
                    {
                        "iteration": 1,
                        "phase": "audit_result",
                        "message": "ok",
                        "detail": {"error_count": 0},
                        "latest_refs": {},
                    }
                )
            return TranscriptEditAgentRunResult(
                run_artifact_ref="in-memory://run",
                session_id="s1",
                iterations=1,
                status="completed",
                reason_code="tx_agent_clean_no_promote",
                latest_refs={},
                review_required=False,
            )

        class _Bus:
            def publish_sync(self, channel: str, event: dict[str, Any]) -> None:
                del channel
                captured_events.append(event)

        monkeypatch.setattr(transcript_edit_agent, "run_transcript_edit_controller_loop", _fake_run_loop)
        monkeypatch.setattr(transcript_edit_agent, "viewer_event_bus", _Bus())
        monkeypatch.setattr(
            transcript_edit_agent,
            "build_handoff_packet",
            lambda **kwargs: {"handoff_summary": "Mapping-ready."},
        )
        monkeypatch.setattr(
            transcript_edit_agent,
            "persist_handoff_packet",
            lambda **kwargs: "in-memory://handoff.json",
        )

        request = transcript_edit_agent.TranscriptEditAgentApiRequest(
            source_text="Beginning at ...",
            dossier_id="D1",
            background=False,
        )
        transcript_edit_agent._registry.create_run(run_id="r1", request={"dossier_id": "D1"})  # type: ignore[attr-defined]
        transcript_edit_agent._execute_run("r1", request)
        done = next(evt for evt in captured_events if evt.get("event_type") == "done")
        payload = done.get("payload") or {}
        assert payload.get("handoff_packet_ref") == "in-memory://handoff.json"
        assert payload.get("handoff_summary") == "Mapping-ready."
        run = asyncio.run(transcript_edit_agent.get_run("r1"))
        assert run["snapshot"]["terminal_summary"]["handoff_packet_ref"] == "in-memory://handoff.json"


def test_execute_run_preserves_critical_hitl_events_when_progress_log_is_truncated(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))

        def _fake_run_loop(**kwargs: Any) -> TranscriptEditAgentRunResult:
            progress_cb = kwargs.get("progress_cb")
            if callable(progress_cb):
                progress_cb(
                    {
                        "iteration": 1,
                        "phase": "human_feedback_received",
                        "event_type": "human_feedback",
                        "prompt_id": "hitl_range_1_resolver",
                        "message": "Human feedback received.",
                        "latest_refs": {},
                    }
                )
                for idx in range(60):
                    progress_cb(
                        {
                            "iteration": 1,
                            "phase": "image_verify",
                            "message": f"tick {idx}",
                            "latest_refs": {},
                        }
                    )
                progress_cb(
                    {
                        "iteration": 1,
                        "phase": "audit_result",
                        "message": "audit done",
                        "detail": {"error_count": 0, "decision_ledger": {"items": [], "summary": {"blocking_open_count": 0}}},
                        "latest_refs": {},
                    }
                )
            return TranscriptEditAgentRunResult(
                run_artifact_ref="in-memory://run",
                session_id="s2",
                iterations=1,
                status="needs_review",
                reason_code="tx_agent_no_progress",
                latest_refs={},
                review_required=True,
                runtime_hitl_state={
                    "used_human_feedback": True,
                    "feedback_received_count": 1,
                    "feedback_consumed_count": 1,
                    "feedback_stale_count": 0,
                    "feedback_superseded_count": 0,
                    "pending_feedback_prompt_id": None,
                    "superseded_prompt_ids": [],
                    "hitl_lifecycle_log": [{"phase": "human_feedback_consumed", "prompt_id": "hitl_range_1_resolver"}],
                },
            )

        monkeypatch.setattr(transcript_edit_agent, "run_transcript_edit_controller_loop", _fake_run_loop)
        monkeypatch.setattr(
            transcript_edit_agent,
            "build_handoff_packet",
            lambda **kwargs: {"handoff_summary": "test"},
        )
        monkeypatch.setattr(
            transcript_edit_agent,
            "persist_handoff_packet",
            lambda **kwargs: "in-memory://handoff.json",
        )
        request = transcript_edit_agent.TranscriptEditAgentApiRequest(
            source_text="Beginning at ...",
            dossier_id="D1",
            background=False,
        )
        transcript_edit_agent._registry.create_run(run_id="r2", request={"dossier_id": "D1"})  # type: ignore[attr-defined]
        transcript_edit_agent._execute_run("r2", request)
        run = asyncio.run(transcript_edit_agent.get_run("r2"))
        snapshot = run.get("snapshot") if isinstance(run.get("snapshot"), dict) else {}
        progress_log = snapshot.get("progress_log") if isinstance(snapshot.get("progress_log"), list) else []
        critical_events = snapshot.get("critical_events") if isinstance(snapshot.get("critical_events"), list) else []
        terminal = snapshot.get("terminal_summary") if isinstance(snapshot.get("terminal_summary"), dict) else {}
        assert len(progress_log) <= 40
        assert len(critical_events) >= 1
        assert terminal.get("used_human_feedback") is True
