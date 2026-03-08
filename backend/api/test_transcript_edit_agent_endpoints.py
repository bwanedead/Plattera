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


def test_execute_run_transitions_to_waiting_feedback_when_pending_human_feedback(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))
        captured_events: list[dict[str, Any]] = []

        def _fake_run_loop(**kwargs: Any) -> TranscriptEditAgentRunResult:
            progress_cb = kwargs.get("progress_cb")
            if callable(progress_cb):
                progress_cb(
                    {
                        "iteration": 1,
                        "phase": "human_feedback_needed",
                        "event_type": "human_feedback_needed",
                        "prompt_id": "hitl_range_1_wait",
                        "message": "Need human confirmation.",
                        "latest_refs": {},
                    }
                )
            return TranscriptEditAgentRunResult(
                run_artifact_ref="in-memory://run",
                session_id="s3",
                iterations=1,
                status="needs_review",
                reason_code="tx_agent_closure_requirements_unresolved",
                latest_refs={},
                review_required=True,
                runtime_hitl_state={
                    "pending_feedback_prompt_id": "hitl_range_1_wait",
                    "pending_feedback_decision_key": "range",
                    "used_human_feedback": False,
                    "feedback_received_count": 0,
                    "feedback_consumed_count": 0,
                    "feedback_stale_count": 0,
                    "feedback_superseded_count": 0,
                    "hitl_lifecycle_log": [],
                },
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
            lambda **kwargs: {"handoff_summary": "waiting"},
        )
        monkeypatch.setattr(
            transcript_edit_agent,
            "persist_handoff_packet",
            lambda **kwargs: "in-memory://handoff_waiting.json",
        )
        monkeypatch.setattr(
            transcript_edit_agent,
            "terminal_summary",
            lambda *args, **kwargs: {
                "human_feedback_pending": True,
                "pending_feedback_prompt_ids": ["hitl_range_1_wait"],
                "terminal_classification": "blocked_human_feedback_needed",
            },
        )

        request = transcript_edit_agent.TranscriptEditAgentApiRequest(
            source_text="Beginning at ...",
            dossier_id="D1",
            background=False,
        )
        transcript_edit_agent._registry.create_run(run_id="r_wait", request={"dossier_id": "D1"})  # type: ignore[attr-defined]
        transcript_edit_agent._execute_run("r_wait", request)
        run = asyncio.run(transcript_edit_agent.get_run("r_wait"))
        assert run["status"] == "waiting_feedback"
        snapshot = run.get("snapshot") if isinstance(run.get("snapshot"), dict) else {}
        assert bool(snapshot.get("waiting_feedback")) is True
        assert bool(snapshot.get("resumable")) is True
        runtime_hitl_state = snapshot.get("runtime_hitl_state") if isinstance(snapshot.get("runtime_hitl_state"), dict) else {}
        assert runtime_hitl_state.get("pending_feedback_prompt_id") == "hitl_range_1_wait"
        assert any(
            isinstance(evt, dict)
            and str(evt.get("event_type") or "") == "status"
            and isinstance(evt.get("payload"), dict)
            and str((evt.get("payload") or {}).get("phase") or "") == "waiting_feedback"
            for evt in captured_events
        )


