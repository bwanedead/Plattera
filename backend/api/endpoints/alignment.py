"""
Alignment API Endpoints
======================

Dedicated endpoints for BioPython-based alignment engine functionality.
Handles legal document draft alignment, confidence analysis, and visualization.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
import json
from collections import defaultdict

from backend.alignment.schemas import AlignmentRequest
from backend.alignment.biopython_engine import BioPythonAlignmentEngine
from backend.alignment.format_factory import FormatFactory

router = APIRouter()

# Initialize the components of our pipeline
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
        # Step 1: Parse the request and "pivot" the data from a draft-centric
        # structure to the block-centric structure the engine needs.
        # This is the "organize by block ID" logic, now living in the API layer.
        block_texts = defaultdict(dict)
        for draft_obj in request.drafts:
            draft_id = draft_obj.get('draft_id')
            # The user's sample data is a JSON string in the first block's text field.
            # We must handle this specific "legacy" format.
            try:
                legacy_json_text = draft_obj['blocks'][0]['text']
                document_data = json.loads(legacy_json_text)
                for section in document_data.get('sections', []):
                    block_id = f"section_{section.get('id')}"
                    header = section.get('header') or ""
                    body = section.get('body') or ""
                    block_texts[block_id][draft_id] = f"{header} {body}".strip()
            except (json.JSONDecodeError, IndexError, KeyError, TypeError):
                # If parsing fails, fall back to the standard format.
                for block in draft_obj.get('blocks', []):
                    block_id = block.get('id')
                    text = block.get('text', '')
                    if block_id and draft_id:
                        block_texts[block_id][draft_id] = text

        # Step 2: Run the alignment engine with the correctly structured data.
        engine_output = alignment_engine.align_drafts(block_texts=dict(block_texts))

        if not engine_output.get('success'):
            raise HTTPException(status_code=500, detail=engine_output.get('error', "Unknown alignment error"))

        # Step 3: Use the Format Factory to reconstruct the two different outputs.
        reconstructed_outputs = format_factory.reconstruct_outputs(
            alignment_results=engine_output['alignment_results'],
            format_maps=engine_output['format_maps']
        )

        # Step 4: Combine results for the final response.
        final_response = {
            "status": "completed",
            "reconstructed_outputs": reconstructed_outputs,
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