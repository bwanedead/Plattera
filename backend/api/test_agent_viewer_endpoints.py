import asyncio
import json
from pathlib import Path

from fastapi import HTTPException

from api.endpoints import agent_viewer as endpoint
from api.router import api_router
from services.agent_viewer import artifact_gateway, feedback_store, projection
from services.agent_viewer.event_bus import event_bus


def _patch_roots(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    dossiers_root = tmp_path / "dossiers_artifacts"
    harness_root = tmp_path / "harness_cli"
    dossiers_root.mkdir()
    harness_root.mkdir()

    monkeypatch.setattr(artifact_gateway, "dossiers_artifacts_root", lambda: dossiers_root)
    monkeypatch.setattr(artifact_gateway, "harness_cli_artifacts_root", lambda: harness_root)
    monkeypatch.setattr(feedback_store, "dossiers_artifacts_root", lambda: dossiers_root)
    monkeypatch.setattr(projection, "dossiers_artifacts_root", lambda: dossiers_root)
    return dossiers_root, harness_root


def test_agent_viewer_routes_are_registered() -> None:
    route_paths = {getattr(route, "path", "") for route in api_router.routes}

    assert "/api/agent-viewer/snapshot/{loop_kind}/{run_id}" in route_paths
    assert "/api/agent-viewer/events/{loop_kind}/{run_id}" in route_paths
    assert "/api/agent-viewer/feedback/{loop_kind}/{run_id}" in route_paths


def test_snapshot_unknown_run_returns_valid_empty_shape(monkeypatch, tmp_path: Path) -> None:
    _patch_roots(monkeypatch, tmp_path)

    payload = asyncio.run(endpoint.get_snapshot("test_loop", "missing_run"))

    assert payload["protocol"] == "agent_viewer_snapshot_v1"
    assert payload["run"]["loop_kind"] == "test_loop"
    assert payload["run"]["run_id"] == "missing_run"
    assert payload["run"]["status"] == "unavailable"
    assert payload["run"]["reason"] == "viewer_snapshot_not_found"
    for key in ("chapters", "activity", "artifacts", "evidence", "work_items", "hitl_prompts", "actions"):
        assert payload[key] == []


def test_snapshot_uses_persisted_viewer_snapshot(monkeypatch, tmp_path: Path) -> None:
    dossiers_root, _ = _patch_roots(monkeypatch, tmp_path)
    snapshot_path = dossiers_root / "agent_viewer" / "snapshots" / "loop_a" / "run_a.json"
    snapshot_path.parent.mkdir(parents=True)
    snapshot_path.write_text(
        json.dumps(
            {
                "protocol": "agent_viewer_snapshot_v1",
                "run": {"loop_kind": "loop_a", "run_id": "run_a", "status": "running"},
                "chapters": [{"id": "ch1", "title": "Chapter 1", "status": "running"}],
                "activity": [],
                "artifacts": [],
                "evidence": [],
                "work_items": [],
                "hitl_prompts": [],
                "actions": [],
            }
        ),
        encoding="utf-8",
    )

    payload = asyncio.run(endpoint.get_snapshot("loop_a", "run_a"))

    assert payload["run"]["status"] == "running"
    assert payload["chapters"][0]["id"] == "ch1"


def test_feedback_post_and_get_round_trip(monkeypatch, tmp_path: Path) -> None:
    _patch_roots(monkeypatch, tmp_path)

    post_response = asyncio.run(
        endpoint.post_feedback(
            "loop_b",
            "run_b",
            endpoint.FeedbackRequest(
                prompt_id="prompt_1",
                choice="A",
                note="operator note",
                metadata={"source": "test"},
            ),
        )
    )
    get_response = asyncio.run(endpoint.get_feedback("loop_b", "run_b"))

    assert post_response["entry"]["prompt_id"] == "prompt_1"
    assert post_response["count"] == 1
    entries = get_response.model_dump(mode="json")["entries"]
    assert len(entries) == 1
    assert entries[0]["choice"] == "A"
    assert entries[0]["metadata"] == {"source": "test"}


def test_feedback_rejects_path_like_identifiers(monkeypatch, tmp_path: Path) -> None:
    _patch_roots(monkeypatch, tmp_path)

    try:
        asyncio.run(endpoint.get_feedback("..\\..\\escape", "run_x"))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "loop_kind_path_segment_invalid"
    else:
        raise AssertionError("path-like loop_kind was accepted")


def test_snapshot_rejects_path_like_identifiers(monkeypatch, tmp_path: Path) -> None:
    _patch_roots(monkeypatch, tmp_path)

    try:
        asyncio.run(endpoint.get_snapshot("loop_x", "..\\escape"))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "run_id_path_segment_invalid"
    else:
        raise AssertionError("path-like run_id was accepted")


def test_stream_key_rejects_ambiguous_identifiers() -> None:
    try:
        projection.stream_key_for("loop_x", "run..x")
    except ValueError as exc:
        assert str(exc) == "run_id_path_segment_invalid"
    else:
        raise AssertionError("ambiguous run_id was accepted")


def test_json_artifact_reads_relative_ref_and_rejects_traversal(monkeypatch, tmp_path: Path) -> None:
    dossiers_root, _ = _patch_roots(monkeypatch, tmp_path)
    artifact_path = dossiers_root / "runs" / "run_c" / "artifact.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(json.dumps({"ok": True}), encoding="utf-8")

    good = asyncio.run(endpoint.get_json_artifact("artifact://dossiers/runs/run_c/artifact.json"))

    assert Path(good["artifact_path"]) == artifact_path
    assert good["json"] == {"ok": True}
    try:
        asyncio.run(endpoint.get_json_artifact("../outside.json"))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "artifact_ref_path_traversal_forbidden"
    else:
        raise AssertionError("unsafe artifact ref was accepted")


def test_artifact_gateway_rejects_sensitive_paths(monkeypatch, tmp_path: Path) -> None:
    dossiers_root, _ = _patch_roots(monkeypatch, tmp_path)
    secret_path = dossiers_root / ".env"
    secret_path.write_text("TOKEN=not-for-viewer", encoding="utf-8")

    try:
        asyncio.run(endpoint.get_json_artifact(".env"))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "artifact_ref_sensitive_path_forbidden"
    else:
        raise AssertionError("sensitive artifact ref was accepted")


def test_image_artifact_serves_allowed_image_type(monkeypatch, tmp_path: Path) -> None:
    dossiers_root, _ = _patch_roots(monkeypatch, tmp_path)
    image_path = dossiers_root / "images" / "crop.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89"
    )

    response = asyncio.run(endpoint.get_image_artifact("images/crop.png"))

    assert Path(response.path) == image_path
    assert response.media_type == "image/png"


