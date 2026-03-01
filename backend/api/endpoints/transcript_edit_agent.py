"""Kernel-backed transcript-edit agent run endpoints."""

from __future__ import annotations

from threading import Thread
from time import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from agents.transcript_edit.controller import run_transcript_edit_controller_loop
from agents.transcript_edit.contracts import TranscriptEditAgentRunRequest
from agent_kernel.actions import ActionExecutor, ActionExecutorDeps
from agent_kernel.session import KernelSessionManager
from agent_kernel.tooling import (
    TranscriptAuditTool,
    TranscriptEditPlanApplyTool,
    TranscriptMappingPromoterTool,
    TranscriptSpanOpenerTool,
)
from services.agent_kernel.run_artifact_persistence_service import RunArtifactPersistenceService
from transcript_edit.run_registry import TranscriptionEditRunRegistry

router = APIRouter()

_registry = TranscriptionEditRunRegistry()


class TranscriptEditAgentApiRequest(TranscriptEditAgentRunRequest):
    background: bool = True


def _execute_run(run_id: str, request: TranscriptEditAgentApiRequest) -> None:
    try:
        persistence = RunArtifactPersistenceService()
        session_manager = KernelSessionManager(
            action_executor=ActionExecutor(
                deps=ActionExecutorDeps(
                    transcript_auditor=TranscriptAuditTool(),
                    transcript_span_opener=TranscriptSpanOpenerTool(),
                    transcript_plan_applier=TranscriptEditPlanApplyTool(),
                    transcript_promoter=TranscriptMappingPromoterTool(),
                )
            ),
            persistence_service=persistence,
        )
        result = run_transcript_edit_controller_loop(
            session_manager=session_manager,
            request=TranscriptEditAgentRunRequest.model_validate(request.model_dump(mode="json")),
            request_id_prefix=f"tx-agent-{run_id}",
        )
        _registry.update_run(
            run_id=run_id,
            patch={
                "status": result.status,
                "snapshot": {
                    "run_id": run_id,
                    "status": result.status,
                    "reason_code": result.reason_code,
                    "iterations": result.iterations,
                    "session_id": result.session_id,
                    "run_artifact_ref": result.run_artifact_ref,
                    "latest_refs": result.latest_refs,
                    "review_required": result.review_required,
                },
            },
        )
    except Exception as exc:
        _registry.update_run(run_id=run_id, patch={"status": "failed", "error": str(exc)})


@router.post("/run")
async def start_run(request: TranscriptEditAgentApiRequest) -> dict[str, Any]:
    if not request.source_transcript_ref and not request.source_text:
        raise HTTPException(status_code=400, detail="source_transcript_ref_or_source_text_required")
    run_id = f"tx_agent_{int(time())}_{uuid4().hex[:8]}"
    _registry.create_run(
        run_id=run_id,
        request={
            "dossier_id": request.dossier_id,
            "model": request.model,
            "max_iterations": request.max_iterations,
            "auto_promote": request.auto_promote,
            "mode": request.mode,
            "has_source_transcript_ref": bool(request.source_transcript_ref),
            "has_source_text": bool(request.source_text),
            "has_edit_plan": isinstance(request.edit_plan, dict),
        },
    )
    if request.background:
        thread = Thread(target=_execute_run, args=(run_id, request), daemon=True)
        thread.start()
        return {"run_id": run_id, "status": "running"}
    _execute_run(run_id, request)
    run = _registry.get_run(run_id)
    return run or {"run_id": run_id, "status": "unknown"}


@router.get("/run/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    run = _registry.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return run


@router.get("/runs")
async def list_runs(limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
    runs = _registry.list_runs(limit=limit)
    return {"runs": runs, "count": len(runs)}
