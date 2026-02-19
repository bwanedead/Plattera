"""Backend API endpoints for controller-driven agent-loop runs."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from threading import Thread
from time import time
from typing import Any, AsyncGenerator, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_kernel.models import KernelBudgets, KernelGoal, KernelSessionStartRequest
from agent_kernel.session import KernelSessionManager
from agent_kernel.tooling import CorpusArtifactOpener
from agents.controller.controller import run_controller_loop
from agents.controller.openai_client import OpenAINextStepClient
from agents.controller.bootstrap import persist_deed_text_artifact
from services.agent_kernel.run_artifact_persistence_service import RunArtifactPersistenceService
from services.agent_loop.event_bus import event_bus
from services.agent_loop.run_registry_service import AgentLoopRunRegistryService
from config.paths import agent_kernel_artifacts_root

router = APIRouter()
logger = logging.getLogger(__name__)

_run_registry = AgentLoopRunRegistryService()
_artifact_opener = CorpusArtifactOpener()
_MAX_ARTIFACT_JSON_BYTES = 262144


class AgentLoopRunRequest(BaseModel):
    dossier_id: Optional[str] = None
    text: Optional[str] = None
    initial_ir_ref: Optional[str] = None
    model: str = "gpt-5-mini"
    max_iterations: int = Field(default=12, ge=1, le=100)
    requires_global_placement: bool = False
    render_required: bool = False
    background: bool = True


def _build_start_request(run_id: str, request: AgentLoopRunRequest) -> KernelSessionStartRequest:
    request_id = f"agent-loop-{run_id}"
    initial_graph_json = None
    if request.text and request.text.strip():
        deed_artifact = persist_deed_text_artifact(
            request_id=request_id,
            deed_text=request.text.strip(),
            dossier_id=request.dossier_id,
        )
        initial_graph_json = {
            "graph_id": f"graph_{request_id}",
            "nodes": [],
            "edges": [],
            "metadata": {
                "source": "agent_loop_api_text_bootstrap",
                "dossier_id": request.dossier_id,
                "deed_text_excerpt": deed_artifact.excerpt,
                "deed_text_artifact_ref": deed_artifact.artifact_path,
            },
        }
    return KernelSessionStartRequest(
        request_id=request_id,
        goal=KernelGoal(
            requires_global_placement=request.requires_global_placement,
            render_required=request.render_required,
            objective="agent_loop_api_run",
        ),
        budgets=KernelBudgets(
            max_steps=30,
            max_wall_time_seconds=600,
            max_retrieval_calls=12,
            max_semantic_calls=8,
            max_patch_calls=8,
        ),
        dossier_id=request.dossier_id,
        source_entry_ref=(f"final:{request.dossier_id}" if request.dossier_id else None),
        initial_ir_ref=request.initial_ir_ref,
        initial_graph_json=initial_graph_json,
    )


def _execute_run(run_id: str, request: AgentLoopRunRequest) -> None:
    try:
        persistence = RunArtifactPersistenceService()
        session_manager = KernelSessionManager(persistence_service=persistence)
        llm_client = OpenAINextStepClient()
        start_request = _build_start_request(run_id, request)
        result = run_controller_loop(
            session_manager=session_manager,
            llm_client=llm_client,
            start_request=start_request,
            model=request.model,
            max_iterations=request.max_iterations,
        )
        patch = {
            "status": "completed",
            "session_id": result.session_id,
            "run_artifact_ref": result.run_artifact_ref,
            "transcript_artifact_ref": result.transcript_artifact_ref,
            "terminal": result.terminal.model_dump(mode="json"),
            "dashboard": result.last_dashboard,
        }
        updated = _run_registry.update_run(run_id=run_id, patch=patch)
        if updated is not None:
            event_bus.publish_sync(run_id, {"event_type": "run_completed", "run": updated})
    except Exception as exc:
        logger.exception("agent_loop_run_failed")
        patch = {"status": "failed", "error": str(exc)}
        updated = _run_registry.update_run(run_id=run_id, patch=patch)
        if updated is not None:
            event_bus.publish_sync(run_id, {"event_type": "run_failed", "run": updated})


@router.post("/run")
async def start_agent_loop_run(request: AgentLoopRunRequest) -> dict[str, Any]:
    if not request.initial_ir_ref and not request.text and not request.dossier_id:
        raise HTTPException(status_code=400, detail="one_of_dossier_id_or_text_or_initial_ir_ref_required")
    run_id = f"run_{int(time())}_{uuid4().hex[:8]}"
    entry = _run_registry.create_run(
        run_id=run_id,
        request={
            "request_id": f"agent-loop-{run_id}",
            "dossier_id": request.dossier_id,
            "model": request.model,
        },
    )
    await event_bus.publish(run_id, {"event_type": "run_started", "run": entry})

    if request.background:
        thread = Thread(target=_execute_run, args=(run_id, request), daemon=True)
        thread.start()
        return {"run_id": run_id, "status": "running"}

    _execute_run(run_id, request)
    run = _run_registry.get_run(run_id)
    return run or {"run_id": run_id, "status": "unknown"}


@router.get("/run/{run_id}")
async def get_agent_loop_run(run_id: str) -> dict[str, Any]:
    run = _run_registry.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return run


@router.get("/runs")
async def list_agent_loop_runs(limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
    runs = _run_registry.list_runs(limit=limit)
    return {"runs": runs, "count": len(runs)}


@router.get("/artifact/open")
async def open_agent_loop_artifact(artifact_ref: str = Query(..., min_length=1)) -> dict[str, Any]:
    payload = _artifact_opener.open_artifact({"artifact_ref": artifact_ref})
    return {
        "reason_codes": payload.get("reason_codes", []),
        "summary": payload.get("summary", ""),
        "artifact_ref": (
            payload.get("artifact_ref").model_dump(mode="json")
            if hasattr(payload.get("artifact_ref"), "model_dump")
            else payload.get("artifact_ref")
        ),
    }


@router.get("/artifact/json")
async def get_agent_loop_artifact_json(artifact_ref: str = Query(..., min_length=1)) -> dict[str, Any]:
    safe_path = _resolve_agent_kernel_artifact_path(artifact_ref)
    if safe_path is None:
        raise HTTPException(status_code=400, detail="artifact_ref_outside_agent_kernel_root")
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="artifact_not_found")
    try:
        raw = safe_path.read_bytes()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"artifact_read_failed:{type(exc).__name__}") from exc
    if len(raw) > _MAX_ARTIFACT_JSON_BYTES:
        raise HTTPException(status_code=413, detail="artifact_json_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"artifact_json_invalid:{type(exc).__name__}") from exc
    if not isinstance(payload, (dict, list)):
        raise HTTPException(status_code=400, detail="artifact_json_not_object_or_array")
    return {"artifact_path": str(safe_path), "json": payload}


async def _sse_stream(run_id: str, q: asyncio.Queue) -> AsyncGenerator[str, None]:
    try:
        while True:
            try:
                data = await asyncio.wait_for(q.get(), timeout=10.0)
                yield f"data: {data}\n\n"
            except asyncio.TimeoutError:
                yield "event: ping\ndata: {}\n\n"
    except asyncio.CancelledError:
        return
    finally:
        await event_bus.unsubscribe(run_id, q)


@router.get("/events/{run_id}", include_in_schema=False)
async def stream_agent_loop_events(run_id: str):
    q = await event_bus.subscribe(run_id)
    return StreamingResponse(_sse_stream(run_id, q), media_type="text/event-stream")


def _resolve_agent_kernel_artifact_path(artifact_ref: str) -> Path | None:
    try:
        root = agent_kernel_artifacts_root().resolve()
        path = Path(artifact_ref).resolve()
    except Exception:
        return None
    if path == root or root in path.parents:
        return path
    return None
