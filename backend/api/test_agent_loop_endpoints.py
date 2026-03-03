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
from config.paths import dossiers_views_root
from services.agent_loop.run_registry_service import AgentLoopRunRegistryService
import config.paths as legacy_paths


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


def test_direct_text_run_creates_real_dossier_and_finalized_snapshot(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _reset_registry(root / "state")
        original_legacy_dossiers_root = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        class _ImmediateThread:
            def __init__(self, target, args, daemon) -> None:
                self._target = target
                self._args = args
                self._daemon = daemon

            def start(self) -> None:
                self._target(*self._args)

        def _fake_execute(run_id: str, request: Any) -> None:
            del request
            agent_loop._run_registry.update_run(run_id=run_id, patch={"status": "completed"})  # type: ignore[attr-defined]

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        monkeypatch.setattr(agent_loop, "Thread", _ImmediateThread)
        monkeypatch.setattr(agent_loop, "_execute_run", _fake_execute)
        try:
            start = asyncio.run(
                agent_loop.start_agent_loop_run(
                    agent_loop.AgentLoopRunRequest(
                        text="Direct text deed body for finalized snapshot.",
                        background=True,
                    )
                )
            )
            dossier_id = str(start.get("dossier_id") or "")
            assert dossier_id
            final_path = dossiers_views_root() / dossier_id / "final" / "dossier_final.json"
            assert final_path.exists()
            payload = json.loads(final_path.read_text(encoding="utf-8"))
            assert payload["dossier_id"] == dossier_id
            assert payload["stitched_text"].startswith("Direct text deed body")

            hydrated = agent_loop.hydrate_and_persist_finalized_dossier_text(  # type: ignore[attr-defined]
                request_id="req_direct_text_hydrate",
                dossier_id=dossier_id,
            )
            assert hydrated is not None
            assert hydrated.excerpt.startswith("Direct text deed body")
        finally:
            legacy_paths.dossiers_root = original_legacy_dossiers_root  # type: ignore[assignment]


def test_agent_tape_event_formatter_emits_compact_kernel_step_status() -> None:
    event = {
        "event_type": "kernel_step_result",
        "detail": "executed",
        "timestamp_epoch_seconds": 123,
        "payload": {
            "iteration": 4,
            "execution_state": "executed",
            "action_type": "judge",
            "dashboard_failure_classification": {"reason_code": None},
            "latest_refs": {
                "judge_ref": "artifacts/feature_graphs/D1/judge.json",
                "compile_ref": "artifacts/feature_graphs/D1/compile.json",
            },
        },
    }
    out = agent_loop._agent_tape_event_from_transcript_event(  # type: ignore[attr-defined]
        run_id="run_1",
        event=event,
        seq=7,
    )
    assert isinstance(out, dict)
    assert out["event_type"] == "agent_tape_update"
    status = out["status"]
    assert status["iteration"] == 4
    assert status["action_type"] == "judge"
    assert status["outcome"] == "executed"
    assert "Updated refs:" in str(status["line2"])


def test_build_start_request_includes_handoff_bootstrap_metadata(monkeypatch) -> None:
    packet = {
        "terminal": {"mapping_ready": False, "readiness_blocker": "mapping_critical_image_verification_unresolved"},
        "resume_recommendation": "proceed_with_caution",
        "mapping_watchlist": ["range"],
        "handoff_summary": "Not mapping-ready.",
        "transcript_edit_run_id": "tx_run_1",
    }
    monkeypatch.setattr(agent_loop, "load_transcript_handoff_packet", lambda **kwargs: packet)
    req = agent_loop.AgentLoopRunRequest(
        dossier_id="D1",
        transcript_handoff_ref="artifacts/transcript_edit_handoffs/D1/run.json",
        mapping_readiness_mode="best_effort",
    )
    start = agent_loop._build_start_request("run_x", req)  # type: ignore[attr-defined]
    metadata = start.initial_graph_json.get("metadata") if isinstance(start.initial_graph_json, dict) else {}
    assert metadata.get("transcript_mapping_ready") is False
    assert metadata.get("transcript_mapping_watchlist") == ["range"]
    assert metadata.get("mapping_readiness_mode") == "best_effort"


def test_execute_run_emits_upstream_correction_request_event(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))
        captured_events: list[dict[str, Any]] = []

        class _FakeResult:
            session_id = "s1"
            run_artifact_ref = "ref://run"
            transcript_artifact_ref = "ref://tape"
            last_dashboard = {}

            class _Terminal:
                def model_dump(self, mode: str = "json") -> dict[str, Any]:
                    del mode
                    return {"terminal_outcome": "FAILED", "stop_reason": "needs_review", "success": False}

            terminal = _Terminal()

        def _fake_run_controller_loop(**kwargs: Any):
            del kwargs
            previous = agent_loop.set_transcript_event_hook(None)
            try:
                if callable(previous):
                    previous(
                        {
                            "event_type": "kernel_step_result",
                            "timestamp_epoch_seconds": 123,
                            "payload": {
                                "action_type": "georeference",
                                "execution_state": "refused",
                                "refusal": {"reason_code": "georef_range_mismatch"},
                                "latest_refs": {"judge_ref": "artifacts/feature_graphs/D1/judge.json"},
                            },
                        }
                    )
            finally:
                agent_loop.restore_transcript_event_hook(previous)
            return _FakeResult()

        monkeypatch.setattr(agent_loop, "run_controller_loop", _fake_run_controller_loop)
        monkeypatch.setattr(agent_loop, "load_transcript_handoff_packet", lambda **kwargs: {"mapping_watchlist": ["range"]})

        class _Bus:
            def publish_sync(self, run_id: str, event: dict[str, Any]) -> None:
                del run_id
                captured_events.append(event)

            async def publish(self, run_id: str, event: dict[str, Any]) -> None:
                del run_id
                captured_events.append(event)

        monkeypatch.setattr(agent_loop, "event_bus", _Bus())

        req = agent_loop.AgentLoopRunRequest(dossier_id="D1", background=False)
        run_id = "run_test_upstream_req"
        agent_loop._run_registry.create_run(run_id=run_id, request={"dossier_id": "D1"})  # type: ignore[attr-defined]
        agent_loop._execute_run(run_id, req)
        run = asyncio.run(agent_loop.get_agent_loop_run(run_id))
        requests = run.get("upstream_correction_requests") or []
        assert isinstance(requests, list) and len(requests) == 1
        assert requests[0]["source"] == "mapping"
        assert run.get("upstream_correction_requests_ref")


