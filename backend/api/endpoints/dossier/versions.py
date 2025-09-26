from fastapi import APIRouter, Form, HTTPException
from typing import Optional
from services.dossier.edit_persistence_service import EditPersistenceService


router = APIRouter()


@router.post("/set-raw-head")
async def set_raw_head(
	dossier_id: str = Form(...),
	transcription_id: str = Form(...),
	head: str = Form(...),
):
	svc = EditPersistenceService()
	if head not in ("v1", "v2"):
		raise HTTPException(status_code=400, detail="head must be v1 or v2")
	if not svc.set_raw_head(dossier_id, transcription_id, head):
		raise HTTPException(status_code=404, detail="Requested version not found")
	return {"success": True, "raw_head": head}


@router.post("/revert-to-v1")
async def revert_to_v1(
	dossier_id: str = Form(...),
	transcription_id: str = Form(...),
	purge: Optional[bool] = Form(False)
):
	svc = EditPersistenceService()
	ok = svc.revert_to_v1(dossier_id, transcription_id, purge=bool(purge))
	if not ok:
		raise HTTPException(status_code=404, detail="v1 not found")
	return {"success": True}


