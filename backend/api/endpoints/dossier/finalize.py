"""
Dossier Finalization API Endpoints
==================================

Endpoint for finalizing a dossier by stitching all segment final selections
into a single snapshot document.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import logging
import json
from pathlib import Path
from datetime import datetime

from services.dossier.management_service import DossierManagementService
from services.dossier.view_service import DossierViewService
from services.dossier.edit_persistence_service import EditPersistenceService
from services.dossier.final_registry_service import FinalRegistryService

logger = logging.getLogger(__name__)
router = APIRouter()


class FinalizeRequest(BaseModel):
    """Request model for dossier finalization"""
    dossier_id: str


class SegmentFinalInfo(BaseModel):
    """Info about a finalized segment"""
    segment_id: str
    transcription_id: str
    draft_id_used: str
    text_length: int


class FinalizeError(BaseModel):
    """Error info for failed segment"""
    segment_id: str
    transcription_id: str
    draft_id: str
    reason: str


class FinalizeResponse(BaseModel):
    """Response model for dossier finalization"""
    success: bool
    dossier_id: str
    text_length: int
    segments: List[SegmentFinalInfo]
    errors: List[FinalizeError]
    path: Optional[str] = None
    error: Optional[str] = None


@router.post("/finalize", response_model=FinalizeResponse)
async def finalize_dossier(request: FinalizeRequest):
    """
    Finalize a dossier by stitching all segment final selections.

    For each segment:
    - If final.selected_id is set, load that exact version strictly (with retry, no fallback).
    - If not set, use fallback policy (consensus → best → longest).
    - Record errors for any 404s.

    Writes the result to .../final/dossier_final.json.

    Args:
        request: Contains dossier_id

    Returns:
        FinalizeResponse with stitched text info and any errors
    """
    dossier_id = request.dossier_id
    logger.info(f"🎯 Finalizing dossier: {dossier_id}")

    try:
        # Load dossier structure
        mgmt_svc = DossierManagementService()
        dossier = mgmt_svc.get_dossier(dossier_id)
        if not dossier:
            raise HTTPException(status_code=404, detail=f"Dossier not found: {dossier_id}")

        view_svc = DossierViewService()
        persist_svc = EditPersistenceService()
        fr_svc = FinalRegistryService()

        # Build stitched content
        stitched_parts: list[str] = []
        segments_info: list[dict[str, Any]] = []
        errors_list: list[dict[str, Any]] = []

        for segment in dossier.segments:
            # Pick latest run for this segment
            runs = segment.runs or []
            if not runs:
                logger.warning(f"⚠️ Segment {segment.id} has no runs, skipping")
                continue

            # Sort by position desc to get latest
            run = sorted(runs, key=lambda r: r.position, reverse=True)[0]
            transcription_id = run.transcription_id

            # Prefer registry final for this segment
            final_entry = fr_svc.get_segment_final(dossier_id, str(segment.id))
            final_id = (final_entry or {}).get('draft_id')

            if final_id and isinstance(final_id, str) and final_id.strip():
                # Strict load with retry
                text = await _load_with_retry(view_svc, transcription_id, final_id, dossier_id, retries=2)
                if text is None:
                    # Record error, skip this segment
                    errors_list.append({
                        "segment_id": segment.id,
                        "transcription_id": transcription_id,
                        "draft_id": final_id,
                        "reason": "Draft not found (404 after retries)"
                    })
                    logger.warning(f"⚠️ Final selection {final_id} not found for segment {segment.id}, skipping")
                    continue

                stitched_parts.append(text)
                segments_info.append({
                    "segment_id": segment.id,
                    "transcription_id": transcription_id,
                    "draft_id_used": final_id,
                    "text_length": len(text)
                })
                logger.info(f"✅ Segment {segment.id} finalized with final selection: {final_id}")
            else:
                # Fallback to policy (consensus → best → longest)
                draft_id, text = await _load_with_policy(view_svc, run, dossier_id)
                if text:
                    stitched_parts.append(text)
                    segments_info.append({
                        "segment_id": segment.id,
                        "transcription_id": transcription_id,
                        "draft_id_used": draft_id,
                        "text_length": len(text)
                    })
                    logger.info(f"✅ Segment {segment.id} finalized with policy fallback: {draft_id}")
                else:
                    errors_list.append({
                        "segment_id": segment.id,
                        "transcription_id": transcription_id,
                        "draft_id": "none",
                        "reason": "No drafts available"
                    })
                    logger.warning(f"⚠️ No drafts available for segment {segment.id}")

        # Stitch and persist
        stitched_text = "\n\n".join(stitched_parts)

        # Write to final directory
        backend_dir = Path(__file__).resolve().parents[3]
        final_dir = backend_dir / "dossiers_data" / "views" / "transcriptions" / str(dossier_id) / "final"
        final_dir.mkdir(parents=True, exist_ok=True)
        final_path = final_dir / "dossier_final.json"

        final_payload = {
            "dossier_id": dossier_id,
            "text": stitched_text,
            "segments": segments_info,
            "errors": errors_list,
            "generated_at": datetime.utcnow().isoformat(),
            "total_segments": len(dossier.segments),
            "finalized_segments": len(segments_info),
            "failed_segments": len(errors_list)
        }

        with open(final_path, 'w', encoding='utf-8') as f:
            json.dump(final_payload, f, indent=2, ensure_ascii=False)

        logger.info(f"✅ Dossier finalized: {dossier_id} ({len(segments_info)}/{len(dossier.segments)} segments, {len(errors_list)} errors)")

        return FinalizeResponse(
            success=True,
            dossier_id=dossier_id,
            text_length=len(stitched_text),
            segments=segments_info,
            errors=errors_list,
            path=str(final_path)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to finalize dossier {dossier_id}: {e}")
        return FinalizeResponse(
            success=False,
            dossier_id=dossier_id,
            text_length=0,
            segments=[],
            errors=[],
            error=str(e)
        )


@router.get("/final/{dossier_id}")
async def get_finalized_dossier(dossier_id: str):
	"""
	Get the finalized dossier snapshot.
	
	Args:
		dossier_id: The dossier ID
	
	Returns:
		The finalized snapshot or 404
	"""
	try:
		backend_dir = Path(__file__).resolve().parents[3]
		final_path = backend_dir / "dossiers_data" / "views" / "transcriptions" / str(dossier_id) / "final" / "dossier_final.json"
		
		if not final_path.exists():
			raise HTTPException(status_code=404, detail="Finalized dossier not found. Run finalize first.")
		
		with open(final_path, 'r', encoding='utf-8') as f:
			data = json.load(f)
		
		return {"success": True, "data": data}
	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"❌ Failed to get finalized dossier {dossier_id}: {e}")
		raise HTTPException(status_code=500, detail=str(e))


async def _load_with_retry(view_svc: DossierViewService, transcription_id: str, draft_id: str, dossier_id: str, retries: int = 2) -> Optional[str]:
	"""Load draft with retry, return None on failure."""
	import asyncio
	for attempt in range(retries + 1):
		try:
			content = view_svc._load_transcription_content_scoped(draft_id, dossier_id)
			if content:
				# Extract text from sections
				if isinstance(content, dict) and 'sections' in content:
					sections = content.get('sections', [])
					text = "\n\n".join(s.get('body', '') for s in sections if isinstance(s, dict))
					return text.strip()
				elif isinstance(content, dict) and 'text' in content:
					return str(content.get('text', '')).strip()
			return None
		except Exception as e:
			if attempt < retries:
				await asyncio.sleep(0.2 * (attempt + 1))  # 200ms, 400ms backoff
				logger.debug(f"Retry {attempt + 1} for {draft_id}")
			else:
				logger.warning(f"Failed to load {draft_id} after {retries + 1} attempts: {e}")
				return None
	return None


async def _load_with_policy(view_svc: DossierViewService, run: Any, dossier_id: str) -> tuple[str, str]:
	"""Load draft using fallback policy: consensus → best → longest. Returns (draft_id, text)."""
	drafts = run.drafts or []
	if not drafts:
		return ("none", "")
	
	# Try consensus first
	consensus_drafts = [d for d in drafts if isinstance(d.id, str) and ('_consensus_llm' in d.id or '_consensus_alignment' in d.id)]
	if consensus_drafts:
		# Pick latest by createdAt
		try:
			pick = max(consensus_drafts, key=lambda d: (d.metadata or {}).get('createdAt', ''))
		except:
			pick = consensus_drafts[0]
		
		content = view_svc._load_transcription_content_scoped(pick.id, dossier_id)
		if content:
			text = _extract_text(content)
			if text:
				return (pick.id, text)
	
	# Try best flag
	best = next((d for d in drafts if d.is_best), None)
	if best:
		content = view_svc._load_transcription_content_scoped(best.id, dossier_id)
		if content:
			text = _extract_text(content)
			if text:
				return (best.id, text)
	
	# Try longest by size
	try:
		longest = max(drafts, key=lambda d: (d.metadata or {}).get('sizeBytes', 0))
		content = view_svc._load_transcription_content_scoped(longest.id, dossier_id)
		if content:
			text = _extract_text(content)
			if text:
				return (longest.id, text)
	except:
		pass
	
	# Fallback to first
	if drafts:
		content = view_svc._load_transcription_content_scoped(drafts[0].id, dossier_id)
		if content:
			text = _extract_text(content)
			return (drafts[0].id, text)
	
	return ("none", "")


def _extract_text(content: Dict[str, Any]) -> str:
	"""Extract text from draft content."""
	if isinstance(content, dict):
		if 'sections' in content:
			sections = content.get('sections', [])
			text = "\n\n".join(s.get('body', '') for s in sections if isinstance(s, dict))
			return text.strip()
		elif 'text' in content:
			return str(content.get('text', '')).strip()
	return ""

