from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.endpoints import agent_loop
from agents.controller.bootstrap import DeedTextArtifact
from services.agent_loop.run_registry_service import AgentLoopRunRegistryService


def _reset_registry(tmp_state_dir: Path) -> None:
    agent_loop._run_registry = AgentLoopRunRegistryService(state_dir=tmp_state_dir)  # type: ignore[assignment]


def test_run_endpoint_background_false_returns_completed_snapshot(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))

        def _fake_execute(run_id: str, request: Any) -> None:
            del request
            agent_loop._run_registry.update_run(  # type: ignore[attr-defined]
                run_id=run_id,
                patch={
                    "status": "completed",
                    "session_id": "s1",
                    "run_artifact_ref": "ref://run",
                    "transcript_artifact_ref": "ref://transcript",
                    "terminal": {"terminal_outcome": "SUCCESS", "stop_reason": "completed", "success": True},
                    "dashboard": {"ok": True},
                },
            )

        monkeypatch.setattr(agent_loop, "_execute_run", _fake_execute)

        payload = asyncio.run(
            agent_loop.start_agent_loop_run(
                agent_loop.AgentLoopRunRequest(
                    text="deed text",
                    background=False,
                    max_iterations=3,
                )
            )
        )
        assert payload["status"] == "completed"
        assert payload["session_id"] == "s1"


def test_run_endpoint_background_true_returns_running_and_poll_works(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))

        def _fake_execute(run_id: str, request: Any) -> None:
            del request
            agent_loop._run_registry.update_run(  # type: ignore[attr-defined]
                run_id=run_id,
                patch={"status": "completed"},
            )

        class _ImmediateThread:
            def __init__(self, target, args, daemon) -> None:
                self._target = target
                self._args = args
                self._daemon = daemon

            def start(self) -> None:
                self._target(*self._args)

        monkeypatch.setattr(agent_loop, "_execute_run", _fake_execute)
        monkeypatch.setattr(agent_loop, "Thread", _ImmediateThread)

        start = asyncio.run(
            agent_loop.start_agent_loop_run(
                agent_loop.AgentLoopRunRequest(
                    text="deed text",
                    background=True,
                )
            )
        )
        run_id = start["run_id"]
        assert start["status"] == "running"

        polled = asyncio.run(agent_loop.get_agent_loop_run(run_id))
        assert polled["run_id"] == run_id


def test_get_run_404_and_list_runs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))

        try:
            asyncio.run(agent_loop.get_agent_loop_run("does-not-exist"))
            assert False, "expected HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 404

        listed = asyncio.run(agent_loop.list_agent_loop_runs(limit=20))
        assert listed["count"] == 0


def test_artifact_open_endpoint_happy_and_not_found() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))
        path = Path(tmp) / "artifact.json"
        path.write_text(json.dumps({"alpha": 1, "beta": 2}), encoding="utf-8")

        ok = asyncio.run(agent_loop.open_agent_loop_artifact(artifact_ref=str(path)))
        assert "json_keys=" in ok["summary"]

        missing = asyncio.run(
            agent_loop.open_agent_loop_artifact(artifact_ref=str(path) + ".missing")
        )
        assert "artifact_open_not_found" in missing["reason_codes"]


def test_events_endpoint_receives_run_started_event() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))
        run_id = "run_events_test"
        async def _case() -> None:
            q = await agent_loop.event_bus.subscribe(run_id)  # type: ignore[attr-defined]
            stream = agent_loop._sse_stream(run_id, q)
            agent_loop.event_bus.publish_sync(  # type: ignore[attr-defined]
                run_id,
                {"event_type": "run_started", "run": {"run_id": run_id}},
            )
            chunk = await asyncio.wait_for(stream.__anext__(), timeout=1.0)
            assert "data: " in chunk
            payload = json.loads(chunk.split("data: ", maxsplit=1)[1].strip())
            assert payload["event_type"] == "run_started"
            await stream.aclose()

        asyncio.run(_case())


def test_build_start_request_dossier_bootstrap_includes_deed_ref_and_excerpt(monkeypatch) -> None:
    def _fake_hydrate(*, request_id: str, dossier_id: str):
        del request_id, dossier_id
        return DeedTextArtifact(
            artifact_path="artifacts/deed/d1.json",
            excerpt="Deed excerpt for bootstrap",
        )

    monkeypatch.setattr(
        agent_loop,
        "hydrate_and_persist_finalized_dossier_text",
        _fake_hydrate,
    )
    req = agent_loop.AgentLoopRunRequest(dossier_id="D1", background=False)
    start = agent_loop._build_start_request("run_x", req)  # type: ignore[attr-defined]
    assert isinstance(start.initial_graph_json, dict)
    metadata = start.initial_graph_json.get("metadata")
    assert isinstance(metadata, dict)
    assert metadata.get("deed_text_artifact_ref") == "artifacts/deed/d1.json"
    assert metadata.get("deed_text_excerpt") == "Deed excerpt for bootstrap"
