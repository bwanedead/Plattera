"""
Alignment API Endpoints
======================

Dedicated endpoints for BioPython-based alignment engine functionality.
Handles legal document draft alignment, confidence analysis, and visualization.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic Models
class JsonDraftBlock(BaseModel):
    """Model for a single block within a JSON draft"""
    id: str
    text: str


class JsonDraft(BaseModel):
    """Model for a single JSON draft"""
    draft_id: str
    blocks: List[JsonDraftBlock]


class AlignmentRequest(BaseModel):
    """Request model for BioPython alignment processing"""
    drafts: List[JsonDraft]
    generate_visualization: bool = True
    consensus_strategy: str = "highest_confidence"


class AlignmentResponse(BaseModel):
    """Response model for BioPython alignment results"""
    success: bool
    processing_time: float
    summary: Dict[str, Any]
    consensus_text: Optional[str] = None
    visualization_html: Optional[str] = None
    error: Optional[str] = None


# Endpoints
@router.post("/align-drafts", response_model=AlignmentResponse)
async def align_legal_drafts(request: AlignmentRequest):
    """
    BioPython-based alignment of multiple legal document drafts
    
    Performs consistency-based multiple sequence alignment to identify differences
    and generate confidence scores for legal document transcriptions.
    """
    logger.info(f"🧬 BIOPYTHON ALIGNMENT REQUEST ► Processing {len(request.drafts)} drafts")
    
    try:
        # Import BioPython engine
        from alignment import BioPythonAlignmentEngine, check_dependencies
        
        # Check dependencies
        dependencies_available, missing_packages = check_dependencies()
        if not dependencies_available:
            logger.error(f"❌ Missing BioPython dependencies: {missing_packages}")
            return AlignmentResponse(
                success=False,
                processing_time=0.0,
                summary={},
                error=f"Missing required dependencies: {', '.join(missing_packages)}. Install with: pip install {' '.join(missing_packages)}"
            )
        
        # Convert Pydantic models to dictionaries
        draft_jsons = []
        for draft in request.drafts:
            draft_dict = {
                "draft_id": draft.draft_id,
                "blocks": [
                    {"id": block.id, "text": block.text}
                    for block in draft.blocks
                ]
            }
            draft_jsons.append(draft_dict)
        
        # Initialize BioPython engine
        engine = BioPythonAlignmentEngine()
        
        # Perform alignment
        results = engine.align_drafts(
            draft_jsons, 
            generate_visualization=request.generate_visualization
        )
        
        if not results['success']:
            logger.error(f"❌ BioPython alignment failed: {results.get('error', 'Unknown error')}")
            return AlignmentResponse(
                success=False,
                processing_time=results.get('processing_time', 0.0),
                summary={},
                error=results.get('error', 'Alignment failed')
            )
        
        # Generate consensus text if requested
        consensus_text = None
        if request.consensus_strategy:
            try:
                consensus_text = engine.generate_consensus_text(
                    results['alignment_results'],
                    results['confidence_results'],
                    consensus_strategy=request.consensus_strategy
                )
            except Exception as e:
                logger.warning(f"⚠️ Consensus generation failed: {e}")
        
        logger.info(f"✅ BioPython alignment completed successfully in {results['processing_time']:.2f}s")
        
        return AlignmentResponse(
            success=True,
            processing_time=results['processing_time'],
            summary=results['summary'],
            consensus_text=consensus_text,
            visualization_html=results['visualization_html']
        )
        
    except ImportError as e:
        logger.error(f"❌ BioPython alignment module not available: {e}")
        return AlignmentResponse(
            success=False,
            processing_time=0.0,
            summary={},
            error=f"BioPython alignment engine not available: {e}"
        )
    except Exception as e:
        logger.error(f"❌ Unexpected error in BioPython alignment: {e}")
        logger.exception("Full traceback:")
        return AlignmentResponse(
            success=False,
            processing_time=0.0,
            summary={},
            error=f"Alignment processing failed: {str(e)}"
        )


@router.get("/align-drafts/status")
async def get_alignment_engine_status():
    """
    Get status and availability of the BioPython alignment engine
    
    Returns:
        Dict with engine status, dependencies, and capabilities
    """
    try:
        from alignment import check_biopython_engine_status
        
        status = check_biopython_engine_status()
        return status
        
    except ImportError:
        return {
            'status': 'unavailable',
            'error': 'BioPython alignment engine not installed'
        }
    except Exception as e:
        logger.error(f"❌ Error checking alignment engine status: {e}")
        return {
            'status': 'error',
            'error': str(e)
        }


@router.post("/align-drafts/test")
async def test_alignment_engine():
    """
    Test the BioPython alignment engine with sample data
    
    Returns:
        Dict with test results and sample alignment data
    """
    try:
        from alignment import test_biopython_engine
        
        logger.info("🧪 Testing BioPython alignment engine...")
        results = test_biopython_engine()
        
        if results['success']:
            logger.info("✅ BioPython alignment engine test passed")
        else:
            logger.error(f"❌ BioPython alignment engine test failed: {results.get('error', 'Unknown')}")
        
        return results
        
    except ImportError as e:
        logger.error(f"❌ BioPython alignment engine not available for testing: {e}")
        return {
            'success': False,
            'error': f'BioPython alignment engine not available: {e}'
        }
    except Exception as e:
        logger.error(f"❌ Error testing alignment engine: {e}")
        logger.exception("Full traceback:")
        return {
            'success': False,
            'error': f'Test failed: {str(e)}'
        } 