"""
Dossier Management API Endpoints
===============================

Endpoints for core CRUD operations on dossiers themselves.
Handles dossier lifecycle: create, read, update, delete.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import logging

from services.dossier.management_service import DossierManagementService

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


# Initialize service
dossier_service = DossierManagementService()


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
        dossier_id = dossier_service.create_dossier(
            title=request.title,
            description=request.description
        )

        logger.info(f"✅ API: Created dossier {dossier_id}")
        return DossierResponse(
            success=True,
            dossier_id=dossier_id
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


@router.get("/{dossier_id}/details", response_model=DossierResponse)
async def get_dossier_details(dossier_id: str):
    """
    Get detailed information about a dossier.

    Args:
        dossier_id: The dossier identifier

    Returns:
        DossierResponse with dossier details
    """
    logger.info(f"📖 API: Getting dossier details for {dossier_id}")

    try:
        dossier = dossier_service.get_dossier(dossier_id)

        if not dossier:
            raise HTTPException(status_code=404, detail=f"Dossier not found: {dossier_id}")

        logger.info(f"✅ API: Retrieved dossier {dossier_id}")
        return DossierResponse(
            success=True,
            dossier=dossier.to_dict()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to get dossier {dossier_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get dossier: {str(e)}")


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
        success = dossier_service.delete_dossier(dossier_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Dossier not found: {dossier_id}")

        logger.info(f"✅ API: Deleted dossier {dossier_id}")
        return DossierResponse(success=True)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to delete dossier {dossier_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete dossier: {str(e)}")


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
    logger.info(f"📋 API: Listing dossiers (limit={limit}, offset={offset})")

    try:
        dossiers = dossier_service.list_dossiers(limit=limit, offset=offset)
        logger.info(f"🔍 Service returned {len(dossiers)} dossiers")

        dossier_dicts = [dossier.to_dict() for dossier in dossiers]
        logger.info(f"📝 Converted {len(dossier_dicts)} dossiers to dict format")

        logger.info(f"✅ API: Listed {len(dossiers)} dossiers")
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