def test_sse_replays_event_bus_history(monkeypatch, tmp_path: Path) -> None:
    _patch_roots(monkeypatch, tmp_path)
    asyncio.run(
        event_bus.publish(
            "loop_sse:run_sse",
            {"id": "evt_1", "title": "Started work", "status": "running"},
        )
    )

    first_line = asyncio.run(_first_sse_line())

    assert first_line.startswith("data: ")
    assert json.loads(first_line.removeprefix("data: "))["title"] == "Started work"


def test_snapshot_projects_current_agent_viewer_event_envelope(monkeypatch, tmp_path: Path) -> None:
    _patch_roots(monkeypatch, tmp_path)
    asyncio.run(
        event_bus.publish(
            "loop_envelope:run_envelope",
            {
                "protocol": "agent_viewer_event_v1",
                "run_id": "run_envelope",
                "loop_kind": "loop_envelope",
                "lane": "main",
                "lane_seq": 7,
                "timestamp_epoch_seconds": 123,
                "event_type": "human_feedback_needed",
                "status": {
                    "stage": "waiting",
                    "line1": "Human feedback needed",
                    "line2": "Pick the best candidate",
                },
                "artifact_refs": {"crop": {"artifact_path": "crops/crop.png"}},
                "payload": {"prompt_id": "prompt_7"},
            },
        )
    )

    payload = asyncio.run(endpoint.get_snapshot("loop_envelope", "run_envelope"))

    assert payload["run"]["status"] == "observed"
    assert payload["activity"][0]["id"] == "7"
    assert payload["activity"][0]["chapter_id"] == "main"
    assert payload["activity"][0]["title"] == "Human feedback needed"
    assert payload["activity"][0]["detail"] == "Pick the best candidate"
    assert payload["activity"][0]["status"] == "waiting"
    assert payload["activity"][0]["event_type"] == "human_feedback_needed"
    assert payload["activity"][0]["payload"]["artifact_refs"]["crop"]["artifact_path"] == "crops/crop.png"


async def _first_sse_line() -> str:
    response = await endpoint.stream_events("loop_sse", "run_sse")
    agen = response.body_iterator
    try:
        chunk = await agen.__anext__()
    finally:
        await agen.aclose()
    return chunk.strip()
