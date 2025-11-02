"""
Finals Endpoints (Segment-Scoped)
=================================

Clean RESTful endpoints to get/set/clear per-segment final selections.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from services.dossier.final_registry_service import FinalRegistryService


class PutSegmentFinalBody(BaseModel):
    transcription_id: str
    draft_id: str
    set_by: Optional[str] = None


router = APIRouter()


@router.get("/dossier/{dossier_id}/finals")
async def list_finals(dossier_id: str) -> Dict[str, Any]:
    svc = FinalRegistryService()
    data = svc.list_finals(dossier_id)
    return {"success": True, "segments": data}


@router.get("/dossier/{dossier_id}/segments/{segment_id}/final")
async def get_segment_final(dossier_id: str, segment_id: str) -> Dict[str, Any]:
    svc = FinalRegistryService()
    val = svc.get_segment_final(dossier_id, segment_id)
    if not val:
        # Treat as unset; do not 404 to keep FE simple when polling
        return {"success": True, "final": None}
    return {"success": True, "final": val}


@router.put("/dossier/{dossier_id}/segments/{segment_id}/final")
async def put_segment_final(dossier_id: str, segment_id: str, body: PutSegmentFinalBody) -> Dict[str, Any]:
    try:
        svc = FinalRegistryService()
        val = svc.set_segment_final(dossier_id, segment_id, body.transcription_id, body.draft_id, body.set_by)
        return {"success": True, "final": val}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/dossier/{dossier_id}/segments/{segment_id}/final")
async def delete_segment_final(dossier_id: str, segment_id: str) -> Dict[str, Any]:
    try:
        svc = FinalRegistryService()
        removed = svc.clear_segment_final(dossier_id, segment_id)
        return {"success": True, "removed": removed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