def test_execute_run_throttles_noncritical_progress_persistence(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))

        def _fake_run_loop(**kwargs: Any) -> TranscriptEditAgentRunResult:
            progress_cb = kwargs.get("progress_cb")
            if callable(progress_cb):
                for idx in range(20):
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
                        "phase": "human_feedback_needed",
                        "event_type": "human_feedback_needed",
                        "message": "Need feedback.",
                        "latest_refs": {},
                    }
                )
            return TranscriptEditAgentRunResult(
                run_artifact_ref="in-memory://run",
                session_id="s4",
                iterations=1,
                status="needs_review",
                reason_code="tx_agent_no_progress:pending_human_feedback_no_new_signal",
                latest_refs={},
                review_required=True,
                runtime_hitl_state={"pending_feedback_prompt_id": "hitl_range_1_wait"},
            )

        monkeypatch.setattr(transcript_edit_agent, "run_transcript_edit_controller_loop", _fake_run_loop)
        monkeypatch.setattr(
            transcript_edit_agent,
            "build_handoff_packet",
            lambda **kwargs: {"handoff_summary": "waiting"},
        )
        monkeypatch.setattr(
            transcript_edit_agent,
            "persist_handoff_packet",
            lambda **kwargs: "in-memory://handoff_waiting.json",
        )
        monkeypatch.setattr(
            transcript_edit_agent,
            "terminal_summary",
            lambda *args, **kwargs: {
                "human_feedback_pending": True,
                "pending_feedback_prompt_ids": ["hitl_range_1_wait"],
                "terminal_classification": "blocked_human_feedback_needed",
            },
        )

        persisted_snapshots: list[dict[str, Any]] = []
        original_update_run = transcript_edit_agent._registry.update_run  # type: ignore[attr-defined]

        def _tracking_update_run(*, run_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
            snapshot = patch.get("snapshot") if isinstance(patch.get("snapshot"), dict) else None
            if snapshot is not None and str(patch.get("status") or "") == "running":
                persisted_snapshots.append(dict(snapshot))
            return original_update_run(run_id=run_id, patch=patch)

        monkeypatch.setattr(transcript_edit_agent._registry, "update_run", _tracking_update_run)  # type: ignore[attr-defined]

        request = transcript_edit_agent.TranscriptEditAgentApiRequest(
            source_text="Beginning at ...",
            dossier_id="D1",
            background=False,
        )
        transcript_edit_agent._registry.create_run(run_id="r_throttle", request={"dossier_id": "D1"})  # type: ignore[attr-defined]
        transcript_edit_agent._execute_run("r_throttle", request)

        # 21 progress events were emitted; throttling should persist materially fewer running snapshots.
        assert len(persisted_snapshots) < 21
        assert any(
            str((snap.get("live_status") or {}).get("phase") or "") == "human_feedback_needed"
            for snap in persisted_snapshots
        )


def test_resume_run_carries_pending_prompt_identity_from_waiting_snapshot(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))
        transcript_edit_agent._registry.create_run(  # type: ignore[attr-defined]
            run_id="r_resume_pending",
            request={
                "dossier_id": "D1",
                "resume_request": {
                    "dossier_id": "D1",
                    "source_text": "Beginning at ...",
                    "mode": "audit_then_repair_then_promote",
                    "auto_promote": False,
                    "hitl_enabled": True,
                },
            },
        )
        transcript_edit_agent._registry.update_run(  # type: ignore[attr-defined]
            run_id="r_resume_pending",
            patch={
                "status": "waiting_feedback",
                "snapshot": {
                    "run_id": "r_resume_pending",
                    "status": "waiting_feedback",
                    "waiting_feedback": True,
                    "resumable": True,
                    "latest_refs": {},
                    "runtime_hitl_state": {
                        "blocker_registry": {
                            "version": 1,
                            "active_blocker_id": "blocker:range",
                            "counts": {"answered_unintegrated": 1, "total": 1},
                            "rows": [
                                {
                                    "blocker_id": "blocker:range",
                                    "decision_key": "range",
                                    "state": "answered_unintegrated",
                                    "linked_prompt_id": "hitl_range_1_wait",
                                }
                            ],
                            "history": [{"iteration": 1, "action_attempted": "request_hitl"}],
                        }
                    },
                    "terminal_summary": {
                        "pending_feedback_prompt_ids": ["hitl_range_1_wait"],
                    },
                },
            },
        )

        captured_request: dict[str, Any] = {}

        def _fake_execute(run_id: str, request: Any) -> None:
            captured_request["run_id"] = run_id
            captured_request["request"] = request
            transcript_edit_agent._registry.update_run(  # type: ignore[attr-defined]
                run_id=run_id,
                patch={"status": "completed", "snapshot": {"status": "completed"}},
            )

        class _ImmediateThread:
            def __init__(self, target, args, daemon) -> None:
                self._target = target
                self._args = args
                self._daemon = daemon

            def start(self) -> None:
                self._target(*self._args)

        monkeypatch.setattr(transcript_edit_agent, "_execute_run", _fake_execute)
        monkeypatch.setattr(transcript_edit_agent, "Thread", _ImmediateThread)

        out = asyncio.run(
            transcript_edit_agent.resume_run(
                run_id="r_resume_pending",
                request=transcript_edit_agent.TranscriptEditAgentResumeRequest(background=True, trigger="feedback_post"),
            )
        )
        assert out["resumed"] is True
        request = captured_request.get("request")
        assert request is not None
        assert str(request.resume_pending_feedback_prompt_id) == "hitl_range_1_wait"
        assert str(request.resume_pending_feedback_decision_key) == "range"
        assert isinstance(request.resume_blocker_registry, dict)
        assert str(request.resume_blocker_registry.get("active_blocker_id") or "") == "blocker:range"


