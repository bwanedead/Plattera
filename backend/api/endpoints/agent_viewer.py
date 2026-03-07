"""Unified Agent Viewer SSE/artifact facade across loop kinds."""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import re
from datetime import datetime
from pathlib import Path
from time import time
from typing import Any, AsyncGenerator, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.logs import get_frontend_logs_snapshot
from config.paths import dossiers_artifacts_root, dossiers_root, dossiers_views_root
from services.agent_viewer import feedback_store
from services.agent_loop.event_bus import event_bus as agent_loop_event_bus
from services.agent_viewer.event_bus import event_bus as viewer_event_bus
from services.logging_service import get_active_log_file

router = APIRouter()
logger = logging.getLogger(__name__)

_MAX_ARTIFACT_JSON_BYTES = 262144
_VALID_LOOP_KINDS = {"agent_loop", "transcript_edit"}
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})")
_MARKER_RE = re.compile(r"AGENT_VIEWER_TIMING\s+►\s+([a-zA-Z0-9_]+)")


class AgentViewerFeedbackRequest(BaseModel):
    prompt_id: str | None = None
    choice: str | None = None
    note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/events/{loop_kind}/{run_id}", include_in_schema=False)
async def stream_agent_viewer_events(
    loop_kind: Literal["agent_loop", "transcript_edit"],
    run_id: str,
):
    if loop_kind not in _VALID_LOOP_KINDS:
        raise HTTPException(status_code=400, detail="invalid_loop_kind")
    if loop_kind == "agent_loop":
        logger.info("AGENT_VIEWER_TIMING ► sse_subscribe_start loop_kind=%s run_id=%s", loop_kind, run_id)
        q = await agent_loop_event_bus.subscribe(run_id)
        return StreamingResponse(
            _agent_loop_sse_stream(run_id=run_id, q=q),
            media_type="text/event-stream",
        )
    stream_key = _stream_key(loop_kind, run_id)
    logger.info(
        "AGENT_VIEWER_TIMING ► sse_subscribe_start loop_kind=%s run_id=%s stream_key=%s",
        loop_kind,
        run_id,
        stream_key,
    )
    q = await viewer_event_bus.subscribe(stream_key)
    return StreamingResponse(
        _viewer_sse_stream(stream_key=stream_key, q=q),
        media_type="text/event-stream",
    )


@router.get("/artifact/open")
async def open_agent_viewer_artifact(artifact_ref: str = Query(..., min_length=1)) -> dict[str, Any]:
    safe_path = _resolve_artifact_path(artifact_ref)
    if safe_path is None:
        raise HTTPException(status_code=400, detail="artifact_ref_outside_allowed_roots")
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="artifact_not_found")
    return {"artifact_path": str(safe_path), "exists": True, "size_bytes": safe_path.stat().st_size}


@router.get("/artifact/json")
async def agent_viewer_artifact_json(artifact_ref: str = Query(..., min_length=1)) -> dict[str, Any]:
    safe_path = _resolve_artifact_path(artifact_ref)
    if safe_path is None:
        raise HTTPException(status_code=400, detail="artifact_ref_outside_allowed_roots")
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="artifact_not_found")
    raw = safe_path.read_bytes()
    if len(raw) > _MAX_ARTIFACT_JSON_BYTES:
        raise HTTPException(status_code=413, detail="artifact_json_too_large")
    try:
        # Tolerate UTF-8 BOM written by some Windows tooling.
        payload = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"artifact_json_invalid:{type(exc).__name__}") from exc
    return {"artifact_path": str(safe_path), "json": payload}


@router.get("/artifact/image")
async def agent_viewer_artifact_image(artifact_ref: str = Query(..., min_length=1)):
    safe_path = _resolve_artifact_path(artifact_ref)
    if safe_path is None:
        raise HTTPException(status_code=400, detail="artifact_ref_outside_allowed_roots")
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="artifact_not_found")
    mime_type, _ = mimetypes.guess_type(str(safe_path))
    if not mime_type or not mime_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="artifact_not_image")
    from fastapi.responses import FileResponse

    return FileResponse(str(safe_path), media_type=mime_type)


@router.get("/feedback/{loop_kind}/{run_id}")
async def get_agent_viewer_feedback(
    loop_kind: Literal["agent_loop", "transcript_edit"],
    run_id: str,
) -> dict[str, Any]:
    entries = feedback_store.list_entries(loop_kind=loop_kind, run_id=run_id)
    return {"loop_kind": loop_kind, "run_id": run_id, "entries": entries}


