"""
Transcription Association API Endpoints
======================================

Endpoints for managing transcription-to-dossier relationships.
Handles adding, removing, and reordering transcriptions within dossiers.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import logging

from services.dossier.association_service import TranscriptionAssociationService

logger = logging.getLogger(__name__)
router = APIRouter()


# Pydantic Models
class AddTranscriptionRequest(BaseModel):
    """Request model for adding transcription to dossier"""
    transcription_id: str
    position: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class ReorderTranscriptionsRequest(BaseModel):
    """Request model for reordering transcriptions"""
    transcription_ids: List[str]


class UpdateMetadataRequest(BaseModel):
    """Request model for updating transcription metadata"""
    metadata: Dict[str, Any]


class AssociationResponse(BaseModel):
    """Response model for association operations"""
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None


class TranscriptionListResponse(BaseModel):
    """Response model for transcription listing"""
    success: bool
    dossier_id: str
    transcriptions: List[Dict[str, Any]]
    count: int
    error: Optional[str] = None


# Initialize service
association_service = TranscriptionAssociationService()


@router.post("/{dossier_id}/add", response_model=AssociationResponse)
async def add_transcription_to_dossier(dossier_id: str, request: AddTranscriptionRequest):
    """
    Add a transcription to a dossier.

    Args:
        dossier_id: The dossier to add to
        request: Transcription details

    Returns:
        AssociationResponse with success status
    """
    logger.info(f"➕ API: Adding transcription {request.transcription_id} to dossier {dossier_id}")

    try:
        success = association_service.add_transcription(
            dossier_id=dossier_id,
            transcription_id=request.transcription_id,
            position=request.position,
            metadata=request.metadata
        )

        if not success:
            raise HTTPException(
                status_code=409,
                detail=f"Transcription {request.transcription_id} already exists in dossier {dossier_id}"
            )

        logger.info(f"✅ API: Added transcription {request.transcription_id} to dossier {dossier_id}")
        return AssociationResponse(
            success=True,
            message=f"Added transcription {request.transcription_id} to dossier {dossier_id}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to add transcription to dossier: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add transcription: {str(e)}")


@router.delete("/{dossier_id}/remove/{transcription_id}", response_model=AssociationResponse)
async def remove_transcription_from_dossier(dossier_id: str, transcription_id: str):
    """
    Remove a transcription from a dossier.

    Args:
        dossier_id: The dossier to remove from
        transcription_id: The transcription to remove

    Returns:
        AssociationResponse with success status
    """
    logger.info(f"➖ API: Removing transcription {transcription_id} from dossier {dossier_id}")

    try:
        success = association_service.remove_transcription(dossier_id, transcription_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Transcription {transcription_id} not found in dossier {dossier_id}"
            )

        logger.info(f"✅ API: Removed transcription {transcription_id} from dossier {dossier_id}")
        return AssociationResponse(
            success=True,
            message=f"Removed transcription {transcription_id} from dossier {dossier_id}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to remove transcription from dossier: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to remove transcription: {str(e)}")


@router.put("/{dossier_id}/reorder", response_model=AssociationResponse)
async def reorder_transcriptions_in_dossier(dossier_id: str, request: ReorderTranscriptionsRequest):
    """
    Reorder transcriptions within a dossier.

    Args:
        dossier_id: The dossier to reorder
        request: New order of transcription IDs

    Returns:
        AssociationResponse with success status
    """
    logger.info(f"🔄 API: Reordering transcriptions in dossier {dossier_id}")

    try:
        success = association_service.reorder_transcriptions(
            dossier_id=dossier_id,
            transcription_ids=request.transcription_ids
        )

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Reorder validation failed. Check transcription IDs."
            )

        logger.info(f"✅ API: Reordered transcriptions in dossier {dossier_id}")
        return AssociationResponse(
            success=True,
            message=f"Reordered {len(request.transcription_ids)} transcriptions in dossier {dossier_id}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to reorder transcriptions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reorder transcriptions: {str(e)}")


@router.get("/{dossier_id}/transcriptions", response_model=TranscriptionListResponse)
async def get_dossier_transcriptions(dossier_id: str):
    """
    Get all transcriptions in a dossier, ordered by position.

    Args:
        dossier_id: The dossier to query

    Returns:
        TranscriptionListResponse with ordered transcriptions
    """
    logger.info(f"📄 API: Getting transcriptions for dossier {dossier_id}")

    try:
        transcriptions = association_service.get_dossier_transcriptions(dossier_id)

        transcription_dicts = [t.to_dict() for t in transcriptions]

        logger.info(f"✅ API: Retrieved {len(transcriptions)} transcriptions for dossier {dossier_id}")
        return TranscriptionListResponse(
            success=True,
            dossier_id=dossier_id,
            transcriptions=transcription_dicts,
            count=len(transcriptions)
        )

    except Exception as e:
        logger.error(f"❌ API: Failed to get transcriptions for dossier {dossier_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transcriptions: {str(e)}")


@router.get("/{dossier_id}/count")
async def get_transcription_count(dossier_id: str):
    """
    Get the number of transcriptions in a dossier.

    Args:
        dossier_id: The dossier

    Returns:
        Dictionary with count
    """
    logger.info(f"🔢 API: Getting transcription count for dossier {dossier_id}")

    try:
        count = association_service.get_transcription_count(dossier_id)

        logger.info(f"✅ API: Dossier {dossier_id} has {count} transcriptions")
        return {
            "success": True,
            "dossier_id": dossier_id,
            "transcription_count": count
        }

    except Exception as e:
        logger.error(f"❌ API: Failed to get transcription count: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get count: {str(e)}")


@router.put("/{dossier_id}/transcription/{transcription_id}/metadata", response_model=AssociationResponse)
async def update_transcription_metadata(dossier_id: str, transcription_id: str, request: UpdateMetadataRequest):
    """
    Update metadata for a transcription in a dossier.

    Args:
        dossier_id: The dossier
        transcription_id: The transcription
        request: New metadata

    Returns:
        AssociationResponse with success status
    """
    logger.info(f"🔄 API: Updating metadata for {transcription_id} in dossier {dossier_id}")

    try:
        success = association_service.update_transcription_metadata(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            metadata=request.metadata
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Transcription {transcription_id} not found in dossier {dossier_id}"
            )

        logger.info(f"✅ API: Updated metadata for {transcription_id} in dossier {dossier_id}")
        return AssociationResponse(
            success=True,
            message=f"Updated metadata for transcription {transcription_id}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to update metadata: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update metadata: {str(e)}")


@router.get("/health")
async def transcription_association_health_check():
    """Simple health check for transcription association service"""
    return {"status": "healthy", "service": "transcription-association"}
