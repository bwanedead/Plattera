from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import tempfile
from typing import Any

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.endpoints import transcript_edit_agent
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