def test_resume_run_endpoint_resumes_waiting_feedback_run(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))
        transcript_edit_agent._registry.create_run(  # type: ignore[attr-defined]
            run_id="r_resume",
            request={
                "dossier_id": "D1",
                "resume_request": {
                    "dossier_id": "D1",
                    "source_text": "Beginning at ...",
                    "mode": "audit_then_repair_then_promote",
                    "auto_promote": False,
                    "hitl_enabled": True,
                },
            },
        )
        transcript_edit_agent._registry.update_run(  # type: ignore[attr-defined]
            run_id="r_resume",
            patch={
                "status": "waiting_feedback",
                "snapshot": {
                    "run_id": "r_resume",
                    "status": "waiting_feedback",
                    "waiting_feedback": True,
                    "resumable": True,
                    "latest_refs": {},
                },
            },
        )

        def _fake_execute(run_id: str, request: Any) -> None:
            del request
            transcript_edit_agent._registry.update_run(  # type: ignore[attr-defined]
                run_id=run_id,
                patch={"status": "completed", "snapshot": {"status": "completed"}},
            )

        class _ImmediateThread:
            def __init__(self, target, args, daemon) -> None:
                self._target = target
                self._args = args
                self._daemon = daemon

            def start(self) -> None:
                self._target(*self._args)

        monkeypatch.setattr(transcript_edit_agent, "_execute_run", _fake_execute)
        monkeypatch.setattr(transcript_edit_agent, "Thread", _ImmediateThread)

        out = asyncio.run(
            transcript_edit_agent.resume_run(
                run_id="r_resume",
                request=transcript_edit_agent.TranscriptEditAgentResumeRequest(background=True, trigger="manual_resume"),
            )
        )
        assert out["resumed"] is True
        run = asyncio.run(transcript_edit_agent.get_run("r_resume"))
        assert run["status"] == "completed"


def test_request_run_resume_if_waiting_returns_registry_update_failed_when_mark_running_fails(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))
        transcript_edit_agent._registry.create_run(  # type: ignore[attr-defined]
            run_id="r_resume_fail",
            request={
                "dossier_id": "D1",
                "resume_request": {
                    "dossier_id": "D1",
                    "source_text": "Beginning at ...",
                },
            },
        )
        transcript_edit_agent._registry.update_run(  # type: ignore[attr-defined]
            run_id="r_resume_fail",
            patch={
                "status": "waiting_feedback",
                "snapshot": {"run_id": "r_resume_fail", "status": "waiting_feedback"},
            },
        )

        def _fail_update_run(*, run_id: str, patch: dict[str, Any]):
            del run_id, patch
            raise PermissionError(13, "Access is denied")

        monkeypatch.setattr(transcript_edit_agent._registry, "update_run", _fail_update_run)  # type: ignore[attr-defined]
        out = transcript_edit_agent.request_run_resume_if_waiting(
            run_id="r_resume_fail",
            trigger="feedback_post",
            background=True,
        )
        assert out["resumed"] is False
        assert out["reason"] == "resume_registry_update_failed"
