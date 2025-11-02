"""
Dossier Management API Endpoints
===============================

Endpoints for core CRUD operations on dossiers themselves.
Handles dossier lifecycle: create, read, update, delete.
"""

from fastapi import APIRouter, HTTPException, Query
import asyncio
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import logging
from starlette.concurrency import run_in_threadpool
from services.dossier.delete_job_manager import delete_job_manager

from services.dossier.management_service import DossierManagementService
from services.dossier.view_service import DossierViewService
from services.dossier.event_bus import event_bus
from services.dossier.title_lock_service import TitleLockService

logger = logging.getLogger(__name__)
router = APIRouter()


# Pydantic Models
class CreateDossierRequest(BaseModel):
    """Request model for creating a dossier"""
    title: str
    description: Optional[str] = None


class UpdateDossierRequest(BaseModel):
    """Request model for updating a dossier"""
    title: Optional[str] = None
    description: Optional[str] = None


class CreateSegmentRequest(BaseModel):
    name: str


class UpdateSegmentRequest(BaseModel):
    name: str


class DossierResponse(BaseModel):
    """Response model for dossier operations"""
    success: bool
    dossier_id: Optional[str] = None
    dossier: Optional[Dict[str, Any]] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class DossierListResponse(BaseModel):
    """Response model for dossier listing"""
    success: bool
    dossiers: List[Dict[str, Any]]
    total_count: int
    error: Optional[str] = None


# Bulk operations models
class BulkDeleteRequest(BaseModel):
    type: str
    targetIds: List[str]


class BulkDeleteResponse(BaseModel):
    success: bool
    deletedIds: List[str]
    failed: List[Dict[str, Any]]


# Initialize service
dossier_service = DossierManagementService()
view_service = DossierViewService()
title_lock_service = TitleLockService()


@router.post("/create", response_model=DossierResponse)
async def create_dossier(request: CreateDossierRequest):
    """
    Create a new dossier.

    Args:
        request: Dossier creation parameters

    Returns:
        DossierResponse with new dossier ID
    """
    logger.info(f"📝 API: Creating dossier '{request.title}'")
    logger.info(f"📝 API: Request data: title='{request.title}', description='{request.description}'")

    try:
        logger.info(f"🔧 API: Calling service.create_dossier with title='{request.title}', description='{request.description}'")
        created_dossier = dossier_service.create_dossier(
            title=request.title,
            description=request.description
        )

        logger.info(f"✅ API: Created dossier {created_dossier.id}")
        return DossierResponse(
            success=True,
            dossier_id=created_dossier.id,
            dossier=created_dossier.to_dict()
        )

    except Exception as e:
        logger.error(f"❌ API: Failed to create dossier: {e}")
        logger.error(f"❌ API: Error type: {type(e).__name__}")
        logger.error(f"❌ API: Request validation: title='{request.title}', description='{request.description}'")
        raise HTTPException(status_code=500, detail=f"Failed to create dossier: {str(e)}")


