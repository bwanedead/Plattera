"""
Alignment API Endpoints
======================

Dedicated endpoints for BioPython-based alignment engine functionality.
Handles legal document draft alignment, confidence analysis, and visualization.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any

from backend.schema.alignment import AlignmentRequest, AlignmentResponse
from backend.alignment.biopython_engine import BioPythonAlignmentEngine
from backend.alignment.format_factory import FormatFactory
from backend.services.registry import get_service

router = APIRouter()

# Initialize the engine and reconstructor once
alignment_engine = BioPythonAlignmentEngine()
format_factory = FormatFactory()

@router.post("/align-drafts", response_model=Dict[str, Any])
async def align_drafts_endpoint(request: AlignmentRequest):
    """
    Receives document drafts, performs alignment, and returns the results.
    """
    if not request.drafts:
        raise HTTPException(status_code=400, detail="No drafts provided for alignment.")

    try:
        # Step 1: Get raw alignment results from the core engine
        engine_output = alignment_engine.align_drafts(draft_jsons=request.drafts)

        if not engine_output.get('success'):
            raise HTTPException(status_code=500, detail=engine_output.get('error', "Unknown alignment error"))

        # Step 2: Reconstruct the formatted text for the frontend
        formatted_alignment = format_factory.reconstruct_formatted_alignment(
            alignment_results=engine_output['alignment_results'],
            tokenized_data=engine_output['tokenized_data']
        )

        # Combine results for the final response
        final_response = {
            "status": "completed",
            "alignment": formatted_alignment,
            "confidence_scores": engine_output.get('confidence_results'),
            "processing_time": engine_output.get('processing_time')
        }

        return final_response

    except Exception as e:
        # Log the full exception for debugging
        # Consider using a more structured logger in a real application
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}") 