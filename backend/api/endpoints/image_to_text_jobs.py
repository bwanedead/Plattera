from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from datetime import datetime

from config.settings import IMAGE_TO_TEXT_BATCH_MAX
from utils.file_handler import save_uploaded_file, is_valid_image_file
from services.image_queue import ImageToTextJob, ImageToTextJobStore, get_queue_service
from pathlib import Path

# Dossier services (optional pre-association for progressive visibility)
try:
    from services.dossier.management_service import DossierManagementService
    from services.dossier.association_service import TranscriptionAssociationService
except Exception:
    DossierManagementService = None  # type: ignore
    TranscriptionAssociationService = None  # type: ignore


router = APIRouter()


@router.post("/image-to-text/jobs")
async def enqueue_image_to_text_jobs(
    files: List[UploadFile] = File(...),
    # processing parameters
    model: str = Form("gpt-4o"),
    extraction_mode: str = Form("legal_document_json"),
    contrast: str = Form("2.0"),
    sharpness: str = Form("2.0"),
    brightness: str = Form("1.5"),
    color: str = Form("1.0"),
    redundancy: str = Form("1"),
    consensus_strategy: str = Form("sequential"),
    auto_llm_consensus: str = Form("false"),
    llm_consensus_model: str = Form("gpt-5-consensus"),
    dossier_id: Optional[str] = Form(None),
    transcription_id: Optional[str] = Form(None),
    segment_id: Optional[str] = Form(None),
    auto_create_dossier_per_file: str = Form("false"),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > IMAGE_TO_TEXT_BATCH_MAX:
        raise HTTPException(status_code=400, detail=f"Maximum {IMAGE_TO_TEXT_BATCH_MAX} files are allowed per batch")

    # parse settings
    try:
        enhancement_settings = {
            'contrast': max(0.1, min(5.0, float(contrast))),
            'sharpness': max(0.1, min(5.0, float(sharpness))),
            'brightness': max(0.1, min(3.0, float(brightness))),
            'color': max(0.0, min(3.0, float(color)))
        }
    except Exception:
        enhancement_settings = {'contrast': 1.5, 'sharpness': 1.2, 'brightness': 1.0, 'color': 1.0}

    try:
        redundancy_count = max(1, min(10, int(redundancy)))
    except Exception:
        redundancy_count = 1

    # create jobs
    store = ImageToTextJobStore()
    queue = get_queue_service()
    job_ids: List[str] = []

    for f in files:
        if not is_valid_image_file(f.filename):
            raise HTTPException(status_code=400, detail=f"Invalid file type: {f.filename}")
        content = await f.read()
        success, error, temp_path = save_uploaded_file(content, f.filename)
        if not success or not temp_path:
            raise HTTPException(status_code=400, detail=error or "Failed to save file")
        # HARD MODE: force per-file new dossier for every file (ignore incoming dossier_id/selection)
        per_file_dossier_id = None
        auto_flag = True

        # Do NOT pre-create transcription or run metadata here; the worker creates a new dossier per file on start
        per_file_transcription_id: Optional[str] = None

        job = ImageToTextJob.new(
            source_filename=f.filename,
            source_path=temp_path,
            model=model,
            extraction_mode=extraction_mode,
            enhancement_settings=enhancement_settings,
            user_id=None,
            dossier_id=per_file_dossier_id,
            transcription_id=(per_file_transcription_id or None),
            redundancy_count=redundancy_count,
            consensus_strategy=consensus_strategy,
            auto_llm_consensus=str(auto_llm_consensus).strip().lower() in ("1", "true", "yes", "on"),
            llm_consensus_model=llm_consensus_model,
            auto_create_dossier_per_file=auto_flag,
        )
        store.create(job)
        job_ids.append(job.id)

    queue.enqueue_batch(job_ids)
    return {"status": "enqueued", "count": len(job_ids), "job_ids": job_ids}


@router.get("/image-to-text/jobs/{job_id}")
async def get_image_to_text_job(job_id: str):
    store = ImageToTextJobStore()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/image-to-text/jobs")
async def list_image_to_text_jobs(limit: int = 50):
    store = ImageToTextJobStore()
    return {"jobs": store.list(limit=limit)}


