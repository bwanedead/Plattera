"""API endpoints for transcription edit loop v0.

Legacy compatibility endpoint for deterministic transcription-edit v0 surfaces.
Canonical harness-facing transcript-edit API lives in
``api.endpoints.transcript_edit_agent``.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from time import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from config.paths import dossiers_artifacts_root
from transcript_edit.contracts import (
    TranscriptionEditRunRequestV0,
)
from transcript_edit.run_registry import TranscriptionEditRunRegistry
from transcript_edit.run_service import TranscriptionEditRunService

router = APIRouter()

_registry = TranscriptionEditRunRegistry()
_service = TranscriptionEditRunService()
_MAX_ARTIFACT_JSON_BYTES = 262144


class StartTranscriptionEditRequest(TranscriptionEditRunRequestV0):
    background: bool = True


def _execute_run(run_id: str, request: StartTranscriptionEditRequest) -> None:
    try:
        snapshot = _service.run(
            TranscriptionEditRunRequestV0(
                start=request.start,
                plan=request.plan,
                promote_for_mapping=request.promote_for_mapping,
            )
        )
        _registry.update_run(run_id=run_id, patch={"status": "completed", "snapshot": snapshot.model_dump(mode="json")})
    except Exception as exc:
        _registry.update_run(run_id=run_id, patch={"status": "failed", "error": str(exc)})


@router.post("/run")
async def start_run(request: StartTranscriptionEditRequest) -> dict[str, Any]:
    run_id = f"txe_{int(time())}_{uuid4().hex[:8]}"
    _registry.create_run(
        run_id=run_id,
        request={
            "dossier_id": request.start.dossier_id,
            "mode": request.start.mode.value,
            "has_plan": request.plan is not None,
            "promote_for_mapping": request.promote_for_mapping,
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


@router.get("/artifact/open")
async def open_artifact(artifact_ref: str = Query(..., min_length=1)) -> dict[str, Any]:
    safe_path = _resolve_artifact_path(artifact_ref)
    if safe_path is None:
        raise HTTPException(status_code=400, detail="artifact_ref_outside_allowed_roots")
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="artifact_not_found")
    return {"artifact_path": str(safe_path), "exists": True, "size_bytes": safe_path.stat().st_size}


@router.get("/artifact/json")
async def artifact_json(artifact_ref: str = Query(..., min_length=1)) -> dict[str, Any]:
    safe_path = _resolve_artifact_path(artifact_ref)
    if safe_path is None:
        raise HTTPException(status_code=400, detail="artifact_ref_outside_allowed_roots")
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="artifact_not_found")
    raw = safe_path.read_bytes()
    if len(raw) > _MAX_ARTIFACT_JSON_BYTES:
        raise HTTPException(status_code=413, detail="artifact_json_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"artifact_json_invalid:{type(exc).__name__}") from exc
    if not isinstance(payload, (dict, list)):
        raise HTTPException(status_code=400, detail="artifact_json_not_object_or_array")
    return {"artifact_path": str(safe_path), "json": payload}


def _resolve_artifact_path(artifact_ref: str) -> Path | None:
    try:
        path = Path(artifact_ref).resolve()
        root = (dossiers_artifacts_root() / "transcription_edit").resolve()
    except Exception:
        return None
    if path == root or root in path.parents:
        return path
    return None
