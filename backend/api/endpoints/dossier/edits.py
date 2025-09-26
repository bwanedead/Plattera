from fastapi import APIRouter, Form, HTTPException
from typing import Optional
import json
from services.dossier.edit_persistence_service import EditPersistenceService


router = APIRouter()


@router.post("/save")
async def save_raw_edit(
	dossier_id: str = Form(...),
	transcription_id: str = Form(...),
	edited_text: Optional[str] = Form(None),
	edited_sections: Optional[str] = Form(None)
):
	try:
		svc = EditPersistenceService()
		sections = None
		if edited_sections:
			try:
				sections = json.loads(edited_sections)
			except Exception:
				sections = None

		ok, head = svc.save_raw_v2(dossier_id, transcription_id, edited_text=edited_text, edited_sections=sections)
		if not ok:
			raise HTTPException(status_code=500, detail="Failed to save v2")
		return {"success": True, "raw_head": head}
	except HTTPException:
		raise
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))


@router.get("/head")
async def get_head(dossier_id: str, transcription_id: str):
	svc = EditPersistenceService()
	return {"success": True, "head": svc.get_head(dossier_id, transcription_id)}