@router.post("/feedback/{loop_kind}/{run_id}")
async def post_agent_viewer_feedback(
    loop_kind: Literal["agent_loop", "transcript_edit"],
    run_id: str,
    request: AgentViewerFeedbackRequest,
) -> dict[str, Any]:
    has_choice = isinstance(request.choice, str) and request.choice.strip() != ""
    has_note = isinstance(request.note, str) and request.note.strip() != ""
    has_prompt = isinstance(request.prompt_id, str) and request.prompt_id.strip() != ""
    if has_prompt and not (has_choice or has_note):
        raise HTTPException(status_code=400, detail="feedback_requires_choice_or_note_for_prompt")
    if not has_prompt and has_choice:
        raise HTTPException(status_code=400, detail="feedback_choice_requires_prompt_id")

    entry = feedback_store.append_entry(
        loop_kind=loop_kind,
        run_id=run_id,
        prompt_id=request.prompt_id,
        choice=request.choice,
        note=request.note,
        metadata=request.metadata,
    )
    logger.info(
        "AGENT_VIEWER_FEEDBACK ► loop_kind=%s run_id=%s prompt_id=%s choice=%s note_len=%s",
        loop_kind,
        run_id,
        str(request.prompt_id or "")[:80] or "n/a",
        str(request.choice or "")[:80] or "n/a",
        len(str(request.note or "")),
    )
    viewer_event_bus.publish_sync(
        _stream_key(loop_kind, run_id),
        {
            "protocol": "agent_viewer_event_v1",
            "run_id": run_id,
            "loop_kind": loop_kind,
            "seq": int(time() * 1000),
            "iteration": None,
            "timestamp_epoch_seconds": int(time()),
            "event_type": "human_feedback",
            "status": {
                "stage": "human_feedback",
                "line1": "Human feedback submitted",
                "line2": request.choice or (request.note[:120] if isinstance(request.note, str) else None),
            },
            "artifact_refs": {},
            "payload": entry,
        },
    )
    if loop_kind == "agent_loop":
        agent_loop_event_bus.publish_sync(
            run_id,
            {"event_type": "agent_viewer_feedback", "run_id": run_id, "entry": entry},
        )
    auto_resume: dict[str, Any] | None = None
    if loop_kind == "transcript_edit":
        try:
            from api.endpoints.transcript_edit_agent import request_run_resume_if_waiting

            auto_resume = request_run_resume_if_waiting(
                run_id=run_id,
                trigger="feedback_post",
                background=True,
            )
        except Exception:
            auto_resume = {"resumed": False, "reason": "resume_trigger_error"}
    count = len(feedback_store.list_entries(loop_kind=loop_kind, run_id=run_id))
    return {"ok": True, "entry": entry, "count": count, "auto_resume": auto_resume}


@router.get("/timing-summary/{run_id}")
async def get_agent_viewer_timing_summary(
    run_id: str,
    max_backend_lines: int = Query(default=5000, ge=200, le=20000),
    max_frontend_entries: int = Query(default=2000, ge=100, le=5000),
) -> dict[str, Any]:
    backend_events = _collect_backend_timing_events(run_id=run_id, max_lines=max_backend_lines)
    frontend_events = _collect_frontend_timing_events(run_id=run_id, max_entries=max_frontend_entries)
    timeline = sorted([*backend_events, *frontend_events], key=lambda item: float(item.get("ts") or 0.0))
    first_key_ts: dict[str, float] = {}
    for evt in timeline:
        key = str(evt.get("key") or "")
        ts = float(evt.get("ts") or 0.0)
        if not key or ts <= 0:
            continue
        first_key_ts.setdefault(key, ts)
    return {
        "run_id": run_id,
        "backend_count": len(backend_events),
        "frontend_count": len(frontend_events),
        "timeline_count": len(timeline),
        "keys": first_key_ts,
        "deltas_ms": _compute_timing_deltas_ms(first_key_ts),
        "backend_events": backend_events,
        "frontend_events": frontend_events,
        "timeline": timeline,
    }


def _stream_key(loop_kind: str, run_id: str) -> str:
    return f"{loop_kind}:{run_id}"


def _collect_backend_timing_events(*, run_id: str, max_lines: int) -> list[dict[str, Any]]:
    path = Path(get_active_log_file())
    if not path.exists():
        return []
    lines: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.rstrip("\r\n")
            if "AGENT_VIEWER_TIMING" not in line:
                continue
            lines.append(line)
            if len(lines) > max_lines:
                del lines[:-max_lines]
    out: list[dict[str, Any]] = []
    for line in lines:
        clean = _ANSI_RE.sub("", line)
        if not _line_matches_run(clean, run_id):
            continue
        marker = _MARKER_RE.search(clean)
        key = marker.group(1) if marker is not None else "unknown"
        out.append(
            {
                "source": "backend",
                "key": key,
                "ts": _parse_backend_log_ts(clean),
                "line": clean[-500:],
            }
        )
    return out


