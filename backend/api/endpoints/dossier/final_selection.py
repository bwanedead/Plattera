"""
Final Selection API Endpoints
==============================

Endpoints for setting and retrieving per-segment final draft selections.
"""

from fastapi import APIRouter, HTTPException, Form, Query
from typing import Optional
import logging
from services.dossier.edit_persistence_service import EditPersistenceService
from services.dossier.segment_resolution import resolve_segment_id
from services.dossier.final_registry_service import FinalRegistryService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/set")
async def set_final_selection(
    dossier_id: str = Form(...),
    transcription_id: str = Form(...),
    draft_id: str = Form(...)
):
    """
    Set the final selection for a segment/transcription to a specific versioned draft.

    Args:
        dossier_id: The dossier ID
        transcription_id: The transcription ID
        draft_id: The exact versioned draft ID (e.g., {tid}_v2_v2, {tid}_draft_1_v1)

    Returns:
        Success response with the selected draft_id
    """
    try:
        logger.info(f"🎯 Setting final selection: dossier={dossier_id} transcription={transcription_id} draft={draft_id}")
        # Delegate to Final Registry via segment resolution
        seg_id = resolve_segment_id(dossier_id, transcription_id)
        if not seg_id:
            raise HTTPException(status_code=404, detail="Segment not found for transcription")
        fr = FinalRegistryService()
        fr.set_segment_final(dossier_id, seg_id, transcription_id, draft_id)
        logger.info(f"✅ Final selection set (registry): segment={seg_id}, draft={draft_id}")
        return {"success": True, "segment_id": seg_id, "draft_id": draft_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to set final selection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear")
async def clear_final_selection(
    dossier_id: str = Form(...),
    transcription_id: str = Form(...)
):
    """
    Clear the final selection for a segment/transcription.

    Args:
        dossier_id: The dossier ID
        transcription_id: The transcription ID

    Returns:
        Success response
    """
    try:
        logger.info(f"🎯 Clearing final selection: dossier={dossier_id} transcription={transcription_id}")
        seg_id = resolve_segment_id(dossier_id, transcription_id)
        if not seg_id:
            raise HTTPException(status_code=404, detail="Segment not found for transcription")
        fr = FinalRegistryService()
        fr.clear_segment_final(dossier_id, seg_id)
        logger.info(f"✅ Final selection cleared (registry): segment={seg_id}")
        return {"success": True, "segment_id": seg_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to clear final selection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get")
async def get_final_selection(
    dossier_id: str = Query(...),
    transcription_id: str = Query(...)
):
    """
    Get the final selection for a segment/transcription.

    Args:
        dossier_id: The dossier ID
        transcription_id: The transcription ID

    Returns:
        The selected draft_id or null
    """
    try:
        seg_id = resolve_segment_id(dossier_id, transcription_id)
        if not seg_id:
            return {"success": True, "draft_id": None}
        fr = FinalRegistryService()
        val = fr.get_segment_final(dossier_id, seg_id)
        return {"success": True, "draft_id": (val or {}).get("draft_id")}
    except Exception as e:
        logger.error(f"❌ Failed to get final selection: {e}")
        raise HTTPException(status_code=500, detail=str(e))