@router.post("/{dossier_id}/segments", response_model=DossierResponse)
async def create_segment(dossier_id: str, request: CreateSegmentRequest):
    """Create a new manual segment within a dossier."""
    try:
        seg = dossier_service.add_segment(dossier_id, request.name)
        if not seg:
            raise HTTPException(status_code=404, detail=f"Dossier not found: {dossier_id}")
        return DossierResponse(success=True, data=seg)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to create segment in dossier {dossier_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create segment: {str(e)}")


@router.put("/segments/{segment_id}", response_model=DossierResponse)
async def update_segment(segment_id: str, request: UpdateSegmentRequest):
    """Rename an existing segment by id."""
    try:
        ok = dossier_service.update_segment_by_id(segment_id, request.name)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
        return DossierResponse(success=True, data={"id": segment_id, "name": request.name})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to update segment {segment_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update segment: {str(e)}")


@router.delete("/segments/{segment_id}", response_model=DossierResponse)
async def delete_segment(segment_id: str):
    """Delete a segment by id."""
    try:
        ok = dossier_service.delete_segment_by_id(segment_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
        return DossierResponse(success=True, data={"id": segment_id})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to delete segment {segment_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete segment: {str(e)}")


@router.get("/{dossier_id}/details", response_model=DossierResponse)
async def get_dossier_details(dossier_id: str):
    """
    Get detailed information about a dossier.

    Args:
        dossier_id: The dossier identifier

    Returns:
        DossierResponse with dossier details
    """
    logger.debug(f"API: Getting dossier details for {dossier_id}")

    try:
        dossier = dossier_service.get_dossier(dossier_id)

        if not dossier:
            raise HTTPException(status_code=404, detail=f"Dossier not found: {dossier_id}")

        logger.debug(f"API: Retrieved dossier {dossier_id}")
        return DossierResponse(
            success=True,
            dossier=dossier.to_dict()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to get dossier {dossier_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get dossier: {str(e)}")


@router.get("/drafts/{draft_id}")
async def get_draft_raw_json(draft_id: str, dossier_id: str | None = Query(default=None)):
    """
    Return raw JSON for a single draft/transcription.

    This reads the transcription content via the view service, which resolves from dossiers_data.
    """
    try:
        logger.info(f"API:get_draft_raw_json draft_id={draft_id} dossier_id={dossier_id}")
        try:
            content = view_service._load_transcription_content_scoped(draft_id, dossier_id)
        except AttributeError:
            content = view_service._load_transcription_content(draft_id)  # Fallback if scoped missing
        if not content:
            raise HTTPException(status_code=404, detail=f"Draft not found: {draft_id}")
        # Log summary of content source
        try:
            doc_id = content.get('documentId') if isinstance(content, dict) else None
            sections = len(content.get('sections', [])) if isinstance(content, dict) else 0
            logger.info(f"API:get_draft_raw_json_ok draft_id={draft_id} dossier_id={dossier_id} documentId={doc_id} sections={sections}")
        except Exception:
            logger.info(f"API:get_draft_raw_json_ok draft_id={draft_id} dossier_id={dossier_id} (non-dict content)")
        return {"success": True, "draft_id": draft_id, "data": content}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to load draft {draft_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load draft: {str(e)}")


@router.put("/{dossier_id}/update", response_model=DossierResponse)
async def update_dossier(dossier_id: str, request: UpdateDossierRequest):
    """
    Update a dossier's metadata.

    Args:
        dossier_id: The dossier to update
        request: Update parameters

    Returns:
        DossierResponse with success status
    """
    logger.info(f"🔄 API: Updating dossier {dossier_id}")
    logger.info(f"🔄 API: Update request data: title='{request.title}', description='{request.description}'")
    logger.info(f"🔄 API: Request validation - title is None: {request.title is None}, description is None: {request.description is None}")

    try:
        # Build updates dictionary
        updates = {}
        if request.title is not None:
            updates['title'] = request.title
            logger.info(f"🔄 API: Adding title update: '{request.title}'")
        if request.description is not None:
            updates['description'] = request.description
            logger.info(f"🔄 API: Adding description update: '{request.description}'")

        if not updates:
            logger.warning(f"⚠️ API: No updates provided for dossier {dossier_id}")
            raise HTTPException(status_code=400, detail="No updates provided")

        logger.info(f"🔄 API: Calling service.update_dossier with updates: {updates}")
        updated_dossier = dossier_service.update_dossier(dossier_id, updates)

        if not updated_dossier:
            logger.warning(f"⚠️ API: Service returned None for dossier update {dossier_id}")
            raise HTTPException(status_code=404, detail=f"Dossier not found: {dossier_id}")

        logger.info(f"✅ API: Successfully updated dossier {dossier_id}")
        # Return the updated dossier data for frontend
        return DossierResponse(success=True, dossier=updated_dossier.to_dict())

    except HTTPException:
        logger.error(f"❌ API: HTTP exception during dossier update {dossier_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"❌ API: Unexpected error updating dossier {dossier_id}: {e}")
        logger.error(f"❌ API: Error type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ API: Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to update dossier: {str(e)}")


@router.delete("/{dossier_id}/delete", response_model=DossierResponse)
async def delete_dossier(dossier_id: str):
    """
    Delete a dossier.

    Note: This only deletes the dossier metadata.
    Associated transcriptions are preserved.

    Args:
        dossier_id: The dossier to delete

    Returns:
        DossierResponse with success status
    """
    logger.info(f"🗑️ API: Deleting dossier {dossier_id}")

    try:
        # Offload purge to threadpool to avoid blocking the event loop
        success = await run_in_threadpool(dossier_service.delete_dossier, dossier_id, True)

        if not success:
            raise HTTPException(status_code=404, detail=f"Dossier not found: {dossier_id}")

        logger.info(f"✅ API: Deleted dossier {dossier_id}")
        try:
            await event_bus.publish({
                "type": "dossier:deleted",
                "dossier_id": str(dossier_id)
            })
        except Exception:
            pass
        return DossierResponse(success=True)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to delete dossier {dossier_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete dossier: {str(e)}")


@router.post("/bulk", response_model=BulkDeleteResponse)
async def bulk_action(request: BulkDeleteRequest):
    """
    Perform a bulk action on dossiers. Currently supports type 'delete'.

    Body: { type: 'delete', targetIds: string[] }
    Returns list of deleted ids and failures with error messages.
    """
    if request.type != 'delete':
        raise HTTPException(status_code=405, detail=f"Unsupported bulk action: {request.type}")

    logger.info(f"🗑️ API: Bulk delete start count={len(request.targetIds)}")

    deleted_ids: List[str] = []
    failed: List[Dict[str, Any]] = []

    # Bound concurrent filesystem operations to avoid overwhelming disk/locks
    semaphore = asyncio.Semaphore(4)

    async def purge_one(dossier_id: str) -> None:
        try:
            async with semaphore:
                ok = await run_in_threadpool(dossier_service.delete_dossier, dossier_id, True)
            if ok:
                deleted_ids.append(dossier_id)
                try:
                    await event_bus.publish({
                        "type": "dossier:deleted",
                        "dossier_id": str(dossier_id)
                    })
                except Exception:
                    # Non-fatal publish error
                    pass
            else:
                failed.append({"id": dossier_id, "error": "not_found"})
        except Exception as e:
            failed.append({"id": dossier_id, "error": str(e)})

    await asyncio.gather(*(purge_one(did) for did in request.targetIds))

    logger.info(f"🗑️ API: Bulk delete done deleted={len(deleted_ids)} failed={len(failed)}")
    return BulkDeleteResponse(success=True, deletedIds=deleted_ids, failed=failed)


# -----------------------------
# Background job-based bulk API
# -----------------------------

class BulkStartRequest(BaseModel):
    targetIds: List[str]

class BulkStartResponse(BaseModel):
    success: bool
    job_id: str
    total: int
    acceptedIds: List[str]
    rejectedIds: List[str]

@router.post("/bulk/start", response_model=BulkStartResponse)
async def bulk_start(request: BulkStartRequest):
    ids = [str(i) for i in (request.targetIds or []) if isinstance(i, str)]
    if not ids:
        raise HTTPException(status_code=400, detail="No targetIds provided")
    job = await delete_job_manager.create_job(ids)
    await delete_job_manager.start_job(job.job_id)
    return BulkStartResponse(success=True, job_id=job.job_id, total=job.total, acceptedIds=ids, rejectedIds=[])


class BulkStatusResponse(BaseModel):
    success: bool
    job_id: str
    total: int
    done: int
    deletedIds: List[str]
    failedIds: List[str]
    inProgressIds: List[str]

@router.get("/bulk/status/{job_id}", response_model=BulkStatusResponse)
async def bulk_status(job_id: str):
    st = await delete_job_manager.status(job_id)
    if not st:
        raise HTTPException(status_code=404, detail="job not found")
    return BulkStatusResponse(success=True, **st)


@router.get("/list", response_model=DossierListResponse)
async def list_dossiers(limit: int = 50, offset: int = 0):
    """
    List all dossiers with summary information.

    Args:
        limit: Maximum number of dossiers to return (default: 50)
        offset: Pagination offset (default: 0)

    Returns:
        DossierListResponse with dossier summaries
    """
    # Removed noisy DOSS list logs

    try:
        dossiers = dossier_service.list_dossiers(limit=limit, offset=offset)

        dossier_dicts = [dossier.to_dict() for dossier in dossiers]
        logger.debug(f"API: Converted {len(dossier_dicts)} dossiers to dict format")

        # Removed noisy DOSS list logs
        return DossierListResponse(
            success=True,
            dossiers=dossier_dicts,
            total_count=len(dossiers)  # Note: This is approximate for now
        )

    except Exception as e:
        logger.error(f"❌ API: Failed to list dossiers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list dossiers: {str(e)}")


@router.get("/health")
async def dossier_management_health_check():
    """Simple health check for dossier management service"""
    return {"status": "healthy", "service": "dossier-management"}


class TitleLockResponse(BaseModel):
    success: bool
    data: Dict[str, Any] | None = None
    error: str | None = None


@router.post("/{dossier_id}/lock-title", response_model=TitleLockResponse)
async def lock_title_from_first_segment(dossier_id: str):
    try:
        out = title_lock_service.lock_title_from_first_segment(str(dossier_id))
        return TitleLockResponse(success=True, data=out)
    except Exception as e:
        return TitleLockResponse(success=False, error=str(e))


@router.post("/lock-title/all", response_model=TitleLockResponse)
async def lock_all_titles():
    try:
        out = title_lock_service.lock_all()
        return TitleLockResponse(success=True, data=out)
    except Exception as e:
        return TitleLockResponse(success=False, error=str(e))