def _collect_frontend_timing_events(*, run_id: str, max_entries: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in get_frontend_logs_snapshot(limit=max_entries):
        if not isinstance(entry, dict):
            continue
        message = str(entry.get("message") or "")
        if "AGENT_VIEWER_TIMING" not in message:
            continue
        meta = entry.get("meta") if isinstance(entry.get("meta"), dict) else {}
        if f"run={run_id}" not in message and str(meta.get("run_id") or "") != run_id:
            continue
        marker = _MARKER_RE.search(message)
        key = marker.group(1) if marker is not None else "unknown"
        out.append(
            {
                "source": "frontend",
                "key": key,
                "ts": float(entry.get("ts") or 0.0),
                "message": message[-500:],
            }
        )
    return out


def _line_matches_run(line: str, run_id: str) -> bool:
    if f"run_id={run_id}" in line:
        return True
    if f"run={run_id}" in line:
        return True
    if f"stream_key=transcript_edit:{run_id}" in line:
        return True
    return False


def _parse_backend_log_ts(line: str) -> float:
    match = _TS_RE.search(line)
    if match is None:
        return 0.0
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S,%f").timestamp()
    except Exception:
        return 0.0


def _compute_timing_deltas_ms(first_key_ts: dict[str, float]) -> dict[str, float | None]:
    def _delta(start_key: str, end_key: str) -> float | None:
        start = first_key_ts.get(start_key)
        end = first_key_ts.get(end_key)
        if start is None or end is None:
            return None
        return round((end - start) * 1000.0, 1)

    return {
        "tx_run_created_to_first_progress": _delta("tx_run_created", "tx_first_progress_emitted"),
        "first_progress_to_first_viewer_publish": _delta("tx_first_progress_emitted", "tx_first_viewer_publish"),
        "first_viewer_publish_to_sse_first_delivery": _delta("tx_first_viewer_publish", "sse_first_delivery"),
        "sse_first_delivery_to_frontend_first_event": _delta("sse_first_delivery", "first_event_received"),
        "frontend_first_event_to_first_live_event": _delta("first_event_received", "first_live_event_received"),
        "prompt_event_received_to_prompt_rendered": _delta("prompt_event_received", "prompt_rendered"),
    }


def _resolve_artifact_path(artifact_ref: str) -> Path | None:
    try:
        path = Path(artifact_ref).resolve()
        artifacts_root = dossiers_artifacts_root().resolve()
        views_root = dossiers_views_root().resolve()
        dossier_root = dossiers_root().resolve()
    except Exception:
        return None
    if path == artifacts_root or artifacts_root in path.parents:
        return path
    if path == views_root or views_root in path.parents:
        return path
    if path == dossier_root or dossier_root in path.parents:
        return path
    return None


def _to_artifact_ref_map(obj: Any) -> dict[str, dict[str, str]]:
    if not isinstance(obj, dict):
        return {}
    refs: dict[str, dict[str, str]] = {}
    for key, value in obj.items():
        if isinstance(value, str) and value.strip():
            refs[str(key)] = {"artifact_path": value}
        elif isinstance(value, dict):
            path = value.get("artifact_path")
            if isinstance(path, str) and path.strip():
                refs[str(key)] = {"artifact_path": path}
    return refs


def _normalize_agent_loop_event(run_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    event_type = str(payload.get("event_type") or "")
    if event_type == "agent_tape_update":
        status = payload.get("status") if isinstance(payload.get("status"), dict) else {}
        return {
            "protocol": "agent_viewer_event_v1",
            "run_id": run_id,
            "loop_kind": "agent_loop",
            "seq": payload.get("seq"),
            "iteration": status.get("iteration"),
            "timestamp_epoch_seconds": payload.get("timestamp_epoch_seconds"),
            "event_type": "status",
            "status": {
                "stage": status.get("stage"),
                "line1": status.get("line1") or status.get("status_chip") or "Agent update",
                "line2": status.get("line2") or status.get("display_delta"),
            },
            "artifact_refs": _to_artifact_ref_map(status.get("artifact_refs")),
            "payload": {
                "source_event_type": payload.get("source_event_type"),
                "action_type": status.get("action_type"),
                "outcome": status.get("outcome"),
                "reason_code": status.get("reason_code"),
                "phase": status.get("phase"),
            },
        }
    if event_type == "upstream_correction_request":
        request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
        line1 = str(request.get("message") or "Upstream correction request")
        line2 = str(request.get("reason_code") or "")
        return {
            "protocol": "agent_viewer_event_v1",
            "run_id": run_id,
            "loop_kind": "agent_loop",
            "seq": None,
            "iteration": None,
            "timestamp_epoch_seconds": int(time()),
            "event_type": "upstream_correction_request",
            "status": {
                "stage": "upstream_correction_request",
                "line1": line1[:200],
                "line2": line2[:240] or None,
            },
            "artifact_refs": _to_artifact_ref_map({"request_ref": payload.get("request_ref")}),
            "payload": {"request": request, "source_event_type": event_type},
        }
    if event_type in {"run_started", "run_completed", "run_failed"}:
        run = payload.get("run") if isinstance(payload.get("run"), dict) else {}
        return {
            "protocol": "agent_viewer_event_v1",
            "run_id": run_id,
            "loop_kind": "agent_loop",
            "seq": None,
            "iteration": None,
            "timestamp_epoch_seconds": None,
            "event_type": "done" if event_type == "run_completed" else "status",
            "status": {
                "stage": run.get("status") or event_type,
                "line1": event_type.replace("_", " ").title(),
                "line2": str(run.get("error") or "")[:240] or None,
            },
            "artifact_refs": _to_artifact_ref_map(run),
            "payload": {"run": run, "source_event_type": event_type},
        }
    return None


async def _agent_loop_sse_stream(run_id: str, q: asyncio.Queue) -> AsyncGenerator[str, None]:
    stream_key = _stream_key("agent_loop", run_id)
    viewer_q = await viewer_event_bus.subscribe(stream_key)
    fallback_seq = 0
    try:
        while True:
            try:
                agent_task = asyncio.create_task(q.get())
                viewer_task = asyncio.create_task(viewer_q.get())
                done, pending = await asyncio.wait({agent_task, viewer_task}, timeout=10.0, return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    for p in pending:
                        p.cancel()
                    yield "event: ping\ndata: {}\n\n"
                    continue
                for p in pending:
                    p.cancel()
                # Important: if both queues complete in the same tick, emit both events.
                # Otherwise one event can be dropped under concurrent publish.
                ordered_done = sorted(done, key=lambda t: 0 if t is agent_task else 1)
                for completed in ordered_done:
                    try:
                        data = completed.result()
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        continue
                    try:
                        parsed = json.loads(data)
                    except Exception:
                        continue
                    if not isinstance(parsed, dict):
                        continue
                    normalized = (
                        parsed
                        if parsed.get("protocol") == "agent_viewer_event_v1"
                        else _normalize_agent_loop_event(run_id, parsed)
                    )
                    if normalized is None:
                        continue
                    if normalized.get("seq") is None:
                        normalized["seq"] = fallback_seq
                        fallback_seq += 1
                    if normalized.get("timestamp_epoch_seconds") is None:
                        normalized["timestamp_epoch_seconds"] = int(time())
                    yield f"data: {json.dumps(normalized)}\n\n"
            except Exception:
                continue
    except asyncio.CancelledError:
        return
    finally:
        await agent_loop_event_bus.unsubscribe(run_id, q)
        await viewer_event_bus.unsubscribe(stream_key, viewer_q)


async def _viewer_sse_stream(stream_key: str, q: asyncio.Queue) -> AsyncGenerator[str, None]:
    first_delivery_logged = False
    try:
        while True:
            try:
                data = await asyncio.wait_for(q.get(), timeout=10.0)
                if not first_delivery_logged:
                    first_delivery_logged = True
                    try:
                        parsed = json.loads(data)
                    except Exception:
                        parsed = {}
                    if isinstance(parsed, dict):
                        payload = parsed.get("payload") if isinstance(parsed.get("payload"), dict) else {}
                        logger.info(
                            "AGENT_VIEWER_TIMING ► sse_first_delivery stream_key=%s event_type=%s phase=%s seq=%s",
                            stream_key,
                            str(parsed.get("event_type") or "status"),
                            str(payload.get("phase") or "n/a"),
                            str(parsed.get("seq") if parsed.get("seq") is not None else "n/a"),
                        )
                yield f"data: {data}\n\n"
            except asyncio.TimeoutError:
                yield "event: ping\ndata: {}\n\n"
    except asyncio.CancelledError:
        return
    finally:
        await viewer_event_bus.unsubscribe(stream_key, q)
