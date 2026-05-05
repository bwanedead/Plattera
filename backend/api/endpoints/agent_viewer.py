"""Agent Viewer transport endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from services.agent_viewer import feedback_store
from services.agent_viewer.artifact_gateway import (
    ArtifactAccessError,
    image_artifact,
    json_artifact,
)
from services.agent_viewer.event_bus import event_bus
from services.agent_viewer.identifiers import AgentViewerIdentifierError, validate_viewer_identifiers
from services.agent_viewer.models import FeedbackListResponse, FeedbackRequest
from services.agent_viewer.projection import build_snapshot, stream_key_for

router = APIRouter()


@router.get("/snapshot/{loop_kind}/{run_id}")
async def get_snapshot(loop_kind: str, run_id: str) -> dict:
    try:
        return build_snapshot(loop_kind=loop_kind, run_id=run_id).model_dump(mode="json")
    except AgentViewerIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/events/{loop_kind}/{run_id}")
async def stream_events(loop_kind: str, run_id: str) -> StreamingResponse:
    try:
        stream_key = stream_key_for(loop_kind, run_id)
    except AgentViewerIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    q = await event_bus.subscribe(stream_key)

    async def event_stream():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            await event_bus.unsubscribe(stream_key, q)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/artifact/json")
async def get_json_artifact(artifact_ref: str):
    try:
        artifact = json_artifact(artifact_ref)
    except ArtifactAccessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"artifact_path": str(artifact.path), "json": artifact.json}


@router.get("/artifact/image")
async def get_image_artifact(artifact_ref: str) -> FileResponse:
    try:
        artifact = image_artifact(artifact_ref)
    except ArtifactAccessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(artifact.path, media_type=artifact.media_type)


@router.get("/feedback/{loop_kind}/{run_id}", response_model=FeedbackListResponse)
async def get_feedback(loop_kind: str, run_id: str) -> FeedbackListResponse:
    try:
        safe_loop_kind, safe_run_id = validate_viewer_identifiers(loop_kind=loop_kind, run_id=run_id)
    except AgentViewerIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FeedbackListResponse(
        loop_kind=safe_loop_kind,
        run_id=safe_run_id,
        entries=feedback_store.list_entries(loop_kind=safe_loop_kind, run_id=safe_run_id),
    )


@router.post("/feedback/{loop_kind}/{run_id}")
async def post_feedback(loop_kind: str, run_id: str, request: FeedbackRequest) -> dict:
    try:
        safe_loop_kind, safe_run_id = validate_viewer_identifiers(loop_kind=loop_kind, run_id=run_id)
    except AgentViewerIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    entry = feedback_store.append_entry(
        loop_kind=safe_loop_kind,
        run_id=safe_run_id,
        prompt_id=request.prompt_id,
        choice=request.choice,
        note=request.note,
        metadata=request.metadata,
    )
    count = len(feedback_store.list_entries(loop_kind=safe_loop_kind, run_id=safe_run_id))
    return {"ok": True, "entry": entry, "count": count}