def test_resolve_agent_loop_artifact_path_allows_handoff_and_upstream_artifacts(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        handoff_root = root / "artifacts" / "transcript_edit_handoffs"
        upstream_root = root / "artifacts" / "mapping_upstream_requests"
        handoff_root.mkdir(parents=True, exist_ok=True)
        upstream_root.mkdir(parents=True, exist_ok=True)
        handoff_file = handoff_root / "D1" / "run.json"
        handoff_file.parent.mkdir(parents=True, exist_ok=True)
        handoff_file.write_text("{}", encoding="utf-8")
        upstream_file = upstream_root / "D1" / "run.json"
        upstream_file.parent.mkdir(parents=True, exist_ok=True)
        upstream_file.write_text("{}", encoding="utf-8")

        monkeypatch.setattr(agent_loop, "dossiers_artifacts_root", lambda: root / "artifacts")
        assert agent_loop._resolve_agent_loop_artifact_path(str(handoff_file)) is not None  # type: ignore[attr-defined]
        assert agent_loop._resolve_agent_loop_artifact_path(str(upstream_file)) is not None  # type: ignore[attr-defined]


def test_execute_run_strict_mode_blocks_when_handoff_not_mapping_ready(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _reset_registry(Path(tmp))
        run_id = "run_strict_blocked"
        agent_loop._run_registry.create_run(run_id=run_id, request={"dossier_id": "D1"})  # type: ignore[attr-defined]
        monkeypatch.setattr(
            agent_loop,
            "load_transcript_handoff_packet",
            lambda **kwargs: {
                "terminal": {"mapping_ready": False},
                "resume_recommendation": "requires_upstream_resolution",
                "mapping_watchlist": ["range"],
            },
        )
        req = agent_loop.AgentLoopRunRequest(
            dossier_id="D1",
            background=False,
            transcript_handoff_ref="artifacts/transcript_edit_handoffs/D1/r.json",
            mapping_readiness_mode="strict",
        )
        agent_loop._execute_run(run_id, req)
        run = asyncio.run(agent_loop.get_agent_loop_run(run_id))
        assert run["status"] == "failed"
        assert run["error"] == "mapping_strict_handoff_not_ready"
