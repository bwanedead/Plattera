"""
Final Draft Selection API Endpoints
==================================

Dedicated endpoints for selecting final draft output from image-to-text processing.
Handles consensus drafts, individual drafts, and edited drafts as final output.
"""

from fastapi import APIRouter, HTTPException, Form
from pydantic import BaseModel
from typing import Dict, Any, Optional, Union
import logging

# Import the pipeline
from pipelines.image_to_text.pipeline import ImageToTextPipeline

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic Models
class FinalDraftRequest(BaseModel):
    """Request model for final draft selection"""
    redundancy_analysis: Dict[str, Any]
    selected_draft: Union[int, str] = 'consensus'
    edited_draft_content: Optional[str] = None
    edited_from_draft: Optional[Union[int, str]] = None
    alignment_result: Optional[Dict[str, Any]] = None


class FinalDraftResponse(BaseModel):
    """Response model for final draft selection"""
    success: bool
    final_text: str
    selection_method: str
    selected_draft: Union[int, str]
    metadata: Dict[str, Any]
    error: Optional[str] = None


@router.post("/select-final-draft", response_model=FinalDraftResponse)
async def select_final_draft(
    redundancy_analysis: Dict[str, Any] = Form(...),
    selected_draft: str = Form("consensus"),  # 'consensus', 'best', or draft number
    edited_draft_content: Optional[str] = Form(None),
    edited_from_draft: Optional[str] = Form(None),
    alignment_result: Optional[Dict[str, Any]] = Form(None)
):
    """
    Select the final draft output from image-to-text processing.
    
    Args:
        redundancy_analysis: Results from redundancy analysis
        selected_draft: Which draft to select ('consensus', 'best', or draft number)
        edited_draft_content: Optional edited content
        edited_from_draft: Which draft was edited (if applicable)
        alignment_result: Optional alignment results (for consensus)
        
    Returns:
        Final draft selection result with metadata
    """
    logger.info(f" FINAL DRAFT SELECTION API ► Draft: {selected_draft}")
    
    try:
        # Parse selected draft
        if selected_draft.isdigit():
            selected_draft_int = int(selected_draft)
        else:
            selected_draft_int = selected_draft
        
        # Parse edited from draft
        edited_from_draft_parsed = None
        if edited_from_draft:
            if edited_from_draft.isdigit():
                edited_from_draft_parsed = int(edited_from_draft)
            else:
                edited_from_draft_parsed = edited_from_draft
        
        # Use pipeline to select final draft
        pipeline = ImageToTextPipeline()
        
        final_result = await pipeline.select_final_draft(
            redundancy_analysis=redundancy_analysis,
            alignment_result=alignment_result,
            selected_draft=selected_draft_int,
            edited_draft_content=edited_draft_content,
            edited_from_draft=edited_from_draft_parsed
        )
        
        logger.info(f"✅ FINAL DRAFT SELECTION COMPLETE ► Method: {final_result['selection_method']}")
        
        return FinalDraftResponse(
            success=True,
            final_text=final_result["final_text"],
            selection_method=final_result["selection_method"],
            selected_draft=selected_draft,
            metadata=final_result["metadata"]
        )
        
    except Exception as e:
        logger.error(f"❌ Final draft selection failed: {e}")
        return FinalDraftResponse(
            success=False,
            final_text="",
            selection_method="error",
            selected_draft=selected_draft,
            metadata={},
            error=str(e)
        )


@router.get("/health")
async def final_draft_health_check():
    """Simple health check for final draft selection service"""
    return {"status": "healthy", "service": "final_draft_selector"} 